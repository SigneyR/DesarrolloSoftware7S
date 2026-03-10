"""
app/models/user.py
──────────────────
Users table.

Design decisions:
  • UUID PK → unpredictable IDs, safe for public APIs.
  • followers_count / following_count stored as counters on the row.
    This is a deliberate denormalization: computing COUNT(*) on the
    followers table at query time is O(n) per user and kills performance
    at millions of rows. We update these atomically with UPDATE … SET
    followers_count = followers_count + 1 inside a transaction.
  • password_hash: bcrypt hash, never the plain password.
  • is_private: drives the follow-request flow vs. instant follow.
  • Indexes on username + email (B-tree) → fast lookup on login/search.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_picture_url: Mapped[str | None] = mapped_column(String(512))
    bio: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # user | admin | moderator

    # ── Denormalised counters (updated atomically) ────────────────
    followers_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    following_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    videos_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # ── Relationships ─────────────────────────────────────────────
    videos: Mapped[list["Video"]] = relationship(back_populates="author", lazy="select")
    comments: Mapped[list["Comment"]] = relationship(back_populates="author", lazy="select")
    likes: Mapped[list["Like"]] = relationship(back_populates="user", lazy="select")
    saved_videos: Mapped[list["SavedVideo"]] = relationship(back_populates="user", lazy="select")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", lazy="select")
    views: Mapped[list["VideoView"]] = relationship(back_populates="user", lazy="select")

    # Followers / Following
    following: Mapped[list["Follower"]] = relationship(
        foreign_keys="Follower.follower_id", back_populates="follower_user", lazy="select"
    )
    followers: Mapped[list["Follower"]] = relationship(
        foreign_keys="Follower.following_id", back_populates="following_user", lazy="select"
    )

    # ── Composite indexes ─────────────────────────────────────────
    __table_args__ = (
        Index("ix_users_username_lower", func.lower("username")),  # case-insensitive search
        Index("ix_users_created_at", "created_at"),
        Index("ix_users_role", "role"),
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"
