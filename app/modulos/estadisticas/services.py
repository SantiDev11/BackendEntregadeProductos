# Lógica del endpoint de Estadísticas. El router solo recibe la petición y llama a esta función.
# Cada rol recibe solo las tarjetas y series que puede ver: lo que no puede ver, no se manda.
from datetime import date

from sqlalchemy.orm import Session

from app.modulos.estadisticas import queries
from app.modulos.estadisticas.helpers import periodo, puntos_por_estado, puntos_por_fecha, serie, tarjeta
from app.modulos.estadisticas.schemas import PeriodoOut, ResumenOut
from app.modulos.facturas.helpers import alcance_facturas
from app.modulos.usuarios.models import Usuario


def resumen(db: Session, usuario: Usuario, desde: date | None, hasta: date | None) -> ResumenOut:
    """Panel según el rol, con la misma regla de dueño de GET /facturas:
    admin todas, cliente las suyas, los demás (bodeguero) solo las que crearon."""
    desde, hasta = periodo(desde, hasta)
    alcance = alcance_facturas(usuario)  # "todas", "cliente" o "creadas"
    condiciones = queries.condiciones_facturas(alcance, usuario.id, desde, hasta)

    por_estado = queries.conteo_por_estado(db, condiciones)
    total = sum(por_estado.values())
    facturado = queries.total_facturado(db, condiciones)
    pendientes = por_estado.get("entregada", 0)  # entregadas que el cliente aún no firma ni rechaza
    rechazadas = por_estado.get("rechazada", 0)
    por_fecha = serie("por_fecha", "Facturas en el periodo", "linea",
                      puntos_por_fecha(queries.facturas_por_dia(db, condiciones), desde, hasta))

    if alcance == "cliente":
        tarjetas = [
            tarjeta("facturas", "Mis facturas", total),
            tarjeta("facturado", "Total de mis facturas", facturado, "$"),
            tarjeta("pendientes", "Por firmar", pendientes),
            tarjeta("rechazadas", "Rechazadas", rechazadas),
        ]
        series = [
            serie("por_estado", "Mis facturas por estado", "barras", puntos_por_estado(por_estado, incluir_emitida=False)),
            por_fecha,
        ]
    else:
        tarjetas = [
            tarjeta("facturas", "Facturas", total),
            tarjeta("facturado", "Facturado", facturado, "$"),
            tarjeta("pendientes", "Pendientes de firma", pendientes),
            tarjeta("rechazadas", "Rechazadas", rechazadas),
        ]
        if alcance == "todas":
            tarjetas += [
                tarjeta("usuarios_activos", "Usuarios activos", queries.usuarios_activos(db)),
                tarjeta("bodegas_activas", "Bodegas activas", queries.bodegas_activas(db)),
            ]
        else:
            mis_bodegas = queries.bodegas_del_usuario(db, usuario.id)
            tarjetas += [
                tarjeta("bodegas", "Mis bodegas", len(mis_bodegas)),
                tarjeta("tipos", "Tipos en mis bodegas", queries.tipos_en_bodegas(db, mis_bodegas)),
            ]
        series = [
            serie("por_estado", "Facturas por estado", "barras", puntos_por_estado(por_estado)),
            por_fecha,
            serie("por_bodega", "Facturado por bodega", "barras", queries.facturado_por_bodega(db, condiciones)),
            serie("top_productos", "Productos más vendidos", "barras", queries.productos_mas_vendidos(db, condiciones)),
        ]

    return ResumenOut(
        periodo=PeriodoOut(desde=desde, hasta=hasta),
        generado_para=usuario.rol.nombre,
        tarjetas=tarjetas,
        series=series,
    )
