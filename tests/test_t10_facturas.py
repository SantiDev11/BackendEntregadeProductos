# T10: numeración por empresa (sin duplicados ni con peticiones simultáneas), empresa_id/empresa_nombre y motivo_rechazo.
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import RAIZ, SessionLocal, correr_script, correr_sql, engine
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_t7_aislamiento import datos_bodega, datos_factura, m  # noqa: F401  (m es el fixture)

from app.modulos import Bodega, ConsecutivoFactura, Empresa, Orden

BACKFILL = RAIZ / "migraciones" / "006_backfill_empresas.py"
MIGRACION_005 = RAIZ / "migraciones" / "005_empresas.sql"
MIGRACION_008 = RAIZ / "migraciones" / "008_numeracion_por_empresa.sql"

# Mundo crea 4 facturas: bX (empresa X), bX2 (empresa X), bY (empresa Y) y bV (sin empresa)


def cuerpo(m, b, **c):
    return {**datos_factura(m.id["usuario c1"], m.id[f"bodega {b}"], m.id[f"tipo {b}"]), **c}


def facturar(m, b, quien=None):
    r = m.pedir(quien or b, "POST", "/facturas", cuerpo(m, b))
    assert r.status_code == 201, r.text
    return r.json()


def numero(m, i):
    return m.pedir("admin", "GET", f"/facturas/{i}").json()["numero"]


def empresa_con_bodega(m, nombre):
    """Empresa nueva con su bodega (sin facturas ni contador). Devuelve (empresa_id, cuerpo para facturar en ella)."""
    with SessionLocal() as s:
        e = Empresa(razon_social=nombre, estado="activa")
        s.add(e); s.flush()
        b = Bodega(nombre=f"B {nombre}", codigo=f"B{e.id}", empresa_id=e.id)
        s.add(b); s.commit()
        datos = datos_factura(m.id["usuario c1"], b.id, None)
        bodega, empresa = b.id, e.id
    t = m.crear("/tipos", "admin", {"nombre": f"T {nombre}", "bodega_id": bodega})
    datos["detalle"][0]["tipo_id"] = t
    return empresa, datos


# ===== NUMERACIÓN POR EMPRESA =====

def test_cada_empresa_empieza_en_fe_0001(m):
    assert numero(m, m.id["factura bX"]) == numero(m, m.id["factura bY"]) == numero(m, m.id["factura bV"]) == "FE-0001"
    assert numero(m, m.id["factura bX2"]) == "FE-0002"  # los bodegueros de una empresa comparten la numeración


def test_numeracion_independiente(m):
    pedidas = ["bY", "bX", "bX2", "bV", "bY", "bY", "bX"]
    assert [facturar(m, b)["numero"] for b in pedidas] == ["FE-0002", "FE-0003", "FE-0004", "FE-0002", "FE-0003", "FE-0004", "FE-0005"]
    assert facturar(m, "bX", "X")["numero"] == "FE-0006"      # la empresa y el admin siguen la de la bodega
    assert facturar(m, "bX", "admin")["numero"] == "FE-0007"
    assert facturar(m, "bY", "admin")["numero"] == "FE-0005"
    assert facturar(m, "bV", "admin")["numero"] == "FE-0003"
    _, datos = empresa_con_bodega(m, "Nueva")
    assert [m.pedir("admin", "POST", "/facturas", datos).json()["numero"] for _ in range(3)] == ["FE-0001", "FE-0002", "FE-0003"]


def test_el_formato_crece_despues_de_9999(m):
    with SessionLocal() as s:
        s.get(ConsecutivoFactura, (m.id["empresa X"], "FE")).ultimo = 9998
        s.commit()
    assert [facturar(m, "bX")["numero"] for _ in range(2)] == ["FE-9999", "FE-10000"]
    assert facturar(m, "bY")["numero"] == "FE-0002"


def test_el_numero_no_lo_decide_quien_factura(m):
    r = m.pedir("bX", "POST", "/facturas", cuerpo(m, "bX", numero="FE-0500", consecutivo=500, prefijo="ZZ", empresa_id=m.id["empresa Y"]))
    assert (r.json()["numero"], r.json()["empresa_id"]) == ("FE-0003", m.id["empresa X"])


def test_un_numero_usado_no_se_repite(m):
    i = facturar(m, "bX")
    assert i["numero"] == "FE-0003" and m.pedir("bX", "DELETE", f"/facturas/{i['id']}").status_code == 204
    assert facturar(m, "bX")["numero"] == "FE-0004"
    with SessionLocal() as s:  # ni borrándolas todas
        s.query(Orden).filter(Orden.empresa_id == m.id["empresa Y"]).delete()
        s.commit()
    assert facturar(m, "bY")["numero"] == "FE-0002"


def test_una_factura_que_falla_no_gasta_numero(m):
    malos = [cuerpo(m, "bX", cliente_id=99999), cuerpo(m, "bX", bodega_id=m.id["bodega bY"]), cuerpo(m, "bX", detalle=[]),
             cuerpo(m, "bX", detalle=cuerpo(m, "bY")["detalle"]), {}]
    assert {m.pedir("bX", "POST", "/facturas", c).status_code for c in malos} == {400, 422}
    assert facturar(m, "bX")["numero"] == "FE-0003"


def test_sin_contador_sigue_desde_la_ultima_guardada(m):
    """Como queda una base recién migrada: con facturas pero con la tabla de contadores vacía."""
    with SessionLocal() as s:
        s.query(ConsecutivoFactura).delete()
        s.commit()
    assert [facturar(m, b)["numero"] for b in ("bX", "bY", "bV", "bX")] == ["FE-0003", "FE-0002", "FE-0002", "FE-0004"]


def test_si_el_contador_quedo_atras_se_pone_al_dia(m):
    """El backfill 006 pasa facturas viejas a una empresa sin tocar su contador."""
    with SessionLocal() as s:
        o = s.get(Orden, m.id["factura bV"])
        o.consecutivo, o.numero, o.empresa_id = 40, "FE-0040", m.id["empresa Y"]
        s.commit()
    assert facturar(m, "bY")["numero"] == "FE-0041"


# ===== CONCURRENCIA =====

def a_la_vez(tareas):
    """Corre todas las tareas al mismo tiempo (arrancan juntas) y devuelve sus resultados."""
    barrera = Barrier(len(tareas))

    def correr(tarea):
        barrera.wait()
        return tarea()

    with ThreadPoolExecutor(len(tareas)) as hilos:
        return list(hilos.map(correr, tareas))


def test_simultaneas_de_la_misma_empresa(m):
    quienes = ["bX", "X", "admin"] * 4
    for ronda in range(3):
        respuestas = a_la_vez([lambda q=q: m.pedir(q, "POST", "/facturas", cuerpo(m, "bX")) for q in quienes])
        assert [r.status_code for r in respuestas] == [201] * 12, [r.text for r in respuestas if r.status_code != 201]
    with SessionLocal() as s:
        consecutivos = sorted(c for (c,) in s.query(Orden.consecutivo).filter(Orden.empresa_id == m.id["empresa X"]))
    assert consecutivos == list(range(1, 2 + 36 + 1))  # ni repetidos ni huecos


def test_simultaneas_de_una_empresa_sin_contador(m):
    """Las primeras facturas de la empresa: todavía no hay fila que bloquear."""
    for ronda in range(4):
        _, datos = empresa_con_bodega(m, f"Nueva {ronda}")
        respuestas = a_la_vez([lambda: m.pedir("admin", "POST", "/facturas", datos)] * 10)
        assert [r.status_code for r in respuestas] == [201] * 10, [r.text for r in respuestas if r.status_code != 201]
        assert sorted(r.json()["numero"] for r in respuestas) == [f"FE-{n:04d}" for n in range(1, 11)]


def test_simultaneas_de_empresas_distintas(m):
    nuevas = [empresa_con_bodega(m, f"Otra {i}") for i in range(4)]
    tareas = [lambda d=d: m.pedir("admin", "POST", "/facturas", d) for _, d in nuevas] * 2
    tareas += [lambda b=b: m.pedir("admin", "POST", "/facturas", cuerpo(m, b)) for b in ("bX", "bX2", "bY", "bV")]
    for ronda in range(3):
        respuestas = a_la_vez(tareas)
        assert [r.status_code for r in respuestas] == [201] * 12, [r.text for r in respuestas if r.status_code != 201]
    with SessionLocal() as s:
        por_empresa = {}
        for e, c in s.query(Orden.empresa_id, Orden.consecutivo):
            por_empresa.setdefault(e, []).append(c)
    esperado = {**{e: 6 for e, _ in nuevas}, m.id["empresa X"]: 8, m.id["empresa Y"]: 4, None: 4}
    assert {e: sorted(c) for e, c in por_empresa.items()} == {e: list(range(1, n + 1)) for e, n in esperado.items()}


def test_simultaneas_creando_y_eliminando(m):
    viejas = [facturar(m, "bX")["id"] for _ in range(6)]
    tareas = [lambda: m.pedir("bX", "POST", "/facturas", cuerpo(m, "bX"))] * 6
    tareas += [lambda i=i: m.pedir("bX", "DELETE", f"/facturas/{i}") for i in viejas]
    respuestas = a_la_vez(tareas)
    assert Counter(r.status_code for r in respuestas) == {201: 6, 204: 6}, [r.text for r in respuestas]
    assert sorted(r.json()["numero"] for r in respuestas[:6]) == [f"FE-{n:04d}" for n in range(9, 15)]  # nunca los de las eliminadas


@pytest.mark.parametrize("b", ["bX", "bV"])
def test_la_base_tampoco_permite_repetidos(m, b):
    """La última garantía: aunque alguien inserte a mano (con empresa y sin empresa)."""
    with SessionLocal() as s:
        o = s.get(Orden, m.id[f"factura {b}"])
        s.add(Orden(prefijo=o.prefijo, consecutivo=o.consecutivo, numero="OTRO", bodega_id=o.bodega_id, cliente_id=o.cliente_id,
                    bodeguero_id=o.bodeguero_id, empresa_id=o.empresa_id, emisor_datos={}, adquiriente_datos={}))
        with pytest.raises(IntegrityError, match="uq_ordenes_serie_consecutivo"):
            s.commit()


# ===== EDITAR =====

def test_editar_no_cambia_el_numero(m):
    i, otra = m.id["factura bX2"], m.crear("/bodegas", "bX2", datos_bodega("OTRA"))
    for quien, cambios in (("bX2", {"observaciones": "x"}), ("X", cuerpo(m, "bX2")), ("admin", {"forma_pago": "contado"}),
                           ("admin", cuerpo(m, "bX"))):  # bodega de la misma empresa
        r = m.pedir(quien, "PUT", f"/facturas/{i}", cambios)
        assert (r.status_code, r.json().get("numero")) == (200, "FE-0002"), r.text
    r = m.pedir("bX2", "PUT", f"/facturas/{i}", {"bodega_id": otra})
    assert r.status_code == 400  # ya es de la bodega de bX, y sus líneas también
    assert facturar(m, "bX")["numero"] == "FE-0003"


def test_si_el_admin_la_pasa_a_otra_empresa_recibe_numero_de_esa(m):
    i, antes = m.id["factura bX"], m.pedir("admin", "GET", f"/facturas/{m.id['factura bX']}").json()
    r = m.pedir("admin", "PUT", f"/facturas/{i}", cuerpo(m, "bY")).json()
    assert (r["id"], r["numero"], r["empresa_id"], r["empresa_nombre"]) == (i, "FE-0002", m.id["empresa Y"], "Empresa Y")
    assert r["validacion_electronica"]["cufe"] != antes["validacion_electronica"]["cufe"] and "FE-0002" in r["validacion_electronica"]["qr"]
    assert facturar(m, "bY")["numero"] == "FE-0003"
    assert facturar(m, "bX")["numero"] == "FE-0003"  # el FE-0001 de X no se vuelve a usar
    r = m.pedir("admin", "PUT", f"/facturas/{i}", cuerpo(m, "bV")).json()
    assert (r["numero"], r["empresa_id"], r["empresa_nombre"]) == ("FE-0002", None, None)


def test_un_cambio_de_empresa_que_falla_no_cambia_nada(m):
    r = m.pedir("admin", "PUT", f"/facturas/{m.id['factura bX']}", {"bodega_id": m.id["bodega bY"]})  # las líneas son de bX
    assert r.status_code == 400
    f = m.pedir("admin", "GET", f"/facturas/{m.id['factura bX']}").json()
    assert (f["numero"], f["empresa_id"]) == ("FE-0001", m.id["empresa X"])
    assert facturar(m, "bY")["numero"] == "FE-0002"


# ===== EMPRESA_ID Y EMPRESA_NOMBRE =====

def empresa_de_cada(m):
    x, y = (m.id["empresa X"], "Empresa X"), (m.id["empresa Y"], "Empresa Y")
    return {m.id["factura bX"]: x, m.id["factura bX2"]: x, m.id["factura bY"]: y, m.id["factura bV"]: (None, None)}


def test_listado_y_detalle_traen_la_empresa(m):
    esperado = empresa_de_cada(m)
    for quien, vistas in (("admin", 4), ("X", 2), ("Y", 1), ("bX", 1), ("bV", 1)):
        filas = m.pedir(quien, "GET", "/facturas").json()["data"]
        assert len(filas) == vistas
        for f in filas:
            assert (f["empresa_id"], f["empresa_nombre"]) == esperado[f["id"]], (quien, f)
            d = m.pedir(quien, "GET", f"/facturas/{f['id']}").json()
            assert (d["empresa_id"], d["empresa_nombre"], d["numero"]) == (*esperado[f["id"]], f["numero"])


def test_el_cliente_distingue_dos_fe_0001(m):
    for b in ("bX", "bY", "bV"):
        assert m.pedir(b, "POST", f"/facturas/{m.id[f'factura {b}']}/entregar").status_code == 200
    r = m.pedir("c1", "GET", "/facturas", q="FE-0001").json()
    assert r["total"] == 3 and {f["numero"] for f in r["data"]} == {"FE-0001"}
    assert {f["id"]: (f["empresa_id"], f["empresa_nombre"]) for f in r["data"]} == {
        i: e for i, e in empresa_de_cada(m).items() if i != m.id["factura bX2"]}
    assert {f["id"] for f in m.pedir("X", "GET", "/facturas", q="FE-0001").json()["data"]} == {m.id["factura bX"]}
    for b in ("bX", "bY"):  # cada id abre la suya
        r = m.pedir("c1", "GET", f"/facturas/{m.id[f'factura {b}']}/pdf")
        assert r.status_code == 200 and r.content.startswith(b"%PDF") and "FE-0001.pdf" in r.headers["content-disposition"]


def test_todas_las_respuestas_traen_la_empresa(m):
    e = (m.id["empresa X"], "Empresa X")
    f = facturar(m, "bX")
    respuestas = [f, m.pedir("bX", "PUT", f"/facturas/{f['id']}", {"observaciones": "x"}).json(),
                  m.pedir("bX", "POST", f"/facturas/{f['id']}/entregar").json(),
                  m.pedir("c1", "POST", f"/facturas/{f['id']}/rechazar", {"motivo_rechazo": "x" * 10}).json()]
    assert [(r["empresa_id"], r["empresa_nombre"]) for r in respuestas] == [e] * 4


def test_el_filtro_por_empresa_sigue_igual(m):
    assert m.ids("admin", "/facturas", empresa_id=m.id["empresa X"]) == m.de("factura", "bX", "bX2")
    assert m.ids("X", "/facturas", empresa_id=m.id["empresa Y"]) == m.de("factura", "bX", "bX2")


# ===== MOTIVO DE RECHAZO =====

FALTA, CORTO, LARGO = "es obligatorio", "debe tener al menos 10 caracteres", "es demasiado largo"


@pytest.fixture
def entregada(m):
    i = m.id["factura bX"]
    assert m.pedir("bX", "POST", f"/facturas/{i}/entregar").status_code == 200
    return i


def test_motivo_invalido_recibe_422_y_no_rechaza(m, entregada):
    casos = [({}, FALTA), ({"motivo_rechazo": None}, FALTA),
             ({"motivo": "Este es el campo viejo, ya no sirve"}, FALTA),
             ({"motivo_rechazo": ""}, CORTO), ({"motivo_rechazo": " " * 30}, CORTO), ({"motivo_rechazo": "123456789"}, CORTO),
             ({"motivo_rechazo": "   corto     "}, CORTO), ({"motivo_rechazo": "ñáé", "motivo": "x" * 20}, CORTO),
             ({"motivo_rechazo": "x" * 256}, LARGO), ({"motivo_rechazo": "x" * 5000}, LARGO),
             ({"motivo_rechazo": 1234567890}, "tiene un formato inválido"), ({"motivo_rechazo": ["x" * 10]}, "tiene un formato inválido")]
    for c, mensaje in casos:
        r = m.pedir("c1", "POST", f"/facturas/{entregada}/rechazar", c)
        assert (r.status_code, r.json()) == (422, {"detail": f"motivo_rechazo: {mensaje}", "errores": {"motivo_rechazo": mensaje}}), c
    assert m.pedir("c1", "POST", f"/facturas/{entregada}/rechazar").status_code == 422  # sin cuerpo
    f = m.pedir("c1", "GET", f"/facturas/{entregada}").json()
    assert (f["estado"], f["trazabilidad"]["motivo_rechazo"], f["trazabilidad"]["fecha_respuesta"]) == ("entregada", None, None)


@pytest.mark.parametrize("enviado,guardado", [("x" * 10, "x" * 10), ("x" * 255, "x" * 255), ("ñ" * 255, "ñ" * 255),
                                              ("   Faltaron 2 cajas   ", "Faltaron 2 cajas"), (" " * 50 + "x" * 255 + " " * 50, "x" * 255)])
def test_motivo_valido(m, entregada, enviado, guardado):
    r = m.pedir("c1", "POST", f"/facturas/{entregada}/rechazar", {"motivo_rechazo": enviado})
    assert (r.status_code, r.json()["estado"], r.json()["trazabilidad"]["motivo_rechazo"]) == (200, "rechazada", guardado), r.text
    with SessionLocal() as s:
        assert s.get(Orden, entregada).motivo_rechazo == guardado
    assert m.pedir("bX", "GET", f"/facturas/{entregada}").json()["trazabilidad"]["motivo_rechazo"] == guardado
    assert m.pedir("c1", "GET", f"/facturas/{entregada}/pdf").status_code == 200
    r = m.pedir("c1", "POST", f"/facturas/{entregada}/rechazar", {"motivo_rechazo": "Otro motivo"})  # ya no está entregada
    assert r.status_code == 400


def test_quien_puede_rechazar_no_cambia(m, entregada):
    for quien, codigo in (("X", 403), ("admin", 403), ("bX", 403), ("c2", 404), ("bY", 404)):
        assert m.pedir(quien, "POST", f"/facturas/{entregada}/rechazar", {"motivo_rechazo": "x" * 10}).status_code == codigo, quien
    assert m.pedir("X", "POST", f"/facturas/{entregada}/rechazar", {}).status_code == 403  # el 403 de la empresa va antes que el 422


# ===== MIGRACIÓN 008 =====

def sql(*instrucciones):
    with engine.begin() as c:
        for i in instrucciones:
            c.execute(text(i))


def sembrar_antes():
    sql("INSERT INTO roles (id, nombre) VALUES (2, 'bodeguero'), (3, 'cliente')",
        "INSERT INTO usuarios (id, nombre, correo, contrasena, rol_id) VALUES (7, 'B', 'b@x.com', 'x', 2), (8, 'C', 'c@x.com', 'x', 3)",
        "INSERT INTO empresas (id, razon_social, estado) VALUES (1, 'A', 'activa'), (2, 'B', 'activa')",
        "INSERT INTO bodegas (id, nombre, bodeguero_id) VALUES (3, 'Bod', 7)",
        *(f"INSERT INTO ordenes (prefijo, consecutivo, numero, bodega_id, cliente_id, bodeguero_id, empresa_id, emisor_datos, "
          f"adquiriente_datos) VALUES ('FE', {n}, 'FE-000{n}', 3, 8, 7, {e}, '{{}}', '{{}}')" for n, e in ((1, "NULL"), (2, "NULL"), (3, 1))))


def test_008_no_cambia_los_datos_y_permite_repetir_entre_empresas(base_antes_de_005):
    correr_sql(MIGRACION_005)
    sembrar_antes()

    def leer():
        with engine.connect() as c:  # se cierra: abierta, bloquearía el ALTER TABLE
            return [dict(f) for f in c.execute(text("SELECT * FROM ordenes ORDER BY id")).mappings()]

    antes = leer()
    correr_sql(MIGRACION_008)
    despues = leer()
    assert [f.pop("serie") for f in despues] == [0, 0, 1] and despues == antes
    insertar = ("INSERT INTO ordenes (prefijo, consecutivo, numero, bodega_id, cliente_id, bodeguero_id, empresa_id, emisor_datos, "
                "adquiriente_datos) VALUES ('FE', {}, 'x', 3, 8, 7, {}, '{{}}', '{{}}')")
    sql(insertar.format(1, 1), insertar.format(1, 2))  # FE-0001 en las empresas 1 y 2, que ya existía sin empresa
    for n, e in ((1, "NULL"), (3, 1), (1, 2)):
        with pytest.raises(IntegrityError):
            sql(insertar.format(n, e))


def test_008_la_numeracion_sigue_donde_iba(base_antes_de_005):
    from app.modulos.facturas.queries import siguiente_consecutivo
    correr_sql(MIGRACION_005)
    sembrar_antes()
    correr_sql(MIGRACION_008)
    with SessionLocal() as s:
        assert [siguiente_consecutivo(s, e) for e in (None, 1, 2, None)] == [3, 4, 1, 4]


def test_antes_de_la_008_se_pueden_seguir_leyendo_las_facturas(base_antes_de_005):
    """Si el código nuevo arranca antes de correr la migración, las consultas no se rompen."""
    correr_sql(MIGRACION_005)
    sembrar_antes()
    with SessionLocal() as s:
        assert [o.numero for o in s.query(Orden).order_by(Orden.id)] == ["FE-0001", "FE-0002", "FE-0003"]
        assert s.query(Orden).count() == 3  # count() arma una subconsulta con todas las columnas del modelo


def test_antes_de_la_008_el_modulo_de_facturas_responde(m):
    """Por la API, como lo usa el frontend: la base tiene todo menos la 008."""
    sql("ALTER TABLE ordenes DROP INDEX uq_ordenes_serie_consecutivo, DROP COLUMN serie", "DROP TABLE consecutivos_factura")
    i = m.id["factura bX"]
    for quien in ("admin", "X", "bX", "bV", "c1"):
        for ruta in ("/facturas", "/facturas?q=FE-0001", "/facturas?estado=emitida", "/estadisticas/resumen", "/bodegas", "/tipos"):
            r = m.pedir(quien, "GET", ruta)
            assert r.status_code == 200, (quien, ruta, r.text)
    assert len(m.pedir("admin", "GET", "/facturas").json()["data"]) == 4
    assert m.pedir("bX", "GET", f"/facturas/{i}").status_code == m.pedir("bX", "GET", f"/facturas/{i}/pdf").status_code == 200
    assert m.pedir("admin", "GET", "/empresas").status_code == 200


# ===== BACKFILL 006 =====

def test_backfill_no_deja_numeros_repetidos(m):
    """Las facturas viejas (sin empresa) no se renumeran: si la empresa ya tiene esos números, no se guarda nada."""
    with SessionLocal() as s:
        x, antes = m.id["empresa X"], sorted((o.id, o.empresa_id, o.numero) for o in s.query(Orden))
        sin_bodega = s.get(Bodega, m.id["bodega bV"]).empresa_id
    r = correr_script(BACKFILL, "--empresa-id", str(x), "--aplicar")
    assert r.returncode != 0 and "ya tiene facturas con los mismos números" in r.stderr and "Traceback" not in r.stderr, r.stderr
    with SessionLocal() as s:
        assert sorted((o.id, o.empresa_id, o.numero) for o in s.query(Orden)) == antes
        assert s.get(Bodega, m.id["bodega bV"]).empresa_id == sin_bodega is None


def test_despues_del_backfill_la_numeracion_sigue(m):
    facturar(m, "bV")
    with SessionLocal() as s:
        e = Empresa(razon_social="Vieja", estado="activa")
        s.add(e); s.commit()
        i = e.id
    r = correr_script(BACKFILL, "--empresa-id", str(i), "--aplicar")
    assert r.returncode == 0, r.stdout + r.stderr
    f = facturar(m, "bV")
    assert (f["numero"], f["empresa_id"], f["empresa_nombre"]) == ("FE-0003", i, "Vieja")
