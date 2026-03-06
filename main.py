from fastapi import FastAPI
from database import engine
import models
from routers import videos

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="TikTok Backend - Videos")

app.include_router(videos.router)

from fastapi.staticfiles import StaticFiles

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")