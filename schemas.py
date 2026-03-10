from pydantic import BaseModel

class VideoBase(BaseModel):
    title: str

class VideoCreate(VideoBase):
    pass

class VideoResponse(VideoBase):
    id: int
    filename: str

    class Config:
        orm_mode = True