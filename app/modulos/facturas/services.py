# Lógica de cada endpoint de Facturas. El router solo recibe la petición y llama a estas funciones.
from sqlalchemy.orm import Session

from app.modulos.facturas import errors, helpers, queries
from app.modulos.facturas.emisor import MONEDA, PREFIJO_FACTURA
from app.modulos.facturas.helpers import (ahora, cargar_factura, get_factura_or_404, sellar,
                                          validar_cliente_de_la_factura, validar_estado, validate_bodega,
                                          validate_cliente, validate_tipos)
from app.modulos.facturas.models import ESTADOS_ORDEN, Orden
from app.modulos.facturas.pdf import generar_pdf
from app.modulos.facturas.schemas import (ClienteOpcion, ClientePaginado, FacturaCreate, FacturaPaginado,
                                          FacturaResumen, FacturaUpdate, FirmaIn, RechazoIn)
from app.modulos.usuarios.models import Usuario


def listar_facturas(q: str | None, estado: str | None, page: int, limit: int, db: Session, usuario: Usuario):
    """Lista las facturas. El cliente solo ve las suyas (y no los borradores)."""
    if estado is not None:
        estado = estado.strip().lower()
        if estado not in ESTADOS_ORDEN:
            raise errors.estado_filtro_invalido()

    # El dueño sale del token: admin todas, cliente las suyas, los demás solo las que crearon
    total, ordenes = queries.listar(db, alcance=helpers.alcance_facturas(usuario), usuario_id=usuario.id,
                                    q=q, estado=estado, page=page, limit=limit)
    return FacturaPaginado(
        data=[FacturaResumen(**helpers.factura_resumen(o)) for o in ordenes],
        total=total, page=page, limit=limit,
    )


def listar_clientes_para_facturar(q: str | None, page: int, limit: int, db: Session, usuario: Usuario):
    """Clientes activos (datos mínimos) para el selector de cliente de la factura."""
    total, clientes = queries.listar_clientes(db, q=q, page=page, limit=limit)
    return ClientePaginado(
        data=[ClienteOpcion.model_validate(c) for c in clientes],
        total=total, page=page, limit=limit,
    )


def obtener_factura(factura_id: int, db: Session, usuario: Usuario):
    """Devuelve una factura por su id (con las reglas de visibilidad del cliente)."""
    return helpers.factura_salida(get_factura_or_404(db, factura_id, usuario))


def descargar_pdf(factura_id: int, db: Session, usuario: Usuario) -> tuple[str, bytes]:
    """Genera el PDF de la factura. Devuelve (número de la factura, contenido del PDF)."""
    orden = get_factura_or_404(db, factura_id, usuario)
    return orden.numero, generar_pdf(helpers.factura_salida(orden))


def crear_factura(datos: FacturaCreate, db: Session, usuario: Usuario):
    """Crea la factura en estado emitida, con su número, sus líneas, sus totales y su CUFE."""
    cliente = validate_cliente(db, datos.cliente_id)
    validate_bodega(db, datos.bodega_id, usuario)
    validate_tipos(db, datos.detalle, datos.bodega_id)

    consecutivo = queries.siguiente_consecutivo(db)
    orden = Orden(
        prefijo=PREFIJO_FACTURA,
        consecutivo=consecutivo,
        numero=helpers.formatear_numero(consecutivo),
        fecha_emision=ahora(),
        fecha_vencimiento=datos.fecha_vencimiento,
        moneda=MONEDA,
        forma_pago=datos.forma_pago,
        medio_pago=datos.medio_pago or None,
        bodega_id=datos.bodega_id,
        cliente_id=cliente.id,
        bodeguero_id=usuario.id,
        emisor_datos=helpers.datos_emisor(),
        adquiriente_datos=helpers.datos_adquiriente(cliente),
        observaciones=datos.observaciones or None,
        estado_orden="emitida",
        detalles=helpers.armar_detalles(datos.detalle),
        creado_por=usuario.id,
        actualizado_por=usuario.id,
    )
    sellar(orden)
    db.add(orden)
    db.commit()
    return cargar_factura(db, orden.id)


def actualizar_factura(datos: FacturaUpdate, factura_id: int, db: Session, usuario: Usuario):
    """Edita una factura en estado emitida y recalcula totales y CUFE."""
    orden = get_factura_or_404(db, factura_id, usuario)
    validar_estado(orden, "emitida")
    cambios = datos.model_dump(exclude_none=True, exclude={"detalle"})

    if "cliente_id" in cambios:
        cliente = validate_cliente(db, cambios["cliente_id"])
        orden.adquiriente_datos = helpers.datos_adquiriente(cliente)
    if "bodega_id" in cambios:
        validate_bodega(db, cambios["bodega_id"], usuario)
    if cambios.get("observaciones") == "":
        cambios["observaciones"] = None  # "" borra las observaciones

    for campo, valor in cambios.items():
        setattr(orden, campo, valor)

    if orden.forma_pago == "credito" and orden.fecha_vencimiento is None:
        raise errors.fecha_vencimiento_obligatoria()

    if datos.detalle is not None:
        validate_tipos(db, datos.detalle, orden.bodega_id)
        orden.detalles = helpers.armar_detalles(datos.detalle)  # reemplaza todas las líneas
    elif "bodega_id" in cambios:
        validate_tipos(db, orden.detalles, orden.bodega_id)  # si cambia la bodega, las líneas actuales deben servir

    sellar(orden)
    orden.actualizado_por = usuario.id
    db.commit()
    return cargar_factura(db, factura_id)


def entregar_factura(factura_id: int, db: Session, usuario: Usuario):
    orden = get_factura_or_404(db, factura_id, usuario)
    validar_estado(orden, "emitida")
    orden.estado_orden = "entregada"
    orden.fecha_entrega = ahora()
    orden.actualizado_por = usuario.id
    db.commit()
    return cargar_factura(db, factura_id)


def aceptar_factura(datos: FirmaIn, factura_id: int, db: Session, usuario: Usuario):
    orden = get_factura_or_404(db, factura_id, usuario)
    validar_cliente_de_la_factura(orden, usuario)
    validar_estado(orden, "entregada")
    orden.estado_orden = "firmada"
    orden.firma = datos.firma
    orden.fecha_respuesta = ahora()
    orden.actualizado_por = usuario.id
    db.commit()
    return cargar_factura(db, factura_id)


def rechazar_factura(datos: RechazoIn, factura_id: int, db: Session, usuario: Usuario):
    orden = get_factura_or_404(db, factura_id, usuario)
    validar_cliente_de_la_factura(orden, usuario)
    validar_estado(orden, "entregada")
    orden.estado_orden = "rechazada"
    orden.motivo_rechazo = datos.motivo
    orden.fecha_respuesta = ahora()
    orden.actualizado_por = usuario.id
    db.commit()
    return cargar_factura(db, factura_id)


def recibir_factura(factura_id: int, db: Session, usuario: Usuario):
    orden = get_factura_or_404(db, factura_id, usuario)
    validar_estado(orden, "firmada")
    orden.estado_orden = "recibida"
    orden.fecha_recepcion = ahora()
    orden.actualizado_por = usuario.id
    db.commit()
    return cargar_factura(db, factura_id)


def eliminar_factura(factura_id: int, db: Session, usuario: Usuario):
    orden = get_factura_or_404(db, factura_id, usuario)
    validar_estado(orden, "emitida")
    db.delete(orden)  # las líneas se borran en cascada
    db.commit()
