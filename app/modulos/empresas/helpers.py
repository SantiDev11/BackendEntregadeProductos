# Validaciones del módulo Empresas. Si algo no se cumple, lanzan el error de errors.py.
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.modulos.empresas import errors, queries
from app.modulos.empresas.models import Empresa
from app.modulos.empresas.schemas import EmpresaOut, Entero
from app.modulos.usuarios.models import Usuario

_validar_entero = TypeAdapter(Entero)

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


def validate_empresa_id(db: Session, valor) -> int:
    """El empresa_id que envía el admin al crear. Lanza 422 si falta, si no es un número entero o si no existe,
    y 400 si la empresa no está activa."""
    if valor is None:
        raise errors.empresa_id_obligatorio()
    try:
        empresa_id = _validar_entero.validate_python(valor)
    except ValidationError as error:
        raise errors.empresa_id_invalido(error)
    empresa = queries.obtener(db, empresa_id)
    if empresa is None:
        raise errors.empresa_id_no_existe()
    if empresa.estado != "activa":
        raise errors.empresa_id_no_activa()
    return empresa_id


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


def validate_unique_nit(db: Session, nit: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya hay otra empresa con ese NIT (sin el dígito de verificación)."""
    if queries.existe_nit(db, nit, excluir_id):
        raise errors.nit_duplicado()


def validate_se_puede_eliminar(db: Session, empresa_id: int) -> None:
    """Lanza 400, diciendo qué tiene, si algo impide eliminar la empresa (sus facturas, sobre todo)."""
    datos = queries.lo_que_impide_eliminar(db, empresa_id)
    if datos:
        raise errors.tiene_datos(datos)
