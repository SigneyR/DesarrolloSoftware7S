import pytest
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
VIDEO_ID = "test_video"


# ── TESTS ───────────────────────────────────────────────

def test_agregar_comentario():
    """Debe agregar un comentario exitosamente"""
    response = client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID, "content": "Este es un comentario de prueba"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Comentario agregado"


def test_listar_comentarios():
    """Debe retornar la lista de comentarios de un video"""
    response = client.get(f"/api/videos/{VIDEO_ID}/comments")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_listar_comentarios_tiene_contenido():
    """Despues de agregar un comentario la lista no debe estar vacia"""
    # Primero agrega uno
    client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID, "content": "Comentario para verificar lista"}
    )
    # Luego verifica que hay comentarios
    response = client.get(f"/api/videos/{VIDEO_ID}/comments")
    assert response.status_code == 200
    assert len(response.json()) > 0


def test_eliminar_comentario_propio():
    """El usuario debe poder eliminar su propio comentario"""
    # Primero agrega un comentario
    client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID, "content": "Comentario a eliminar"}
    )
    # Obtiene la lista para sacar el id del ultimo comentario
    comentarios = client.get(f"/api/videos/{VIDEO_ID}/comments").json()
    ultimo_id = comentarios[-1]["id"]

    # Elimina ese comentario
    response = client.delete(
        f"/api/videos/{VIDEO_ID}/comments/{ultimo_id}",
        params={"user_id": USER_ID}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Comentario eliminado"


def test_eliminar_comentario_ajeno():
    """Un usuario NO debe poder eliminar el comentario de otro"""
    # Agrega un comentario con test_user
    client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID, "content": "Comentario de otro usuario"}
    )
    comentarios = client.get(f"/api/videos/{VIDEO_ID}/comments").json()
    ultimo_id = comentarios[-1]["id"]

    # Intenta eliminarlo con otro usuario
    response = client.delete(
        f"/api/videos/{VIDEO_ID}/comments/{ultimo_id}",
        params={"user_id": "otro_usuario"}
    )
    assert response.status_code == 404


def test_agregar_comentario_vacio():
    """No debe permitir agregar un comentario sin contenido"""
    response = client.post(
        f"/api/videos/{VIDEO_ID}/comments",
        params={"user_id": USER_ID, "content": ""}
    )
    assert response.status_code in [400, 422]
