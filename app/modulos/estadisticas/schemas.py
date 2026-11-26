# Formato de la respuesta de Estadísticas. Es el mismo para los 4 roles, para que el frontend pinte lo que llegue
# sin calcular ni decidir nada por rol.
from datetime import date
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

EN_DESUSO = {"deprecated": True}  # formato anterior: se retira cuando el frontend confirme que usa el nuevo

Numero = Union[int, float]


class PeriodoOut(BaseModel):
    fecha_inicio: date = Field(description="Primer día del periodo (incluido).", examples=["2026-11-01"])
    fecha_fin: date = Field(description="Último día del periodo (incluido).", examples=["2026-11-30"])
    desde: date = Field(description="**En desuso:** igual a `fecha_inicio`.", examples=["2026-11-01"], json_schema_extra=EN_DESUSO)
    hasta: date = Field(description="**En desuso:** igual a `fecha_fin`.", examples=["2026-11-30"], json_schema_extra=EN_DESUSO)


class OpcionOut(BaseModel):
    """Una opción de un filtro."""
    id: int = Field(examples=[2])
    nombre: str = Field(examples=["Bodega Centro"])


class FiltrosDisponiblesOut(BaseModel):
    """Solo lo que el usuario puede elegir. Una lista vacía significa que ese filtro no aplica a su rol."""
    empresas: List[OpcionOut] = Field(default_factory=list)
    bodegas: List[OpcionOut] = Field(default_factory=list)
    bodegueros: List[OpcionOut] = Field(default_factory=list)
    tipos: List[OpcionOut] = Field(default_factory=list)


class KpiOut(BaseModel):
    """Una tarjeta del panel."""
    clave: str = Field(description="Identificador fijo.", examples=["tasa_aceptacion"])
    titulo: str = Field(examples=["Tasa de aceptación"])
    valor: Numero = Field(description="Conteo, o porcentaje con hasta 1 decimal.", examples=[94.5])
    formato: str = Field(description="`numero` o `porcentaje`.", examples=["porcentaje"])
    alerta: bool = Field(description="`true` si hay que resaltarla.", examples=[False])


class DesgloseOut(BaseModel):
    """La tabla principal. Las columnas van en el mismo orden que las claves de cada fila."""
    titulo: str = Field(examples=["Rendimiento por Bodega"])
    columnas: List[str] = Field(examples=[["Bodega", "Emitidas", "Completadas", "Rechazadas", "Efectividad"]])
    filas: List[Dict[str, Union[int, str]]] = Field(
        examples=[[{"nombre": "Bodega Norte", "emitidas": 90, "completadas": 86, "rechazadas": 4, "efectividad": "95.6%"}]])


class PuntoFechaOut(BaseModel):
    fecha: date = Field(description="El día, o el primer día del mes si el periodo es de más de 62 días.", examples=["2026-11-01"])
    completadas: int = Field(examples=[14])
    rechazadas: int = Field(examples=[1])


class AlertaOut(BaseModel):
    """Una factura rechazada."""
    factura_id: int = Field(description="Id de la factura (`numero_factura` se puede repetir entre empresas).", examples=[42])
    numero_factura: str = Field(examples=["FE-0042"])
    motivo_rechazo: Optional[str] = Field(default=None, examples=["Caja golpeada al momento de la entrega"])
    fecha: date = Field(description="Día en que el cliente la rechazó.", examples=["2026-11-23"])


# ===== FORMATO ANTERIOR (en desuso) =====

class TarjetaOut(BaseModel):
    """Un número grande del panel."""
    clave: str = Field(description="Identificador fijo de la tarjeta.", examples=["facturas"])
    etiqueta: str = Field(description="Texto para mostrar.", examples=["Facturas"])
    valor: Union[int, float] = Field(description="El número: entero si no tiene decimales; dinero con hasta 2 decimales.",
                                     examples=[24])
    sufijo: str = Field(default="", description='"$" si es dinero; "" si es un conteo.', examples=[""])


class PuntoOut(BaseModel):
    """Una barra o un punto de una serie."""
    etiqueta: str = Field(examples=["Entregada"])
    valor: Union[int, float] = Field(examples=[6])


class SerieOut(BaseModel):
    """Un gráfico del panel."""
    clave: str = Field(description="Identificador fijo de la serie.", examples=["por_estado"])
    titulo: str = Field(examples=["Facturas por estado"])
    tipo: str = Field(description='`barras` o `linea`.', examples=["barras"])
    datos: List[PuntoOut]


class ResumenOut(BaseModel):
    """Panel de estadísticas del usuario de la sesión."""
    generado_para: str = Field(description="Rol del usuario. Solo informativo.", examples=["empresa"])
    periodo: PeriodoOut
    filtros_disponibles: FiltrosDisponiblesOut
    kpis: List[KpiOut] = Field(description="Las 4 tarjetas del rol.")
    desglose_principal: DesgloseOut
    serie_temporal: List[PuntoFechaOut] = Field(description="Facturas completadas y rechazadas según su fecha de emisión, sin huecos.")
    alertas_detalle: List[AlertaOut] = Field(description="Empresa y bodeguero: las últimas 5 rechazadas. A los demás, vacía.")
    tarjetas: List[TarjetaOut] = Field(description="**En desuso:** usar `kpis`.", json_schema_extra=EN_DESUSO)
    series: List[SerieOut] = Field(description="**En desuso:** usar `desglose_principal` y `serie_temporal`.", json_schema_extra=EN_DESUSO)
