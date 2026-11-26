# T13: panel de estadísticas por rol (especificación del frontend): kpis, desglose, serie, alertas, filtros y aislamiento.
from datetime import date, datetime, timedelta

import pytest
from conftest import SessionLocal, entrar
from sqlalchemy import event
from test_t7_aislamiento import CLAVE, datos_bodega, datos_factura, foto, m  # noqa: F401  (m es el fixture)
from test_t11_aislamiento import MARCA, SENTIDOS, e, sin_rastro  # noqa: F401  (e es el fixture)

from app.config.main import app
from app.core.security import hash_password
from app.modulos import Empresa, Orden, Permiso, Rol, Usuario
from app.modulos.estadisticas.helpers import efectividad, porcentaje

RUTA = "/estadisticas/resumen"
SIN_PERMISO = (403, {"detail": "No tiene permiso para esta acción"})
VACIOS = {"empresas": [], "bodegas": [], "bodegueros": [], "tipos": []}

# Escenario (por empresa): el bodeguero 1 tiene 5 facturas en la bodega UNO, una en cada estado, para cliente1;
# el bodeguero 2 tiene 1 emitida en la bodega DOS para cliente2; la bodega SINDUENO no tiene facturas.


def panel(x, quien, **p):
    r = x.pedir(quien, "GET", RUTA, **p)
    assert r.status_code == 200, (quien, p, r.text)
    return r.json()


def valores(d):
    return {k["clave"]: k["valor"] for k in d["kpis"]}


def alertas(d):
    return {k["clave"] for k in d["kpis"] if k["alerta"]}


def filas(d):
    return [tuple(f.values()) for f in d["desglose_principal"]["filas"]]


def nombres(d):
    return {lista: [o["nombre"] for o in opciones] for lista, opciones in d["filtros_disponibles"].items()}


def mover(orden_id, **campos):
    with SessionLocal() as s:
        o = s.get(Orden, orden_id)
        for c, v in campos.items():
            setattr(o, c, v)
        s.commit()


# ===== FORMA DE LA RESPUESTA =====

def test_la_forma_es_la_misma_para_los_4_roles(e):
    for quien, rol in (("admin", "admin"), ("A", "empresa"), ("A1", "bodeguero"), ("cliente1", "cliente")):
        d = panel(e, quien)
        assert list(d) == ["generado_para", "periodo", "filtros_disponibles", "kpis", "desglose_principal", "serie_temporal",
                           "alertas_detalle", "tarjetas", "series"]
        assert d["generado_para"] == rol and list(d["filtros_disponibles"]) == ["empresas", "bodegas", "bodegueros", "tipos"]
        assert len(d["kpis"]) == 4 and all(list(k) == ["clave", "titulo", "valor", "formato", "alerta"] for k in d["kpis"])
        assert all(k["formato"] in ("numero", "porcentaje") and isinstance(k["alerta"], bool) and k["titulo"] for k in d["kpis"])
        assert list(d["desglose_principal"]) == ["titulo", "columnas", "filas"] and d["desglose_principal"]["filas"]
        for f in d["desglose_principal"]["filas"]:
            assert len(f) == len(d["desglose_principal"]["columnas"])
        assert d["serie_temporal"] and all(list(p) == ["fecha", "completadas", "rechazadas"] for p in d["serie_temporal"])


# ===== PANEL DE CADA ROL =====

def test_panel_admin(e):
    d = panel(e, "admin")
    assert valores(d) == {"empresas_activas": 2, "empresas_pendientes": 0, "clientes_globales": 3, "tasa_entrega_global": 33.3}
    assert [k["formato"] for k in d["kpis"]] == ["numero", "numero", "numero", "porcentaje"] and alertas(d) == set()
    assert (d["desglose_principal"]["titulo"], d["desglose_principal"]["columnas"]) == (
        "Top Empresas por Volumen", ["Empresa", "Bodegas", "Facturas", "Rechazadas", "Efectividad"])
    assert d["desglose_principal"]["filas"][0] == {"nombre": "Alfa SAS", "bodegas": 3, "facturas": 6, "rechazadas": 1, "efectividad": "33.3%"}
    assert filas(d) == [("Alfa SAS", 3, 6, 1, "33.3%"), ("Beta SAS", 3, 6, 1, "33.3%")]
    assert nombres(d) == {**VACIOS, "empresas": ["Alfa SAS", "Beta SAS"]} and d["alertas_detalle"] == []
    e.api.post("/register", json={"tipo": "empresa", "razon_social": "Nueva", "nit": "800111222-3", "telefono": "3001234567", "direccion": "C",
                                  "representante": "R", "correo": "n@n.com", "contrasena": CLAVE})
    d = panel(e, "admin")
    assert valores(d)["empresas_pendientes"] == 1 and alertas(d) == {"empresas_pendientes"}
    assert filas(d)[-1] == ("Nueva", 0, 0, 0, "0.0%")


@SENTIDOS
def test_panel_empresa(e, yo, otra):
    d, x = panel(e, yo), MARCA[yo]
    assert valores(d) == {"total_facturas": 6, "pendientes_cierre": 3, "tasa_aceptacion": 33.3, "tasa_rechazo": 16.7}
    assert alertas(d) == {"pendientes_cierre", "tasa_rechazo"}
    assert [k["formato"] for k in d["kpis"]] == ["numero", "numero", "porcentaje", "porcentaje"]
    assert (d["desglose_principal"]["titulo"], d["desglose_principal"]["columnas"]) == (
        "Rendimiento por Bodega", ["Bodega", "Emitidas", "Completadas", "Rechazadas", "Efectividad"])
    assert d["desglose_principal"]["filas"][0] == {"nombre": f"Bodega UNO {x}", "emitidas": 5, "completadas": 2, "rechazadas": 1, "efectividad": "40.0%"}
    assert filas(d)[1:] == [(f"Bodega DOS {x}", 1, 0, 0, "0.0%"), (f"Bodega SINDUENO {x}", 0, 0, 0, "0.0%")]
    assert nombres(d) == {"empresas": [], "bodegas": [f"Bodega DOS {x}", f"Bodega SINDUENO {x}", f"Bodega UNO {x}"],
                          "bodegueros": [f"Bod 1 {x}", f"Bod 2 {x}"], "tipos": [f"Producto {n} {x}" for n in range(3)]}
    assert {o["id"] for o in d["filtros_disponibles"]["bodegas"]} == set(e.ids[yo]["bodega"])
    rechazada = e.ids[yo]["factura"][3]
    assert d["alertas_detalle"] == [{"factura_id": rechazada, "numero_factura": "FE-0004", "motivo_rechazo": "No era lo pedido",
                                     "fecha": date.today().isoformat()}]


@SENTIDOS
def test_panel_bodeguero(e, yo, otra):
    d, x = panel(e, yo + "1"), MARCA[yo]
    assert valores(d) == {"por_despachar": 1, "sin_firma": 1, "completadas": 2, "rechazadas": 1} and alertas(d) == set()
    assert (d["desglose_principal"]["titulo"], d["desglose_principal"]["columnas"]) == (
        "Actividad por Tipo de Producto", ["Tipo Producto", "Emitidas", "Completadas", "Rechazadas"])
    assert d["desglose_principal"]["filas"] == [{"nombre": f"Producto 0 {x}", "emitidas": 5, "completadas": 2, "rechazadas": 1}]
    assert nombres(d) == {**VACIOS, "tipos": [f"Producto 0 {x}"]}  # solo los de sus bodegas
    assert [a["factura_id"] for a in d["alertas_detalle"]] == [e.ids[yo]["factura"][3]]
    d = panel(e, yo + "2")
    assert valores(d) == {"por_despachar": 1, "sin_firma": 0, "completadas": 0, "rechazadas": 0} and d["alertas_detalle"] == []
    assert filas(d) == [(f"Producto 1 {x}", 1, 0, 0)]


def test_panel_cliente(e):
    d = panel(e, "cliente1")  # 4 de cada empresa: nunca las emitidas, que no ve
    assert valores(d) == {"pendientes_accion": 2, "recibidas_total": 4, "rechazadas_total": 2, "empresas_proveedoras": 2} and alertas(d) == set()
    assert (d["desglose_principal"]["titulo"], d["desglose_principal"]["columnas"]) == (
        "Resumen por Empresa Proveedora", ["Empresa", "Total Facturas", "Aceptadas", "Rechazadas"])
    assert d["desglose_principal"]["filas"] == [{"nombre": f"{x} SAS", "total_facturas": 4, "aceptadas": 2, "rechazadas": 1} for x in ("Alfa", "Beta")]
    assert nombres(d) == {**VACIOS, "empresas": ["Alfa SAS", "Beta SAS"]} and d["alertas_detalle"] == []
    d = panel(e, "cliente2")  # sus dos facturas siguen emitidas: ni un rastro
    assert valores(d) == {"pendientes_accion": 0, "recibidas_total": 0, "rechazadas_total": 0, "empresas_proveedoras": 0}
    assert d["desglose_principal"]["filas"] == [] and nombres(d) == VACIOS and all(p["completadas"] == p["rechazadas"] == 0 for p in d["serie_temporal"])


def test_un_rol_personalizado_recibe_el_panel_del_bodeguero(m):
    with SessionLocal() as s:
        rol = Rol(nombre="GERENTE")
        s.add(rol); s.flush()
        s.add(Usuario(nombre="G", correo="g@g.com", contrasena=hash_password(CLAVE), rol_id=rol.id,
                      permisos=s.query(Permiso).filter(Permiso.nombre == "estadisticas_view").all()))
        s.commit()
    m.h["g"] = entrar(m.api, "g@g.com", CLAVE)
    d = panel(m, "g")
    assert d["generado_para"] == "GERENTE" and valores(d) == {"por_despachar": 0, "sin_firma": 0, "completadas": 0, "rechazadas": 0}
    assert d["desglose_principal"]["filas"] == [] and nombres(d) == VACIOS


def test_facturas_sin_empresa(m):
    """Las anteriores a las empresas: cuentan en el total del admin y el cliente las ve como "Sin empresa"."""
    for b in ("bX", "bV"):
        m.pedir(b, "POST", f"/facturas/{m.id[f'factura {b}']}/entregar")
    d = panel(m, "c1")
    assert filas(d) == [("Sin empresa", 1, 0, 0), ("Empresa X", 1, 0, 0)] or filas(d) == [("Empresa X", 1, 0, 0), ("Sin empresa", 1, 0, 0)]
    assert valores(d)["empresas_proveedoras"] == 1 and nombres(d)["empresas"] == ["Empresa X"]
    assert [f[0] for f in filas(panel(m, "admin"))] == ["Empresa X", "Empresa Y"]
    assert sum(valores(panel(m, "bV")).values()) == 1 and filas(panel(m, "bV")) == [("Tipo bV", 1, 0, 0)]


def test_usuario_empresa_sin_empresa_no_ve_nada(m):
    d = panel(m, "sin")
    assert valores(d) == {"total_facturas": 0, "pendientes_cierre": 0, "tasa_aceptacion": 0, "tasa_rechazo": 0} and alertas(d) == set()
    assert d["desglose_principal"]["filas"] == [] and nombres(d) == VACIOS and d["alertas_detalle"] == []


# ===== LOS NÚMEROS CUADRAN CON LOS LISTADOS =====

def test_los_kpis_cuadran_con_get_facturas(e):
    contar = lambda quien, *estados: sum(e.pedir(quien, "GET", "/facturas", estado=s).json()["total"] for s in estados)
    for quien in ("A", "B"):
        v, total = valores(panel(e, quien)), e.pedir(quien, "GET", "/facturas").json()["total"]
        assert v["total_facturas"] == total and v["pendientes_cierre"] == contar(quien, "emitida", "entregada")
        assert v["tasa_aceptacion"] == float(porcentaje(contar(quien, "firmada", "recibida"), total))
    for quien in ("A1", "A2", "B1"):
        v = valores(panel(e, quien))
        assert v == {"por_despachar": contar(quien, "emitida"), "sin_firma": contar(quien, "entregada"),
                     "completadas": contar(quien, "firmada", "recibida"), "rechazadas": contar(quien, "rechazada")}
    v = valores(panel(e, "cliente1"))
    assert (v["pendientes_accion"], v["recibidas_total"], v["rechazadas_total"]) == (
        contar("cliente1", "entregada"), contar("cliente1", "firmada", "recibida"), contar("cliente1", "rechazada"))


def test_cada_factura_cuenta_una_vez_por_tipo(e):
    """Aunque el tipo se repita en sus líneas o la factura tenga varios tipos."""
    b = e.ids["A"]["bodega"][0]
    otro = e.crear("A", "/tipos", {"nombre": "Otro", "bodega_id": b})
    c = datos_factura(e.ids["cliente1"], b, otro)
    c["detalle"] = [c["detalle"][0], c["detalle"][0], {**c["detalle"][0], "tipo_id": e.ids["A"]["tipo"][0]}]
    e.crear("A1", "/facturas", c)
    d = panel(e, "A1")
    assert filas(d) == [("Producto 0 Alfa", 6, 2, 1), ("Otro", 1, 0, 0)] and valores(d)["por_despachar"] == 2
    d = panel(e, "A1", tipo_id=otro)
    assert filas(d) == [("Otro", 1, 0, 0)] and sum(valores(d).values()) == 1
    assert valores(panel(e, "A", tipo_id=otro))["total_facturas"] == 1


@pytest.mark.parametrize("parte,total,pct", [(0, 0, "0.0"), (0, 5, "0.0"), (5, 5, "100.0"), (1, 3, "33.3"), (2, 3, "66.7"), (86, 90, "95.6"),
                                             (54, 58, "93.1"), (1, 16, "6.3"), (1, 2000, "0.1"), (1, 8, "12.5")])
def test_porcentajes(parte, total, pct):
    assert str(porcentaje(parte, total)) == pct and efectividad(parte, total) == f"{pct}%"


def test_alerta_de_rechazo_solo_si_pasa_de_10(e):
    ids = e.ids["A"]["factura"]
    for _ in range(4):  # 10 facturas, 1 rechazada: 10 % justo
        ids.append(e.crear("A1", "/facturas", datos_factura(e.ids["cliente1"], e.ids["A"]["bodega"][0], e.ids["A"]["tipo"][0])))
    d = panel(e, "A")
    assert valores(d)["tasa_rechazo"] == 10 and "tasa_rechazo" not in alertas(d)
    e.pedir("A1", "DELETE", f"/facturas/{ids.pop()}")
    d = panel(e, "A")
    assert valores(d)["tasa_rechazo"] == 11.1 and "tasa_rechazo" in alertas(d)
    for i in ids:
        mover(i, estado_orden="recibida")
    assert alertas(panel(e, "A")) == set()


# ===== PERIODO =====

def test_periodo(e):
    hoy = date.today()
    inicio = hoy.replace(day=1)
    fin = (inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    per = lambda **p: tuple(panel(e, "A", **p)["periodo"][c] for c in ("fecha_inicio", "fecha_fin"))
    assert per() == (inicio.isoformat(), fin.isoformat())
    assert per(fecha_inicio="2026-02-10") == ("2026-02-10", "2026-02-28")
    assert per(fecha_fin="2026-02-10") == ("2026-02-01", "2026-02-10")
    assert per(fecha_inicio="2026-02-10", fecha_fin="2026-02-10") == ("2026-02-10", "2026-02-10")
    d = panel(e, "A", fecha_inicio="2026-02-10", fecha_fin="2026-03-01")["periodo"]
    assert d == {"fecha_inicio": "2026-02-10", "fecha_fin": "2026-03-01", "desde": "2026-02-10", "hasta": "2026-03-01"}


def test_los_limites_del_periodo_estan_incluidos(e):
    ids = e.ids["A"]["factura"]
    for i, f in zip(ids, (datetime(2026, 1, 31, 23, 59, 59), datetime(2026, 2, 1), datetime(2026, 2, 10, 12), datetime(2026, 2, 28, 23, 59, 59),
                          datetime(2026, 3, 1), datetime(2025, 2, 10))):
        mover(i, fecha_emision=f)
    rango = {"fecha_inicio": "2026-02-01", "fecha_fin": "2026-02-28"}
    d = panel(e, "A", **rango)
    assert valores(d)["total_facturas"] == 3 and filas(d)[0][1] == 3 and len(d["serie_temporal"]) == 28
    assert {p["fecha"]: (p["completadas"], p["rechazadas"]) for p in d["serie_temporal"] if p["completadas"] or p["rechazadas"]} == {
        "2026-02-10": (1, 0), "2026-02-28": (0, 1)}  # las de los ids 2 (firmada) y 3 (rechazada)
    assert [a["factura_id"] for a in d["alertas_detalle"]] == [ids[3]]
    assert valores(panel(e, "A", fecha_inicio="2026-03-01", fecha_fin="2026-03-01"))["total_facturas"] == 1
    assert valores(panel(e, "A", fecha_inicio="2024-01-01", fecha_fin="2024-12-31"))["total_facturas"] == 0


def test_serie_por_mes_si_el_periodo_es_largo(e):
    ids = e.ids["A"]["factura"]
    mover(ids[2], fecha_emision=datetime(2026, 1, 20)); mover(ids[4], fecha_emision=datetime(2026, 1, 5)); mover(ids[3], fecha_emision=datetime(2025, 12, 31))
    serie = lambda i, f: [tuple(p.values()) for p in panel(e, "A", fecha_inicio=i, fecha_fin=f)["serie_temporal"]]
    assert serie("2025-12-15", "2026-03-10") == [("2025-12-01", 0, 1), ("2026-01-01", 2, 0), ("2026-02-01", 0, 0), ("2026-03-01", 0, 0)]
    assert len(serie("2026-01-01", "2026-03-03")) == 62 and len(serie("2026-01-01", "2026-03-04")) == 3  # 62 días / 63 días


def test_fechas_invalidas(e):
    for quien in ("admin", "A", "A1", "cliente1"):
        r = e.pedir(quien, "GET", RUTA, fecha_inicio="2026-02-10", fecha_fin="2026-02-09")
        m_ = "debe ser igual o posterior a fecha_inicio"
        assert (r.status_code, r.json()) == (422, {"detail": f"fecha_fin: {m_}", "errores": {"fecha_fin": m_}})
        for campo in ("fecha_inicio", "fecha_fin"):
            for valor in ("ayer", "2026-13-01", "2026-02-30", "10/02/2026", ""):
                r = e.pedir(quien, "GET", RUTA, **{campo: valor})
                assert r.status_code == 422 and list(r.json()["errores"]) == [campo], (campo, valor, r.text)


def test_fechas_extremas_no_dan_500(e):
    for p in ({"fecha_fin": "9999-12-31"}, {"fecha_inicio": "9999-12-31"}, {"fecha_inicio": "0001-01-01"}, {"hasta": "9999-12-31"},
              {"fecha_inicio": "9990-01-01", "fecha_fin": "9999-12-31"}):
        for quien in ("admin", "A", "A1", "cliente1"):
            assert e.pedir(quien, "GET", RUTA, **p).status_code == 200, (quien, p)


# ===== FILTROS DE CADA ROL =====

def test_filtros_del_admin(e):
    a, b = e.empresa["A"], e.empresa["B"]
    d = panel(e, "admin", empresa_id=a)
    assert filas(d) == [("Alfa SAS", 3, 6, 1, "33.3%")]
    assert valores(d)["empresas_activas"] == 2 and nombres(d)["empresas"] == ["Alfa SAS", "Beta SAS"]  # no dependen del filtro
    sin_rastro_de_b = [p for p in d["serie_temporal"] if p["completadas"]]
    assert sum(p["completadas"] for p in sin_rastro_de_b) == 2
    e.pedir("admin", "PATCH", f"/empresas/{b}/estado", {"estado": "suspendida"})
    for estado, esperado in (("activa", ["Alfa SAS"]), ("suspendida", ["Beta SAS"]), ("pendiente", []), ("rechazada", []),
                             ("todas", ["Alfa SAS", "Beta SAS"]), ("", ["Alfa SAS", "Beta SAS"]), (" ACTIVA ", ["Alfa SAS"])):
        d = panel(e, "admin", estado=estado)
        assert [f[0] for f in filas(d)] == esperado, estado
        assert sum(p["completadas"] for p in d["serie_temporal"]) == 2 * len(esperado)
        assert valores(d)["tasa_entrega_global"] == (33.3 if esperado else 0)
    assert filas(panel(e, "admin", empresa_id=a, estado="suspendida")) == []
    assert filas(panel(e, "admin", empresa_id=99999)) == [] and valores(panel(e, "admin", empresa_id=99999))["tasa_entrega_global"] == 0
    assert panel(e, "admin", bodega_id=1, bodeguero_id=1, tipo_id=1) == panel(e, "admin")


def test_top_10_empresas(e):
    with SessionLocal() as s:
        s.add_all([Empresa(razon_social=f"Z{n:02d}", estado="activa") for n in range(12)])
        s.commit()
    f = filas(panel(e, "admin"))
    assert len(f) == 10 and [x[0] for x in f[:3]] == ["Alfa SAS", "Beta SAS", "Z00"]
    assert len(panel(e, "admin")["filtros_disponibles"]["empresas"]) == 14  # el selector las trae todas


@SENTIDOS
def test_filtros_de_la_empresa(e, yo, otra):
    uno, dos, sin = e.ids[yo]["bodega"]
    b1, b2 = e.ids[yo]["usuario"]
    t0, t1, _ = e.ids[yo]["tipo"]
    completo = nombres(panel(e, yo))
    for p, total, tabla in (({"bodega_id": uno}, 5, [5]), ({"bodega_id": dos}, 1, [1]), ({"bodega_id": sin}, 0, [0]),
                            ({"bodeguero_id": b1}, 5, [5, 0, 0]), ({"bodeguero_id": b2}, 1, [1, 0, 0]), ({"tipo_id": t0}, 5, [5, 0, 0]),
                            ({"tipo_id": t1}, 1, [1, 0, 0]), ({"bodega_id": uno, "bodeguero_id": b2}, 0, [0]),
                            ({"bodega_id": uno, "tipo_id": t0, "bodeguero_id": b1}, 5, [5]), ({"tipo_id": 99999}, 0, [0, 0, 0])):
        d = panel(e, yo, **p)
        assert (valores(d)["total_facturas"], [f[1] for f in filas(d)]) == (total, tabla), p
        assert nombres(d) == completo  # las opciones no cambian al filtrar
        assert len(d["alertas_detalle"]) == (1 if total == 5 else 0)
    assert panel(e, yo, empresa_id=e.empresa[otra], estado="rechazadas") == panel(e, yo)  # no son suyos: se ignoran


@SENTIDOS
def test_la_empresa_no_filtra_por_una_bodega_ajena(e, yo, otra):
    for b in [*e.ids[otra]["bodega"], 99999, 0, -1]:  # ajena o inexistente: igual
        r = e.pedir(yo, "GET", RUTA, bodega_id=b)
        assert (r.status_code, r.json()) == SIN_PERMISO, b
    for p in ({"bodeguero_id": e.ids[otra]["usuario"][0]}, {"tipo_id": e.ids[otra]["tipo"][0]}):
        r = e.pedir(yo, "GET", RUTA, **p)
        assert valores(r.json())["total_facturas"] == 0 and r.json()["alertas_detalle"] == []
        sin_rastro(r, otra)


def test_filtros_del_bodeguero(e):
    for estado, esperado in (("pendientes", (1, 1, 0, 0)), ("completadas", (0, 0, 2, 0)), ("rechazadas", (0, 0, 0, 1)), ("todas", (1, 1, 2, 1)),
                             (" Pendientes ", (1, 1, 0, 0))):
        d = panel(e, "A1", estado=estado)
        assert tuple(valores(d).values()) == esperado and filas(d)[0][1] == sum(esperado), estado
        assert len(d["alertas_detalle"]) == (1 if esperado[3] else 0)
    assert filas(panel(e, "A2", estado="completadas")) == []
    ajenos = {"empresa_id": e.empresa["B"], "bodega_id": e.ids["B"]["bodega"][0], "bodeguero_id": e.ids["A"]["usuario"][1]}
    assert panel(e, "A1", **ajenos) == panel(e, "A1")  # se ignoran (ni siquiera 403)
    assert sum(valores(panel(e, "A1", tipo_id=e.ids["A"]["tipo"][1])).values()) == 0


def test_filtros_del_cliente(e):
    d = panel(e, "cliente1", empresa_id=e.empresa["A"])
    assert filas(d) == [("Alfa SAS", 4, 2, 1)] and valores(d)["empresas_proveedoras"] == 1
    assert nombres(d)["empresas"] == ["Alfa SAS", "Beta SAS"]
    for estado, total in (("pendientes", 1), ("aceptadas", 2), ("rechazadas", 1), ("todas", 4)):
        assert [f[1] for f in filas(panel(e, "cliente1", estado=estado))] == [total, total], estado
    assert filas(panel(e, "cliente1", empresa_id=e.empresa["B"], estado="rechazadas")) == [("Beta SAS", 1, 0, 1)]
    assert filas(panel(e, "cliente1", empresa_id=99999)) == filas(panel(e, "cliente2", empresa_id=e.empresa["A"])) == []
    ajenos = {"bodega_id": e.ids["A"]["bodega"][0], "bodeguero_id": e.ids["A"]["usuario"][0], "tipo_id": e.ids["A"]["tipo"][0]}
    assert panel(e, "cliente1", **ajenos) == panel(e, "cliente1")


@pytest.mark.parametrize("quien,opciones", [("admin", "todas, activa, pendiente, suspendida o rechazada"),
                                            ("A1", "todas, pendientes, completadas o rechazadas"), ("cliente1", "todas, pendientes, aceptadas o rechazadas")])
def test_estado_invalido(e, quien, opciones):
    for estado in ("otra", "firmada", "emitida", "aceptada", "%"):
        r = e.pedir(quien, "GET", RUTA, estado=estado)
        assert (r.status_code, r.json()) == (422, {"detail": f"estado: debe ser {opciones}", "errores": {"estado": f"debe ser {opciones}"}}), estado
    assert e.pedir("A", "GET", RUTA, estado="otra").status_code == 200  # a la empresa se le ignora


def test_ids_que_no_son_numeros(e):
    for campo in ("empresa_id", "bodega_id", "bodeguero_id", "tipo_id"):
        r = e.pedir("A", "GET", RUTA, **{campo: "abc"})
        assert (r.status_code, r.json()["errores"]) == (422, {campo: "tiene un formato inválido"})


# ===== ALERTAS =====

def test_alertas_las_ultimas_5_por_fecha_de_rechazo(e):
    nuevas = [e.crear("A1", "/facturas", datos_factura(e.ids["cliente1"], e.ids["A"]["bodega"][0], e.ids["A"]["tipo"][0])) for _ in range(6)]
    ayer = datetime.now().replace(microsecond=0)
    for n, i in enumerate(nuevas):
        mover(i, estado_orden="rechazada", motivo_rechazo=f"Motivo {n}", fecha_respuesta=ayer - timedelta(hours=1 + (n * 5) % 6))
    esperado = sorted(nuevas, key=lambda i: (nuevas.index(i) * 5) % 6)[:4]
    ids = [a["factura_id"] for a in panel(e, "A")["alertas_detalle"]]
    assert len(ids) == 5 and ids[0] == e.ids["A"]["factura"][3] and ids[1:] == esperado  # la más reciente primero
    assert ids == [a["factura_id"] for a in panel(e, "A1")["alertas_detalle"]] and panel(e, "A2")["alertas_detalle"] == []
    for i in ids:  # cada uno puede abrir las que le muestran
        assert e.pedir("A", "GET", f"/facturas/{i}").status_code == e.pedir("A1", "GET", f"/facturas/{i}").status_code == 200


# ===== AISLAMIENTO =====

@SENTIDOS
def test_nada_de_la_otra_empresa_con_ningun_filtro(e, yo, otra):
    x = e.ids[otra]
    combos = [{}, {"empresa_id": e.empresa[otra]}, {"bodeguero_id": x["usuario"][0]}, {"tipo_id": x["tipo"][0]}, {"estado": "todas"},
              {"empresa_id": e.empresa[otra], "bodeguero_id": x["usuario"][0], "tipo_id": x["tipo"][0]},
              {"fecha_inicio": "2020-01-01", "fecha_fin": "2035-12-31", "empresa_id": e.empresa[otra]}]
    for quien in (yo, yo + "1", yo + "2"):
        for p in combos:
            r = e.pedir(quien, "GET", RUTA, **p)
            assert r.status_code == 200
            sin_rastro(r, otra)
            assert not {a["factura_id"] for a in r.json()["alertas_detalle"]} & set(x["factura"])


@SENTIDOS
def test_la_actividad_de_la_otra_no_cambia_mi_panel(e, yo, otra):
    ver = lambda: [panel(e, q) for q in (yo, yo + "1", yo + "2")]
    antes = ver()
    b = e.crear(otra, "/bodegas", datos_bodega("MAS"))
    t = e.crear(otra, "/tipos", {"nombre": "Mas", "bodega_id": b})
    for estado in ("entregada", "rechazada", "recibida"):
        e.llevar_a(otra, e.crear(otra, "/facturas", datos_factura(e.ids["cliente1"], b, t)), estado)
    assert ver() == antes


def test_un_bodeguero_no_ve_lo_de_su_companero(e):
    r = e.pedir("A2", "GET", RUTA)
    assert "Producto 0" not in r.text and "UNO" not in r.text and r.json()["alertas_detalle"] == []
    f = e.crear("A", "/facturas", datos_factura(e.ids["cliente1"], e.ids["A"]["bodega"][1], e.ids["A"]["tipo"][1]))  # la crea la empresa en su bodega
    assert valores(panel(e, "A2"))["por_despachar"] == 1 and e.pedir("A2", "GET", f"/facturas/{f}").status_code == 404  # cuadra con su listado


def test_permiso_y_sesion(e):
    assert e.api.get(RUTA).status_code == 401
    with SessionLocal() as s:
        s.get(Usuario, e.ids["A"]["usuario"][0]).permisos = s.query(Permiso).filter(Permiso.nombre != "estadisticas_view").all()
        s.commit()
    r = e.pedir("A1", "GET", RUTA, fecha_inicio="mal")  # el 403 va antes que el 422
    assert (r.status_code, r.json()) == SIN_PERMISO


def test_no_modifica_nada_y_no_trae_filas_a_memoria(e):
    """Los cálculos se hacen en MySQL: la cantidad de consultas no crece con las facturas."""
    from app.config.database import engine

    def consultas(quien):
        n = []
        contar = lambda *a: n.append(1)
        event.listen(engine, "before_cursor_execute", contar)
        try:
            panel(e, quien)
        finally:
            event.remove(engine, "before_cursor_execute", contar)
        return len(n)

    antes, primero = foto(), {q: consultas(q) for q in ("admin", "A", "A1", "cliente1")}
    assert foto() == antes
    for _ in range(8):
        e.llevar_a("A1", e.crear("A1", "/facturas", datos_factura(e.ids["cliente1"], e.ids["A"]["bodega"][0], e.ids["A"]["tipo"][0])), "rechazada")
    assert {q: consultas(q) for q in primero} == primero


# ===== FORMATO ANTERIOR (EN DESUSO) =====

def test_el_formato_anterior_sigue_igual(e):
    d = panel(e, "A")
    assert {t["clave"] for t in d["tarjetas"]} == {"facturas", "facturado", "pendientes", "rechazadas", "bodegueros", "bodegas", "tipos"}
    assert {s["clave"] for s in d["series"]} == {"por_estado", "por_fecha", "por_bodega", "top_productos"}
    viejo, nuevo = panel(e, "A", desde="2026-02-01", hasta="2026-02-05"), panel(e, "A", fecha_inicio="2026-02-01", fecha_fin="2026-02-05")
    assert viejo == nuevo and viejo["periodo"]["desde"] == "2026-02-01"
    assert panel(e, "A", fecha_inicio="2026-02-01", fecha_fin="2026-02-05", desde="2020-01-01", hasta="2020-01-31") == nuevo  # manda el nuevo
    r = e.pedir("A", "GET", RUTA, desde="2026-02-10", hasta="2026-02-09")
    assert (r.status_code, r.json()["errores"]) == (422, {"hasta": "debe ser igual o posterior a desde"})
    filtrado = panel(e, "A", bodega_id=e.ids["A"]["bodega"][1])
    assert (filtrado["tarjetas"], filtrado["series"]) == (d["tarjetas"], d["series"])  # no usa los filtros nuevos


def test_lo_anterior_esta_marcado_en_desuso():
    o = app.openapi()
    assert {p["name"] for p in o["paths"][RUTA]["get"]["parameters"] if p.get("deprecated")} == {"desde", "hasta"}
    marcados = lambda esquema: {c for c, v in o["components"]["schemas"][esquema]["properties"].items() if v.get("deprecated")}
    assert marcados("ResumenOut") == {"tarjetas", "series"} and marcados("PeriodoOut") == {"desde", "hasta"}
