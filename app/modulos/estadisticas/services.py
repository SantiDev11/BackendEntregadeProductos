# Lógica del endpoint de Estadísticas. El router solo recibe la petición y llama a resumen().
# Un panel por rol, todos con la misma forma. Los cálculos se hacen en MySQL (ver queries.py).
from datetime import date

from sqlalchemy.orm import Session

from app.core.alcance import Alcance, alcance_de
from app.modulos.estadisticas import queries
from app.modulos.estadisticas.helpers import (Filtros, alertas, efectividad, filtros_validos, kpi, perfil_de, periodo_pedido,
                                              porcentaje, puntos_por_estado, puntos_por_fecha, serie, serie_temporal, tarjeta)
from app.modulos.estadisticas.schemas import DesgloseOut, FiltrosDisponiblesOut, KpiOut, OpcionOut, PeriodoOut, ResumenOut
from app.modulos.facturas.helpers import es_cliente
from app.modulos.usuarios.models import Usuario

ALERTA_RECHAZO = 10  # % de rechazo a partir del cual (sin incluirlo) se alerta a la empresa


def resumen(db: Session, usuario: Usuario, fecha_inicio: date | None, fecha_fin: date | None, desde: date | None,
            hasta: date | None, pedidos: Filtros) -> ResumenOut:
    """Panel según el rol, con la misma regla de dueño de GET /facturas (así los números cuadran con su listado):
    admin todas (o las de una empresa), empresa las suyas, cliente las suyas, los demás (bodeguero) solo las que crearon."""
    inicio, fin = periodo_pedido(fecha_inicio, fecha_fin, desde, hasta)
    alcance = alcance_de(usuario, pedidos.empresa_id)  # empresa_id solo cuenta aquí si es admin
    perfil = perfil_de(alcance)
    filtros = filtros_validos(db, alcance, perfil, pedidos)
    condiciones = queries.condiciones_panel(alcance, perfil, filtros, inicio, fin)
    kpis, desglose, opciones = PANELES[perfil](db, alcance, condiciones, filtros)

    return ResumenOut(
        generado_para=usuario.rol.nombre,
        periodo=PeriodoOut(fecha_inicio=inicio, fecha_fin=fin, desde=inicio, hasta=fin),
        filtros_disponibles=opciones,
        kpis=kpis,
        desglose_principal=desglose,
        serie_temporal=serie_temporal(queries.por_dia(db, condiciones), inicio, fin),
        alertas_detalle=alertas(queries.ultimas_rechazadas(db, condiciones)) if perfil in ("empresa", "bodeguero") else [],
        **formato_anterior(db, alcance, inicio, fin),
    )


# ===== UN PANEL POR ROL: (kpis, desglose_principal, filtros_disponibles) =====

Panel = tuple[list[KpiOut], DesgloseOut, FiltrosDisponiblesOut]


def _opciones(filas) -> list[OpcionOut]:
    return [OpcionOut(id=i, nombre=nombre) for i, nombre in filas]


def _conteo(db: Session, condiciones: list) -> tuple[dict[str, int], int, int, int]:
    """(por estado, total, completadas, rechazadas) de las facturas del panel."""
    estados = queries.conteo_por_estado(db, condiciones)
    completadas = sum(estados.get(e, 0) for e in queries.COMPLETADAS)
    return estados, sum(estados.values()), completadas, estados.get("rechazada", 0)


def _panel_admin(db: Session, alcance: Alcance, condiciones: list, f: Filtros) -> Panel:
    _, total, completadas, _ = _conteo(db, condiciones)
    empresas = queries.empresas_por_estado(db)  # las tarjetas de la plataforma no dependen de los filtros
    pendientes = empresas.get("pendiente", 0)
    kpis = [
        kpi("empresas_activas", "Empresas activas", empresas.get("activa", 0)),
        kpi("empresas_pendientes", "Solicitudes pendientes", pendientes, alerta=pendientes > 0),
        kpi("clientes_globales", "Clientes registrados", queries.clientes_registrados(db)),
        kpi("tasa_entrega_global", "Tasa de entrega", porcentaje(completadas, total), formato="porcentaje"),
    ]
    desglose = DesgloseOut(
        titulo="Top Empresas por Volumen", columnas=["Empresa", "Bodegas", "Facturas", "Rechazadas", "Efectividad"],
        filas=[{"nombre": nombre, "bodegas": bodegas, "facturas": n, "rechazadas": int(r), "efectividad": efectividad(int(c), n)}
               for nombre, bodegas, n, c, r in queries.por_empresa(db, alcance, condiciones, f.estado)])
    return kpis, desglose, FiltrosDisponiblesOut(empresas=_opciones(queries.opciones_empresas(db)))


def _panel_empresa(db: Session, alcance: Alcance, condiciones: list, f: Filtros) -> Panel:
    estados, total, completadas, rechazadas = _conteo(db, condiciones)
    pendientes = sum(estados.get(e, 0) for e in queries.PENDIENTES)
    tasa_rechazo = porcentaje(rechazadas, total)
    kpis = [
        kpi("total_facturas", "Facturas del periodo", total),
        kpi("pendientes_cierre", "Pendientes de firma", pendientes, alerta=pendientes > 0),
        kpi("tasa_aceptacion", "Tasa de aceptación", porcentaje(completadas, total), formato="porcentaje"),
        kpi("tasa_rechazo", "Tasa de rechazo", tasa_rechazo, alerta=tasa_rechazo > ALERTA_RECHAZO, formato="porcentaje"),
    ]
    desglose = DesgloseOut(
        titulo="Rendimiento por Bodega", columnas=["Bodega", "Emitidas", "Completadas", "Rechazadas", "Efectividad"],
        filas=[{"nombre": nombre, "emitidas": n, "completadas": int(c), "rechazadas": int(r), "efectividad": efectividad(int(c), n)}
               for nombre, n, c, r in queries.por_bodega(db, alcance, condiciones, f.bodega_id)])
    opciones = FiltrosDisponiblesOut(
        bodegas=_opciones(queries.opciones_bodegas(db, alcance)),
        bodegueros=_opciones(queries.opciones_bodegueros(db, alcance)),
        tipos=_opciones(queries.opciones_tipos(db, queries.bodegas_del_usuario(db, alcance))))
    return kpis, desglose, opciones


def _panel_bodeguero(db: Session, alcance: Alcance, condiciones: list, f: Filtros) -> Panel:
    estados, _, completadas, rechazadas = _conteo(db, condiciones)
    kpis = [
        kpi("por_despachar", "Por despachar", estados.get("emitida", 0)),
        kpi("sin_firma", "Esperando firma", estados.get("entregada", 0)),
        kpi("completadas", "Completadas", completadas),
        kpi("rechazadas", "Rechazadas", rechazadas),
    ]
    desglose = DesgloseOut(
        titulo="Actividad por Tipo de Producto", columnas=["Tipo Producto", "Emitidas", "Completadas", "Rechazadas"],
        filas=[{"nombre": nombre, "emitidas": n, "completadas": c, "rechazadas": r}
               for nombre, n, c, r in queries.por_tipo(db, condiciones, f.tipo_id)])
    opciones = FiltrosDisponiblesOut(tipos=_opciones(queries.opciones_tipos(db, queries.bodegas_del_usuario(db, alcance))))
    return kpis, desglose, opciones


def _panel_cliente(db: Session, alcance: Alcance, condiciones: list, f: Filtros) -> Panel:
    estados, _, completadas, rechazadas = _conteo(db, condiciones)
    kpis = [
        # El cliente no ve los borradores (emitida), así que son las entregadas
        kpi("pendientes_accion", "Por firmar", sum(estados.get(e, 0) for e in queries.PENDIENTES)),
        kpi("recibidas_total", "Aceptadas", completadas),
        kpi("rechazadas_total", "Rechazadas", rechazadas),
        kpi("empresas_proveedoras", "Empresas proveedoras", queries.empresas_proveedoras(db, condiciones)),
    ]
    desglose = DesgloseOut(
        titulo="Resumen por Empresa Proveedora", columnas=["Empresa", "Total Facturas", "Aceptadas", "Rechazadas"],
        filas=[{"nombre": nombre, "total_facturas": n, "aceptadas": int(a), "rechazadas": int(r)}
               for nombre, n, a, r in queries.por_proveedora(db, condiciones)])
    return kpis, desglose, FiltrosDisponiblesOut(empresas=_opciones(queries.opciones_proveedoras(db, alcance)))


PANELES = {"admin": _panel_admin, "empresa": _panel_empresa, "bodeguero": _panel_bodeguero, "cliente": _panel_cliente}


# ===== FORMATO ANTERIOR =====
# DEPRECATED: tarjetas y series. Se retira cuando el frontend confirme que usa el nuevo (con los parámetros desde y hasta).
# No le aplican los filtros nuevos.

def formato_anterior(db: Session, alcance: Alcance, desde: date, hasta: date) -> dict:
    usuario = alcance.usuario
    condiciones = queries.condiciones_facturas(alcance, desde, hasta)

    por_estado = queries.conteo_por_estado(db, condiciones)
    total = sum(por_estado.values())
    facturado = queries.total_facturado(db, condiciones)
    pendientes = por_estado.get("entregada", 0)  # entregadas que el cliente aún no firma ni rechaza
    rechazadas = por_estado.get("rechazada", 0)
    por_fecha = serie("por_fecha", "Facturas en el periodo", "linea",
                      puntos_por_fecha(queries.facturas_por_dia(db, condiciones), desde, hasta))

    if es_cliente(usuario):
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
        if alcance.es_admin:
            tarjetas += [
                tarjeta("usuarios_activos", "Usuarios activos", queries.usuarios_activos(db, alcance)),
                tarjeta("bodegas_activas", "Bodegas activas", queries.bodegas_activas(db, alcance)),
            ]
        else:
            mis_bodegas = queries.bodegas_del_usuario(db, alcance)
            if alcance.es_empresa:
                tarjetas.append(tarjeta("bodegueros", "Mis bodegueros", queries.bodegueros(db, alcance)))
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

    return {"tarjetas": tarjetas, "series": series}
