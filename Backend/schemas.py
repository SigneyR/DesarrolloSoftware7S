from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# ─── AUTH ───────────────────────────────────────────
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# ─── VIDEOS ─────────────────────────────────────────
class VideoResponse(BaseModel):
    id: str
    title: str
    filename: str
    user_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ─── COMMENTS ───────────────────────────────────────
class CommentCreate(BaseModel):
    content: str

class CommentResponse(BaseModel):
    id: str
    content: str
    user_id: str
    video_id: str
    created_at: datetime

    class Config:
        from_attributes = True

# ─── LIKES / FOLLOWS ────────────────────────────────
class LikeResponse(BaseModel):
    id: str
    user_id: str
    video_id: str

    class Config:
        from_attributes = True

class FollowResponse(BaseModel):
    id: str
    follower_id: str
    following_id: str

    class Config:
        from_attributes = True