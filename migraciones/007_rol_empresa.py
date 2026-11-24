# Migración 007: rol `empresa` con su plantilla de permisos (app/core/permisos.py).
#   python migraciones/007_rol_empresa.py
#
# Se puede correr las veces que sea: si el rol ya existe no lo duplica y solo agrega los permisos que le falten.
# No toca los demás roles ni los permisos de ningún usuario. El id lo pone la base (el front lo busca por nombre).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # carpeta del proyecto

from sqlalchemy import func

from app.config.database import SessionLocal
from app.config.seed import ROLES
from app.core.permisos import PLANTILLAS
from app.modulos import Permiso, Rol

NOMBRE = "empresa"


def crear_rol_empresa(db) -> Rol:
    """Crea el rol si no existe y le completa la plantilla. No hace commit."""
    nombres = PLANTILLAS[NOMBRE]
    permisos = {p.nombre: p for p in db.query(Permiso).filter(Permiso.nombre.in_(nombres)).all()}
    faltan = sorted(set(nombres) - set(permisos))
    if faltan:
        raise SystemExit(f"Faltan permisos en la base, corra antes las migraciones 002 y 004: {', '.join(faltan)}")

    rol = db.query(Rol).filter(func.lower(Rol.nombre) == NOMBRE).first()
    if rol is None:
        rol = Rol(nombre=NOMBRE, descripcion=dict(ROLES)[NOMBRE])
        db.add(rol)
        print(f"[creado]     rol '{NOMBRE}'")
    else:
        rol.nombre = NOMBRE  # por si existía con mayúsculas: el código lo compara en minúsculas
        print(f"[ya existía] rol '{NOMBRE}'")

    nuevos = [permisos[n] for n in nombres if permisos[n] not in rol.permisos]
    rol.permisos.extend(nuevos)
    print(f"[permisos]   +{len(nuevos)} -> {len(rol.permisos)} en la plantilla")

    extras = sorted(p.nombre for p in rol.permisos if p.nombre not in nombres)
    if extras:
        print(f"[ATENCIÓN]   el rol ya tenía permisos que no son de la plantilla (no se quitan): {', '.join(extras)}")
    db.flush()
    return rol


def main():
    db = SessionLocal()
    try:
        rol = crear_rol_empresa(db)
        db.commit()
        print(f"Migración 007 terminada (id del rol: {rol.id}).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
