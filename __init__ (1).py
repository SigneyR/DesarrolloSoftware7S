"""
app/routers/
────────────
FastAPI routers – thin HTTP layer only.
All business logic lives in crud/ and core/.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.cache import (
    cache_video_meta, check_rate_limit, get_feed_from_cache,
    revoke_refresh_token, store_refresh_token, validate_refresh_token,
)
from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.database import get_db, get_redis
from app.models.user import User
from app.schemas import (
    CommentCreate, CommentPublic, FollowResponse, LikeResponse,
    MessageCreate, MessagePublic, ReportCreate, TokenResponse,
    UserCreate, UserLogin, UserPublic, UserUpdate, VideoCreate,
    VideoFeedItem, VideoPublic, VideoViewCreate,
)

# ─── Auth ─────────────────────────────────────────────────────────
auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/register", response_model=UserPublic, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    if await crud.get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await crud.get_user_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username taken")
    return await crud.create_user(db, data)


@auth_router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    user = await crud.authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    await store_refresh_token(redis, str(user.id), refresh)
    return TokenResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(refresh_token: str, redis=Depends(get_redis)):
    user_id = await validate_refresh_token(redis, refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    await revoke_refresh_token(redis, refresh_token)
    new_access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    await store_refresh_token(redis, user_id, new_refresh)
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@auth_router.post("/logout")
async def logout(refresh_token: str, redis=Depends(get_redis)):
    await revoke_refresh_token(redis, refresh_token)
    return {"detail": "Logged out"}


# ─── Users ────────────────────────────────────────────────────────
user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@user_router.patch("/me", response_model=UserPublic)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.update_user(db, current_user, data)


@user_router.get("/{username}", response_model=UserPublic)
async def get_user(username: str, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@user_router.post("/{user_id}/follow", response_model=FollowResponse)
async def follow(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    if not await check_rate_limit(redis, "follow", str(current_user.id), max_calls=100):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    target = await crud.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404)
    followed = await crud.follow_user(db, current_user.id, user_id)
    await db.refresh(target)
    return FollowResponse(following=followed, followers_count=target.followers_count)


@user_router.delete("/{user_id}/follow", response_model=FollowResponse)
async def unfollow(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = await crud.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404)
    await crud.unfollow_user(db, current_user.id, user_id)
    await db.refresh(target)
    return FollowResponse(following=False, followers_count=target.followers_count)


# ─── Videos ───────────────────────────────────────────────────────
video_router = APIRouter(prefix="/videos", tags=["videos"])


@video_router.get("/feed", response_model=list[VideoFeedItem])
async def get_feed(
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    # 1. Try Redis cache
    offset = (page - 1) * 20
    cached_ids = await get_feed_from_cache(redis, str(current_user.id), offset, 20)
    if cached_ids:
        # Fetch lightweight metadata from Redis or Postgres
        # (production: batch GET video:meta:{id})
        pass  # simplified for brevity

    # 2. Fallback to Postgres
    return await crud.get_feed_videos(db, page=page)


@video_router.post("", response_model=VideoPublic, status_code=201)
async def upload_video(
    data: VideoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.create_video(db, current_user.id, data)


@video_router.get("/{video_id}", response_model=VideoPublic)
async def get_video(video_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    video = await crud.get_video(db, video_id)
    if not video:
        raise HTTPException(status_code=404)
    return video


@video_router.delete("/{video_id}", status_code=204)
async def delete_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    video = await crud.get_video(db, video_id)
    if not video:
        raise HTTPException(status_code=404)
    if video.user_id != current_user.id and current_user.role not in ("admin", "moderator"):
        raise HTTPException(status_code=403)
    await crud.soft_delete_video(db, video)


@video_router.post("/{video_id}/like", response_model=LikeResponse)
async def like_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    if not await check_rate_limit(redis, "like", str(current_user.id), max_calls=200):
        raise HTTPException(status_code=429, detail="Too many likes")
    liked = await crud.toggle_like(db, current_user.id, video_id)
    video = await crud.get_video(db, video_id)
    return LikeResponse(liked=liked, new_count=video.likes_count)


@video_router.post("/{video_id}/view", status_code=204)
async def record_view(
    video_id: uuid.UUID,
    data: VideoViewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    await crud.record_view(db, getattr(current_user, "id", None), data)


@video_router.post("/{video_id}/save", status_code=200)
async def save_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    saved = await crud.toggle_save(db, current_user.id, video_id)
    return {"saved": saved}


@video_router.post("/{video_id}/report", status_code=201)
async def report_video(
    video_id: uuid.UUID,
    data: ReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data.video_id = video_id
    await crud.create_report(db, current_user.id, data)
    return {"detail": "Report submitted"}


# ─── Comments ─────────────────────────────────────────────────────
comment_router = APIRouter(prefix="/videos/{video_id}/comments", tags=["comments"])


@comment_router.get("", response_model=list[CommentPublic])
async def list_comments(video_id: uuid.UUID, page: int = 1, db: AsyncSession = Depends(get_db)):
    return await crud.get_comments(db, video_id, page=page)


@comment_router.post("", response_model=CommentPublic, status_code=201)
async def add_comment(
    video_id: uuid.UUID,
    data: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.create_comment(db, current_user.id, video_id, data)


# ─── Messages ─────────────────────────────────────────────────────
message_router = APIRouter(prefix="/messages", tags=["messages"])


@message_router.post("", response_model=MessagePublic, status_code=201)
async def send_message(
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.create_message(db, current_user.id, data)


@message_router.get("/{user_id}", response_model=list[MessagePublic])
async def get_conversation(
    user_id: uuid.UUID,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await crud.get_conversation(db, current_user.id, user_id, page)
