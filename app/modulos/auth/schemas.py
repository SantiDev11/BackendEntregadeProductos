# Esquemas de autenticación (entrada y salida de /login)
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modulos.empresas.schemas import EmpresaResumen
from app.modulos.roles.schemas import PermisoResumen  # {id, nombre} de cada permiso


# Correo o número de documento: se quitan los espacios de los lados y no puede quedar vacío
Identificador = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class LoginRequest(BaseModel):
    """Datos que envía el frontend para iniciar sesión: correo o número de documento, y contraseña."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"correo": "usuario@entrega.com", "contrasena": "Clave123*"},
                                        {"identificador": "1020304050", "contrasena": "Clave123*"}]}
    )

    correo: Optional[Identificador] = Field(
        default=None,
        description="**Obligatorio (o `identificador`).** Correo **o número de documento** del usuario. Si tiene `@` se busca por "
                    "correo; si no, por número de documento (sin distinguir mayúsculas). Quien no tiene documento entra con su correo.",
        examples=["usuario@entrega.com"],
    )
    identificador: Optional[Identificador] = Field(
        default=None,
        description="Alternativa a `correo`, con el mismo uso: correo o número de documento. Si llegan los dos, se usa este.",
        examples=["1020304050"],
    )
    contrasena: str = Field(
        description="**Obligatorio.** Contraseña del usuario. El servidor la compara con el hash guardado y nunca la devuelve.",
        examples=["Clave123*"],
    )

    @property
    def usuario(self) -> str | None:
        """Con lo que se identifica: `identificador` si llegó; si no, `correo`."""
        return self.identificador or self.correo


class UserOut(BaseModel):
    """Datos públicos del usuario (nunca incluye la contraseña)."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"id": 1, "nombre": "Administrador", "correo": "admin@entrega.com", "rol": "admin",
                          "empresa": None, "permisos": [{"id": 1, "nombre": "ver_facturas"}]}]
        }
    )

    id: int = Field(description="Id del usuario.", examples=[1])
    nombre: str = Field(description="Nombre del usuario.", examples=["Administrador"])
    correo: str = Field(description="Correo del usuario.", examples=["admin@entrega.com"])
    rol: str = Field(  # nombre del rol como texto, no el id
        description="Nombre del rol como texto: `admin`, `bodeguero` o `cliente`.",
        examples=["admin"],
    )
    empresa: Optional[EmpresaResumen] = Field(default=None, description="Empresa del usuario `{id, razon_social, estado}`, "
                                                                        "o `null` si no tiene (admin, clientes...).")
    permisos: List[PermisoResumen] = Field(default_factory=list,
                                           description="Permisos efectivos del usuario `{id, nombre}` (lista vacía si no tiene).")


class LoginResponse(BaseModel):
    """Respuesta de un login correcto."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {"id": 1, "nombre": "Administrador", "correo": "admin@entrega.com", "rol": "admin"},
            }]
        }
    )

    access_token: str = Field(
        description="Token JWT. Se envía en el header `Authorization: Bearer <token>`. Vence a los 60 minutos.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    refresh_token: str = Field(
        description="Token de refresco. Se envía a `POST /refresh` para obtener un nuevo access_token sin pedir contraseña. "
                    "Vence a los 7 días por defecto (configurable con `REFRESH_TOKEN_EXPIRE_DAYS`).",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    token_type: str = Field(default="bearer", description="Tipo de token. Siempre `bearer`.", examples=["bearer"])
    user: UserOut = Field(description="Datos del usuario que inició sesión.")


class RefreshRequest(BaseModel):
    """Cuerpo de la petición POST /refresh."""
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}]}
    )

    refresh_token: str = Field(
        description="**Obligatorio.** El refresh_token que se recibió en el login.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


class RefreshResponse(BaseModel):
    """Respuesta de un refresh correcto: nuevo access_token y nuevo refresh_token (rotación)."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }]
        }
    )

    access_token: str = Field(
        description="Nuevo token JWT de acceso. Vence a los 60 minutos.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    refresh_token: str = Field(
        description="Nuevo refresh token (rotación). El anterior ya no se debe usar.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    token_type: str = Field(default="bearer", description="Tipo de token. Siempre `bearer`.", examples=["bearer"])
