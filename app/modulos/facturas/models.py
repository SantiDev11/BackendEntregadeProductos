# Órdenes de entrega (la orden ES la factura) y sus líneas de detalle
from sqlalchemy import (JSON, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from app.database import Base
from app.modulos.comun.mixins import EstadoAuditoriaMixin

# Estados por los que pasa una orden (factura)
ESTADOS_ORDEN = ["emitida", "entregada", "firmada", "rechazada", "recibida"]


class Orden(EstadoAuditoriaMixin, Base):
    __tablename__ = "ordenes"
    __table_args__ = (
        # el mismo consecutivo no se puede repetir dentro de un prefijo
        UniqueConstraint("prefijo", "consecutivo", name="uq_ordenes_prefijo_consecutivo"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Numeración y fechas
    prefijo = Column(String(10), nullable=False)  # prefijo de la factura, ej. "FE"
    consecutivo = Column(Integer, nullable=False)  # número consecutivo dentro del prefijo
    numero = Column(String(30), nullable=False, unique=True)  # número completo, ej. "FE-0001"
    fecha_emision = Column(DateTime, nullable=False, server_default=func.now())  # cuándo se emitió
    fecha_vencimiento = Column(Date, nullable=True)  # fecha límite de pago (solo si es a crédito)

    # Pago
    moneda = Column(String(3), nullable=False, default="COP", server_default="COP")  # moneda de la factura
    forma_pago = Column(String(20), nullable=False, default="contado", server_default="contado")  # contado o credito
    medio_pago = Column(String(30), nullable=True)  # efectivo, transferencia, tarjeta...

    # Relaciones: bodega que despacha, cliente que recibe (adquiriente) y bodeguero que emite
    bodega_id = Column(Integer, ForeignKey("bodegas.id"), nullable=False)  # bodega desde donde se despacha
    cliente_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)  # usuario cliente (adquiriente)
    bodeguero_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)  # usuario que emite la factura

    # Copias de los datos al momento de emitir (la factura no cambia si después se edita el cliente o las constantes)
    emisor_datos = Column(JSON, nullable=False)  # copia de EMISOR (app/core/emisor.py)
    adquiriente_datos = Column(JSON, nullable=False)  # copia de los datos del cliente

    # Totales (los calcula el backend)
    subtotal = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))  # suma antes de descuentos e IVA
    descuento_total = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))  # suma de descuentos
    impuesto_total = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))  # suma del IVA
    total = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))  # valor a pagar

    observaciones = Column(Text, nullable=True)  # notas libres de la factura

    # Estado del flujo de la factura (NO confundir con "estado", el booleano activo/inactivo del mixin)
    estado_orden = Column(String(20), nullable=False, default="emitida", server_default="emitida", index=True)

    # Trazabilidad del flujo
    fecha_entrega = Column(DateTime, nullable=True)  # cuándo el bodeguero la entregó al cliente
    fecha_respuesta = Column(DateTime, nullable=True)  # cuándo el cliente la firmó o la rechazó
    fecha_recepcion = Column(DateTime, nullable=True)  # cuándo el bodeguero recibió la factura firmada
    motivo_rechazo = Column(String(255), nullable=True)  # por qué el cliente la rechazó
    firma = Column(LONGTEXT, nullable=True)  # imagen de la firma del cliente en base64 (data URL)

    # Validación electrónica SIMULADA (no se envía a la DIAN)
    cufe = Column(String(128), nullable=True)  # código único de la factura (hash simulado)
    fecha_validacion = Column(DateTime, nullable=True)  # cuándo se generó la validación

    # Relaciones con otros modelos (foreign_keys explícito porque hay dos FK a usuarios)
    bodega = relationship("Bodega")
    cliente = relationship("Usuario", foreign_keys=[cliente_id])
    bodeguero = relationship("Usuario", foreign_keys=[bodeguero_id])
    detalles = relationship(
        "OrdenDetalle",
        back_populates="orden",
        cascade="all, delete-orphan",  # al borrar la orden se borran sus líneas
        order_by="OrdenDetalle.linea",
    )


class OrdenDetalle(EstadoAuditoriaMixin, Base):
    __tablename__ = "orden_detalle"

    id = Column(Integer, primary_key=True, index=True)
    orden_id = Column(Integer, ForeignKey("ordenes.id", ondelete="CASCADE"), nullable=False)  # orden a la que pertenece
    linea = Column(Integer, nullable=False)  # número de línea dentro de la factura (1, 2, 3...)
    tipo_id = Column(Integer, ForeignKey("tipos.id"), nullable=True)  # tipo de producto (opcional)
    descripcion = Column(String(255), nullable=False)  # descripción del producto
    unidad_medida = Column(String(20), nullable=False, default="UND", server_default="UND")  # unidad: UND, KG, CAJA...

    # Valores de la línea
    cantidad = Column(Numeric(12, 2), nullable=False)  # cantidad entregada
    precio_unitario = Column(Numeric(14, 2), nullable=False)  # precio de una unidad sin IVA
    descuento_porcentaje = Column(Numeric(5, 2), nullable=False, default=0, server_default=text("0"))  # % de descuento
    iva_porcentaje = Column(Numeric(5, 2), nullable=False, default=19, server_default=text("19"))  # % de IVA (0, 5 o 19)
    subtotal = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))  # cantidad x precio (antes del descuento)
    iva_valor = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))  # valor del IVA de la línea
    total = Column(Numeric(14, 2), nullable=False, default=0, server_default=text("0"))  # subtotal - descuento + IVA

    # Relaciones
    orden = relationship("Orden", back_populates="detalles")
    tipo = relationship("Tipo")
