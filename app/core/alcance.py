# Alcance por empresa: qué registros puede ver y modificar cada usuario. Es la ÚNICA implementación de la regla;
# los módulos la usan en sus listados (condiciones) y en sus endpoints por id (incluye).
#
#   admin                -> todo; en los listados puede filtrar con ?empresa_id=
#   empresa              -> solo lo de su empresa (si no tiene empresa asignada, nada)
#   los demás            -> solo lo de su empresa, o lo que no tiene empresa si ellos tampoco tienen
#                           (datos anteriores a las empresas). Además cada módulo aplica su regla de dueño.
# La empresa SIEMPRE sale del usuario del token: a quien no es admin se le ignora ?empresa_id= y el empresa_id del body.
# Al crear, el admin (que no tiene empresa) la indica en el body y es obligatoria.
from dataclasses import dataclass

from fastapi import Depends, Query
from sqlalchemy import false
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import error_403
from app.modulos.empresas.helpers import validate_empresa_id
from app.modulos.usuarios.models import Usuario


@dataclass(frozen=True)
class Alcance:
    usuario: Usuario
    empresa_id: int | None
    todo: bool = False  # True = sin filtro de empresa (solo admin)

    @property
    def es_admin(self) -> bool:
        return self.usuario.rol.nombre == "admin"

    @property
    def es_empresa(self) -> bool:
        return self.usuario.rol.nombre == "empresa"

    @property
    def ve_toda_la_empresa(self) -> bool:
        """Admin y empresa ven todo lo de la empresa; los demás, además, solo lo que es suyo (dueño o creador)."""
        return self.es_admin or self.es_empresa

    @property
    def solo_bodegueros(self) -> bool:
        """Quien pertenece a una empresa solo puede gestionar usuarios bodegueros de esa empresa."""
        return not self.es_admin and (self.es_empresa or self.usuario.empresa_id is not None)

    def condiciones(self, columna) -> list:
        """Condiciones SQL para un listado: query.filter(*alcance.condiciones(Bodega.empresa_id))."""
        if self.todo:
            return []
        if self.empresa_id is None:
            return [false() if self.es_empresa else columna.is_(None)]
        return [columna == self.empresa_id]

    def incluye(self, registro) -> bool:
        """La misma regla sobre un registro ya cargado (cualquiera con empresa_id)."""
        if self.todo:
            return True
        if self.empresa_id is None and self.es_empresa:
            return False
        return registro.empresa_id == self.empresa_id

    def empresa_para_crear(self, db: Session, empresa_id_body) -> int | None:
        """Empresa con la que nace lo que crea el usuario: el admin la indica en el body (422 si falta o no existe, 400 si no está activa);
        para los demás es la del token y el body se ignora."""
        if self.es_admin:
            return validate_empresa_id(db, empresa_id_body)
        if self.es_empresa and self.usuario.empresa_id is None:
            raise error_403("No tiene permiso para esta acción")
        return self.usuario.empresa_id


def alcance_de(usuario: Usuario, empresa_id: int | None = None) -> Alcance:
    """Alcance de un usuario. `empresa_id` solo cuenta si es admin."""
    if usuario.rol.nombre == "admin":
        return Alcance(usuario, empresa_id, todo=empresa_id is None)
    return Alcance(usuario, usuario.empresa_id)


def filtro_empresa(
    empresa_id: int | None = Query(None, description="**Solo admin:** filtra por empresa. Si no se envía, trae todo. "
                                                     "A los demás se les ignora: su empresa sale del token."),
    usuario: Usuario = Depends(get_current_user),
) -> Alcance:
    """Dependencia de los listados: el alcance del usuario, con el ?empresa_id= del admin."""
    return alcance_de(usuario, empresa_id)
