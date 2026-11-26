# Consultas a la base de datos del módulo Clientes
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario


def buscar(db: Session, q: str, page: int, limit: int) -> tuple[int, list[Usuario]]:
    """Devuelve (total que cumple la búsqueda, clientes activos de la página), ordenados por nombre.
    Los clientes no pertenecen a ninguna empresa, así que no se filtra por empresa. Filtrar por el rol es lo que
    impide que salgan los usuarios (bodegueros, empresa, admin) de una empresa."""
    # autoescape: "%" y "_" se buscan tal cual. Si no, "%%%%%" traería a todos y el mínimo de caracteres no serviría
    coincide = or_(*(campo.icontains(q, autoescape=True) for campo in (Usuario.nombre, Usuario.numero_documento, Usuario.correo)))
    query = db.query(Usuario).join(Usuario.rol).filter(Rol.nombre == "cliente", Usuario.estado.is_(True), coincide)

    total = query.count()  # total que cumple la búsqueda, antes de paginar
    clientes = query.order_by(Usuario.nombre, Usuario.id).offset((page - 1) * limit).limit(limit).all()
    return total, clientes
