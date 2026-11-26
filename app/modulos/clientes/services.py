# Lógica de cada endpoint de Clientes. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.modulos.clientes import queries
from app.modulos.clientes.schemas import ClienteOpcion, ClientePaginado


def buscar_clientes(q: str, page: int, limit: int, db: Session) -> ClientePaginado:
    """Clientes activos (datos mínimos) que coinciden con la búsqueda."""
    total, clientes = queries.buscar(db, q=q, page=page, limit=limit)
    return ClientePaginado(
        data=[ClienteOpcion.model_validate(c) for c in clientes],
        total=total, page=page, limit=limit,
    )
