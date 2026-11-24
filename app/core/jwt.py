# Utilidades JWT: crear y leer tokens de acceso y de refresco
import os
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Falta SECRET_KEY en el archivo .env")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def create_access_token(user_id: int, rol: str) -> str:
    """Crea un token con el id del usuario, su rol y vencimiento a 60 minutos."""
    expira = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    claims = {
        "sub": str(user_id),  # el estándar JWT pide que "sub" sea texto
        "rol": rol,
        "exp": expira,
    }
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Crea un refresh token (JWT) con vencimiento largo y un jti único para rotación."""
    expira = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    claims = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": secrets.token_hex(16),  # identificador único para permitir rotación
        "exp": expira,
    }
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Devuelve los claims si el token es válido; None si está vencido, alterado o mal formado."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def decode_refresh_token(token: str) -> dict | None:
    """Devuelve los claims si el refresh token es válido y es de tipo 'refresh';
    None si está vencido, alterado, mal formado o no es un refresh token."""
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if claims.get("type") != "refresh":
            return None
        return claims
    except JWTError:
        return None
