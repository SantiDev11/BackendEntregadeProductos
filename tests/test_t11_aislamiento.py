# T11: aislamiento entre dos empresas por el camino real: se registran, el admin las aprueba y TODO se crea por la API,
# con los permisos de sus plantillas. Nada de B puede verlo, editarlo, borrarlo ni contarlo A (y al revés).
#
# Todo lo de cada empresa lleva su marca en el nombre ("Alfa" o "Beta"): así, además de los ids y los códigos, se comprueba
# que la marca de la otra no aparece en NINGUNA parte de la respuesta.
import base64
import io

import pytest
from conftest import SessionLocal, engine, entrar
from PIL import Image
from sqlalchemy import text
from test_t7_aislamiento import datos_bodega, datos_factura, foto

from app.modulos import Bodega, Orden, Tipo, Usuario

CLAVE = "Temp1234*"
MARCA = {"A": "Alfa", "B": "Beta"}
ESTADOS = ("emitida", "entregada", "firmada", "rechazada", "recibida")
RUTAS = {"usuario": "/usuarios", "bodega": "/bodegas", "tipo": "/tipos", "factura": "/facturas"}
MODELOS = {"usuario": Usuario, "bodega": Bodega, "tipo": Tipo, "factura": Orden}
SENTIDOS = pytest.mark.parametrize("yo,otra", [("A", "B"), ("B", "A")])


def firma_png() -> str:
    imagen = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(imagen, "PNG")
    return "data:image/png;base64," + base64.b64encode(imagen.getvalue()).decode()


class Escenario:
    """e.h["A"] es la sesión de la empresa A; e.h["A1"] y e.h["A2"] las de sus bodegueros; e.ids["A"]["factura"], sus ids."""

    def __init__(self, api):
        self.api, self.h, self.ids, self.empresa = api, {"admin": entrar(api, "admin@entrega.com", "Admin123*")}, {}, {}
        for n in (1, 2):
            r = api.post("/register", json={"tipo": "cliente", "nombre": f"Cliente {n}", "tipo_documento": "CC", "numero_documento": f"55566{n}",
                                            "telefono": "3001234567", "correo": f"cliente{n}@c.com", "contrasena": CLAVE})
            self.ids[f"cliente{n}"], self.h[f"cliente{n}"] = r.json()["user"]["id"], entrar(api, f"cliente{n}@c.com", CLAVE)
        for i, lado in enumerate("AB"):
            self.montar(lado, precio=100 if lado == "A" else 70000, nit=f"90011122{i}-1")

    def montar(self, lado, precio, nit):
        marca, correo = MARCA[lado], f"{lado.lower()}@{MARCA[lado].lower()}.com"
        r = self.api.post("/register", json={"tipo": "empresa", "razon_social": f"{marca} SAS", "nit": nit, "telefono": "3001234567",
                                             "direccion": "C 1", "representante": f"Rep {marca}", "correo": correo, "contrasena": CLAVE})
        self.empresa[lado] = r.json()["empresa"]["id"]
        assert self.pedir("admin", "PATCH", f"/empresas/{self.empresa[lado]}/estado", {"estado": "activa"}).status_code == 200
        self.h[lado] = entrar(self.api, correo, CLAVE)
        mios = self.ids[lado] = {"usuario": [], "bodega": [], "tipo": [], "factura": []}

        for n in "12":  # dos bodegueros
            mios["usuario"].append(self.crear(lado, "/usuarios", {"nombre": f"Bod {n} {marca}", "correo": f"b{n}@{marca.lower()}.com", "contrasena": CLAVE}))
            self.h[lado + n] = entrar(self.api, f"b{n}@{marca.lower()}.com", CLAVE)
        b = lambda c, **x: datos_bodega(f"{c}-{lado}", nombre=f"Bodega {c} {marca}", recibe_nombre=f"Recibe {marca}", **x)
        mios["bodega"] = [self.crear(lado + "1", "/bodegas", b("UNO")), self.crear(lado + "2", "/bodegas", b("DOS")),
                          self.crear(lado, "/bodegas", b("SINDUENO"))]
        mios["tipo"] = [self.crear(lado, "/tipos", {"nombre": f"Producto {n} {marca}", "bodega_id": bo}) for n, bo in enumerate(mios["bodega"])]
        for estado in ESTADOS:  # el bodeguero 1 tiene una factura en cada estado
            f = self.crear(lado + "1", "/facturas", datos_factura(self.ids["cliente1"], mios["bodega"][0], mios["tipo"][0], precio))
            mios["factura"].append(f)
            self.llevar_a(lado + "1", f, estado)
        mios["factura"].append(self.crear(lado + "2", "/facturas", datos_factura(self.ids["cliente2"], mios["bodega"][1], mios["tipo"][1], precio)))

    def llevar_a(self, quien, f, estado):
        pasos = {"emitida": [], "entregada": ["entregar"], "firmada": ["entregar", "aceptar"], "rechazada": ["entregar", "rechazar"],
                 "recibida": ["entregar", "aceptar", "recibir"]}[estado]
        for paso in pasos:
            cuerpo = {"aceptar": {"firma": firma_png()}, "rechazar": {"motivo_rechazo": "No era lo pedido"}}.get(paso)
            r = self.pedir("cliente1" if cuerpo else quien, "POST", f"/facturas/{f}/{paso}", cuerpo)
            assert r.status_code == 200, r.text

    def pedir(self, quien, metodo, ruta, cuerpo=None, **params):
        return self.api.request(metodo, ruta, headers=self.h[quien], json=cuerpo, params=params or None)

    def crear(self, quien, ruta, cuerpo):
        r = self.pedir(quien, "POST", ruta, cuerpo)
        assert r.status_code == 201, (quien, ruta, r.text)
        return r.json()["id"]

    def todas(self, quien, ruta, **params):
        r = self.pedir(quien, "GET", ruta, limit=100, **params)
        assert r.status_code == 200, (quien, ruta, params, r.text)
        assert r.json()["total"] == len(r.json()["data"])  # el total tampoco cuenta lo ajeno
        return {x["id"] for x in r.json()["data"]}, r.text


@pytest.fixture
def e(api):
    return Escenario(api)


def sin_rastro(r, otra):
    """La respuesta no menciona a la otra empresa en ninguna parte."""
    assert MARCA[otra].lower() not in r.text.lower(), r.text[:300]


# ===== QUE LA PRUEBA NO ESTÉ VACÍA =====

@SENTIDOS
def test_cada_empresa_si_ve_lo_suyo(e, yo, otra):
    for tipo, ruta in RUTAS.items():
        assert e.todas(yo, ruta)[0] == set(e.ids[yo][tipo]), tipo
        assert len(e.ids[yo][tipo]) >= 2 and e.todas("admin", ruta, empresa_id=e.empresa[yo])[0] >= set(e.ids[yo][tipo])
        for i in e.ids[yo][tipo]:
            r = e.pedir(yo, "GET", f"{ruta}/{i}")
            assert r.status_code == 200 and MARCA[yo] in r.text
    estados = {f["id"]: f["estado"] for f in e.pedir(yo, "GET", "/facturas").json()["data"]}
    assert [estados[i] for i in e.ids[yo]["factura"]] == [*ESTADOS, "emitida"]


# ===== VER =====

@SENTIDOS
def test_no_ve_nada_en_los_listados(e, yo, otra):
    ajeno = e.ids[otra]
    filtros = {
        "/usuarios": [{}, {"q": MARCA[otra]}, {"q": f"@{MARCA[otra].lower()}.com"}, {"rol": "empresa"}, {"rol": "bodeguero"}, {"rol": "admin"},
                      {"rol": "cliente"}, {"estado": True}, {"empresa_id": e.empresa[otra]}],
        "/bodegas": [{}, {"q": MARCA[otra]}, {"estado": True}, {"empresa_id": e.empresa[otra]}, *({"bodeguero_id": u} for u in ajeno["usuario"])],
        "/tipos": [{}, {"q": MARCA[otra]}, {"estado": True}, {"empresa_id": e.empresa[otra]}, *({"bodega_id": b} for b in ajeno["bodega"])],
        "/facturas": [{}, {"q": "FE-0001"}, {"q": "Cliente"}, {"q": MARCA[otra]}, {"empresa_id": e.empresa[otra]}, *({"estado": s} for s in ESTADOS)],
    }
    for tipo, ruta in RUTAS.items():
        for quien in (yo, yo + "1", yo + "2"):
            if ruta == "/usuarios" and quien != yo:
                assert e.pedir(quien, "GET", ruta).status_code == 403  # un bodeguero no tiene usuarios_view
                continue
            for f in filtros[ruta]:
                ids, cuerpo = e.todas(quien, ruta, **f)
                assert not ids & set(ajeno[tipo]) and ids <= set(e.ids[yo][tipo]), (quien, ruta, f)
                assert MARCA[otra].lower() not in cuerpo.lower(), (quien, ruta, f)
            for pagina in range(1, 8):  # tampoco pasando páginas
                assert MARCA[otra] not in e.pedir(quien, "GET", ruta, page=pagina, limit=2).text


@SENTIDOS
def test_no_ve_nada_recorriendo_todos_los_ids(e, yo, otra):
    """Probar uno por uno todos los ids que existen: solo responden 200 los propios, y lo ajeno es igual que lo inexistente."""
    with SessionLocal() as s:
        ultimo = max(max(i for (i,) in s.query(M.id)) for M in MODELOS.values()) + 2
    for tipo, ruta in RUTAS.items():
        inexistente = e.pedir(yo, "GET", f"{ruta}/999999")
        for i in range(1, ultimo + 1):
            r = e.pedir(yo, "GET", f"{ruta}/{i}")
            if i in e.ids[yo][tipo]:
                assert r.status_code == 200
                continue
            assert r.status_code in (403, 404), (ruta, i)
            sin_rastro(r, otra)
            if tipo != "tipo":  # en tipos lo ajeno ya daba 403 (T7)
                assert (r.status_code, r.json()) == (404, inexistente.json()), (ruta, i)
    for f in e.ids[otra]["factura"]:
        for quien in (yo, yo + "1", yo + "2"):
            assert e.pedir(quien, "GET", f"/facturas/{f}").status_code == e.pedir(quien, "GET", f"/facturas/{f}/pdf").status_code == 404


@SENTIDOS
def test_no_ve_datos_de_la_otra_por_otros_caminos(e, yo, otra):
    for quien in (yo, yo + "1"):
        for ruta, params in (("/me", {}), ("/clientes/buscar", {"q": MARCA[otra] + " SAS"}), ("/clientes/buscar", {"q": f"@{MARCA[otra].lower()}.com"}),
                             ("/clientes/buscar", {"q": "Cliente"}), ("/facturas/clientes", {}), ("/facturas/clientes", {"q": MARCA[otra]})):
            r = e.pedir(quien, "GET", ruta, **params)
            assert r.status_code == 200, (ruta, params, r.text)
            sin_rastro(r, otra)
        for ruta in ("/empresas", f"/empresas?q={MARCA[otra]}", "/roles", "/permisos"):
            r = e.pedir(quien, "GET", ruta)
            assert r.status_code == 403, (quien, ruta)
        assert e.pedir(quien, "PATCH", f"/empresas/{e.empresa[otra]}/estado", {"estado": "suspendida"}).status_code == 403
    # los mensajes de error tampoco la revelan
    r = e.pedir(yo, "POST", "/bodegas", datos_bodega("ZZ", bodeguero_id=e.ids[otra]["usuario"][0]))
    assert r.status_code == 400
    sin_rastro(r, otra)


# ===== EDITAR Y BORRAR =====

def ataques(e, otra):
    """Todas las peticiones por id sobre TODO lo de la otra empresa, con cuerpos que serían válidos si fuera suyo."""
    for u in e.ids[otra]["usuario"]:
        yield "usuario", "PUT", f"/usuarios/{u}", {"nombre": "HACK", "correo": f"hack{u}@x.com", "contrasena": "Hackeado1*", "estado": False}
        yield "usuario", "DELETE", f"/usuarios/{u}", None
        yield "usuario", "PATCH", f"/usuarios/{u}/estado", {"estado": False}
        yield "permisos", "GET", f"/usuarios/{u}/permisos", None
        yield "permisos", "PUT", f"/usuarios/{u}/permisos", {"permisos_ids": []}
        yield "permisos", "POST", f"/usuarios/{u}/permisos/1", None
        yield "permisos", "DELETE", f"/usuarios/{u}/permisos/1", None
    for b in e.ids[otra]["bodega"]:
        yield "bodega", "PUT", f"/bodegas/{b}", {"nombre": f"HACK {b}", "codigo": f"HK{b}", "estado": False}
        yield "bodega", "DELETE", f"/bodegas/{b}", None
        yield "bodega", "PATCH", f"/bodegas/{b}/estado", {"estado": False}
    for t in e.ids[otra]["tipo"]:
        yield "tipo", "PUT", f"/tipos/{t}", {"nombre": f"HACK {t}", "estado": False}
        yield "tipo", "DELETE", f"/tipos/{t}", None
        yield "tipo", "PATCH", f"/tipos/{t}/estado", {"estado": False}
    for f in e.ids[otra]["factura"]:
        yield "factura", "PUT", f"/facturas/{f}", {"observaciones": "HACK"}
        yield "factura", "DELETE", f"/facturas/{f}", None
        yield "factura", "POST", f"/facturas/{f}/entregar", None
        yield "factura", "POST", f"/facturas/{f}/recibir", None
        yield "aceptar", "POST", f"/facturas/{f}/aceptar", {"firma": firma_png()}
        yield "aceptar", "POST", f"/facturas/{f}/rechazar", {"motivo_rechazo": "Motivo de prueba"}


@SENTIDOS
def test_no_edita_ni_borra_nada(e, yo, otra):
    antes, fallos, hechas = foto(), [], 0
    esperado = {"usuario": 404, "bodega": 404, "factura": 404, "tipo": 403, "permisos": 403, "aceptar": 403}
    for tipo, metodo, ruta, cuerpo in ataques(e, otra):
        for quien in (yo, yo + "1", yo + "2"):
            codigo = 403 if quien != yo and tipo == "usuario" else esperado[tipo]  # un bodeguero no tiene permisos de usuarios
            r = e.pedir(quien, metodo, ruta, cuerpo)
            hechas += 1
            if r.status_code != codigo or MARCA[otra] in r.text:
                fallos.append((quien, metodo, ruta, r.status_code, r.text[:80]))
    assert fallos == [] and hechas >= 150
    assert foto() == antes  # ni un solo dato cambió
    for n in "12":
        entrar(e.api, f"b{n}@{MARCA[otra].lower()}.com", CLAVE)  # y siguen entrando con su contraseña


@SENTIDOS
def test_no_crea_nada_dentro_de_la_otra(e, yo, otra):
    """Ni apuntando a sus bodegas, bodegueros o tipos, ni enviando su empresa_id."""
    antes_otra = filas_de(e, otra)
    mio, ajeno, c = e.ids[yo], e.ids[otra], e.ids["cliente1"]
    for quien in (yo, yo + "1"):
        for b in ajeno["bodega"]:
            for t in ajeno["tipo"] + mio["tipo"]:
                assert e.pedir(quien, "POST", "/facturas", datos_factura(c, b, t)).status_code == 400, (quien, b, t)
            assert e.pedir(quien, "PUT", f"/facturas/{mio['factura'][0]}", {"bodega_id": b}).status_code == 400
        for t in ajeno["tipo"]:
            assert e.pedir(quien, "POST", "/facturas", datos_factura(c, mio["bodega"][0], t)).status_code == 400
            assert e.pedir(quien, "PUT", f"/facturas/{mio['factura'][0]}", datos_factura(c, mio["bodega"][0], t)).status_code == 400
    for b in ajeno["bodega"]:
        assert e.pedir(yo, "POST", "/tipos", {"nombre": "Z", "bodega_id": b}).status_code == 400
        assert e.pedir(yo, "PUT", f"/tipos/{mio['tipo'][0]}", {"bodega_id": b}).status_code == 400  # a una bodega ajena: 400 (T21)
    for u in ajeno["usuario"]:
        assert e.pedir(yo, "POST", "/bodegas", datos_bodega("Z", bodeguero_id=u)).status_code == 400
        assert e.pedir(yo, "PUT", f"/bodegas/{mio['bodega'][0]}", {"bodeguero_id": u}).status_code == 400

    nuevos = {"usuario": e.crear(yo, "/usuarios", {"nombre": "N", "correo": "n@n.com", "contrasena": CLAVE, "empresa_id": e.empresa[otra]}),
              "bodega": e.crear(yo, "/bodegas", datos_bodega("NN", empresa_id=e.empresa[otra]))}
    nuevos["tipo"] = e.crear(yo, "/tipos", {"nombre": "N", "bodega_id": nuevos["bodega"], "empresa_id": e.empresa[otra]})
    nuevos["factura"] = e.crear(yo, "/facturas", {**datos_factura(c, nuevos["bodega"], nuevos["tipo"]), "empresa_id": e.empresa[otra]})
    with SessionLocal() as s:
        assert {tipo: s.get(MODELOS[tipo], i).empresa_id for tipo, i in nuevos.items()} == {tipo: e.empresa[yo] for tipo in nuevos}
    assert filas_de(e, otra) == antes_otra


def filas_de(e, lado):
    """Todas las filas de la empresa, en las cuatro tablas."""
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT * FROM {t} WHERE empresa_id = :e ORDER BY id"), {"e": e.empresa[lado]}).all()
                for t in ("usuarios", "bodegas", "tipos", "ordenes")}


@SENTIDOS
def test_los_numeros_de_factura_no_se_mezclan(e, yo, otra):
    numeros = lambda lado: [e.pedir("admin", "GET", f"/facturas/{i}").json()["numero"] for i in e.ids[lado]["factura"]]
    assert numeros(yo) == numeros(otra) == [f"FE-{n:04d}" for n in range(1, 7)]
    for quien in (yo, yo + "1"):  # buscando el número de ambas solo sale la propia
        r = e.pedir(quien, "GET", "/facturas", q="FE-0001").json()
        assert [(f["id"], f["empresa_nombre"]) for f in r["data"]] == [(e.ids[yo]["factura"][0], f"{MARCA[yo]} SAS")]


# ===== ESTADÍSTICAS =====

def panel(e, quien, **p):
    r = e.pedir(quien, "GET", "/estadisticas/resumen", **p)
    assert r.status_code == 200, r.text
    return r


@SENTIDOS
def test_estadisticas_solo_cuentan_lo_propio(e, yo, otra):
    precio = 100 if yo == "A" else 70000
    r = panel(e, yo)
    sin_rastro(r, otra)
    tarjetas = {t["clave"]: t["valor"] for t in r.json()["tarjetas"]}
    series = {s["clave"]: {d["etiqueta"]: d["valor"] for d in s["datos"]} for s in r.json()["series"]}
    assert tarjetas == {"facturas": 6, "facturado": 5 * precio, "pendientes": 1, "rechazadas": 1, "bodegueros": 2, "bodegas": 3, "tipos": 3}
    assert series["por_estado"] == {"Emitida": 2, "Entregada": 1, "Firmada": 1, "Rechazada": 1, "Recibida": 1}
    assert series["por_bodega"] == {f"Bodega UNO {MARCA[yo]}": 4 * precio, f"Bodega DOS {MARCA[yo]}": precio}
    assert series["top_productos"] == {f"Producto 0 {MARCA[yo]}": 4, f"Producto 1 {MARCA[yo]}": 1}
    assert sum(series["por_fecha"].values()) == 6
    uno = {t["clave"]: t["valor"] for t in panel(e, yo + "1").json()["tarjetas"]}
    assert uno == {"facturas": 5, "facturado": 4 * precio, "pendientes": 1, "rechazadas": 1, "bodegas": 1, "tipos": 1}


@SENTIDOS
def test_lo_que_hace_la_otra_no_mueve_mis_estadisticas(e, yo, otra):
    rangos = ({}, {"desde": "2020-01-01", "hasta": "2035-12-31"}, {"desde": "2020-01-01"}, {"hasta": "2035-12-31"})
    ver = lambda: [panel(e, q, **r).json() for q in (yo, yo + "1", yo + "2") for r in rangos]
    antes = ver()
    e.crear(otra, "/usuarios", {"nombre": "Otro", "correo": "otro@o.com", "contrasena": CLAVE})
    b = e.crear(otra, "/bodegas", datos_bodega("MAS"))
    t = e.crear(otra, "/tipos", {"nombre": "Mas", "bodega_id": b})
    for _ in range(3):
        e.llevar_a(otra, e.crear(otra, "/facturas", datos_factura(e.ids["cliente1"], b, t, 999)), "entregada")
    e.pedir(otra, "DELETE", f"/facturas/{e.ids[otra]['factura'][0]}")
    assert ver() == antes


@SENTIDOS
def test_empresa_id_no_abre_las_estadisticas_de_la_otra(e, yo, otra):
    for quien in (yo, yo + "1", yo + "2"):
        for i in (e.empresa[otra], e.empresa[yo], 0, 99999):
            assert panel(e, quien, empresa_id=i).json() == panel(e, quien).json(), (quien, i)
        sin_rastro(panel(e, quien, empresa_id=e.empresa[otra], desde="2020-01-01", hasta="2035-12-31"), otra)
    d = panel(e, "admin", empresa_id=e.empresa[yo]).json()  # y al admin le filtra bien
    assert {o["id"] for o in d.pop("filtros_disponibles")["empresas"]} == set(e.empresa.values())  # T13: su selector trae todas
    assert MARCA[yo] in str(d) and MARCA[otra] not in str(d)


# ===== CLIENTES Y ADMIN =====

def test_los_clientes_no_abren_paso_entre_empresas(e):
    """El mismo cliente compra a las dos: ve las suyas de ambas, pero ninguna empresa ve las de la otra a través de él."""
    vistas = {f["id"]: f["empresa_nombre"] for f in e.pedir("cliente1", "GET", "/facturas", limit=100).json()["data"]}
    assert vistas == {i: f"{MARCA[lado]} SAS" for lado in "AB" for i in e.ids[lado]["factura"][1:5]}  # sin las emitidas
    assert e.todas("cliente2", "/facturas")[0] == set()  # las suyas siguen emitidas
    for lado in "AB":
        assert e.todas(lado, "/facturas", q="Cliente 1")[0] == set(e.ids[lado]["factura"][:5])
        for f in e.ids[lado]["factura"]:
            assert e.pedir("cliente2", "GET", f"/facturas/{f}").status_code == 404


def test_el_admin_ve_las_dos(e):
    for tipo, ruta in RUTAS.items():
        assert set(e.ids["A"][tipo]) | set(e.ids["B"][tipo]) <= e.todas("admin", ruta)[0]
    t = {x["clave"]: x["valor"] for x in panel(e, "admin").json()["tarjetas"]}
    assert (t["facturas"], t["facturado"]) == (12, 5 * 100 + 5 * 70000)
    totales = {x["razon_social"]: (x["total_bodegueros"], x["total_bodegas"], x["total_facturas"])
               for x in e.pedir("admin", "GET", "/empresas").json()["data"]}
    assert totales == {"Alfa SAS": (2, 3, 6), "Beta SAS": (2, 3, 6)}
