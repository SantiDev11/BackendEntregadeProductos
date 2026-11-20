# Formato de la respuesta de Estadísticas. Es genérico (tarjetas y series) para que el frontend
# pinte lo que llegue sin decidir nada por rol.
from datetime import date
from typing import List, Union

from pydantic import BaseModel, Field


class PeriodoOut(BaseModel):
    desde: date = Field(description="Primer día del periodo (incluido).", examples=["2026-11-01"])
    hasta: date = Field(description="Último día del periodo (incluido).", examples=["2026-11-30"])


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
    periodo: PeriodoOut
    generado_para: str = Field(description="Rol del usuario. Solo informativo.", examples=["bodeguero"])
    tarjetas: List[TarjetaOut]
    series: List[SerieOut]
