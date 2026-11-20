# Utilidades de seguridad: hash y verificación de contraseñas
from passlib.context import CryptContext

# Contexto de passlib con bcrypt (12 rondas por defecto -> prefijo $2b$12$)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt de una contraseña en texto plano."""
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Devuelve True si la contraseña coincide con el hash guardado."""
    return pwd_context.verify(password, hashed)
