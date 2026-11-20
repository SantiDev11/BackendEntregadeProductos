# Migración 004: permiso nuevo `estadisticas_view` (módulo Estadísticas).
# Se corre UNA sola vez:
#   python migraciones/004_permiso_estadisticas.py
#
# 1) Crea el permiso `estadisticas_view` en la tabla permisos (si no existe).
# 2) Lo agrega a la plantilla de los roles admin, bodeguero y cliente.
# 3) Se lo da a los usuarios que ya existen de esos roles. Solo agrega ESTE permiso:
#    no les devuelve otros permisos que el admin les haya quitado a propósito.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # carpeta del proyecto

from app.config.database import SessionLocal
from app.config.seed import aplicar_plantillas, crear_catalogo
from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario

PERMISO = "estadisticas_view"


def main():
    db = SessionLocal()
    try:
        roles = {r.nombre: r for r in db.query(Rol).all()}
        permisos = crear_catalogo(db)
        aplicar_plantillas(db, roles, permisos)

        nuevo = permisos[PERMISO]
        for usuario in db.query(Usuario).all():
            if nuevo in usuario.rol.permisos and nuevo not in usuario.permisos:
                usuario.permisos.append(nuevo)
                print(f"[usuario]    {usuario.correo} ({usuario.rol.nombre}): + {PERMISO}")

        db.commit()
        print("Migración 004 terminada.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
