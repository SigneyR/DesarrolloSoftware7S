from pydantic import BaseModel
from datetime import datetime

class VideoBase(BaseModel):
    title: str
    description: str

class VideoResponse(VideoBase):
    id: int
    file_path: str
    created_at: datetime

    class Config:
        orm_mode = True