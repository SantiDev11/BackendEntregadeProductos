# Validaciones y reglas del módulo Bodegas. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.core.alcance import Alcance, alcance_de
from app.modulos.bodegas import errors, queries
from app.modulos.bodegas.models import Bodega
from app.modulos.usuarios.models import Usuario


def puede_usar_bodega(bodega: Bodega, usuario: Usuario) -> bool:
    """Admin: todas. Empresa: las de su empresa. Los demás: las suyas, y que además sean de su empresa."""
    alcance = alcance_de(usuario)
    return alcance.incluye(bodega) and (alcance.ve_toda_la_empresa or bodega.bodeguero_id == usuario.id)


def get_bodega_or_404(db: Session, bodega_id: int, usuario: Usuario) -> Bodega:
    """Devuelve la bodega o lanza 404 si no existe o si está fuera del alcance del usuario."""
    bodega = queries.obtener(db, bodega_id)
    if bodega is None or not puede_usar_bodega(bodega, usuario):
        raise errors.bodega_no_encontrada()
    return bodega


def validate_unique_bodega_name(db: Session, nombre: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otra bodega con ese nombre (sin distinguir mayúsculas)."""
    if queries.existe_nombre(db, nombre, excluir_id):
        raise errors.nombre_duplicado()


def validate_unique_bodega_codigo(db: Session, codigo: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otra bodega con ese código (sin distinguir mayúsculas)."""
    if queries.existe_codigo(db, codigo, excluir_id):
        raise errors.codigo_duplicado()


def validate_bodeguero(db: Session, bodeguero_id: int, alcance: Alcance) -> Usuario:
    """Devuelve el bodeguero; lanza 400 si el id no es de un bodeguero que el usuario pueda asignar."""
    bodeguero = queries.obtener_bodeguero(db, bodeguero_id)
    if bodeguero is None or not alcance.incluye(bodeguero):
        raise errors.bodeguero_invalido()
    return bodeguero


def validate_se_puede_eliminar(db: Session, bodega_id: int) -> None:
    """Lanza 400 si la bodega tiene facturas: las facturas la necesitan (evita el error 500 de clave foránea).
    Sus tipos no impiden borrarla: pasan a generales de la empresa."""
    if queries.tiene_facturas(db, bodega_id):
        raise errors.tiene_facturas()


def validate_estado_segun_empresa(registro, cambios: dict) -> None:
    """Si llega estado: no deja activar nada de una empresa que no está activa (400). Activar o desactivar a mano quita la
    marca de la suspensión: lo que alguien desactivó durante ella sigue inactivo al reactivar la empresa."""
    if "estado" not in cambios:
        return
    if cambios["estado"] and registro.empresa is not None and registro.empresa.estado != "activa":
        raise errors.empresa_no_activa(registro.empresa.estado)
    cambios["desactivado_por_empresa"] = False
