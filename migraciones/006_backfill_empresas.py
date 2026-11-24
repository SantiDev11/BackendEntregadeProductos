# Migración 006: asigna una empresa a los datos que existían antes de ser multiempresa (backfill).
# Requiere haber corrido antes 005_empresas.sql.
#
#   python migraciones/006_backfill_empresas.py                          solo MUESTRA qué haría (no guarda nada)
#   python migraciones/006_backfill_empresas.py --aplicar                lo hace, con la empresa por defecto
#   python migraciones/006_backfill_empresas.py --empresa-id 3 --aplicar lo hace, con una empresa que ya existe
#
# Empresa por defecto: la del emisor (app/modulos/facturas/emisor.py), porque las facturas viejas ya salieron a su nombre.
#
# Reglas (solo toca registros con empresa_id NULL, así que se puede repetir sin problema):
#   usuarios -> solo los bodegueros. Admin, clientes y otros roles no pertenecen a ninguna empresa.
#   bodegas  -> la empresa de su bodeguero; si no tiene bodeguero (o él no tiene empresa), la elegida.
#   tipos    -> la empresa de su bodega. Los tipos generales (sin bodega) quedan sin empresa.
#   ordenes  -> la empresa de su bodega. No cambia el emisor, el número ni ningún otro dato de la factura.
# Se usa SQL directo para no alterar la fecha actualizado_en de los registros.
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # carpeta del proyecto

from sqlalchemy import text

from app.config.database import SessionLocal
from app.modulos.facturas.emisor import EMISOR

PASOS = [
    ("usuarios (bodegueros)", """
        UPDATE usuarios u JOIN roles r ON r.id = u.rol_id
        SET u.empresa_id = :empresa WHERE u.empresa_id IS NULL AND r.nombre = 'bodeguero'"""),
    ("bodegas", """
        UPDATE bodegas b LEFT JOIN usuarios u ON u.id = b.bodeguero_id
        SET b.empresa_id = COALESCE(u.empresa_id, :empresa) WHERE b.empresa_id IS NULL"""),
    ("tipos", """
        UPDATE tipos t JOIN bodegas b ON b.id = t.bodega_id
        SET t.empresa_id = b.empresa_id WHERE t.empresa_id IS NULL AND b.empresa_id IS NOT NULL"""),
    ("ordenes (facturas)", """
        UPDATE ordenes o JOIN bodegas b ON b.id = o.bodega_id
        SET o.empresa_id = b.empresa_id WHERE o.empresa_id IS NULL AND b.empresa_id IS NOT NULL"""),
]

# Todo debe dar 0: si no, hay datos cruzados entre empresas
REVISIONES = [
    ("bodegas de una empresa distinta a la de su bodeguero", """
        SELECT COUNT(*) FROM bodegas b JOIN usuarios u ON u.id = b.bodeguero_id JOIN roles r ON r.id = u.rol_id
        WHERE r.nombre = 'bodeguero' AND NOT (b.empresa_id <=> u.empresa_id)"""),
    ("tipos de una empresa distinta a la de su bodega", """
        SELECT COUNT(*) FROM tipos t JOIN bodegas b ON b.id = t.bodega_id WHERE NOT (t.empresa_id <=> b.empresa_id)"""),
    ("facturas de una empresa distinta a la de su bodega", """
        SELECT COUNT(*) FROM ordenes o JOIN bodegas b ON b.id = o.bodega_id WHERE NOT (o.empresa_id <=> b.empresa_id)"""),
]


def obtener_empresa(db, empresa_id: int | None, crear: bool) -> int:
    """Id de la empresa a usar: la indicada, o la del emisor. Si la del emisor no existe la crea activa;
    con crear=False (simulación) no inserta nada, para no gastar un id, y devuelve 0 como marcador."""
    if empresa_id is not None:
        if db.execute(text("SELECT id FROM empresas WHERE id = :id"), {"id": empresa_id}).scalar() is None:
            raise SystemExit(f"No existe la empresa con id {empresa_id}")
        return empresa_id

    existente = db.execute(text("SELECT id FROM empresas WHERE nit = :nit"), {"nit": EMISOR["nit"]}).scalar()
    if existente is not None:
        return existente
    if not crear:
        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))  # solo esta conexión: permite simular con el marcador 0
        return 0
    db.execute(text("""
        INSERT INTO empresas (razon_social, nit, dv, correo, telefono, direccion, estado)
        VALUES (:razon_social, :nit, :dv, :correo, :telefono, :direccion, 'activa')"""),
        {campo: EMISOR[campo] for campo in ("razon_social", "nit", "dv", "correo", "telefono", "direccion")})
    return db.execute(text("SELECT LAST_INSERT_ID()")).scalar()


def rellenar(db, empresa_id: int | None = None, crear: bool = True) -> dict[str, int]:
    """Asigna las empresas y devuelve cuántos registros cambió en cada tabla. No hace commit."""
    empresa = obtener_empresa(db, empresa_id, crear)
    return {nombre: db.execute(text(sql), {"empresa": empresa}).rowcount for nombre, sql in PASOS}


def revisar(db) -> dict[str, int]:
    """Cuántos registros quedan cruzados entre empresas, por cada revisión."""
    return {nombre: db.execute(text(sql)).scalar() for nombre, sql in REVISIONES}


def main():
    opciones = argparse.ArgumentParser(description="Asigna empresa a los datos existentes")
    opciones.add_argument("--aplicar", action="store_true", help="guarda los cambios (sin esto solo los muestra)")
    opciones.add_argument("--empresa-id", type=int, help="usar esta empresa en vez de la del emisor")
    args = opciones.parse_args()

    db = SessionLocal()
    try:
        cambios = rellenar(db, args.empresa_id, crear=args.aplicar)
        for nombre, cantidad in cambios.items():
            print(f"{nombre:24s} {cantidad} registro(s)")
        generales = db.execute(text("SELECT COUNT(*) FROM tipos WHERE bodega_id IS NULL")).scalar()
        print(f"tipos sin bodega que quedan sin empresa: {generales}")

        cruzados = {nombre: n for nombre, n in revisar(db).items() if n}
        for nombre, n in cruzados.items():
            print(f"[ATENCIÓN] {n} {nombre}")

        if args.aplicar and not cruzados:
            db.commit()
            print("Backfill aplicado.")
        else:
            db.rollback()
            print("No se guardó nada: hay datos cruzados." if cruzados else "Simulación: no se guardó nada (use --aplicar).")
            if cruzados:
                sys.exit(1)
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        db.close()


if __name__ == "__main__":
    main()
