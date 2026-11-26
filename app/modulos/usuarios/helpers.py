# Validaciones del módulo Usuarios. Si algo no se cumple, lanzan el error de errors.py.
from sqlalchemy.orm import Session

from app.core.alcance import Alcance, alcance_de
from app.modulos.permisos.models import Permiso
from app.modulos.roles.models import Rol
from app.modulos.usuarios import errors, queries
from app.modulos.usuarios.models import Usuario

# Roles que pertenecen a una empresa: el admin debe indicarla al crearlos. Los demás (admin, cliente...) no tienen
ROLES_CON_EMPRESA = ("bodeguero", "empresa")
ROLES_SIN_EMPRESA = ("admin", "cliente")

# Roles que solo puede dar el admin: los demás no pueden crear ni convertir a nadie en uno de estos
ROLES_SOLO_ADMIN = ("admin", "empresa")


def get_usuario_or_404(db: Session, usuario_id: int, actual: Usuario) -> Usuario:
    """Devuelve el usuario o lanza 404 si no existe o si está fuera del alcance de `actual` (otra empresa,
    o no es bodeguero cuando `actual` pertenece a una empresa)."""
    usuario, alcance = queries.obtener(db, usuario_id), alcance_de(actual)
    if usuario is None or not alcance.incluye(usuario) or (alcance.solo_bodegueros and usuario.rol.nombre != "bodeguero"):
        raise errors.usuario_no_encontrado()
    return usuario


def get_usuario_editable(db: Session, usuario_id: int, actual: Usuario) -> Usuario:
    """El usuario que se va a modificar o eliminar: 404 como get_usuario_or_404, y 403 si es un admin y `actual` no lo es
    (aunque tenga el permiso: podría cambiarle la contraseña y entrar como él)."""
    usuario = get_usuario_or_404(db, usuario_id, actual)
    if usuario.rol.nombre == "admin" and not alcance_de(actual).es_admin:
        raise errors.rol_no_permitido()
    return usuario


def rol_asignable(db: Session, alcance: Alcance, rol_id: int) -> Rol:
    """El rol indicado: 400 si no existe o está inactivo, y 403 si solo lo puede dar el admin."""
    rol = validate_rol_exists(db, rol_id)
    if not rol.estado:
        raise errors.rol_inactivo()
    if rol.nombre in ROLES_SOLO_ADMIN and not alcance.es_admin:
        raise errors.rol_no_permitido()
    return rol


def empresa_al_cambiar_rol(db: Session, alcance: Alcance, editado: Usuario, rol: Rol, empresa_id_body) -> int | None:
    """Empresa del usuario cuando le cambian el rol: se conserva la que tiene, pero
    - si el rol pertenece a una empresa y no tiene ninguna, el admin debe indicarla (422), igual que al crearlo;
    - si pasa a admin o cliente la pierde, porque esos roles no pertenecen a ninguna."""
    if rol.nombre in ROLES_SIN_EMPRESA:
        return None
    if editado.empresa_id is None:
        return empresa_para_nuevo_usuario(db, alcance, rol, empresa_id_body)
    return editado.empresa_id


def rol_para_nuevo_usuario(db: Session, alcance: Alcance, rol_id: int | None) -> Rol:
    """Rol del usuario nuevo. Quien pertenece a una empresa solo crea bodegueros: si no envía rol_id se asigna
    ese, y con otro rol recibe 403. A los demás les es obligatorio (422), debe existir (400) y, si no son admin,
    no puede ser uno de los que solo da el admin (403)."""
    if alcance.solo_bodegueros:
        bodeguero = queries.rol_por_nombre(db, "bodeguero")
        if rol_id not in (None, bodeguero.id):
            raise errors.rol_no_permitido()
        return bodeguero
    if rol_id is None:
        raise errors.rol_obligatorio()
    return rol_asignable(db, alcance, rol_id)


def empresa_para_nuevo_usuario(db: Session, alcance: Alcance, rol: Rol, empresa_id_body) -> int | None:
    """Empresa del usuario nuevo. Quien pertenece a una empresa crea en la suya (la del token). El admin debe indicarla
    si el rol pertenece a una empresa (422); en los demás roles no aplica y se ignora."""
    if alcance.solo_bodegueros or (alcance.es_admin and rol.nombre in ROLES_CON_EMPRESA):
        return alcance.empresa_para_crear(db, empresa_id_body)
    return None


def validate_unique_usuario_email(db: Session, correo: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro usuario con ese correo (sin distinguir mayúsculas)."""
    if queries.existe_correo(db, correo, excluir_id):
        raise errors.correo_duplicado()


def validate_rol_exists(db: Session, rol_id: int) -> Rol:
    """Lanza 400 si el rol indicado no existe; si existe, lo devuelve."""
    rol = queries.obtener_rol(db, rol_id)
    if rol is None:
        raise errors.rol_no_existe()
    return rol


def get_permiso_or_404(db: Session, permiso_id: int) -> Permiso:
    """Devuelve el permiso o lanza 404 si no existe."""
    permiso = queries.obtener_permiso(db, permiso_id)
    if permiso is None:
        raise errors.permiso_no_encontrado()
    return permiso


def validate_unique_usuario_documento(db: Session, numero_documento: str, excluir_id: int | None = None) -> None:
    """Lanza 400 si ya existe otro usuario con ese número de documento."""
    if queries.existe_documento(db, numero_documento, excluir_id):
        raise errors.documento_duplicado()


def vacios_a_none(valores: dict) -> dict:
    """Convierte "" en None para guardar NULL (evita choques en los campos únicos como numero_documento)."""
    return {campo: (None if valor == "" else valor) for campo, valor in valores.items()}
