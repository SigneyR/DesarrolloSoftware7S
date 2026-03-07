from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Like, Comment, Follow

router = APIRouter(prefix="/api", tags=["interactions"])

# ── LIKES ──────────────────────────────────────────
@router.post("/videos/{video_id}/like")
def toggle_like(video_id: str, user_id: str, db: Session = Depends(get_db)):
    like = db.query(Like).filter_by(video_id=video_id, user_id=user_id).first()
    if like:
        db.delete(like)
        db.commit()
        return {"message": "Like eliminado"}
    nuevo = Like(user_id=user_id, video_id=video_id)
    db.add(nuevo)
    db.commit()
    return {"message": "Like agregado"}

@router.get("/videos/{video_id}/likes")
def contar_likes(video_id: str, db: Session = Depends(get_db)):
    total = db.query(Like).filter_by(video_id=video_id).count()
    return {"video_id": video_id, "likes": total}

# ── COMENTARIOS ────────────────────────────────────
@router.get("/videos/{video_id}/comments")
def listar_comentarios(video_id: str, db: Session = Depends(get_db)):
    comentarios = db.query(Comment).filter_by(video_id=video_id).all()
    return comentarios

@router.post("/videos/{video_id}/comments")
def agregar_comentario(video_id: str, user_id: str, content: str, db: Session = Depends(get_db)):
    comentario = Comment(user_id=user_id, video_id=video_id, content=content)
    db.add(comentario)
    db.commit()
    return {"message": "Comentario agregado"}

@router.delete("/videos/{video_id}/comments/{comment_id}")
def eliminar_comentario(video_id: str, comment_id: str, user_id: str, db: Session = Depends(get_db)):
    comentario = db.query(Comment).filter_by(id=comment_id, user_id=user_id).first()
    if not comentario:
        raise HTTPException(status_code=404, detail="Comentario no encontrado o no eres el autor")
    db.delete(comentario)
    db.commit()
    return {"message": "Comentario eliminado"}

# ── SEGUIR USUARIOS ────────────────────────────────
@router.post("/users/{user_id}/follow")
def toggle_follow(user_id: str, follower_id: str, db: Session = Depends(get_db)):
    follow = db.query(Follow).filter_by(follower_id=follower_id, following_id=user_id).first()
    if follow:
        db.delete(follow)
        db.commit()
        return {"message": "Dejaste de seguir al usuario"}
    nuevo = Follow(follower_id=follower_id, following_id=user_id)
    db.add(nuevo)
    db.commit()
    return {"message": "Ahora sigues al usuario"}

@router.get("/users/{user_id}/followers")
def listar_seguidores(user_id: str, db: Session = Depends(get_db)):
    total = db.query(Follow).filter_by(following_id=user_id).count()
    return {"user_id": user_id, "followers": total}

@router.get("/users/{user_id}/following")
def listar_siguiendo(user_id: str, db: Session = Depends(get_db)):
    total = db.query(Follow).filter_by(follower_id=user_id).count()
    return {"user_id": user_id, "following": total}