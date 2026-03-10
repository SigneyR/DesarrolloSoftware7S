"""
app/models/video.py
───────────────────
All video-related ORM models.

Design decisions:
  ─ Video
    • views_count / likes_count / comments_count: denormalised counters.
      Recomputing via JOIN + COUNT for every feed item at high QPS
      would overwhelm Postgres. Counters are incremented atomically:
        UPDATE videos SET likes_count = likes_count + 1 WHERE id = $1
      This is safe inside a serialisable (or READ COMMITTED + FOR UPDATE)
      transaction and eliminates the expensive aggregation query.

    • is_deleted uses soft-delete so referential integrity for likes,
      comments etc. is maintained and content moderation has an audit trail.

    • engagement_score: pre-computed float updated by a background job
      (e.g. Celery beat every 15 min). The feed query simply ORDER BY
      engagement_score DESC, avoiding real-time weighted ranking.

  ─ Like / SavedVideo
    • Composite UNIQUE constraint prevents duplicate rows and doubles
      as a covering index for "has this user liked this video?" lookups.

  ─ Comment
    • parent_comment_id enables threaded replies (depth-1 nesting is
      standard in TikTok; deeper trees need an adjacency-list traversal).

  ─ Follower
    • (follower_id, following_id) UNIQUE + both FK indexes make
      "does A follow B?" a single index scan.

  ─ VideoView
    • Append-only; never updated. Partitioned by created_at (range)
      so old partitions can be archived / dropped cheaply.
    • watch_time (seconds) + completed feed the recommendation engine.

  ─ Notification
    • reference_id stores the ID of the triggering entity
      (like_id, comment_id, follower_id). Kept as UUID to stay generic.
    • Soft push: a background job flushes pending notifications via
      WebSocket or FCM; the DB row acts as the durable store.

  ─ Report
    • Reason stored as enum-string for easy filtering in moderation UI.

  ─ Message
    • Basic structure. Production DMs would live in a dedicated
      message-service with its own Cassandra/ScyllaDB cluster for
      linear write scalability; this model is the bootstrap schema.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float,
    ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey


# ─────────────────────────────────────────────────────────────────
# VIDEO
# ─────────────────────────────────────────────────────────────────
class Video(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "videos"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str] = mapped_column(String(512), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512))
    duration: Mapped[int] = mapped_column(SmallInteger, nullable=False)          # seconds
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Denormalised engagement counters
    views_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    likes_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    comments_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    shares_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Pre-computed algorithmic score (background job refreshes every 15 min)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)

    # Relationships
    author: Mapped["User"] = relationship(back_populates="videos")
    likes: Mapped[list["Like"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    saved_by: Mapped[list["SavedVideo"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    views: Mapped[list["VideoView"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="video", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_videos_user_id_created_at", "user_id", "created_at"),
        Index("ix_videos_engagement_score", "engagement_score"),
        Index("ix_videos_is_deleted_public", "is_deleted", "is_public"),
        CheckConstraint("duration > 0 AND duration <= 600", name="ck_video_duration"),
    )


# ─────────────────────────────────────────────────────────────────
# LIKE
# ─────────────────────────────────────────────────────────────────
class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="likes")
    video: Mapped["Video"] = relationship(back_populates="likes")

    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_like_user_video"),
        Index("ix_likes_video_id", "video_id"),
        Index("ix_likes_user_id", "user_id"),
        Index("ix_likes_created_at", "created_at"),
    )


# ─────────────────────────────────────────────────────────────────
# COMMENT
# ─────────────────────────────────────────────────────────────────
class Comment(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "comments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    likes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    author: Mapped["User"] = relationship(back_populates="comments")
    video: Mapped["Video"] = relationship(back_populates="comments")
    replies: Mapped[list["Comment"]] = relationship(
        foreign_keys=[parent_comment_id], back_populates="parent_comment"
    )
    parent_comment: Mapped["Comment | None"] = relationship(
        foreign_keys=[parent_comment_id], back_populates="replies", remote_side="Comment.id"
    )

    __table_args__ = (
        Index("ix_comments_video_id_created_at", "video_id", "created_at"),
        Index("ix_comments_user_id", "user_id"),
    )


# ─────────────────────────────────────────────────────────────────
# FOLLOWER
# ─────────────────────────────────────────────────────────────────
class Follower(Base):
    __tablename__ = "followers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    follower_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    following_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    follower_user: Mapped["User"] = relationship(
        foreign_keys=[follower_id], back_populates="following"
    )
    following_user: Mapped["User"] = relationship(
        foreign_keys=[following_id], back_populates="followers"
    )

    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_follow_pair"),
        CheckConstraint("follower_id != following_id", name="ck_no_self_follow"),
        Index("ix_followers_follower_id", "follower_id"),
        Index("ix_followers_following_id", "following_id"),
    )


# ─────────────────────────────────────────────────────────────────
# SAVED VIDEO
# ─────────────────────────────────────────────────────────────────
class SavedVideo(Base):
    __tablename__ = "saved_videos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="saved_videos")
    video: Mapped["Video"] = relationship(back_populates="saved_by")

    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_saved_user_video"),
        Index("ix_saved_user_id", "user_id"),
    )


# ─────────────────────────────────────────────────────────────────
# VIDEO VIEW  (append-only; partition by month in production)
# ─────────────────────────────────────────────────────────────────
class VideoView(Base):
    __tablename__ = "video_views"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    watch_time: Mapped[int] = mapped_column(SmallInteger, nullable=False)        # seconds watched
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User | None"] = relationship(back_populates="views")
    video: Mapped["Video"] = relationship(back_populates="views")

    __table_args__ = (
        Index("ix_views_video_id_created_at", "video_id", "created_at"),
        # Range partitioning key hint (actual DDL managed by Alembic migration):
        # PARTITION BY RANGE (created_at)
    )


# ─────────────────────────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────────────────────────
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)    # like|comment|follow|mention
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # entity that triggered
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="notifications")

    __table_args__ = (
        Index("ix_notif_user_id_is_read", "user_id", "is_read"),
        Index("ix_notif_created_at", "created_at"),
    )


# ─────────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────────
class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(50), nullable=False)   # spam|hate|violence|nudity|other
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|reviewed|dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    video: Mapped["Video"] = relationship(back_populates="reports")

    __table_args__ = (
        UniqueConstraint("reporter_id", "video_id", name="uq_report_user_video"),
        Index("ix_reports_status", "status"),
    )


# ─────────────────────────────────────────────────────────────────
# MESSAGE  (bootstrap structure; scales to dedicated service later)
# ─────────────────────────────────────────────────────────────────
class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_msg_sender_receiver", "sender_id", "receiver_id"),
        Index("ix_msg_receiver_is_read", "receiver_id", "is_read"),
        Index("ix_msg_created_at", "created_at"),
        CheckConstraint("sender_id != receiver_id", name="ck_no_self_msg"),
    )
