# Genera el PDF de una factura con fpdf2 a partir del dict que arma services/facturas.factura_salida
import base64
import io
from decimal import Decimal

from fpdf import FPDF

FIRMA_PREFIJO = "data:image/png;base64,"


def _t(valor) -> str:
    """Texto seguro para las fuentes básicas del PDF (latin-1). None -> ''."""
    if valor is None:
        return ""
    return str(valor).encode("latin-1", "replace").decode("latin-1")


def _dinero(valor) -> str:
    """36750.5 -> '$ 36.750,50' (formato colombiano)."""
    texto = f"{Decimal(valor):,.2f}"  # 36,750.50
    return "$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _numero(valor) -> str:
    """Cantidades y porcentajes sin ceros de sobra: 10.00 -> '10', 2.50 -> '2,5'."""
    texto = f"{Decimal(valor).normalize():f}"
    return texto.replace(".", ",")


def _fecha(valor) -> str:
    if valor is None:
        return ""
    return valor.strftime("%Y-%m-%d %H:%M") if hasattr(valor, "hour") else valor.strftime("%Y-%m-%d")


class _PdfFactura(FPDF):
    def __init__(self, factura: dict):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.factura = factura
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(12, 12, 12)

    def footer(self):
        """Pie de página: texto legal, software y número de página."""
        self.set_y(-20)
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(90)
        self.multi_cell(0, 3, _t(self.factura["pie_pagina"]), align="C", new_x="LMARGIN", new_y="NEXT")
        sw = self.factura["software"]
        self.cell(0, 3, _t(f"Software: {sw['nombre']} v{sw['version']} - {sw['fabricante']}   |   Página {self.page_no()}/{{nb}}"),
                  align="C")
        self.set_text_color(0)


def _titulo(pdf: FPDF, texto: str):
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 236, 245)
    pdf.cell(0, 6, _t(texto), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)


def _par(pdf: FPDF, etiqueta: str, valor, ancho_etiqueta=40):
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(ancho_etiqueta, 5, _t(etiqueta))
    pdf.set_font("Helvetica", "", 8.5)
    pdf.multi_cell(0, 5, _t(valor), new_x="LMARGIN", new_y="NEXT")


def _unir(*partes) -> str:
    """Une con " | " solo las partes que tienen algo."""
    return "  |  ".join(p for p in partes if p)


def generar_pdf(f: dict) -> bytes:
    """Devuelve los bytes del PDF de la factura."""
    pdf = _PdfFactura(f)
    pdf.alias_nb_pages()
    pdf.add_page()
    emisor, adq, bodega = f["emisor"], f["adquiriente"], f["bodega"]

    # Encabezado: emisor a la izquierda, número de factura a la derecha
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(120, 7, _t(emisor.get("razon_social")))
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, _t("FACTURA DE VENTA"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    nit = "-".join(filter(None, [emisor.get("nit"), emisor.get("dv")]))
    pdf.cell(120, 4.5, _t(_unir(f"NIT {nit}" if nit else None, emisor.get("regimen"))))
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 4.5, _t(f["numero"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    lugar = ", ".join(filter(None, [emisor.get("ciudad"), emisor.get("departamento")]))
    pdf.cell(120, 4.5, _t(" - ".join(filter(None, [emisor.get("direccion"), lugar]))))
    pdf.cell(0, 4.5, _t(f"Estado: {f['estado'].upper()}"), align="R", new_x="LMARGIN", new_y="NEXT")
    responsabilidad = emisor.get("responsabilidad_fiscal")
    pdf.cell(0, 4.5, _t(_unir(f"Tel. {emisor['telefono']}" if emisor.get("telefono") else None, emisor.get("correo"),
                              f"Resp. fiscal: {responsabilidad}" if responsabilidad else None)), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Datos generales
    _titulo(pdf, "Datos de la factura")
    _par(pdf, "Fecha de emisión:", _fecha(f["fecha_emision"]))
    if f.get("fecha_vencimiento"):
        _par(pdf, "Fecha de vencimiento:", _fecha(f["fecha_vencimiento"]))
    _par(pdf, "Forma / medio de pago:", f"{f['forma_pago']} / {f.get('medio_pago') or '-'}")
    _par(pdf, "Moneda:", f["moneda"])
    pdf.ln(2)

    # Adquiriente
    _titulo(pdf, "Adquiriente (cliente)")
    _par(pdf, "Nombre:", adq.get("nombre"))
    _par(pdf, "Documento:", f"{adq.get('tipo_documento') or ''} {adq.get('numero_documento') or ''}".strip() or "-")
    _par(pdf, "Dirección:", f"{adq.get('direccion') or '-'} {('- ' + adq['ciudad']) if adq.get('ciudad') else ''}")
    _par(pdf, "Teléfono / correo:", f"{adq.get('telefono') or '-'} / {adq.get('correo') or '-'}")
    pdf.ln(2)

    # Bodega
    _titulo(pdf, "Bodega de despacho")
    _par(pdf, "Bodega:", f"{bodega.get('nombre')} {('(' + bodega['codigo'] + ')') if bodega.get('codigo') else ''}")
    _par(pdf, "Dirección:", f"{bodega.get('direccion') or '-'} {('- ' + bodega['ciudad']) if bodega.get('ciudad') else ''}")
    if bodega.get("correo"):
        _par(pdf, "Correo:", bodega["correo"])
    if bodega.get("recibe_nombre"):
        _par(pdf, "Recibe:", f"{bodega['recibe_nombre']} {bodega.get('recibe_documento') or ''} "
                             f"{('- ' + bodega['recibe_cargo']) if bodega.get('recibe_cargo') else ''}")
    pdf.ln(2)

    # Detalle
    _titulo(pdf, "Detalle")
    columnas = [("#", 8, "C"), ("Descripción", 62, "L"), ("Und", 12, "C"), ("Cant.", 16, "R"),
                ("Precio unit.", 26, "R"), ("Desc. %", 14, "R"), ("IVA %", 12, "R"), ("Total", 0, "R")]
    pdf.set_font("Helvetica", "B", 8)
    for nombre, ancho, alin in columnas:
        pdf.cell(ancho, 6, _t(nombre), border="B", align=alin)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for d in f["detalle"]:
        valores = [str(d["linea"]), d["descripcion"][:48], d["unidad_medida"], _numero(d["cantidad"]),
                   _dinero(d["precio_unitario"]), _numero(d["descuento_porcentaje"]), _numero(d["iva_porcentaje"]),
                   _dinero(d["total_linea"])]
        for (nombre, ancho, alin), valor in zip(columnas, valores):
            pdf.cell(ancho, 5.5, _t(valor), align=alin)
        pdf.ln()
    pdf.ln(2)

    # Totales a la derecha
    tot = f["totales"]
    for etiqueta, valor, negrita in [("Subtotal", tot["subtotal"], False), ("Descuentos", tot["total_descuento"], False),
                                     ("Base gravable", tot["base_gravable"], False), ("IVA", tot["total_iva"], False),
                                     ("TOTAL A PAGAR", tot["total"], True)]:
        pdf.set_font("Helvetica", "B" if negrita else "", 9.5 if negrita else 8.5)
        pdf.cell(150, 5.5, _t(etiqueta), align="R")
        pdf.cell(0, 5.5, _t(_dinero(valor)), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    if f.get("observaciones"):
        _titulo(pdf, "Observaciones")
        pdf.multi_cell(0, 4.5, _t(f["observaciones"]), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # Validación electrónica (simulada)
    val = f["validacion_electronica"]
    _titulo(pdf, "Validación electrónica (SIMULADA)")
    pdf.set_font("Helvetica", "", 7)
    pdf.multi_cell(0, 3.8, _t(f"CUFE: {val.get('cufe') or '-'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 3.8, _t(f"Fecha de validación: {_fecha(val.get('fecha_validacion'))}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Trazabilidad y firma
    tr = f["trazabilidad"]
    _titulo(pdf, "Trazabilidad")
    _par(pdf, "Emitida por:", tr.get("creada_por") or "-")
    _par(pdf, "Entregada:", _fecha(tr.get("fecha_entrega")) or "-")
    _par(pdf, "Respuesta del cliente:", _fecha(tr.get("fecha_respuesta")) or "-")
    if tr.get("motivo_rechazo"):
        _par(pdf, "Motivo de rechazo:", tr["motivo_rechazo"])
    _par(pdf, "Recibida firmada:", _fecha(tr.get("fecha_recepcion")) or "-")

    firma = tr.get("firma")
    if firma and firma.startswith(FIRMA_PREFIJO):
        pdf.ln(2)
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(0, 5, _t("Firma del cliente:"), new_x="LMARGIN", new_y="NEXT")
        try:
            imagen = io.BytesIO(base64.b64decode(firma[len(FIRMA_PREFIJO):]))
            pdf.image(imagen, w=60)
        except Exception:
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(0, 5, _t("(no se pudo mostrar la imagen de la firma)"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(60, 4, _t(adq.get("nombre")), border="T", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
