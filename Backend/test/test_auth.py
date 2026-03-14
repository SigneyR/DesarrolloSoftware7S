from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app
from models import User

# ── BASE DE DATOS DE TEST ───────────────────────────────
DATABASE_TEST_URL = "postgresql://postgres:1234@localhost/tiktokdb"

engine_test = create_engine(DATABASE_TEST_URL)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine_test
)

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
TEST_EMAIL = "testauth@example.com"
TEST_USERNAME = "test_auth_user"
TEST_PASSWORD = "test1234"


# ── HELPERS ─────────────────────────────────────────────
def limpiar_usuario():
    db = TestingSessionLocal()
    try:
        db.query(User).filter(User.username == TEST_USERNAME).delete()
        db.query(User).filter(User.username == "username_actualizado").delete()
        db.query(User).filter(User.username == "usuario_existente").delete()
        db.commit()
    finally:
        db.close()


def registrar_usuario():
    """Registra el usuario de prueba y retorna el token"""
    limpiar_usuario()

    r = client.post("/auth/register", json={
        "username": TEST_USERNAME,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })

    return r.json().get("access_token")


# ── TESTS ───────────────────────────────────────────────

def test_register():
    """Debe registrar un usuario y retornar un token"""
    limpiar_usuario()

    response = client.post("/auth/register", json={
        "username": TEST_USERNAME,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })

    assert response.status_code == 201
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_email_duplicado():
    """No debe permitir registrar el mismo email dos veces"""
    limpiar_usuario()

    client.post("/auth/register", json={
        "username": TEST_USERNAME,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })

    response = client.post("/auth/register", json={
        "username": "otro_username",
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })

    assert response.status_code == 400
    assert response.json()["detail"] == "El email ya esta registrado"


def test_register_username_duplicado():
    """No debe permitir registrar el mismo username dos veces"""
    limpiar_usuario()

    client.post("/auth/register", json={
        "username": TEST_USERNAME,
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })

    response = client.post("/auth/register", json={
        "username": TEST_USERNAME,
        "email": "otro@example.com",
        "password": TEST_PASSWORD
    })

    assert response.status_code == 400
    assert response.json()["detail"] == "El username ya existe"


def test_login():
    """Debe hacer login y retornar un token"""
    registrar_usuario()

    response = client.post("/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_password_incorrecta():
    """Debe fallar con contraseña incorrecta"""
    registrar_usuario()

    response = client.post("/auth/login", json={
        "email": TEST_EMAIL,
        "password": "password_incorrecta"
    })

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas"


def test_login_email_inexistente():
    """Debe fallar si el email no existe"""
    response = client.post("/auth/login", json={
        "email": "noexiste@example.com",
        "password": TEST_PASSWORD
    })

    assert response.status_code == 401


def test_get_me():
    """Debe retornar los datos del usuario autenticado"""
    token = registrar_usuario()

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["email"] == TEST_EMAIL
    assert data["username"] == TEST_USERNAME


def test_get_me_sin_token():
    """Debe fallar si no se envía token"""
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_get_me_token_invalido():
    """Debe fallar si el token es inválido"""
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer token_invalido"}
    )

    assert response.status_code == 401


def test_update_profile():
    """Debe actualizar el username del usuario"""
    token = registrar_usuario()
    nuevo_username = "username_actualizado"

    response = client.put(
        f"/auth/profile?username={nuevo_username}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["username"] == nuevo_username


def test_update_profile_username_en_uso():
    """No debe permitir usar un username que ya existe"""
    token = registrar_usuario()

    db = TestingSessionLocal()
    try:
        from utils import hash_password

        segundo = User(
            username="usuario_existente",
            email="segundo@example.com",
            hashed_password=hash_password("pass123")
        )

        db.add(segundo)
        db.commit()
    finally:
        db.close()

    response = client.put(
        "/auth/profile?username=usuario_existente",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Ese username ya está en uso"


def test_update_profile_sin_token():
    """Debe fallar si no se envía token"""
    response = client.put("/auth/profile?username=nuevo")

    assert response.status_code == 401