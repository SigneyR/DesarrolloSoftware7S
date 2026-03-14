from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app

# ── BASE DE DATOS DE TEST ───────────────────────────────
DATABASE_TEST_URL = "postgresql://postgres:1234@localhost/tiktokdb"

engine_test = create_engine(DATABASE_TEST_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

Base.metadata.create_all(bind=engine_test)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# ── DATOS DE PRUEBA ─────────────────────────────────────
USER_ID = "test_user"
USER_ID_2 = "test_user_2"
VIDEO_ID = "test_video"


# ── TESTS DE FLUJO COMPLETO ─────────────────────────────

def test_flujo_completo_like():
    """Simula un usuario dando y quitando like a un video"""
    from models import Like
    db = TestingSessionLocal()
    db.query(Like).filter_by(user_id=USER_ID, video_id=VIDEO_ID).delete()
    db.commit()
    db.close()

    r1 = client.post(f"/api/videos/{VIDEO_ID}/like?user_id={USER_ID}")
    assert r1.status_code == 200

    r2 = client.get(f"/api/videos/{VIDEO_ID}/likes")
    likes_con = r2.json()["likes"]
    assert likes_con >= 1

    r3 = client.post(f"/api/videos/{VIDEO_ID}/like?user_id={USER_ID}")
    assert r3.status_code == 200

    r4 = client.get(f"/api/videos/{VIDEO_ID}/likes")
    likes_sin = r4.json()["likes"]
    assert likes_sin < likes_con


def test_flujo_completo_comentarios():
    """Simula agregar, listar y eliminar un comentario"""
    r1 = client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID, "content": "Comentario flujo completo"}
    )
    assert r1.status_code == 200

    r2 = client.get(f"/api/videos/{VIDEO_ID}/comments")
    comentarios = r2.json()
    assert len(comentarios) > 0

    contenidos = [c["content"] for c in comentarios]
    assert "Comentario flujo completo" in contenidos

    ultimo_id = next(c["id"] for c in comentarios if c["content"] == "Comentario flujo completo")
    r3 = client.delete(
        f"/api/videos/{VIDEO_ID}/comments/{ultimo_id}",
        params={"user_id": USER_ID}
    )
    assert r3.status_code == 200


def test_flujo_completo_seguimiento():
    """Simula seguir a un usuario y verificar contadores"""
    # Limpia estado previo para garantizar que NO está siguiendo
    from models import Follow
    db = TestingSessionLocal()
    db.query(Follow).filter_by(follower_id=USER_ID, following_id=USER_ID_2).delete()
    db.commit()
    db.close()

    # 1er POST: debe seguir (estado limpio)
    r1 = client.post(
        f"/api/users/{USER_ID_2}/follow",
        params={"follower_id": USER_ID}
    )
    assert r1.status_code == 200
    assert r1.json()["message"] == "Ahora sigues al usuario"

    # Verifica contadores
    r2 = client.get(f"/api/users/{USER_ID_2}/followers")
    assert r2.json()["followers"] >= 1

    r3 = client.get(f"/api/users/{USER_ID}/following")
    assert r3.json()["following"] >= 1

    # 2do POST: debe dejar de seguir (toggle)
    r4 = client.post(
        f"/api/users/{USER_ID_2}/follow",
        params={"follower_id": USER_ID}
    )
    assert r4.status_code == 200
    assert r4.json()["message"] == "Dejaste de seguir al usuario"


def test_interacciones_multiples_usuarios():
    """Simula dos usuarios interactuando con el mismo video"""
    from models import Like
    db = TestingSessionLocal()
    db.query(Like).filter_by(video_id=VIDEO_ID).delete()
    db.commit()
    db.close()

    r1 = client.post(f"/api/videos/{VIDEO_ID}/like?user_id={USER_ID}")
    assert r1.status_code == 200

    r2 = client.post(f"/api/videos/{VIDEO_ID}/like?user_id={USER_ID_2}")
    assert r2.status_code == 200

    r3 = client.get(f"/api/videos/{VIDEO_ID}/likes")
    assert r3.json()["likes"] >= 2

    r4 = client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID, "content": "Comentario usuario 1"}
    )
    assert r4.status_code == 200

    r5 = client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID_2, "content": "Comentario usuario 2"}
    )
    assert r5.status_code == 200

    r6 = client.get(f"/api/videos/{VIDEO_ID}/comments")
    assert len(r6.json()) >= 2