from fastapi import FastAPI
from auth.routers import auth

app = FastAPI(title="TikTok Clone API")

app.include_router(auth.router)

@app.get("/")
def root():
    return {"message": "TikTok Clone API funcionando!"}