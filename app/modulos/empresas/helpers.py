# Validaciones del módulo Empresas. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.modulos.empresas import errors, queries
from app.modulos.empresas.models import Empresa
from app.modulos.empresas.schemas import EmpresaOut
from app.modulos.usuarios.models import Usuario


# A qué estados puede pasar cada empresa
CAMBIOS_PERMITIDOS = {
    "pendiente": ("activa", "rechazada"),
    "activa": ("suspendida",),
    "suspendida": ("activa",),
    "rechazada": ("activa",),
}


def get_empresa_or_404(db: Session, empresa_id: int) -> Empresa:
    """Devuelve la empresa o lanza 404 si no existe."""
    empresa = queries.obtener(db, empresa_id)
    if empresa is None:
        raise errors.empresa_no_encontrada()
    return empresa


def validate_cambio_estado(actual: str, nuevo: str) -> None:
    """Lanza 400 si una empresa no puede pasar de un estado al otro."""
    if nuevo not in CAMBIOS_PERMITIDOS[actual]:
        raise errors.cambio_no_permitido(actual, nuevo)


def empresa_salida(empresa: Empresa, totales: dict[str, int]) -> EmpresaOut:
    return EmpresaOut(
        id=empresa.id, razon_social=empresa.razon_social, nit=empresa.nit_completo, correo=empresa.correo,
        telefono=empresa.telefono, direccion=empresa.direccion, representante=empresa.representante, estado=empresa.estado,
        motivo_rechazo=empresa.motivo_rechazo, fecha_registro=empresa.creado_en, **totales)


def validate_empresa_activa(usuario: Usuario) -> None:
    """Lanza 403 si el usuario pertenece a una empresa que no está activa (pendiente, rechazada o suspendida).
    Los usuarios sin empresa (admin, clientes...) pasan."""
    if usuario.empresa is not None and usuario.empresa.estado != "activa":
        raise errors.empresa_no_activa(usuario.empresa.estado, usuario.empresa.motivo_rechazo)


def validate_unique_nit(db: Session, nit: str) -> None:
    """Lanza 400 si ya hay una empresa con ese NIT (sin el dígito de verificación)."""
    if queries.existe_nit(db, nit):
        raise errors.nit_duplicado()
