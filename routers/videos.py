import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
import models
import schemas
from database import SessionLocal

router = APIRouter(prefix="/videos", tags=["Videos"])

UPLOAD_FOLDER = "app/uploads"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 🎬 Subir video
@router.post("/", response_model=schemas.VideoResponse)
def upload_video(
    title: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    file_location = f"{UPLOAD_FOLDER}/{file.filename}"

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    new_video = models.Video(
        title=title,
        description=description,
        file_path=file_location
    )

    db.add(new_video)
    db.commit()
    db.refresh(new_video)

    return new_video


# 📜 Listar videos
@router.get("/", response_model=list[schemas.VideoResponse])
def list_videos(db: Session = Depends(get_db)):
    return db.query(models.Video).all()


# 👀 Ver video por ID
@router.get("/{video_id}", response_model=schemas.VideoResponse)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()

    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")

    return video


# 🗑 Eliminar video
@router.delete("/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()

    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")

    if os.path.exists(video.file_path):
        os.remove(video.file_path)

    db.delete(video)
    db.commit()

    return {"message": "Video eliminado correctamente"}