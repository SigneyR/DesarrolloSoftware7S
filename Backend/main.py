from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import engine, SessionLocal
import models
from routers import videos, auth, interactions

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="TikTok Clone API")

# Routers
app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(interactions.router)

# Static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    videos_list = db.query(models.Video).all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "videos": videos_list}
    )

@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})