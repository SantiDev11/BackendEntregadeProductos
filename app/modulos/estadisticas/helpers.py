# Validaciones y ayudas del módulo Estadísticas. Si algo no se cumple, lanzan el error de errors.py.
import calendar
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.alcance import Alcance
from app.modulos.estadisticas import errors, queries
from app.modulos.estadisticas.schemas import AlertaOut, KpiOut, PuntoFechaOut, PuntoOut, SerieOut, TarjetaOut

ETIQUETAS_ESTADO = {"emitida": "Emitida", "entregada": "Entregada", "firmada": "Firmada",
                    "rechazada": "Rechazada", "recibida": "Recibida"}
MAX_DIAS_POR_DIA = 62  # hasta ~2 meses la serie va día por día; si el rango es mayor, va mes por mes


def fin_de_mes(dia: date) -> date:
    return dia.replace(day=calendar.monthrange(dia.year, dia.month)[1])


# ===== FILTROS =====

# Qué filtros acepta cada perfil; los demás se ignoran (el alcance siempre sale del token)
FILTROS = {"admin": ("empresa_id", "estado"), "empresa": ("bodega_id", "bodeguero_id", "tipo_id"),
           "bodeguero": ("tipo_id", "estado"), "cliente": ("empresa_id", "estado")}

# Valores de ?estado= en cada perfil. Para el admin es el estado de la EMPRESA; para los demás agrupa los de la factura
TODAS = "todas"
ESTADOS = {"admin": (TODAS, "activa", "pendiente", "suspendida", "rechazada"),
           "bodeguero": (TODAS, "pendientes", "completadas", "rechazadas"),
           "cliente": (TODAS, "pendientes", "aceptadas", "rechazadas")}


@dataclass(frozen=True)
class Filtros:
    empresa_id: int | None = None
    bodega_id: int | None = None
    bodeguero_id: int | None = None
    tipo_id: int | None = None
    estado: str | None = None


def perfil_de(alcance: Alcance) -> str:
    """Qué panel recibe: el de su rol. Los roles personalizados reciben el del bodeguero (solo lo que crearon)."""
    rol = alcance.usuario.rol.nombre
    return rol if rol in FILTROS else "bodeguero"


def filtros_validos(db: Session, alcance: Alcance, perfil: str, f: Filtros) -> Filtros:
    """Deja solo los filtros que el perfil puede usar. Lanza 422 si el estado no es válido y 403 si una empresa
    pide una bodega que no es suya."""
    f = replace(f, **{campo: None for campo in Filtros.__dataclass_fields__ if campo not in FILTROS[perfil]})
    if f.estado is not None:
        estado = f.estado.strip().lower()
        if estado and estado not in ESTADOS[perfil]:
            raise errors.estado_invalido(ESTADOS[perfil])
        f = replace(f, estado=None if estado in ("", TODAS) else estado)
    if f.bodega_id is not None:
        bodega = queries.obtener_bodega(db, f.bodega_id)
        if bodega is None or not alcance.incluye(bodega):
            raise errors.bodega_de_otra_empresa()
    return f


# ===== PERIODO =====

def periodo_pedido(fecha_inicio: date | None, fecha_fin: date | None, desde: date | None, hasta: date | None) -> tuple[date, date]:
    """El periodo completo. `desde` y `hasta` están en desuso: solo cuentan si no llega el parámetro nuevo."""
    inicio, fin = periodo(fecha_inicio or desde, fecha_fin or hasta)
    if fin < inicio:
        raise errors.rango_invalido() if fecha_fin else errors.rango_anterior_invalido()
    return inicio, fin


def periodo(desde: date | None, hasta: date | None, hoy: date | None = None) -> tuple[date, date]:
    """Completa el rango de fechas:
    - Sin ninguna: el mes actual.
    - Solo `desde`: hasta el fin de ese mes. Solo `hasta`: desde el inicio de ese mes."""
    hoy = hoy or date.today()
    if desde is None and hasta is None:
        desde, hasta = hoy.replace(day=1), fin_de_mes(hoy)
    elif desde is None:
        desde = hasta.replace(day=1)
    elif hasta is None:
        hasta = fin_de_mes(desde)
    return desde, hasta


def numero(valor) -> int | float:
    """Número con máximo 2 decimales; si no tiene decimales sale entero (24 y no 24.0)."""
    valor = round(Decimal(valor or 0), 2)
    return int(valor) if valor == valor.to_integral_value() else float(valor)


def porcentaje(parte: int, total: int) -> Decimal:
    """% de `parte` sobre `total` con 1 decimal (0 si no hay total)."""
    return (Decimal(parte) * 100 / total).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if total else Decimal("0.0")


def kpi(clave: str, titulo: str, valor, alerta: bool = False, formato: str = "numero") -> KpiOut:
    return KpiOut(clave=clave, titulo=titulo, valor=numero(valor), formato=formato, alerta=alerta)


def efectividad(completadas: int, total: int) -> str:
    """"95.6%": facturas completadas sobre el total."""
    return f"{porcentaje(completadas, total)}%"


def dias_o_meses(desde: date, hasta: date) -> list[date]:
    """Los días del periodo o, si es de más de 62 días, el primer día de cada mes."""
    if (hasta - desde).days < MAX_DIAS_POR_DIA:
        return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    meses = range(desde.year * 12 + desde.month - 1, hasta.year * 12 + hasta.month)
    return [date(m // 12, m % 12 + 1, 1) for m in meses]


def serie_temporal(por_dia: dict[date, tuple[int, int]], desde: date, hasta: date) -> list[PuntoFechaOut]:
    """Completadas y rechazadas por día (o por mes si el periodo es largo), con 0 donde no hay."""
    por_mes = (hasta - desde).days >= MAX_DIAS_POR_DIA
    puntos = {d: [0, 0] for d in dias_o_meses(desde, hasta)}
    for dia, (completadas, rechazadas) in por_dia.items():
        punto = puntos[dia.replace(day=1) if por_mes else dia]
        punto[0] += completadas
        punto[1] += rechazadas
    return [PuntoFechaOut(fecha=d, completadas=c, rechazadas=r) for d, (c, r) in puntos.items()]


def alertas(filas) -> list[AlertaOut]:
    return [AlertaOut(factura_id=i, numero_factura=numero_, motivo_rechazo=motivo, fecha=fecha.date()) for i, numero_, motivo, fecha in filas]


def tarjeta(clave: str, etiqueta: str, valor, sufijo: str = "") -> TarjetaOut:
    return TarjetaOut(clave=clave, etiqueta=etiqueta, valor=numero(valor), sufijo=sufijo)


def serie(clave: str, titulo: str, tipo: str, puntos: list[tuple[str, float]]) -> SerieOut:
    return SerieOut(clave=clave, titulo=titulo, tipo=tipo,
                    datos=[PuntoOut(etiqueta=e, valor=numero(v)) for e, v in puntos])


def puntos_por_estado(conteo: dict[str, int], incluir_emitida: bool = True) -> list[tuple[str, int]]:
    """Las barras de los 5 estados, en el orden del flujo, con 0 en los que no tienen facturas."""
    return [(etiqueta, conteo.get(estado, 0)) for estado, etiqueta in ETIQUETAS_ESTADO.items()
            if incluir_emitida or estado != "emitida" or conteo.get(estado)]


def puntos_por_fecha(por_dia: dict[date, int], desde: date, hasta: date) -> list[tuple[str, int]]:
    """Facturas por día (rangos de hasta 62 días) o por mes, con 0 en los días/meses sin facturas
    para que la línea no tenga huecos."""
    if (hasta - desde).days < MAX_DIAS_POR_DIA:
        dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
        return [(d.isoformat(), por_dia.get(d, 0)) for d in dias]
    por_mes = {d.isoformat()[:7]: 0 for d in dias_o_meses(desde, hasta)}
    for d, n in por_dia.items():
        por_mes[d.isoformat()[:7]] += n
    return list(por_mes.items())
