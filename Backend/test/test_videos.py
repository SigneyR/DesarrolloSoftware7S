import io
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app
from models import Video

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


# ── HELPER ──────────────────────────────────────────────
def fake_video_file(filename="test_video.mp4"):
    """Genera un archivo falso en memoria para simular un upload"""
    return ("file", (filename, io.BytesIO(b"fake video content"), "video/mp4"))


# ── TESTS ───────────────────────────────────────────────

def test_subir_video():
    """Debe subir un video exitosamente y retornar sus datos"""
    response = client.post(
        "/videos/",
        data={"title": "Video de prueba"},
        files=[fake_video_file()]
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Video de prueba"
    assert "filename" in data
    assert "id" in data
    assert "created_at" in data


def test_subir_video_sin_titulo():
    """Debe fallar si no se envía título"""
    response = client.post(
        "/videos/",
        files=[fake_video_file()]
    )
    assert response.status_code == 422


def test_subir_video_sin_archivo():
    """Debe fallar si no se envía archivo"""
    response = client.post(
        "/videos/",
        data={"title": "Sin archivo"}
    )
    assert response.status_code == 422


def test_listar_videos():
    """Debe retornar una lista de videos"""
    response = client.get("/videos/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_listar_videos_paginado():
    """Debe respetar los parámetros skip y limit"""
    response = client.get("/videos/?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 2


def test_ver_video():
    """Debe retornar un video existente por su ID"""
    r_upload = client.post(
        "/videos/",
        data={"title": "Video para ver"},
        files=[fake_video_file("ver_video.mp4")]
    )
    assert r_upload.status_code == 200
    video_id = r_upload.json()["id"]  # ID es string (UUID)

    response = client.get(f"/videos/{video_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == video_id
    assert data["title"] == "Video para ver"


def test_ver_video_inexistente():
    """Debe retornar 404 si el video no existe"""
    response = client.get("/videos/uuid-que-no-existe")
    assert response.status_code == 404
    assert response.json()["detail"] == "Video no encontrado"


def test_eliminar_video():
    """Debe eliminar un video existente correctamente"""
    r_upload = client.post(
        "/videos/",
        data={"title": "Video para eliminar"},
        files=[fake_video_file("eliminar_video.mp4")]
    )
    assert r_upload.status_code == 200
    video_id = r_upload.json()["id"]  # ID es string (UUID)

    r_delete = client.delete(f"/videos/{video_id}")
    assert r_delete.status_code == 200
    assert r_delete.json()["message"] == "Video eliminado"

    # Verifica que ya no existe
    r_get = client.get(f"/videos/{video_id}")
    assert r_get.status_code == 404


def test_eliminar_video_inexistente():
    """Debe retornar 404 al intentar eliminar un video que no existe"""
    response = client.delete("/videos/uuid-que-no-existe")
    assert response.status_code == 404
    assert response.json()["detail"] == "Video no encontrado"