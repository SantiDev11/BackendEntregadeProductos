# T18: el emisor de cada factura (JSON, CUFE, QR y PDF) es su empresa. Sin empresa, el emisor por defecto de emisor.py.
import pytest
from conftest import SessionLocal
from test_t7_aislamiento import datos_factura, m  # noqa: F401  (m es el fixture)

from app.modulos import Empresa, Orden
from app.modulos.facturas import pdf
from app.modulos.facturas.emisor import EMISOR
from app.modulos.facturas.helpers import generar_cufe

DATOS_X = {"razon_social": "Distribuidora X S.A.S.", "nit": "901234567", "dv": "8", "direccion": "Cra 15 # 45-10",
           "telefono": "6077001122", "correo": "facturas@x.com"}


def emisor_esperado(d):
    return {"nit": d["nit"], "dv": d["dv"], "razon_social": d["razon_social"], "nombre_comercial": None, "direccion": d["direccion"],
            "ciudad": None, "departamento": None, "telefono": d["telefono"], "correo": d["correo"], "regimen": None,
            "responsabilidad_fiscal": None}


def poner_datos(empresa_id, **datos):
    with SessionLocal() as s:
        e = s.get(Empresa, empresa_id)
        for k, v in datos.items():
            setattr(e, k, v)
        s.commit()


def nueva_factura(m, quien="bX", bodega="bodega bX", tipo="tipo bX"):
    return m.crear("/facturas", quien, datos_factura(m.id["usuario c1"], m.id[bodega], m.id[tipo]))


def detalle(m, f):
    return m.pedir("admin", "GET", f"/facturas/{f}").json()


@pytest.fixture
def textos_pdf(monkeypatch):
    """Textos que escribe el PDF (va comprimido, así que se leen al escribirlos)."""
    escritos = []
    original = pdf._PdfFactura.cell

    def cell(self, *args, **kwargs):
        texto = kwargs.get("text", args[2] if len(args) > 2 else "")
        escritos.append(str(texto))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(pdf._PdfFactura, "cell", cell)
    return escritos


def test_la_factura_sale_con_los_datos_de_su_empresa(m, textos_pdf):
    poner_datos(m.id["empresa X"], **DATOS_X)
    f = nueva_factura(m)
    d = detalle(m, f)
    assert d["emisor"] == emisor_esperado(DATOS_X)
    assert f"NitFac:{DATOS_X['nit']} " in d["validacion_electronica"]["qr"]  # el QR (y el CUFE) usan su NIT
    r = m.pedir("admin", "GET", f"/facturas/{f}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    encabezado = textos_pdf[:8]
    assert DATOS_X["razon_social"] in encabezado
    assert "NIT 901234567-8" in encabezado
    assert "Cra 15 # 45-10" in encabezado  # sin " - , " por la ciudad que no tiene
    assert "Tel. 6077001122  |  facturas@x.com" in encabezado  # sin "Resp. fiscal:" vacío
    assert not any("Demo" in t for t in textos_pdf)


def test_sin_empresa_sale_el_emisor_por_defecto(m, textos_pdf):
    f = nueva_factura(m, "bV", "bodega bV", "tipo bV")  # bV: bodeguero anterior a las empresas
    d = detalle(m, f)
    assert d["emisor"] == {k: v for k, v in EMISOR.items()}
    assert m.pedir("admin", "GET", f"/facturas/{f}/pdf").status_code == 200
    assert EMISOR["razon_social"] in textos_pdf and f"NIT {EMISOR['nit']}-{EMISOR['dv']}  |  {EMISOR['regimen']}" in textos_pdf


def test_la_factura_conserva_el_emisor_de_cuando_se_emitio(m):
    poner_datos(m.id["empresa X"], **DATOS_X)
    f = nueva_factura(m)
    cufe = detalle(m, f)["validacion_electronica"]["cufe"]
    poner_datos(m.id["empresa X"], razon_social="Otro Nombre S.A.S.", telefono="3000000000")
    assert detalle(m, f)["emisor"] == emisor_esperado(DATOS_X)                     # la emitida no cambia
    assert detalle(m, f)["validacion_electronica"]["cufe"] == cufe
    assert detalle(m, nueva_factura(m))["emisor"]["razon_social"] == "Otro Nombre S.A.S."  # la nueva sí
    # editarla tampoco le cambia el emisor
    assert m.pedir("bX", "PUT", f"/facturas/{f}", {"observaciones": "editada"}).status_code == 200
    assert detalle(m, f)["emisor"] == emisor_esperado(DATOS_X)


def test_si_el_admin_la_pasa_a_otra_empresa_cambia_el_emisor(m):
    poner_datos(m.id["empresa X"], **DATOS_X)
    datos_y = {**DATOS_X, "razon_social": "Mayorista Y Ltda.", "nit": "800765432", "dv": "1", "correo": "y@y.com"}
    poner_datos(m.id["empresa Y"], **datos_y)
    f = nueva_factura(m)
    def a_la_bodega(b):  # con una línea de un tipo de la bodega de destino
        return {"bodega_id": m.id[f"bodega {b}"], "detalle": datos_factura(0, 0, m.id[f"tipo {b}"])["detalle"]}
    assert m.pedir("admin", "PUT", f"/facturas/{f}", a_la_bodega("bY")).status_code == 200
    d = detalle(m, f)
    assert d["emisor"] == emisor_esperado(datos_y) and f"NitFac:{datos_y['nit']} " in d["validacion_electronica"]["qr"]
    assert m.pedir("admin", "PUT", f"/facturas/{f}", a_la_bodega("bV")).status_code == 200  # a una bodega sin empresa
    assert detalle(m, f)["emisor"] == EMISOR


# ===== MIGRACIÓN 009: las facturas que ya salieron con el emisor demo =====

def test_la_migracion_corrige_las_facturas_viejas_de_cada_empresa(m):
    import json
    from pathlib import Path

    from conftest import correr_script, engine
    from sqlalchemy import text
    from app.modulos.facturas.emisor import RESOLUCION
    script = Path(__file__).parent.parent / "migraciones" / "009_emisor_por_empresa.py"
    poner_datos(m.id["empresa X"], **DATOS_X)
    demo = json.dumps({**EMISOR, "resolucion": {**RESOLUCION, "numero": "VIEJA"}})
    vieja = nueva_factura(m)
    with engine.begin() as c:  # como quedaron las de antes del cambio: con el emisor demo
        c.execute(text("UPDATE ordenes SET emisor_datos = :e, cufe = 'CUFE-CON-NIT-DEMO', actualizado_en = '2026-01-02 03:04:05' "
                       "WHERE id IN :ids"),
                  {"e": demo, "ids": (vieja, m.id["factura bX"], m.id["factura bV"])})
    foto = lambda: {f: detalle(m, f) for f in (vieja, m.id["factura bX"], m.id["factura bV"], m.id["factura bY"])}
    antes = foto()

    r = correr_script(script)  # simulación: no guarda nada
    assert r.returncode == 0 and "Facturas con empresa y emisor demo: 2" in r.stdout and "no se guardó nada" in r.stdout, r.stdout + r.stderr
    assert foto() == antes

    r = correr_script(script, "--aplicar")
    assert r.returncode == 0 and "Quedan con emisor demo: 0" in r.stdout, r.stdout + r.stderr
    despues = foto()
    assert despues[vieja]["emisor"] == emisor_esperado(DATOS_X)
    assert antes[vieja]["validacion_electronica"]["cufe"] == "CUFE-CON-NIT-DEMO"
    with SessionLocal() as s:  # recalculado con el NIT de la empresa
        o = s.get(Orden, vieja)
        assert o.cufe == generar_cufe(o) and o.emisor_datos["nit"] == DATOS_X["nit"]
    assert f"NitFac:{DATOS_X['nit']} " in despues[vieja]["validacion_electronica"]["qr"]
    assert "VIEJA" in despues[vieja]["pie_pagina"]                       # conserva la resolución que se copió al emitirla
    assert despues[m.id["factura bX"]]["emisor"]["razon_social"] == DATOS_X["razon_social"]
    assert despues[m.id["factura bV"]] == antes[m.id["factura bV"]]      # sin empresa: sigue con el emisor por defecto
    assert despues[m.id["factura bY"]] == antes[m.id["factura bY"]]      # ya tenía su empresa: no se toca
    for clave in ("numero", "totales", "detalle", "adquiriente"):
        assert despues[vieja][clave] == antes[vieja][clave], clave
    with engine.connect() as c:
        assert str(c.execute(text("SELECT actualizado_en FROM ordenes WHERE id = :i"), {"i": vieja}).scalar()) == "2026-01-02 03:04:05"

    r = correr_script(script, "--aplicar")  # repetirla no cambia nada
    assert "Facturas con empresa y emisor demo: 0" in r.stdout and foto() == despues
