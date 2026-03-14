from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import SessionLocal
import shutil
import uuid
import os

router = APIRouter(prefix="/videos", tags=["Videos"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# SUBIR VIDEO
@router.post("/", response_model=schemas.VideoResponse)
def upload_video(
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    unique_name = str(uuid.uuid4()) + "_" + file.filename
    file_path = f"uploads/{unique_name}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    video = models.Video(
        title=title,
        filename=unique_name
    )

    db.add(video)
    db.commit()
    db.refresh(video)

    return video


# LISTAR VIDEOS (paginado)
@router.get("/", response_model=list[schemas.VideoResponse])
def list_videos(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    videos = db.query(models.Video).offset(skip).limit(limit).all()
    return videos


# VER VIDEO — cambiado a String
@router.get("/{video_id}", response_model=schemas.VideoResponse)
def get_video(video_id: str, db: Session = Depends(get_db)):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "Video no encontrado")
    return video


# ELIMINAR VIDEO — cambiado a String
@router.delete("/{video_id}")
def delete_video(video_id: str, db: Session = Depends(get_db)):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "Video no encontrado")

    path = f"uploads/{video.filename}"
    if os.path.exists(path):
        os.remove(path)

    db.delete(video)
    db.commit()

    return {"message": "Video eliminado"}