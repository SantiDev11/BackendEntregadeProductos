# Validaciones y ayudas del módulo Estadísticas. Si algo no se cumple, lanzan el error de errors.py.
import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.modulos.estadisticas import errors
from app.modulos.estadisticas.schemas import PuntoOut, SerieOut, TarjetaOut

ETIQUETAS_ESTADO = {"emitida": "Emitida", "entregada": "Entregada", "firmada": "Firmada",
                    "rechazada": "Rechazada", "recibida": "Recibida"}
MAX_DIAS_POR_DIA = 62  # hasta ~2 meses la serie va día por día; si el rango es mayor, va mes por mes


def fin_de_mes(dia: date) -> date:
    return dia.replace(day=calendar.monthrange(dia.year, dia.month)[1])


def periodo(desde: date | None, hasta: date | None, hoy: date | None = None) -> tuple[date, date]:
    """Completa el rango de fechas:
    - Sin ninguna: el mes actual.
    - Solo `desde`: hasta el fin de ese mes. Solo `hasta`: desde el inicio de ese mes.
    Lanza 422 si `hasta` es anterior a `desde`."""
    hoy = hoy or date.today()
    if desde is None and hasta is None:
        desde, hasta = hoy.replace(day=1), fin_de_mes(hoy)
    elif desde is None:
        desde = hasta.replace(day=1)
    elif hasta is None:
        hasta = fin_de_mes(desde)
    if hasta < desde:
        raise errors.rango_invalido()
    return desde, hasta


def numero(valor) -> int | float:
    """Número con máximo 2 decimales; si no tiene decimales sale entero (24 y no 24.0)."""
    valor = round(Decimal(valor or 0), 2)
    return int(valor) if valor == valor.to_integral_value() else float(valor)


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
    por_mes: dict[str, int] = {}
    dia = desde.replace(day=1)
    while dia <= hasta:
        por_mes[dia.strftime("%Y-%m")] = 0
        dia = fin_de_mes(dia) + timedelta(days=1)
    for d, n in por_dia.items():
        por_mes[d.strftime("%Y-%m")] += n
    return list(por_mes.items())
