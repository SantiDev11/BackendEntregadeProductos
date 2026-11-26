# Migración 009: las facturas de una empresa que se emitieron con el emisor demo (antes de que el emisor fuera la empresa)
# pasan a tener como emisor los datos de su empresa, y se les recalcula el CUFE (que incluye el NIT del emisor).
#
#   python migraciones/009_emisor_por_empresa.py             solo MUESTRA qué haría (no guarda nada)
#   python migraciones/009_emisor_por_empresa.py --aplicar   lo hace
#
# Reglas (se puede repetir sin problema: lo ya corregido no vuelve a cambiar):
#   - Solo toca facturas con empresa cuyo emisor guardado es exactamente el demo (app/modulos/facturas/emisor.py).
#   - Las facturas sin empresa siguen con el emisor por defecto.
#   - Conserva la resolución que se copió al emitirla, el número, los totales y todo lo demás.
#   - No cambia la fecha actualizado_en.
import argparse
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # carpeta del proyecto

from sqlalchemy import text

from app.config.database import SessionLocal
from app.modulos.empresas.models import Empresa
from app.modulos.facturas.emisor import EMISOR
from app.modulos.facturas.helpers import datos_emisor, generar_cufe
from app.modulos.facturas.models import Orden


def pendientes(db) -> list[Orden]:
    """Facturas de una empresa que todavía tienen el emisor demo: TODOS sus datos iguales a los de emisor.py
    (no basta el NIT: una empresa real podría tener ese mismo NIT)."""
    def es_demo(emisor: dict | None) -> bool:
        return {k: v for k, v in (emisor or {}).items() if k != "resolucion"} == EMISOR
    return [o for o in db.query(Orden).filter(Orden.empresa_id.isnot(None)).order_by(Orden.id) if es_demo(o.emisor_datos)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Pone como emisor de cada factura a su empresa.")
    parser.add_argument("--aplicar", action="store_true", help="guarda los cambios (sin esto solo los muestra)")
    aplicar = parser.parse_args().aplicar

    with SessionLocal() as db:
        print(f"Base: {db.get_bind().url.database}")
        facturas = pendientes(db)
        print(f"Facturas con empresa y emisor demo: {len(facturas)}")
        for o in facturas:
            empresa = db.get(Empresa, o.empresa_id)
            nuevo = {**datos_emisor(empresa), "resolucion": o.emisor_datos.get("resolucion") or datos_emisor(empresa)["resolucion"]}
            # el CUFE se calcula sobre una copia: la factura del ORM no se toca (no cambia actualizado_en)
            copia = SimpleNamespace(numero=o.numero, fecha_emision=o.fecha_emision, subtotal=o.subtotal, impuesto_total=o.impuesto_total,
                                    total=o.total, emisor_datos=nuevo, adquiriente_datos=o.adquiriente_datos)
            cufe = generar_cufe(copia) if o.cufe else None
            print(f"  {o.numero} (id {o.id}, {o.estado_orden}): {EMISOR['razon_social']} -> {empresa.razon_social} "
                  f"(NIT {empresa.nit_completo})")
            if aplicar:
                db.execute(text("UPDATE ordenes SET emisor_datos = :emisor, cufe = :cufe, actualizado_en = actualizado_en WHERE id = :id"),
                           {"emisor": json.dumps(nuevo, ensure_ascii=False), "cufe": cufe, "id": o.id})
        if aplicar:
            db.commit()
            quedan = len(pendientes(db))
            print(f"Listo. Quedan con emisor demo: {quedan}")
        else:
            db.rollback()
            print("Simulación: no se guardó nada. Para aplicarlo: --aplicar")


if __name__ == "__main__":
    main()
