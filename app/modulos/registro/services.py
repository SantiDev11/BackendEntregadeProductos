# Lógica del registro público. Todo lo de un registro va en UNA transacción: o se guarda completo o no queda nada.
# guardar_todo_o_nada y crear_empresa también los usa el admin (POST /empresas).
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modulos.empresas.models import Empresa
from app.modulos.empresas.schemas import EmpresaCreate
from app.modulos.registro import errors
from app.modulos.registro.helpers import rol_por_nombre, validate_repetidos
from app.modulos.registro.schemas import (EmpresaRegistrada, RegistroCliente, RegistroClienteOut, RegistroEmpresa,
                                          RegistroEmpresaOut, UsuarioRegistrado)
from app.modulos.usuarios.models import Usuario


def registrar(datos: RegistroCliente | RegistroEmpresa, db: Session) -> RegistroClienteOut | RegistroEmpresaOut:
    """Registra un cliente (activo) o una empresa (pendiente) con su usuario."""
    return guardar_todo_o_nada(
        db, datos, lambda: _registrar_cliente(datos, db) if isinstance(datos, RegistroCliente) else _registrar_empresa(datos, db))


def guardar_todo_o_nada(db: Session, datos: RegistroCliente | EmpresaCreate, guardar: Callable):
    """Revisa los repetidos (400), guarda en una transacción y devuelve lo que devuelva `guardar`."""
    validate_repetidos(db, datos)
    try:
        respuesta = guardar()
        db.commit()
        return respuesta
    except IntegrityError:
        # Dos registros iguales al mismo tiempo: la base rechazó el segundo. Se responde el 400 que corresponde
        db.rollback()
        validate_repetidos(db, datos)
        raise
    except Exception:
        db.rollback()
        raise


def crear_empresa(db: Session, datos: EmpresaCreate, estado: str, creado_por: int | None = None) -> Empresa:
    """Agrega la empresa y su usuario (rol empresa, con el correo, la contraseña y el nombre del representante). No hace commit."""
    nit, dv = datos.nit.split("-")
    empresa = Empresa(razon_social=datos.razon_social, nit=nit, dv=dv, correo=datos.correo, telefono=datos.telefono,
                      direccion=datos.direccion, representante=datos.representante, estado=estado)
    db.add(empresa)
    db.flush()  # para obtener el id; todavía no queda guardada
    _crear_usuario(db, "empresa", datos.contrasena, nombre=datos.representante, correo=datos.correo, empresa_id=empresa.id,
                   creado_por=creado_por, actualizado_por=creado_por)
    return empresa


def _crear_usuario(db: Session, rol_nombre: str, contrasena: str, **campos) -> Usuario:
    """Agrega el usuario con su rol y una copia de la plantilla de permisos. No hace commit."""
    rol = rol_por_nombre(db, rol_nombre)
    if not rol.estado:
        raise errors.rol_inactivo(rol_nombre)  # el admin lo desactivó: por ejemplo, para cerrar el registro
    usuario = Usuario(**campos, contrasena=hash_password(contrasena), rol_id=rol.id)  # nunca en texto plano
    usuario.permisos = list(rol.permisos)
    db.add(usuario)
    db.flush()  # para obtener el id antes del commit
    return usuario


def _registrar_cliente(datos: RegistroCliente, db: Session) -> RegistroClienteOut:
    usuario = _crear_usuario(
        db, "cliente", datos.contrasena, nombre=datos.nombre, correo=datos.correo, tipo_documento=datos.tipo_documento,
        numero_documento=datos.numero_documento, telefono=datos.telefono)
    return RegistroClienteOut(
        message="Cuenta creada",
        user=UsuarioRegistrado(id=usuario.id, nombre=usuario.nombre, correo=usuario.correo, rol="cliente"))


def _registrar_empresa(datos: RegistroEmpresa, db: Session) -> RegistroEmpresaOut:
    empresa = crear_empresa(db, datos, "pendiente")
    return RegistroEmpresaOut(
        message="Registro recibido. Un administrador debe aprobar la empresa",
        estado=empresa.estado,
        empresa=EmpresaRegistrada(id=empresa.id, razon_social=empresa.razon_social, nit=datos.nit, estado=empresa.estado))
