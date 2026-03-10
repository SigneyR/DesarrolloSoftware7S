from fastapi import FastAPI
from database import engine, Base
from routers import interactions

Base.metadata.create_all(bind=engine)  # Crea las tablas automáticamente

app = FastAPI(title="TikTok Clone")
app.include_router(interactions.router)