# Esquemas de Facturas (la orden ES la factura): entrada, acciones, salida y listado paginado
import base64
import binascii
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer,
                      StringConstraints, ValidationInfo, field_validator)
from pydantic_core import PydanticCustomError

# ===== TIPOS REUTILIZABLES =====

# Dinero: se calcula con Decimal, pero en el JSON sale como número (no como texto)
Dinero = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

FORMAS_PAGO = ("contado", "credito")
MEDIOS_PAGO = ("efectivo", "transferencia", "tarjeta")
IVAS_PERMITIDOS = (Decimal("0"), Decimal("5"), Decimal("19"))
FIRMA_PREFIJO = "data:image/png;base64,"
FIRMA_MAX_CARACTERES = 500_000  # ~500 KB de texto


def _sin_tildes_minuscula(valor):
    """'Crédito ' -> 'credito' (quita espacios, tildes y mayúsculas) antes de validar."""
    if not isinstance(valor, str):
        return valor
    texto = unicodedata.normalize("NFKD", valor.strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _validar_forma_pago(valor: str) -> str:
    if valor not in FORMAS_PAGO:
        raise PydanticCustomError("forma_pago", "debe ser contado o credito")
    return valor


def _validar_medio_pago(valor: str) -> str:
    if valor not in MEDIOS_PAGO:
        raise PydanticCustomError("medio_pago", "debe ser efectivo, transferencia o tarjeta")
    return valor


def _validar_iva(valor: Decimal) -> Decimal:
    if valor not in IVAS_PERMITIDOS:
        raise PydanticCustomError("iva_porcentaje", "debe ser 0, 5 o 19")
    return valor


def _validar_firma(valor: str) -> str:
    """La firma debe ser una imagen PNG en base64 con el prefijo data:image/png;base64,"""
    if len(valor) > FIRMA_MAX_CARACTERES:
        raise PydanticCustomError("firma", "es demasiado grande (máximo 500 KB)")
    if not valor.startswith(FIRMA_PREFIJO):
        raise PydanticCustomError("firma", "debe ser una imagen PNG en base64 (data:image/png;base64,...)")
    try:
        datos = base64.b64decode(valor[len(FIRMA_PREFIJO):], validate=True)
    except (binascii.Error, ValueError):
        raise PydanticCustomError("firma", "no es un base64 válido")
    if not datos.startswith(b"\x89PNG"):
        raise PydanticCustomError("firma", "debe ser una imagen PNG en base64 (data:image/png;base64,...)")
    return valor


FormaPago = Annotated[str, BeforeValidator(_sin_tildes_minuscula), AfterValidator(_validar_forma_pago)]
MedioPago = Annotated[str, BeforeValidator(_sin_tildes_minuscula), AfterValidator(_validar_medio_pago)]
IvaPorcentaje = Annotated[Decimal, AfterValidator(_validar_iva)]
Descripcion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
UnidadMedida = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20)]
Observaciones = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
Firma = Annotated[str, AfterValidator(_validar_firma)]
Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


# ===== ENTRADA =====

class DetalleIn(BaseModel):
    """Una línea de la factura. **Todos los campos son obligatorios.**
    Los valores calculados (subtotal, IVA, total) los pone el servidor."""
    tipo_id: int = Field(description="**Obligatorio.** Id de un tipo existente (`GET /tipos`).", examples=[1])
    descripcion: Descripcion = Field(description="**Obligatorio.** Descripción del producto, de 1 a 255 caracteres.",
                                     examples=["Arroz 500 g"])
    unidad_medida: UnidadMedida = Field(description="**Obligatorio.** Unidad (UND, KG, CAJA...), hasta 20 caracteres. "
                                                    "Se guarda en mayúsculas.",
                                        examples=["UND"])
    cantidad: Decimal = Field(gt=0, max_digits=12, decimal_places=2,
                              description="**Obligatorio.** Cantidad, mayor que 0, hasta 2 decimales.", examples=[10])
    precio_unitario: Decimal = Field(ge=0, max_digits=14, decimal_places=2,
                                     description="**Obligatorio.** Precio de una unidad **sin IVA**, mayor o igual a 0.",
                                     examples=[3500])
    descuento_porcentaje: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2,
                                          description="**Obligatorio.** Porcentaje de descuento de 0 a 100 (envía 0 si no hay).",
                                          examples=[0])
    iva_porcentaje: IvaPorcentaje = Field(description="**Obligatorio.** IVA: 0, 5 o 19.", examples=[19])


class FacturaCreate(BaseModel):
    """Datos para crear una factura (queda en estado `emitida`). El servidor calcula número, totales y CUFE."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "cliente_id": 3,
        "bodega_id": 1,
        "forma_pago": "contado",
        "medio_pago": "transferencia",
        "fecha_vencimiento": None,
        "observaciones": "Entregar en portería",
        "detalle": [
            {"tipo_id": 1, "descripcion": "Arroz 500 g", "unidad_medida": "UND", "cantidad": 10,
             "precio_unitario": 3500, "descuento_porcentaje": 0, "iva_porcentaje": 5},
        ],
    }]})

    cliente_id: int = Field(description="**Obligatorio.** Id de un usuario **cliente** activo (el adquiriente).", examples=[3])
    bodega_id: int = Field(description="**Obligatorio.** Id de una bodega activa (desde donde se despacha).", examples=[1])
    forma_pago: FormaPago = Field(description="**Obligatorio.** `contado` o `credito` (se acepta `crédito`).",
                                  examples=["contado"])
    medio_pago: MedioPago = Field(description="**Obligatorio.** `efectivo`, `transferencia` o `tarjeta`.",
                                  examples=["transferencia"])
    fecha_vencimiento: Optional[date] = Field(default=None, validate_default=True,
                                              description="Fecha límite de pago (AAAA-MM-DD). **Obligatoria solo si la forma "
                                                          "de pago es crédito**; con contado puede ir `null` u omitirse.",
                                              examples=[None])
    observaciones: Optional[Observaciones] = Field(default=None, description="Opcional. Notas, hasta 1000 caracteres.",
                                                   examples=["Entregar en portería"])
    detalle: List[DetalleIn] = Field(min_length=1, description="**Obligatorio.** Líneas de la factura (al menos 1).")

    @field_validator("fecha_vencimiento", mode="after")
    @classmethod
    def credito_con_vencimiento(cls, valor, info: ValidationInfo):
        """Con crédito la fecha de vencimiento es obligatoria (el error queda asociado al campo)."""
        if info.data.get("forma_pago") == "credito" and valor is None:
            raise PydanticCustomError("credito_sin_vencimiento", "es obligatoria cuando la forma de pago es crédito")
        return valor


class FacturaUpdate(BaseModel):
    """Datos para editar una factura en estado `emitida` (todos opcionales)."""
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "observaciones": "Entregar en recepción",
        "detalle": [
            {"tipo_id": 1, "descripcion": "Arroz 500 g", "unidad_medida": "UND", "cantidad": 12,
             "precio_unitario": 3500, "descuento_porcentaje": 0, "iva_porcentaje": 5},
        ],
    }]})

    cliente_id: Optional[int] = Field(default=None, description="Opcional. Nuevo cliente (usuario cliente activo).", examples=[3])
    bodega_id: Optional[int] = Field(default=None, description="Opcional. Nueva bodega (activa).", examples=[1])
    forma_pago: Optional[FormaPago] = Field(default=None, description="Opcional. `contado` o `credito`.", examples=["credito"])
    medio_pago: Optional[MedioPago] = Field(default=None, description="Opcional. `efectivo`, `transferencia` o `tarjeta`. "
                                                                      "Es obligatorio en la factura: no se puede borrar.",
                                            examples=["efectivo"])
    fecha_vencimiento: Optional[date] = Field(default=None, description="Opcional. Fecha límite de pago (AAAA-MM-DD).",
                                              examples=["2026-12-18"])
    observaciones: Optional[Observaciones] = Field(default=None,
                                                   description='Opcional. Notas. Para **borrarlas** se envía `""`.',
                                                   examples=["Entregar en recepción"])
    detalle: Optional[List[DetalleIn]] = Field(default=None, min_length=1,
                                               description="Opcional. Si se envía, **reemplaza todas** las líneas (al menos 1).")


class FirmaIn(BaseModel):
    """Firma del cliente al aceptar la factura."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"firma": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."}]})

    firma: Firma = Field(description="**Obligatorio.** Imagen PNG de la firma en base64 con el prefijo "
                                     "`data:image/png;base64,`. Máximo 500 KB.",
                         examples=["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."])


class RechazoIn(BaseModel):
    """Motivo del cliente al rechazar la factura."""
    model_config = ConfigDict(json_schema_extra={"examples": [{"motivo": "Llegaron 2 cajas menos de arroz"}]})

    motivo: Motivo = Field(description="**Obligatorio.** Por qué se rechaza, de 1 a 255 caracteres.",
                           examples=["Llegaron 2 cajas menos de arroz"])


# ===== SALIDA =====

class EmisorOut(BaseModel):
    nit: str = Field(description="NIT del emisor (sin dígito de verificación).", examples=["900000000"])
    dv: str = Field(description="Dígito de verificación.", examples=["1"])
    razon_social: str = Field(examples=["Empresa Demo S.A.S."])
    nombre_comercial: Optional[str] = Field(default=None, examples=["Entrega Demo"])
    direccion: Optional[str] = Field(default=None, examples=["Calle 100 # 10-20"])
    ciudad: Optional[str] = Field(default=None, examples=["Bogotá"])
    departamento: Optional[str] = Field(default=None, examples=["Cundinamarca"])
    telefono: Optional[str] = Field(default=None, examples=["6015550000"])
    correo: Optional[str] = Field(default=None, examples=["facturacion@empresademo.com"])
    regimen: Optional[str] = Field(default=None, examples=["Responsable de IVA"])
    responsabilidad_fiscal: Optional[str] = Field(default=None, examples=["R-99-PN"])


class AdquirienteOut(BaseModel):
    id: int = Field(description="Id del usuario cliente.", examples=[3])
    nombre: str = Field(examples=["Cliente Prueba"])
    tipo_documento: Optional[str] = Field(default=None, examples=["CC"])
    numero_documento: Optional[str] = Field(default=None, examples=["1020304050"])
    direccion: Optional[str] = Field(default=None, examples=["Calle 10 # 20-30"])
    ciudad: Optional[str] = Field(default=None, examples=["Bogotá"])
    telefono: Optional[str] = Field(default=None, examples=["3001234567"])
    correo: Optional[str] = Field(default=None, examples=["cliente@entrega.com"])


class BodegaResumen(BaseModel):
    id: int = Field(examples=[1])
    nombre: str = Field(examples=["Bodega Central"])
    codigo: Optional[str] = Field(default=None, examples=["BOD-01"])
    direccion: Optional[str] = Field(default=None, examples=["Calle 1 # 2-3"])
    ciudad: Optional[str] = Field(default=None, examples=["Bogotá"])
    recibe_nombre: Optional[str] = Field(default=None, examples=["Ana Ruiz"])
    recibe_documento: Optional[str] = Field(default=None, examples=["52123456"])
    recibe_cargo: Optional[str] = Field(default=None, examples=["Jefe de bodega"])
    recibe_telefono: Optional[str] = Field(default=None, examples=["3001234567"])


class DetalleOut(BaseModel):
    linea: int = Field(description="Número de línea (1, 2, 3...).", examples=[1])
    tipo_id: Optional[int] = Field(default=None, examples=[1])
    descripcion: str = Field(examples=["Arroz 500 g"])
    unidad_medida: str = Field(examples=["UND"])
    cantidad: Dinero = Field(examples=[10])
    precio_unitario: Dinero = Field(examples=[3500])
    descuento_porcentaje: Dinero = Field(examples=[0])
    iva_porcentaje: Dinero = Field(examples=[5])
    subtotal: Dinero = Field(description="cantidad × precio_unitario (antes de descuento).", examples=[35000])
    valor_descuento: Dinero = Field(description="subtotal × descuento_porcentaje / 100.", examples=[0])
    valor_iva: Dinero = Field(description="(subtotal − valor_descuento) × iva_porcentaje / 100.", examples=[1750])
    total_linea: Dinero = Field(description="subtotal − valor_descuento + valor_iva.", examples=[36750])


class TotalesOut(BaseModel):
    subtotal: Dinero = Field(description="Suma de los subtotales de las líneas.", examples=[35000])
    total_descuento: Dinero = Field(description="Suma de los descuentos.", examples=[0])
    base_gravable: Dinero = Field(description="subtotal − total_descuento.", examples=[35000])
    total_iva: Dinero = Field(description="Suma del IVA.", examples=[1750])
    total: Dinero = Field(description="Valor a pagar.", examples=[36750])


class ValidacionElectronicaOut(BaseModel):
    cufe: Optional[str] = Field(default=None, description="Código único (SHA-384) **simulado**.", examples=["a1b2c3..."])
    qr: Optional[str] = Field(default=None, description="Texto del código QR con los datos principales.", examples=["NumFac:FE-0001 ..."])
    fecha_validacion: Optional[datetime] = Field(default=None, examples=["2026-11-18T10:30:00"])
    simulada: bool = Field(default=True, description="Siempre `true`: no se envía a la DIAN.", examples=[True])


class SoftwareOut(BaseModel):
    nombre: str = Field(examples=["Entrega de Productos"])
    fabricante: str = Field(examples=["Equipo Entrega de Productos"])
    version: str = Field(examples=["1.0.0"])


class TrazabilidadOut(BaseModel):
    creada_por: Optional[str] = Field(default=None, description="Nombre de quien creó la factura (puede ser el admin).",
                                      examples=["Bodeguero Prueba"])
    bodeguero_id: int = Field(description="Id de quien creó la factura (igual a `creado_por_id`; se mantiene por compatibilidad).",
                              examples=[2])
    fecha_entrega: Optional[datetime] = Field(default=None, description="Cuándo se entregó al cliente.")
    fecha_respuesta: Optional[datetime] = Field(default=None, description="Cuándo el cliente firmó o rechazó.")
    motivo_rechazo: Optional[str] = Field(default=None, description="Motivo, si el cliente la rechazó.")
    firma: Optional[str] = Field(default=None, description="Firma del cliente (data URL PNG en base64), si la aceptó.")
    fecha_recepcion: Optional[datetime] = Field(default=None, description="Cuándo el bodeguero recibió la factura firmada.")


class FacturaOut(BaseModel):
    """Factura completa."""
    id: int = Field(examples=[1])
    numero: str = Field(description="Número de la factura: prefijo + consecutivo.", examples=["FE-0001"])
    estado: str = Field(description="Estado de la factura: `emitida`, `entregada`, `firmada`, `rechazada` o `recibida`.",
                        examples=["emitida"])
    creado_por_id: int = Field(description="Id del usuario que creó la factura (el mismo `trazabilidad.bodeguero_id`).",
                               examples=[2])
    creado_por_nombre: Optional[str] = Field(default=None, description="Nombre de quien creó la factura.",
                                             examples=["Bodeguero Prueba"])
    fecha_emision: datetime = Field(examples=["2026-11-18T10:30:00"])
    fecha_vencimiento: Optional[date] = Field(default=None, examples=[None])
    forma_pago: str = Field(examples=["contado"])
    medio_pago: Optional[str] = Field(default=None, examples=["transferencia"])
    moneda: str = Field(examples=["COP"])
    emisor: EmisorOut
    adquiriente: AdquirienteOut
    bodega: BodegaResumen
    detalle: List[DetalleOut]
    totales: TotalesOut
    observaciones: Optional[str] = Field(default=None, examples=["Entregar en portería"])
    pie_pagina: str = Field(description="Texto legal del pie de la factura.")
    validacion_electronica: ValidacionElectronicaOut
    software: SoftwareOut
    trazabilidad: TrazabilidadOut


class FacturaResumen(BaseModel):
    """Una fila del listado de facturas."""
    id: int = Field(examples=[1])
    numero: str = Field(examples=["FE-0001"])
    estado: str = Field(examples=["emitida"])
    fecha_emision: datetime = Field(examples=["2026-11-18T10:30:00"])
    cliente_id: int = Field(examples=[3])
    cliente_nombre: str = Field(examples=["Cliente Prueba"])
    bodega_nombre: str = Field(examples=["Bodega Central"])
    creado_por_id: int = Field(description="Id del usuario que creó la factura (el mismo `trazabilidad.bodeguero_id`).",
                               examples=[2])
    creado_por_nombre: Optional[str] = Field(default=None, description="Nombre de quien creó la factura.",
                                             examples=["Bodeguero Prueba"])
    total: Dinero = Field(examples=[36750])


class ClienteOpcion(BaseModel):
    """Cliente disponible para facturar (solo los datos necesarios para elegirlo)."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Id del usuario cliente (se envía como `cliente_id`).", examples=[3])
    nombre: str = Field(examples=["Cliente Prueba"])
    tipo_documento: Optional[str] = Field(default=None, examples=["CC"])
    numero_documento: Optional[str] = Field(default=None, examples=["1020304050"])


class ClientePaginado(BaseModel):
    """Respuesta de GET /facturas/clientes: {data, total, page, limit}."""
    data: List[ClienteOpcion] = Field(description="Clientes activos de la página, ordenados por nombre.")
    total: int = Field(description="Cantidad total de clientes que cumplen la búsqueda.", examples=[1])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])


class FacturaPaginado(BaseModel):
    """Respuesta del listado: {data, total, page, limit}."""
    data: List[FacturaResumen] = Field(description="Facturas de la página, de la más reciente a la más antigua.")
    total: int = Field(description="Cantidad total de facturas que cumplen los filtros.", examples=[1])
    page: int = Field(description="Página devuelta (empieza en 1).", examples=[1])
    limit: int = Field(description="Cantidad máxima de elementos por página.", examples=[10])
