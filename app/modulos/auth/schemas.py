# Esquemas de autenticación (entrada y salida de /login)
from typing import List

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modulos.roles.schemas import PermisoResumen  # {id, nombre} de cada permiso


class LoginRequest(BaseModel):
    """Datos que envía el frontend para iniciar sesión."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"correo": "usuario@entrega.com", "contrasena": "Clave123*"}]}
    )

    correo: EmailStr = Field(
        description="**Obligatorio.** Correo del usuario. Debe tener formato de correo válido.",
        examples=["usuario@entrega.com"],
    )
    contrasena: str = Field(
        description="**Obligatorio.** Contraseña del usuario. El servidor la compara con el hash guardado y nunca la devuelve.",
        examples=["Clave123*"],
    )


class UserOut(BaseModel):
    """Datos públicos del usuario (nunca incluye la contraseña)."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"id": 1, "nombre": "Administrador", "correo": "admin@entrega.com", "rol": "admin",
                          "permisos": [{"id": 1, "nombre": "ver_facturas"}]}]
        }
    )

    id: int = Field(description="Id del usuario.", examples=[1])
    nombre: str = Field(description="Nombre del usuario.", examples=["Administrador"])
    correo: str = Field(description="Correo del usuario.", examples=["admin@entrega.com"])
    rol: str = Field(  # nombre del rol como texto, no el id
        description="Nombre del rol como texto: `admin`, `bodeguero` o `cliente`.",
        examples=["admin"],
    )
    permisos: List[PermisoResumen] = Field(default_factory=list,
                                           description="Permisos efectivos del usuario `{id, nombre}` (lista vacía si no tiene).")


class LoginResponse(BaseModel):
    """Respuesta de un login correcto."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {"id": 1, "nombre": "Administrador", "correo": "admin@entrega.com", "rol": "admin"},
            }]
        }
    )

    access_token: str = Field(
        description="Token JWT. Se envía en el header `Authorization: Bearer <token>`. Vence a los 60 minutos.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    token_type: str = Field(default="bearer", description="Tipo de token. Siempre `bearer`.", examples=["bearer"])
    user: UserOut = Field(description="Datos del usuario que inició sesión.")
