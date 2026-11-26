# Lógica de cada endpoint de Usuarios. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.core.alcance import Alcance, alcance_de
from app.core.security import hash_password
from app.modulos.roles.schemas import PermisoResumen
from app.modulos.usuarios import errors, queries
from app.modulos.usuarios.helpers import (empresa_al_cambiar_rol, empresa_para_nuevo_usuario, get_permiso_or_404,
                                          get_usuario_editable, get_usuario_or_404, rol_asignable, rol_para_nuevo_usuario,
                                          vacios_a_none, validate_unique_usuario_documento, validate_unique_usuario_email)
from app.modulos.usuarios.models import Usuario
from app.modulos.usuarios.schemas import (UsuarioCreate, UsuarioEstadoUpdate, UsuarioUpdate, UsuarioOut, UsuarioPaginado, UsuarioPermisosOut,
                                          UsuarioPermisosUpdate)


def listar_usuarios(q: str | None, estado: bool | None, rol: str | None, rol_id: int | None, page: int, limit: int,
                    db: Session, alcance: Alcance):
    """Lista los usuarios con búsqueda por nombre o correo, filtros por estado y rol, y paginación.
    Cada uno ve los de su empresa; quien pertenece a una empresa, solo sus bodegueros."""
    total, usuarios = queries.listar(db, alcance, q=q, estado=estado, rol=rol, rol_id=rol_id, page=page, limit=limit)

    return UsuarioPaginado(
        data=[UsuarioOut.model_validate(u) for u in usuarios],
        total=total,
        page=page,
        limit=limit,
    )


def obtener_usuario(usuario_id: int, db: Session, usuario: Usuario):
    """Devuelve un usuario por su id."""
    return get_usuario_or_404(db, usuario_id, usuario)


def crear_usuario(datos: UsuarioCreate, db: Session, usuario: Usuario):
    """Crea un usuario nuevo (correo en minúsculas, contraseña cifrada) y registra quién lo creó."""
    alcance = alcance_de(usuario)
    rol = rol_para_nuevo_usuario(db, alcance, datos.rol_id)
    empresa_id = empresa_para_nuevo_usuario(db, alcance, rol, datos.empresa_id)
    validate_unique_usuario_email(db, datos.correo)

    valores = vacios_a_none(datos.model_dump())  # "" se guarda como NULL
    if valores.get("numero_documento"):
        validate_unique_usuario_documento(db, valores["numero_documento"])

    valores["correo"] = valores["correo"].lower()  # el correo siempre se guarda en minúsculas
    valores["contrasena"] = hash_password(valores["contrasena"])  # nunca se guarda en texto plano

    valores["rol_id"] = rol.id
    valores["empresa_id"] = empresa_id  # nunca el del body sin validar
    nuevo = Usuario(**valores, creado_por=usuario.id, actualizado_por=usuario.id)
    nuevo.permisos = list(rol.permisos)  # el rol es la plantilla: se copian sus permisos actuales
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


def actualizar_usuario(datos: UsuarioUpdate, usuario_id: int, db: Session, usuario: Usuario):
    """Actualiza solo los campos enviados (los que lleguen en null se ignoran)
    y registra quién hizo el cambio. Si no llega contraseña, el hash no se toca."""
    editado = get_usuario_editable(db, usuario_id, usuario)
    # null se ignora (exclude_none); "" sí llega y se convierte en None para borrar el campo
    # empresa_id no se edita: solo se tiene en cuenta si el nuevo rol la exige (ver más abajo)
    cambios = vacios_a_none(datos.model_dump(exclude_none=True, exclude={"empresa_id"}))

    # El admin no puede desactivarse a sí mismo (se quedaría sin acceso)
    if usuario_id == usuario.id and cambios.get("estado") is False:
        raise errors.no_puede_desactivarse()

    if "correo" in cambios:
        cambios["correo"] = cambios["correo"].lower()  # el correo siempre se guarda en minúsculas
        validate_unique_usuario_email(db, cambios["correo"], excluir_id=usuario_id)

    if "rol_id" in cambios:
        # Quien pertenece a una empresa no puede cambiarle el rol a su bodeguero
        alcance = alcance_de(usuario)
        if cambios["rol_id"] != editado.rol_id:
            if alcance.solo_bodegueros:
                raise errors.rol_no_permitido()
            rol = rol_asignable(db, alcance, cambios["rol_id"])
            cambios["empresa_id"] = empresa_al_cambiar_rol(db, alcance, editado, rol, datos.empresa_id)

    if cambios.get("numero_documento"):
        validate_unique_usuario_documento(db, cambios["numero_documento"], excluir_id=usuario_id)

    if "contrasena" in cambios:
        cambios["contrasena"] = hash_password(cambios["contrasena"])  # se guarda el nuevo hash

    for campo, valor in cambios.items():
        setattr(editado, campo, valor)
    editado.actualizado_por = usuario.id  # actualizado_en lo actualiza el mixin (onupdate)

    db.commit()
    db.refresh(editado)
    return editado


def cambiar_estado_usuario(datos: UsuarioEstadoUpdate, usuario_id: int, db: Session, usuario: Usuario):
    """Activa o desactiva el usuario, con las mismas reglas que al editarlo: nadie se desactiva a sí mismo, solo el
    admin toca a un admin y la empresa solo a sus bodegueros."""
    return actualizar_usuario(UsuarioUpdate(estado=datos.estado), usuario_id, db, usuario)


def ver_permisos_usuario(usuario_id: int, db: Session, usuario: Usuario):
    """Permisos efectivos del usuario."""
    consultado = get_usuario_or_404(db, usuario_id, usuario)
    return UsuarioPermisosOut(data=[PermisoResumen.model_validate(p) for p in consultado.permisos])


def asignar_permisos_usuario(datos: UsuarioPermisosUpdate, usuario_id: int, db: Session, usuario: Usuario):
    """Reemplaza todos los permisos del usuario por los de la lista (vacía = sin permisos)."""
    editado = get_usuario_editable(db, usuario_id, usuario)

    ids = set(datos.permisos_ids)  # ignora ids repetidos
    permisos = queries.permisos_por_ids(db, ids)

    # Si algún id no existe, no se cambia nada
    if len(permisos) != len(ids):
        raise errors.permisos_no_existen()

    editado.permisos = permisos  # reemplaza la lista completa en usuario_permisos
    editado.actualizado_por = usuario.id
    db.commit()
    db.refresh(editado)
    return editado


def agregar_permiso_usuario(usuario_id: int, permiso_id: int, db: Session, usuario: Usuario):
    """Agrega un permiso al usuario (idempotente)."""
    editado = get_usuario_editable(db, usuario_id, usuario)
    permiso = get_permiso_or_404(db, permiso_id)
    if permiso not in editado.permisos:
        editado.permisos.append(permiso)
        editado.actualizado_por = usuario.id
        db.commit()
        db.refresh(editado)
    return editado


def quitar_permiso_usuario(usuario_id: int, permiso_id: int, db: Session, usuario: Usuario):
    """Quita un permiso al usuario (idempotente). Responde 204 sin cuerpo."""
    editado = get_usuario_editable(db, usuario_id, usuario)
    permiso = get_permiso_or_404(db, permiso_id)
    if permiso in editado.permisos:
        editado.permisos.remove(permiso)
        editado.actualizado_por = usuario.id
        db.commit()


def eliminar_usuario(usuario_id: int, db: Session, usuario: Usuario):
    """Elimina un usuario (no el propio). Responde 204 sin cuerpo."""
    eliminado = get_usuario_editable(db, usuario_id, usuario)

    # El admin no puede borrarse a sí mismo
    if usuario_id == usuario.id:
        raise errors.no_puede_eliminarse()

    # Si el usuario tiene facturas (como cliente o como emisor), no se borra (evita el error 500)
    if queries.tiene_facturas(db, usuario_id):
        raise errors.tiene_facturas()
    if queries.tiene_bodegas(db, usuario_id):
        raise errors.tiene_bodegas()

    db.delete(eliminado)
    db.commit()
