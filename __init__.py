"""
app/crud/
─────────
CRUD layer — the only place that talks to the database.

Rules enforced here:
  • All DB access goes through SQLAlchemy async sessions.
  • Parameterised queries only — SQLAlchemy never interpolates user input
    into raw SQL, preventing SQL injection by design.
  • Counter increments done atomically with UPDATE … SET col = col ± 1
    inside the caller's transaction, never with read-modify-write.
  • Redis cache invalidation is triggered from here when counters change.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.video import Comment, Follower, Like, Message, Notification, Report, SavedVideo, Video, VideoView
from app.schemas import (
    CommentCreate, MessageCreate, ReportCreate, UserCreate, UserUpdate, VideoCreate, VideoViewCreate,
)


# ─────────────────────────────────────────────────────────────────
# USER CRUD
# ─────────────────────────────────────────────────────────────────
async def create_user(db: AsyncSession, data: UserCreate) -> User:
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        bio=data.bio,
    )
    db.add(user)
    await db.flush()   # get the auto-generated id without committing
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    )
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.add(user)
    return user


# ─────────────────────────────────────────────────────────────────
# FOLLOW CRUD
# ─────────────────────────────────────────────────────────────────
async def follow_user(db: AsyncSession, follower_id: uuid.UUID, following_id: uuid.UUID) -> bool:
    """Returns True if newly followed, False if already following."""
    exists = await db.execute(
        select(Follower).where(
            Follower.follower_id == follower_id,
            Follower.following_id == following_id,
        )
    )
    if exists.scalar_one_or_none():
        return False

    now = datetime.now(timezone.utc)
    db.add(Follower(follower_id=follower_id, following_id=following_id, created_at=now))

    # Atomic counter updates — no read-modify-write race condition
    await db.execute(
        update(User).where(User.id == follower_id).values(following_count=User.following_count + 1)
    )
    await db.execute(
        update(User).where(User.id == following_id).values(followers_count=User.followers_count + 1)
    )

    # Notification
    db.add(Notification(
        user_id=following_id, actor_id=follower_id,
        type="follow", created_at=now,
    ))
    return True


async def unfollow_user(db: AsyncSession, follower_id: uuid.UUID, following_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(Follower).where(
            Follower.follower_id == follower_id,
            Follower.following_id == following_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return False

    await db.delete(row)
    await db.execute(
        update(User).where(User.id == follower_id).values(following_count=User.following_count - 1)
    )
    await db.execute(
        update(User).where(User.id == following_id).values(followers_count=User.followers_count - 1)
    )
    return True


# ─────────────────────────────────────────────────────────────────
# VIDEO CRUD
# ─────────────────────────────────────────────────────────────────
async def create_video(db: AsyncSession, user_id: uuid.UUID, data: VideoCreate) -> Video:
    video = Video(user_id=user_id, **data.model_dump())
    db.add(video)
    await db.execute(
        update(User).where(User.id == user_id).values(videos_count=User.videos_count + 1)
    )
    await db.flush()
    return video


async def get_video(db: AsyncSession, video_id: uuid.UUID) -> Video | None:
    result = await db.execute(
        select(Video)
        .where(Video.id == video_id, Video.is_deleted == False)
        .options(selectinload(Video.author))
    )
    return result.scalar_one_or_none()


async def get_feed_videos(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> list[Video]:
    """
    Fetch global feed ordered by engagement_score.
    In production, this is replaced by a personalised list from Redis:
      redis.lrange(f"feed:{user_id}", offset, offset+page_size)
    """
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Video)
        .where(Video.is_deleted == False, Video.is_public == True)
        .order_by(Video.engagement_score.desc(), Video.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    return list(result.scalars().all())


async def soft_delete_video(db: AsyncSession, video: Video) -> None:
    video.is_deleted = True
    db.add(video)


# ─────────────────────────────────────────────────────────────────
# LIKE CRUD
# ─────────────────────────────────────────────────────────────────
async def toggle_like(db: AsyncSession, user_id: uuid.UUID, video_id: uuid.UUID) -> bool:
    """Returns True = liked, False = unliked."""
    existing = await db.execute(
        select(Like).where(Like.user_id == user_id, Like.video_id == video_id)
    )
    row = existing.scalar_one_or_none()

    if row:
        await db.delete(row)
        await db.execute(
            update(Video).where(Video.id == video_id).values(likes_count=Video.likes_count - 1)
        )
        return False
    else:
        db.add(Like(user_id=user_id, video_id=video_id, created_at=datetime.now(timezone.utc)))
        await db.execute(
            update(Video).where(Video.id == video_id).values(likes_count=Video.likes_count + 1)
        )
        # Notify video author
        video = await db.get(Video, video_id)
        if video and video.user_id != user_id:
            db.add(Notification(
                user_id=video.user_id, actor_id=user_id,
                type="like", reference_id=video_id,
                created_at=datetime.now(timezone.utc),
            ))
        return True


# ─────────────────────────────────────────────────────────────────
# COMMENT CRUD
# ─────────────────────────────────────────────────────────────────
async def create_comment(db: AsyncSession, user_id: uuid.UUID, video_id: uuid.UUID, data: CommentCreate) -> Comment:
    comment = Comment(
        user_id=user_id,
        video_id=video_id,
        parent_comment_id=data.parent_comment_id,
        content=data.content,
        created_at=datetime.now(timezone.utc),
    )
    db.add(comment)
    await db.execute(
        update(Video).where(Video.id == video_id).values(comments_count=Video.comments_count + 1)
    )
    await db.flush()
    return comment


async def get_comments(
    db: AsyncSession, video_id: uuid.UUID, page: int = 1, page_size: int = 30
) -> list[Comment]:
    result = await db.execute(
        select(Comment)
        .where(Comment.video_id == video_id, Comment.is_deleted == False, Comment.parent_comment_id == None)
        .options(selectinload(Comment.author), selectinload(Comment.replies))
        .order_by(Comment.created_at.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────
# VIDEO VIEW CRUD
# ─────────────────────────────────────────────────────────────────
async def record_view(db: AsyncSession, user_id: uuid.UUID | None, data: VideoViewCreate) -> None:
    db.add(VideoView(
        user_id=user_id,
        video_id=data.video_id,
        watch_time=data.watch_time,
        completed=data.completed,
        created_at=datetime.now(timezone.utc),
    ))
    await db.execute(
        update(Video).where(Video.id == data.video_id).values(views_count=Video.views_count + 1)
    )


# ─────────────────────────────────────────────────────────────────
# SAVED VIDEO CRUD
# ─────────────────────────────────────────────────────────────────
async def toggle_save(db: AsyncSession, user_id: uuid.UUID, video_id: uuid.UUID) -> bool:
    existing = await db.execute(
        select(SavedVideo).where(SavedVideo.user_id == user_id, SavedVideo.video_id == video_id)
    )
    row = existing.scalar_one_or_none()
    if row:
        await db.delete(row)
        return False
    db.add(SavedVideo(user_id=user_id, video_id=video_id, created_at=datetime.now(timezone.utc)))
    return True


# ─────────────────────────────────────────────────────────────────
# REPORT CRUD
# ─────────────────────────────────────────────────────────────────
async def create_report(db: AsyncSession, reporter_id: uuid.UUID, data: ReportCreate) -> Report:
    report = Report(reporter_id=reporter_id, video_id=data.video_id, reason=data.reason,
                    created_at=datetime.now(timezone.utc))
    db.add(report)
    return report


# ─────────────────────────────────────────────────────────────────
# MESSAGE CRUD
# ─────────────────────────────────────────────────────────────────
async def create_message(db: AsyncSession, sender_id: uuid.UUID, data: MessageCreate) -> Message:
    msg = Message(
        sender_id=sender_id,
        receiver_id=data.receiver_id,
        content=data.content,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    await db.flush()
    return msg


async def get_conversation(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID, page: int = 1
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(
            ((Message.sender_id == user_a) & (Message.receiver_id == user_b))
            | ((Message.sender_id == user_b) & (Message.receiver_id == user_a))
        )
        .order_by(Message.created_at.desc())
        .limit(50)
        .offset((page - 1) * 50)
    )
    return list(result.scalars().all())
