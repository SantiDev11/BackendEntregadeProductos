# Lógica de negocio de las facturas: cálculos, numeración, CUFE simulado, armado de la respuesta
# y validaciones que usan los endpoints. Si algo no se cumple, lanzan el error de errors.py.
import hashlib
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.modulos.bodegas.models import Bodega
from app.modulos.facturas import errors, queries
from app.modulos.facturas.emisor import EMISOR, PREFIJO_FACTURA, RESOLUCION, SOFTWARE
from app.modulos.facturas.models import Orden, OrdenDetalle
from app.modulos.usuarios.models import Usuario

CENTAVOS = Decimal("0.01")


def redondear(valor: Decimal) -> Decimal:
    """Redondea a 2 decimales (0.005 -> 0.01)."""
    return Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


# ===== CÁLCULOS =====

def calcular_linea(cantidad, precio_unitario, descuento_porcentaje, iva_porcentaje) -> dict:
    """Calcula los valores de una línea:
    subtotal = cantidad × precio; descuento = subtotal × % / 100;
    iva = (subtotal − descuento) × % / 100; total = subtotal − descuento + iva."""
    subtotal = redondear(Decimal(cantidad) * Decimal(precio_unitario))
    valor_descuento = redondear(subtotal * Decimal(descuento_porcentaje) / 100)
    valor_iva = redondear((subtotal - valor_descuento) * Decimal(iva_porcentaje) / 100)
    total = subtotal - valor_descuento + valor_iva
    return {"subtotal": subtotal, "valor_descuento": valor_descuento, "valor_iva": valor_iva, "total": total}


def armar_detalles(lineas) -> list[OrdenDetalle]:
    """Convierte las líneas recibidas (DetalleIn) en OrdenDetalle con sus valores calculados."""
    detalles = []
    for numero, linea in enumerate(lineas, start=1):
        valores = calcular_linea(linea.cantidad, linea.precio_unitario, linea.descuento_porcentaje, linea.iva_porcentaje)
        detalles.append(OrdenDetalle(
            linea=numero,
            tipo_id=linea.tipo_id,
            descripcion=linea.descripcion,
            unidad_medida=linea.unidad_medida,
            cantidad=linea.cantidad,
            precio_unitario=linea.precio_unitario,
            descuento_porcentaje=linea.descuento_porcentaje,
            iva_porcentaje=linea.iva_porcentaje,
            subtotal=valores["subtotal"],
            iva_valor=valores["valor_iva"],
            total=valores["total"],
        ))
    return detalles


def actualizar_totales(orden: Orden) -> None:
    """Recalcula los totales de la orden a partir de sus líneas."""
    subtotal = descuento = iva = Decimal("0")
    for d in orden.detalles:
        valores = calcular_linea(d.cantidad, d.precio_unitario, d.descuento_porcentaje, d.iva_porcentaje)
        subtotal += valores["subtotal"]
        descuento += valores["valor_descuento"]
        iva += valores["valor_iva"]
    orden.subtotal = subtotal
    orden.descuento_total = descuento
    orden.impuesto_total = iva
    orden.total = subtotal - descuento + iva


# ===== NUMERACIÓN Y DATOS COPIADOS =====

def formatear_numero(consecutivo: int) -> str:
    """FE + consecutivo con al menos 4 dígitos: FE-0001."""
    return f"{PREFIJO_FACTURA}-{consecutivo:04d}"


def datos_emisor() -> dict:
    """Copia de los datos del emisor y de la resolución vigente (se guarda en la orden)."""
    return {**EMISOR, "resolucion": dict(RESOLUCION)}


def datos_adquiriente(cliente: Usuario) -> dict:
    """Copia de los datos del cliente al momento de emitir (se guarda en la orden)."""
    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "tipo_documento": cliente.tipo_documento,
        "numero_documento": cliente.numero_documento,
        "direccion": cliente.direccion,
        "ciudad": cliente.ciudad,
        "telefono": cliente.telefono,
        "correo": cliente.correo,
    }


# ===== VALIDACIÓN ELECTRÓNICA SIMULADA =====

def generar_cufe(orden: Orden) -> str:
    """CUFE SIMULADO: SHA-384 de número, fecha, valores, NIT del emisor y documento del adquiriente."""
    fecha = orden.fecha_emision.strftime("%Y-%m-%d%H:%M:%S")
    nit = orden.emisor_datos.get("nit", "")
    documento = orden.adquiriente_datos.get("numero_documento") or ""
    base = f"{orden.numero}{fecha}{orden.subtotal:.2f}{orden.impuesto_total:.2f}{orden.total:.2f}{nit}{documento}"
    return hashlib.sha384(base.encode("utf-8")).hexdigest()


def texto_qr(orden: Orden) -> str | None:
    """Texto del código QR con los datos principales de la factura."""
    if not orden.cufe:
        return None
    return (f"NumFac:{orden.numero} FecFac:{orden.fecha_emision:%Y-%m-%d} "
            f"NitFac:{orden.emisor_datos.get('nit', '')} DocAdq:{orden.adquiriente_datos.get('numero_documento') or ''} "
            f"ValFac:{orden.subtotal:.2f} ValIva:{orden.impuesto_total:.2f} ValTotFac:{orden.total:.2f} CUFE:{orden.cufe}")


def pie_pagina(orden: Orden) -> str:
    """Texto legal del pie de la factura, con la resolución copiada al emitir."""
    res = orden.emisor_datos.get("resolucion") or RESOLUCION
    return (f"Resolución de facturación N.° {res['numero']} del {res['fecha']}, "
            f"rango {PREFIJO_FACTURA}-{res['rango_desde']} a {PREFIJO_FACTURA}-{res['rango_hasta']}. "
            "Validación electrónica SIMULADA: este documento no tiene validez fiscal ante la DIAN.")


# ===== RESPUESTA =====

def detalle_salida(d: OrdenDetalle) -> dict:
    valores = calcular_linea(d.cantidad, d.precio_unitario, d.descuento_porcentaje, d.iva_porcentaje)
    return {
        "linea": d.linea,
        "tipo_id": d.tipo_id,
        "descripcion": d.descripcion,
        "unidad_medida": d.unidad_medida,
        "cantidad": d.cantidad,
        "precio_unitario": d.precio_unitario,
        "descuento_porcentaje": d.descuento_porcentaje,
        "iva_porcentaje": d.iva_porcentaje,
        "subtotal": valores["subtotal"],
        "valor_descuento": valores["valor_descuento"],
        "valor_iva": valores["valor_iva"],
        "total_linea": valores["total"],
    }


def factura_salida(orden: Orden) -> dict:
    """Arma la factura completa con el formato del contrato."""
    bodega = orden.bodega
    emisor = {k: v for k, v in orden.emisor_datos.items() if k != "resolucion"}
    return {
        "id": orden.id,
        "numero": orden.numero,
        "estado": orden.estado_orden,
        "creado_por_id": orden.bodeguero_id,
        "creado_por_nombre": orden.bodeguero.nombre if orden.bodeguero else None,
        "fecha_emision": orden.fecha_emision,
        "fecha_vencimiento": orden.fecha_vencimiento,
        "forma_pago": orden.forma_pago,
        "medio_pago": orden.medio_pago,
        "moneda": orden.moneda,
        "emisor": emisor,
        "adquiriente": orden.adquiriente_datos,
        "bodega": {
            "id": bodega.id, "nombre": bodega.nombre, "codigo": bodega.codigo, "direccion": bodega.direccion,
            "ciudad": bodega.ciudad, "recibe_nombre": bodega.recibe_nombre, "recibe_documento": bodega.recibe_documento,
            "recibe_cargo": bodega.recibe_cargo, "recibe_telefono": bodega.recibe_telefono,
        },
        "detalle": [detalle_salida(d) for d in orden.detalles],
        "totales": {
            "subtotal": orden.subtotal,
            "total_descuento": orden.descuento_total,
            "base_gravable": orden.subtotal - orden.descuento_total,
            "total_iva": orden.impuesto_total,
            "total": orden.total,
        },
        "observaciones": orden.observaciones,
        "pie_pagina": pie_pagina(orden),
        "validacion_electronica": {
            "cufe": orden.cufe, "qr": texto_qr(orden), "fecha_validacion": orden.fecha_validacion, "simulada": True,
        },
        "software": dict(SOFTWARE),
        "trazabilidad": {
            "creada_por": orden.bodeguero.nombre if orden.bodeguero else None,
            "bodeguero_id": orden.bodeguero_id,
            "fecha_entrega": orden.fecha_entrega,
            "fecha_respuesta": orden.fecha_respuesta,
            "motivo_rechazo": orden.motivo_rechazo,
            "firma": orden.firma,
            "fecha_recepcion": orden.fecha_recepcion,
        },
    }


def factura_resumen(orden: Orden) -> dict:
    """Una fila del listado."""
    return {
        "id": orden.id,
        "numero": orden.numero,
        "estado": orden.estado_orden,
        "fecha_emision": orden.fecha_emision,
        "cliente_id": orden.cliente_id,
        "cliente_nombre": orden.adquiriente_datos.get("nombre", ""),
        "bodega_nombre": orden.bodega.nombre if orden.bodega else "",
        "creado_por_id": orden.bodeguero_id,
        "creado_por_nombre": orden.bodeguero.nombre if orden.bodeguero else None,
        "total": orden.total,
    }


# ===== VALIDACIONES Y REGLAS QUE USAN LOS ENDPOINTS =====


def es_cliente(usuario: Usuario) -> bool:
    return usuario.rol.nombre == "cliente"


def ahora() -> datetime:
    return datetime.now().replace(microsecond=0)  # MySQL DATETIME no guarda microsegundos


def alcance_facturas(usuario: Usuario) -> str:
    """Qué facturas puede ver el usuario:
    - "todas": admin.
    - "cliente": las que creó + las que tienen su cliente_id (sin las `emitida`).
    - "creadas": cualquier otro (bodeguero...): solo las que creó."""
    if usuario.rol.nombre == "admin":
        return "todas"
    return "cliente" if es_cliente(usuario) else "creadas"


def puede_ver_factura(orden: Orden, usuario: Usuario) -> bool:
    """La misma regla de queries.filtro_dueno, pero sobre una factura ya cargada."""
    alcance = alcance_facturas(usuario)
    if alcance == "todas" or orden.bodeguero_id == usuario.id:
        return True
    return alcance == "cliente" and orden.cliente_id == usuario.id and orden.estado_orden != "emitida"


def get_factura_or_404(db: Session, factura_id: int, usuario: Usuario) -> Orden:
    """Devuelve la factura si existe y el usuario puede verla; si no es suya responde 404 (no 403),
    para no revelar que existe aunque tenga el link directo."""
    orden = queries.obtener_completa(db, factura_id)
    if orden is None or not puede_ver_factura(orden, usuario):
        raise errors.factura_no_encontrada()
    return orden


def cargar_factura(db: Session, factura_id: int) -> dict:
    """Recarga la factura (con bodega, bodeguero y líneas) para responder después de una acción.
    No aplica el filtro de visibilidad: quien la acaba de crear o modificar siempre recibe el resultado."""
    return factura_salida(queries.obtener_completa(db, factura_id))


def validar_cliente_de_la_factura(orden: Orden, usuario: Usuario) -> None:
    """Solo el cliente de la factura puede aceptarla o rechazarla (ni siquiera el admin en su nombre)."""
    if orden.cliente_id != usuario.id:
        raise errors.solo_el_cliente()


def validar_estado(orden: Orden, *permitidos: str) -> None:
    """Lanza 400 si la factura no está en alguno de los estados permitidos."""
    if orden.estado_orden not in permitidos:
        raise errors.estado_invalido()


def validate_cliente(db: Session, cliente_id: int) -> Usuario:
    """El adquiriente debe ser un usuario con rol cliente y activo."""
    cliente = queries.cliente_activo(db, cliente_id)
    if cliente is None:
        raise errors.cliente_invalido()
    return cliente


def validate_bodega(db: Session, bodega_id: int, usuario: Usuario) -> Bodega:
    """La bodega debe existir, estar activa y, si factura un bodeguero, ser suya."""
    bodega = queries.obtener_bodega(db, bodega_id)
    ajena = usuario.rol.nombre == "bodeguero" and bodega is not None and bodega.bodeguero_id != usuario.id
    if bodega is None or not bodega.estado or ajena:
        raise errors.bodega_invalida()
    return bodega


def validate_tipos(db: Session, lineas, bodega_id: int) -> None:
    """Todos los tipo_id de las líneas deben existir y ser de la bodega de la factura (o no tener bodega)."""
    ids = {linea.tipo_id for linea in lineas if linea.tipo_id is not None}
    if not ids:
        return
    tipos = queries.tipos_por_ids(db, ids)
    if len(tipos) != len(ids):
        raise errors.tipos_no_existen()
    if any(t.bodega_id not in (None, bodega_id) for t in tipos):
        raise errors.tipos_de_otra_bodega()


def sellar(orden: Orden) -> None:
    """Recalcula totales y la validación electrónica simulada (CUFE)."""
    actualizar_totales(orden)
    orden.cufe = generar_cufe(orden)
    orden.fecha_validacion = datetime.now().replace(microsecond=0)
