# Migración 002: catálogo de 29 permisos, plantillas por rol y permisos para los usuarios que ya existen.
# Se corre UNA sola vez, antes de usar los guards por permiso:
#   python migraciones/002_permisos_catalogo_y_usuarios.py
#
# 1) Renombra 'ususarios' -> 'usuarios_view' (conserva el id y sus asignaciones).
# 2) Crea los permisos del catálogo que falten (app/core/permisos.py).
# 3) Completa la plantilla de cada rol.
# 4) A cada usuario existente le AGREGA los permisos de la plantilla de su rol (no le quita ninguno),
#    para que nadie pierda acceso al pasar de guards por rol a guards por permiso.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # carpeta del proyecto

from app.database import SessionLocal
from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario
from app.seed import aplicar_plantillas, crear_catalogo, renombrar_permisos


def main():
    db = SessionLocal()
    try:
        roles = {r.nombre: r for r in db.query(Rol).all()}
        renombrar_permisos(db)
        permisos = crear_catalogo(db)
        aplicar_plantillas(db, roles, permisos)

        for usuario in db.query(Usuario).all():
            faltantes = [p for p in usuario.rol.permisos if p not in usuario.permisos]
            usuario.permisos.extend(faltantes)
            print(f"[usuario]    {usuario.correo} ({usuario.rol.nombre}): +{len(faltantes)} -> {len(usuario.permisos)} permisos")

        db.commit()
        print("Migración 002 terminada.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
