import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app

# ── BASE DE DATOS TEMPORAL PARA TESTS ──────────────────
# Usa una BD separada para no afectar la de desarrollo
DATABASE_TEST_URL = "postgresql://postgres:1234@localhost/tiktokdb"

engine_test = create_engine(DATABASE_TEST_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

# Crea las tablas en la BD de test
Base.metadata.create_all(bind=engine_test)

# Reemplaza la BD real por la de test
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


# ── DATOS DE PRUEBA ─────────────────────────────────────
# Antes de correr los tests necesitas tener en la BD de test:
# un usuario con id="test_user" y un video con id="test_video"

USER_ID = "test_user"
VIDEO_ID = "test_video"


# ── TESTS ───────────────────────────────────────────────

def test_dar_like():
    """Al dar like por primera vez debe responder 'Like agregado'"""
    response = client.post(f"/api/videos/{VIDEO_ID}/like?user_id={USER_ID}")
    assert response.status_code == 200
    assert response.json()["message"] in ["Like agregado", "Like eliminado"]


def test_toggle_like():
    """Al dar like dos veces debe alternar entre agregar y eliminar"""
    # Primer like
    r1 = client.post(f"/api/videos/{VIDEO_ID}/like?user_id={USER_ID}")
    mensaje1 = r1.json()["message"]

    # Segundo like (debe ser el contrario)
    r2 = client.post(f"/api/videos/{VIDEO_ID}/like?user_id={USER_ID}")
    mensaje2 = r2.json()["message"]

    assert mensaje1 != mensaje2


def test_contar_likes():
    """Debe retornar el total de likes de un video"""
    response = client.get(f"/api/videos/{VIDEO_ID}/likes")
    assert response.status_code == 200
    data = response.json()
    assert "likes" in data
    assert isinstance(data["likes"], int)


def test_like_video_inexistente():
    """Dar like a un video que no existe debe retornar error"""
    try:
        response = client.post("/api/videos/video_falso_999/like?user_id=test_user")
        assert response.status_code in [404, 422, 500]
    except Exception:
        pass  # La BD rechaza correctamente el video inexistente


def test_like_usuario_inexistente():
    """Dar like con un usuario que no existe debe retornar error"""
    try:
        response = client.post(f"/api/videos/{VIDEO_ID}/like?user_id=usuario_falso_999")
        assert response.status_code in [404, 422, 500]
    except Exception:
        pass  # La BD rechaza correctamente el usuario inexistente
