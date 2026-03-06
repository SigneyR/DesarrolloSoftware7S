from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base   # ← SIN PUNTO

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    file_path = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())