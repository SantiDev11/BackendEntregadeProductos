# Datos iniciales para pruebas. Se ejecuta a mano con: python -m app.config.seed
# Es idempotente: si se corre varias veces no duplica nada.
from app.config.database import Base, SessionLocal, engine
from app.modulos.permisos.models import Permiso
from app.modulos.roles.models import Rol
from app.modulos.usuarios.models import Usuario
from app.core.permisos import CATALOGO, PLANTILLAS, RENOMBRADOS
from app.core.security import hash_password

# Roles iniciales (provisionales) con su descripción
ROLES = [
    ("admin", "Administra usuarios, roles y toda la aplicación"),
    ("bodeguero", "Gestiona bodegas, productos y entregas"),
    ("cliente", "Consulta y recibe sus entregas"),
    ("empresa", "Gestiona los bodegueros, bodegas, productos y facturas de su empresa"),
]

# Usuarios de prueba
ADMIN = {
    "nombre": "Administrador",
    "correo": "admin@entrega.com",
    "contrasena": "Admin123*",
}

BODEGUERO = {
    "nombre": "Bodeguero Prueba",
    "correo": "bodeguero@entrega.com",
    "contrasena": "Bodega123*",
}

# Cliente de prueba, con sus datos para facturar
CLIENTE = {
    "nombre": "Cliente Prueba",
    "correo": "cliente@entrega.com",
    "contrasena": "Cliente123*",
    "tipo_documento": "CC",
    "numero_documento": "1020304050",
    "telefono": "3001234567",
    "direccion": "Calle 10 # 20-30",
    "ciudad": "Bogotá",
}


def crear_roles(db):
    """Crea los roles que no existan y devuelve un dict nombre -> Rol."""
    roles = {}
    for nombre, descripcion in ROLES:
        rol = db.query(Rol).filter(Rol.nombre == nombre).first()
        if rol:
            print(f"[ya existía] rol '{nombre}'")
        else:
            rol = Rol(nombre=nombre, descripcion=descripcion)
            db.add(rol)
            db.flush()  # para obtener el id antes del commit
            print(f"[creado]     rol '{nombre}'")
        roles[nombre] = rol
    return roles


def renombrar_permisos(db):
    """Renombra permisos viejos (por ejemplo 'ususarios' -> 'usuarios_view') sin perder sus asignaciones."""
    for viejo, nuevo in RENOMBRADOS.items():
        permiso = db.query(Permiso).filter(Permiso.nombre == viejo).first()
        if permiso and not db.query(Permiso).filter(Permiso.nombre == nuevo).first():
            permiso.nombre = nuevo
            db.flush()
            print(f"[renombrado] permiso '{viejo}' -> '{nuevo}'")


def crear_catalogo(db):
    """Crea los permisos del catálogo que no existan y devuelve un dict nombre -> Permiso."""
    permisos = {}
    for nombre, descripcion in CATALOGO:
        permiso = db.query(Permiso).filter(Permiso.nombre == nombre).first()
        if permiso:
            print(f"[ya existía] permiso '{nombre}'")
        else:
            permiso = Permiso(nombre=nombre, descripcion=descripcion, estado=True)
            db.add(permiso)
            db.flush()
            print(f"[creado]     permiso '{nombre}'")
        permisos[nombre] = permiso
    return permisos


def aplicar_plantillas(db, roles, permisos):
    """Agrega a la plantilla de cada rol los permisos que le falten (no quita los que ya tenga)."""
    for nombre_rol, nombres in PLANTILLAS.items():
        if nombre_rol not in roles:
            continue  # migraciones viejas (002 y 004) sobre una base que aún no tiene ese rol
        rol = roles[nombre_rol]
        faltantes = [permisos[n] for n in nombres if permisos[n] not in rol.permisos]
        rol.permisos.extend(faltantes)
        estado = f"[+{len(faltantes)}]" if faltantes else "[ya existía]"
        print(f"{estado:12s} plantilla del rol '{nombre_rol}' ({len(rol.permisos)} permisos)")
    db.flush()


def crear_usuario(db, datos, rol):
    """Crea un usuario de prueba con el rol indicado si no existe (busca por correo)."""
    usuario = db.query(Usuario).filter(Usuario.correo == datos["correo"]).first()
    if usuario:
        print(f"[ya existía] usuario '{datos['correo']}'")
        return
    documento = datos.get("numero_documento")
    if documento and db.query(Usuario).filter(Usuario.numero_documento == documento).first():
        print(f"[omitido]    usuario '{datos['correo']}': otro usuario ya tiene el documento {documento}")
        return
    # Campos adicionales del dict (por ejemplo, los datos para facturar del cliente)
    extras = {k: v for k, v in datos.items() if k not in ("nombre", "correo", "contrasena")}
    usuario = Usuario(
        nombre=datos["nombre"],
        correo=datos["correo"],
        contrasena=hash_password(datos["contrasena"]),
        rol_id=rol.id,
        **extras,
    )
    usuario.permisos = list(rol.permisos)  # el rol es la plantilla: se copian sus permisos actuales
    db.add(usuario)
    print(f"[creado]     usuario '{datos['correo']}' con rol {rol.nombre}")


def main():
    # Crea las tablas si aún no existen (por si no se ha arrancado la API)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        roles = crear_roles(db)
        renombrar_permisos(db)
        permisos = crear_catalogo(db)
        aplicar_plantillas(db, roles, permisos)  # antes de crear usuarios: así heredan la plantilla
        crear_usuario(db, ADMIN, roles["admin"])
        crear_usuario(db, BODEGUERO, roles["bodeguero"])
        crear_usuario(db, CLIENTE, roles["cliente"])
        db.commit()
        print("Seed terminado.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
