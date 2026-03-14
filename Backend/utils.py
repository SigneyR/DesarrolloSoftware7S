from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# ── CARGAR VARIABLES DE ENTORNO ─────────────────────────
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

# ── CONFIGURACIÓN DE HASH DE CONTRASEÑAS ────────────────
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)

# ── FUNCIONES DE CONTRASEÑAS ────────────────────────────
def hash_password(password: str) -> str:
    """
    Genera el hash de una contraseña usando bcrypt.
    bcrypt solo soporta 72 bytes, por seguridad se limita.
    """
    return pwd_context.hash(password[:72])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica si una contraseña coincide con su hash.
    """
    return pwd_context.verify(plain_password[:72], hashed_password)


# ── CREAR TOKEN JWT ─────────────────────────────────────
def create_access_token(data: dict) -> str:
    """
    Crea un token JWT con tiempo de expiración.
    """
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt


# ── DECODIFICAR TOKEN JWT ───────────────────────────────
def decode_token(token: str):
    """
    Decodifica un token JWT y retorna el payload.
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        return payload

    except JWTError:
        return None