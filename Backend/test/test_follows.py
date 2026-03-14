import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app
from models import Follow

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
FOLLOWER_ID = "test_user"
FOLLOWING_ID = "test_user_2"


# ── HELPER ──────────────────────────────────────────────
def limpiar_follow():
    """Elimina el follow entre los usuarios de prueba para garantizar estado limpio"""
    db = TestingSessionLocal()
    db.query(Follow).filter_by(follower_id=FOLLOWER_ID, following_id=FOLLOWING_ID).delete()
    db.commit()
    db.close()


# ── TESTS ───────────────────────────────────────────────

def test_seguir_usuario():
    """Debe poder seguir a un usuario exitosamente"""
    limpiar_follow()  # Estado conocido: no está siguiendo

    response = client.post(
        f"/api/users/{FOLLOWING_ID}/follow",
        params={"follower_id": FOLLOWER_ID}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Ahora sigues al usuario"


def test_toggle_follow():
    """Seguir dos veces debe alternar entre seguir y dejar de seguir"""
    limpiar_follow()  # Estado conocido: no está siguiendo

    r1 = client.post(
        f"/api/users/{FOLLOWING_ID}/follow",
        params={"follower_id": FOLLOWER_ID}
    )
    mensaje1 = r1.json()["message"]  # "Ahora sigues al usuario"

    r2 = client.post(
        f"/api/users/{FOLLOWING_ID}/follow",
        params={"follower_id": FOLLOWER_ID}
    )
    mensaje2 = r2.json()["message"]  # "Dejaste de seguir al usuario"

    assert mensaje1 != mensaje2
    assert mensaje1 == "Ahora sigues al usuario"
    assert mensaje2 == "Dejaste de seguir al usuario"


def test_contar_seguidores():
    """Debe retornar el total de seguidores de un usuario"""
    response = client.get(f"/api/users/{FOLLOWING_ID}/followers")
    assert response.status_code == 200
    data = response.json()
    assert "followers" in data
    assert isinstance(data["followers"], int)


def test_contar_siguiendo():
    """Debe retornar el total de usuarios que sigue un usuario"""
    response = client.get(f"/api/users/{FOLLOWER_ID}/following")
    assert response.status_code == 200
    data = response.json()
    assert "following" in data
    assert isinstance(data["following"], int)


def test_no_seguirse_a_si_mismo():
    """Un usuario no debería poder seguirse a si mismo"""
    response = client.post(
        f"/api/users/{FOLLOWER_ID}/follow",
        params={"follower_id": FOLLOWER_ID}
    )
    assert response.status_code in [400, 422]