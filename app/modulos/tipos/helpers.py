# Validaciones y reglas del módulo Tipos. Si algo no se cumple, lanzan el error de errors.py.
# Cada tipo pertenece a una bodega: el admin maneja todos; cualquier otro usuario solo los de sus bodegas.
from sqlalchemy.orm import Session

from app.core.alcance import alcance_de
from app.modulos.bodegas.models import Bodega
from app.modulos.tipos import errors, queries
from app.modulos.tipos.models import Tipo
from app.modulos.usuarios.models import Usuario


def es_admin(usuario: Usuario) -> bool:
    return usuario.rol.nombre == "admin"


def bodegas_permitidas(db: Session, usuario: Usuario) -> list[int] | None:
    """None si no se filtra por bodega: el admin (todo) y la empresa (todo lo de su empresa, también los tipos generales,
    sin bodega). Los demás, los ids de sus bodegas."""
    alcance = alcance_de(usuario)
    return None if alcance.ve_toda_la_empresa else queries.ids_bodegas(db, alcance)


def get_tipo_or_404(db: Session, tipo_id: int, usuario: Usuario) -> Tipo:
    """Devuelve el tipo; 404 si no existe y 403 si no es del usuario: la empresa maneja todos los de su empresa (también
    los generales, sin bodega); los demás, solo los de sus bodegas."""
    tipo = queries.obtener(db, tipo_id)
    if tipo is None:
        raise errors.tipo_no_encontrado()
    alcance = alcance_de(usuario)
    if not alcance.incluye(tipo) or (not alcance.ve_toda_la_empresa and tipo.bodega_id not in queries.ids_bodegas(db, alcance)):
        raise errors.tipo_ajeno()
    return tipo


def bodega_para_nuevo_tipo(db: Session, usuario: Usuario, bodega_id: int | None) -> int | None:
    """Decide a qué bodega va un tipo nuevo.
    - Admin: la que envía (debe existir) o ninguna si no la envía.
    - Otro usuario: su única bodega; si tiene varias, la que envía (debe ser suya); si no tiene, 400."""
    if es_admin(usuario):
        if bodega_id is not None and queries.obtener_bodega(db, bodega_id) is None:
            raise errors.bodega_invalida()
        return bodega_id

    propias = queries.ids_bodegas(db, alcance_de(usuario))
    if not propias:
        raise errors.sin_bodega()
    if len(propias) == 1:
        return propias[0]  # una sola bodega: se asigna sola, sin importar lo que venga en el cuerpo
    if bodega_id is None:
        raise errors.varias_bodegas()
    if bodega_id not in propias:
        raise errors.bodega_invalida()
    return bodega_id


def validate_bodega_existe(db: Session, bodega_id: int) -> Bodega:
    """Devuelve la bodega o lanza 400 si no existe."""
    bodega = queries.obtener_bodega(db, bodega_id)
    if bodega is None:
        raise errors.bodega_invalida()
    return bodega


def validate_bodega_destino(db: Session, bodega_id: int, usuario: Usuario) -> Bodega:
    """Bodega a la que se mueve un tipo: el admin, cualquiera; la empresa, una de su empresa. Si no, 400."""
    bodega = validate_bodega_existe(db, bodega_id)
    if not alcance_de(usuario).incluye(bodega):
        raise errors.bodega_invalida()
    return bodega


def validate_unique_tipo_name(db: Session, nombre: str, bodega_id: int | None, empresa_id: int | None,
                              excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro tipo con ese nombre en la misma bodega (sin distinguir mayúsculas).
    Los generales (sin bodega) se comparan solo con los generales de su misma empresa."""
    if queries.existe_nombre(db, nombre, bodega_id, empresa_id, excluir_id):
        raise errors.nombre_duplicado()


def validate_se_puede_eliminar(db: Session, tipo_id: int) -> None:
    """Lanza 400 si el tipo está usado en alguna línea de factura (evita el error 500 de clave foránea)."""
    if queries.usado_en_facturas(db, tipo_id):
        raise errors.usado_en_facturas()


def validate_estado_segun_empresa(registro, cambios: dict) -> None:
    """Si llega estado: no deja activar nada de una empresa que no está activa (400). Activar o desactivar a mano quita la
    marca de la suspensión: lo que alguien desactivó durante ella sigue inactivo al reactivar la empresa."""
    if "estado" not in cambios:
        return
    if cambios["estado"] and registro.empresa is not None and registro.empresa.estado != "activa":
        raise errors.empresa_no_activa(registro.empresa.estado)
    cambios["desactivado_por_empresa"] = False
