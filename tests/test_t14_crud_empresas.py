# T14: CRUD de empresas (solo admin): ver una, crear con su usuario, editar y eliminar (con sus usuarios, bodegas y tipos,
# si no tiene facturas).
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import SessionLocal, engine, entrar
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from test_t7_aislamiento import CLAVE, datos_bodega, datos_factura, m  # noqa: F401  (m es el fixture)
from test_t3_registro import EMPRESA as REGISTRO
from test_t3_registro import INVALIDOS

from app.config.main import app
from app.core.permisos import NOMBRES, PLANTILLAS
from app.core.security import verify_password
from app.modulos import Bodega, ConsecutivoFactura, Empresa, Orden, Rol, Tipo, Usuario
from app.modulos.empresas import services

EMPRESA = {k: v for k, v in REGISTRO.items() if k != "tipo"}
SIN_PERMISO = (403, {"detail": "No tiene permiso para esta acción"})
NO_EXISTE = (404, {"detail": "Empresa no encontrada"})
NIT_REPETIDO = (400, {"detail": "Ya existe una empresa con ese NIT"})
CORREO_REPETIDO = (400, {"detail": "Ya existe un usuario con ese correo"})


@pytest.fixture
def h(api):
    return entrar(api, "admin@entrega.com", "Admin123*")


def crear(api, h, **cambios):
    return api.post("/empresas", headers=h, json={**EMPRESA, **cambios})


def creada(api, h, **cambios):
    r = crear(api, h, **cambios)
    assert r.status_code == 201, r.text
    return r.json()


def otra(n):
    return {"nit": f"80011122{n}-3", "correo": f"otra{n}@x.com"}


def resultado(r):
    return r.status_code, r.json()


def todo():
    """Contenido completo de la base, para comprobar que un intento no cambió nada."""
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT * FROM `{t}` ORDER BY 1")).all()
                for t in ("empresas", "usuarios", "usuario_permisos", "bodegas", "tipos", "ordenes", "consecutivos_factura")}


# ===== VER UNA =====

def test_obtener(api, h):
    e = creada(api, h)
    r = api.get(f"/empresas/{e['id']}", headers=h)
    assert resultado(r) == (200, e) and r.json() == api.get("/empresas", headers=h).json()["data"][0]
    for i in (99999, 0, -1):
        assert resultado(api.get(f"/empresas/{i}", headers=h)) == NO_EXISTE
    r = api.get("/empresas/abc", headers=h)
    assert (r.status_code, r.json()["errores"]) == (422, {"empresa_id": "tiene un formato inválido"})


def test_obtener_trae_los_totales(m):
    r = m.pedir("admin", "GET", f"/empresas/{m.id['empresa X']}").json()
    assert (r["total_bodegueros"], r["total_bodegas"], r["total_facturas"]) == (2, 2, 2)


# ===== CREAR =====

def test_crear_queda_activa_y_su_usuario_entra(api, h):
    r = crear(api, h)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e.pop("fecha_registro") and e == {
        "id": e["id"], "razon_social": "Distribuidora Andina S.A.S.", "nit": "900123456-1", "correo": "empresa@andina.com", "telefono": "3001234567",
        "direccion": "Calle 10 # 20-30", "representante": "Ana Torres", "estado": "activa", "motivo_rechazo": None,
        "total_bodegueros": 0, "total_bodegas": 0, "total_facturas": 0}
    assert "contrasena" not in r.text and "$2b$" not in r.text and "token" not in r.text
    u = api.post("/login", json={"correo": EMPRESA["correo"], "contrasena": EMPRESA["contrasena"]}).json()["user"]
    assert (u["nombre"], u["rol"], u["empresa"]) == ("Ana Torres", "empresa", {"id": e["id"], "razon_social": EMPRESA["razon_social"], "estado": "activa"})
    assert {p["nombre"] for p in u["permisos"]} == set(PLANTILLAS["empresa"])
    with SessionLocal() as s:
        x = s.get(Empresa, e["id"])
        assert (x.nit, x.dv) == ("900123456", "1")
        u = s.query(Usuario).filter(Usuario.empresa_id == e["id"]).one()
        assert verify_password(EMPRESA["contrasena"], u.contrasena) and (u.creado_por, u.actualizado_por, u.estado) == (1, 1, True)


def test_la_empresa_creada_trabaja_de_inmediato(api, h):
    creada(api, h)
    e = entrar(api, EMPRESA["correo"], EMPRESA["contrasena"])
    b = api.post("/usuarios", headers=e, json={"nombre": "B", "correo": "b@b.com", "contrasena": CLAVE})
    assert b.status_code == 201 and b.json()["rol"] == "bodeguero"
    assert api.post("/bodegas", headers=e, json=datos_bodega("UNO", bodeguero_id=b.json()["id"])).status_code == 201
    assert api.get("/empresas", headers=h).json()["data"][0]["total_bodegueros"] == 1


def test_crear_normaliza_los_datos(api, h):
    e = creada(api, h, razon_social="  Andina  ", correo="EMPRESA@Andina.COM", nit=" 900123456-1 ", telefono=" 3001234567 ")
    assert (e["razon_social"], e["correo"], e["nit"], e["telefono"]) == ("Andina", "empresa@andina.com", "900123456-1", "3001234567")


def test_crear_ignora_lo_que_decide_el_servidor(api, h):
    e = creada(api, h, estado="suspendida", motivo_rechazo="x" * 20, id=777, rol_id=1, rol="admin", permisos=[1], tipo="cliente", dv="9", creado_por=99)
    assert (e["estado"], e["motivo_rechazo"], e["nit"]) == ("activa", None, "900123456-1") and e["id"] != 777
    with SessionLocal() as s:
        assert s.query(Usuario).filter(Usuario.empresa_id == e["id"]).one().rol.nombre == "empresa"


def test_crear_datos_invalidos(api, h):
    """Las mismas reglas del registro público."""
    antes, fallos = todo(), []
    for campo, valor, mensaje in INVALIDOS["empresa"][1] + [("direccion", "", "no puede estar vacío"), ("representante", " ", "no puede estar vacío")]:
        r = crear(api, h, **{campo: valor})
        if resultado(r) != (422, {"detail": f"{campo}: {mensaje}", "errores": {campo: mensaje}}):
            fallos.append((campo, valor, r.status_code, r.text[:120]))
    assert fallos == []
    r = api.post("/empresas", headers=h, json={})
    assert r.status_code == 422 and r.json()["errores"] == {c: "es obligatorio" for c in EMPRESA}
    for campo in EMPRESA:
        r = crear(api, h, **{campo: None})
        assert r.status_code == 422 and list(r.json()["errores"]) == [campo]
    assert todo() == antes


def test_crear_repetidos(api, h):
    creada(api, h)
    antes = todo()
    for cambios, esperado in (({}, CORREO_REPETIDO), ({"nit": "800111222-3"}, CORREO_REPETIDO), ({"nit": "800111222-3", "correo": "EMPRESA@ANDINA.COM"}, CORREO_REPETIDO),
                              ({"correo": "o@o.com"}, NIT_REPETIDO), ({"correo": "o@o.com", "nit": "900123456-9"}, NIT_REPETIDO),
                              ({"nit": "800111222-3", "correo": "cliente@entrega.com"}, CORREO_REPETIDO)):
        assert resultado(crear(api, h, **cambios)) == esperado, cambios
    assert todo() == antes
    assert resultado(api.post("/register", json={**REGISTRO, "correo": "o@o.com"})) == NIT_REPETIDO  # y contra el registro público
    assert api.post("/register", json={**REGISTRO, **otra(1)}).status_code == 201
    assert resultado(crear(api, h, **otra(1))) == CORREO_REPETIDO


def test_si_falla_el_usuario_no_queda_la_empresa(api, h):
    def explotar(mapper, conexion, usuario):
        raise RuntimeError("falla simulada")
    antes = todo()
    event.listen(Usuario, "before_insert", explotar)
    try:
        r = TestClient(app, raise_server_exceptions=False).post("/empresas", headers=h, json=EMPRESA)
    finally:
        event.remove(Usuario, "before_insert", explotar)
    assert r.status_code == 500 and todo() == antes
    assert crear(api, h).status_code == 201


def test_crear_dos_iguales_a_la_vez(api, h):
    barrera = Barrier(6)

    def una(_):
        barrera.wait()
        return crear(api, h)
    with ThreadPoolExecutor(6) as hilos:
        respuestas = list(hilos.map(una, range(6)))
    assert sorted(r.status_code for r in respuestas) == [201] + [400] * 5, [r.text for r in respuestas]
    with SessionLocal() as s:
        assert s.query(Empresa).count() == s.query(Usuario).filter(Usuario.empresa_id.is_not(None)).count() == 1


def test_el_registro_publico_sigue_igual(api, h):
    r = api.post("/register", json=REGISTRO)
    assert r.status_code == 201 and r.json()["estado"] == "pendiente"
    assert api.post("/login", json={"correo": REGISTRO["correo"], "contrasena": REGISTRO["contrasena"]}).status_code == 403
    with SessionLocal() as s:
        u = s.query(Usuario).filter(Usuario.correo == REGISTRO["correo"]).one()
        assert (u.creado_por, u.actualizado_por) == (None, None)


# ===== EDITAR =====

CAMBIOS = {"razon_social": "Nueva S.A.", "nit": "800999888-7", "telefono": "6015551234", "direccion": "Otra 1", "representante": "Luis", "correo": "c@nueva.com"}


def test_editar_todo_y_de_a_uno(api, h):
    e = creada(api, h)
    for campo, valor in CAMBIOS.items():
        r = api.put(f"/empresas/{e['id']}", headers=h, json={campo: valor})
        e[campo] = valor  # solo cambia ese
        assert resultado(r) == (200, e)
    assert api.get(f"/empresas/{e['id']}", headers=h).json() == e
    for cuerpo in ({}, dict.fromkeys(CAMBIOS)):  # nada o null: no cambia nada
        assert resultado(api.put(f"/empresas/{e['id']}", headers=h, json=cuerpo)) == (200, e)
    with SessionLocal() as s:
        assert (s.get(Empresa, e["id"]).nit, s.get(Empresa, e["id"]).dv) == ("800999888", "7")


def test_editar_no_cambia_al_usuario_ni_el_estado(api, h):
    e = creada(api, h)
    r = api.put(f"/empresas/{e['id']}", headers=h, json={**CAMBIOS, "estado": "suspendida", "motivo_rechazo": "x" * 20, "contrasena": "Otra12345*",
                                                         "id": 777, "fecha_registro": "2020-01-01", "dv": "0"})
    assert (r.status_code, r.json()["id"], r.json()["estado"], r.json()["motivo_rechazo"], r.json()["nit"]) == (200, e["id"], "activa", None, "800999888-7")
    u = api.post("/login", json={"correo": EMPRESA["correo"], "contrasena": EMPRESA["contrasena"]}).json()["user"]  # sigue entrando igual
    assert (u["nombre"], u["empresa"]["razon_social"]) == ("Ana Torres", "Nueva S.A.")


@pytest.mark.parametrize("estado", ["pendiente", "rechazada", "suspendida"])
def test_se_edita_en_cualquier_estado(api, h, estado):
    e = creada(api, h)
    with SessionLocal() as s:
        s.get(Empresa, e["id"]).estado = estado
        s.commit()
    r = api.put(f"/empresas/{e['id']}", headers=h, json={"telefono": "6015551234"})
    assert (r.status_code, r.json()["telefono"], r.json()["estado"]) == (200, "6015551234", estado)


def test_editar_datos_invalidos(api, h):
    e = creada(api, h)
    antes = todo()
    casos = [c for c in INVALIDOS["empresa"][1] if c[0] != "contrasena"] + [("direccion", "", "no puede estar vacío"), ("representante", " ", "no puede estar vacío")]
    for campo, valor, mensaje in casos:
        r = api.put(f"/empresas/{e['id']}", headers=h, json={campo: valor})
        assert resultado(r) == (422, {"detail": f"{campo}: {mensaje}", "errores": {campo: mensaje}}), (campo, valor)
    assert resultado(api.put("/empresas/99999", headers=h, json=CAMBIOS)) == NO_EXISTE
    assert api.put("/empresas/abc", headers=h, json=CAMBIOS).status_code == 422
    assert todo() == antes


def test_editar_nit_repetido(api, h):
    a, b = creada(api, h), creada(api, h, **otra(1))
    antes = todo()
    for nit in (a["nit"], "900123456-7"):  # con otro dígito también es el mismo
        assert resultado(api.put(f"/empresas/{b['id']}", headers=h, json={"nit": nit, "direccion": "HACK"})) == NIT_REPETIDO
    assert todo() == antes
    assert api.put(f"/empresas/{b['id']}", headers=h, json={"nit": b["nit"]}).status_code == 200  # el suyo no es error
    assert api.put(f"/empresas/{b['id']}", headers=h, json={"nit": "800111221-9"}).json()["nit"] == "800111221-9"  # ni cambiar solo el dígito


def test_editar_el_mismo_nit_a_la_vez(api, h, monkeypatch):
    """La segunda pasa la revisión previa y la frena la base: 400, no 500."""
    a, b = creada(api, h), creada(api, h, **otra(1))
    original, llamadas = services.validate_unique_nit, []

    def primera_vez_no_ve_nada(*args, **kw):
        llamadas.append(1)
        if len(llamadas) > 1:
            original(*args, **kw)
    monkeypatch.setattr(services, "validate_unique_nit", primera_vez_no_ve_nada)
    assert resultado(api.put(f"/empresas/{b['id']}", headers=h, json={"nit": a["nit"]})) == NIT_REPETIDO
    assert api.get(f"/empresas/{b['id']}", headers=h).json()["nit"] == b["nit"]


def test_una_empresa_sin_todos_los_datos_se_puede_completar(api, h):
    with SessionLocal() as s:  # como las del backfill
        e = Empresa(razon_social="Vieja", estado="activa")
        s.add(e); s.commit()
        i = e.id
    assert api.get(f"/empresas/{i}", headers=h).json()["nit"] is None
    assert api.put(f"/empresas/{i}", headers=h, json={"nit": "800111222-3"}).json()["nit"] == "800111222-3"


# ===== ELIMINAR =====

@pytest.mark.parametrize("estado", ["activa", "pendiente", "rechazada", "suspendida"])
def test_eliminar_sin_datos(api, h, estado):
    queda = creada(api, h, **otra(1))
    antes = todo()
    e = creada(api, h)
    sesion = entrar(api, EMPRESA["correo"], EMPRESA["contrasena"])
    with SessionLocal() as s:
        s.get(Empresa, e["id"]).estado = estado
        s.add(ConsecutivoFactura(serie=e["id"], prefijo="FE", ultimo=3))
        s.commit()
    r = api.delete(f"/empresas/{e['id']}", headers=h)
    assert (r.status_code, r.content) == (204, b"")
    assert todo() == antes  # se fueron la empresa, su usuario, sus permisos y su contador, y nada más
    assert resultado(api.get(f"/empresas/{e['id']}", headers=h)) == resultado(api.delete(f"/empresas/{e['id']}", headers=h)) == NO_EXISTE
    assert api.get("/me", headers=sesion).status_code == 401  # su sesión deja de servir
    assert api.post("/login", json={"correo": EMPRESA["correo"], "contrasena": EMPRESA["contrasena"]}).status_code == 401
    assert creada(api, h)["id"] not in (e["id"], queda["id"])  # el NIT y el correo quedan libres


FACTURAS = (400, {"detail": "No se puede eliminar: la empresa tiene facturas. Puede suspenderla"})
BODEGA_AJENA = (400, {"detail": "No se puede eliminar: la empresa tiene bodegas de otra empresa a cargo de sus usuarios. Puede suspenderla"})


def filas(tabla, columna, valor, id_="id"):
    with engine.connect() as c:
        return c.execute(text(f"SELECT `{id_}` FROM `{tabla}` WHERE `{columna}` = :v"), {"v": valor}).scalars().all()


def test_con_facturas_no_se_borra_nada(m):
    antes = todo()
    assert resultado(m.pedir("admin", "DELETE", f"/empresas/{m.id['empresa X']}")) == FACTURAS
    assert todo() == antes


def test_sin_facturas_se_va_con_sus_usuarios_bodegas_y_tipos(m):
    x, y = m.id["empresa X"], m.id["empresa Y"]
    for b in ("bX", "bX2"):
        assert m.pedir("admin", "DELETE", f"/facturas/{m.id[f'factura {b}']}").status_code == 204
    otro_tipo = m.crear("/tipos", "bX", {"nombre": "Otro de bX"})
    with SessionLocal() as s:  # un usuario de otro rol también es de la empresa, y el contador se va con ella
        s.add(Usuario(nombre="G", correo="gerente@x.com", contrasena="x", rol_id=m.crear("/roles", "admin", {"nombre": "Gerente X"}),
                      empresa_id=x))
        s.commit()
    assert filas("consecutivos_factura", "serie", x, "prefijo") != []  # ya lo tiene por sus facturas
    suyos = {t: filas(t, "empresa_id", x) for t in ("usuarios", "bodegas", "tipos")}
    assert len(suyos["usuarios"]) == 4 and len(suyos["bodegas"]) == 2 and otro_tipo in suyos["tipos"]
    antes = todo()

    r = m.pedir("admin", "DELETE", f"/empresas/{x}")
    assert (r.status_code, r.content) == (204, b"")

    despues = todo()
    for tabla in ("usuarios", "bodegas", "tipos"):  # se fueron todos los suyos y nada más
        quedan = {f[0] for f in despues[tabla]}
        assert quedan == {f[0] for f in antes[tabla]} - set(suyos[tabla]), tabla
    assert {f.usuario_id for f in despues["usuario_permisos"]}.isdisjoint(suyos["usuarios"])  # y sus permisos
    assert [f for f in despues["empresas"] if f[0] == x] == [] and filas("consecutivos_factura", "serie", x, "prefijo") == []
    assert despues["ordenes"] == antes["ordenes"]  # las facturas de las demás no se tocan
    assert m.pedir("admin", "GET", f"/empresas/{y}").json()["total_bodegas"] == 1
    for quien in ("X", "bX", "bX2"):  # ninguno vuelve a entrar
        assert m.pedir(quien, "GET", "/me").status_code == 401, quien
        assert m.api.post("/login", json={"correo": f"{quien.lower()}@t.com", "contrasena": CLAVE}).status_code == 401
    assert resultado(m.pedir("admin", "DELETE", f"/empresas/{x}")) == NO_EXISTE
    # el NIT y los correos quedan libres
    assert m.pedir("admin", "POST", "/empresas", {**EMPRESA, "nit": "900000001-1", "correo": "x@t.com"}).status_code == 201


@pytest.mark.parametrize("campo", ["bodeguero_id", "cliente_id", "bodega_id", "tipo_id"])
def test_cuentan_las_facturas_que_tocan_algo_suyo(m, campo):
    """Aunque la factura sea de otra empresa (el admin la movió): no puede dar 500 ni dejarla rota."""
    with SessionLocal() as s:
        e = Empresa(razon_social="Z", estado="activa")
        s.add(e); s.flush()
        u = Usuario(nombre="Z", correo="z@z.com", contrasena="x", rol_id=m.rol["empresa"], empresa_id=e.id)
        b = Bodega(**datos_bodega("ZZ"), empresa_id=e.id)
        s.add_all([u, b]); s.flush()
        tipo = Tipo(nombre="Z", bodega_id=b.id, empresa_id=e.id)
        s.add(tipo); s.flush()
        factura = s.get(Orden, m.id["factura bY"])
        if campo == "tipo_id":
            factura.detalles[0].tipo_id = tipo.id
        else:
            setattr(factura, campo, {"bodeguero_id": u.id, "cliente_id": u.id, "bodega_id": b.id}[campo])
        s.commit()
        i = e.id
    antes = todo()
    assert resultado(m.pedir("admin", "DELETE", f"/empresas/{i}")) == FACTURAS
    assert todo() == antes


def test_no_borra_bodegas_ajenas(m):
    with SessionLocal() as s:
        e = Empresa(razon_social="Z", estado="activa")
        s.add(e); s.flush()
        u = Usuario(nombre="Z", correo="z@z.com", contrasena="x", rol_id=m.rol["bodeguero"], empresa_id=e.id)
        s.add(u); s.flush()
        s.get(Bodega, m.id["bodega bY"]).bodeguero_id = u.id
        s.commit()
        i = e.id
    antes = todo()
    assert resultado(m.pedir("admin", "DELETE", f"/empresas/{i}")) == BODEGA_AJENA
    assert todo() == antes


def test_si_aparece_una_factura_mientras_se_borra(m, monkeypatch):
    """La revisión previa no la ve: la base no deja borrar, no se borra nada y responde 400, no 500."""
    original, llamadas = services.validate_se_puede_eliminar, []

    def primera_vez_no_ve_nada(*args):
        llamadas.append(1)
        if len(llamadas) > 1:
            original(*args)
    monkeypatch.setattr(services, "validate_se_puede_eliminar", primera_vez_no_ve_nada)
    antes = todo()
    assert resultado(m.pedir("admin", "DELETE", f"/empresas/{m.id['empresa X']}")) == FACTURAS
    assert todo() == antes
    monkeypatch.setattr(services, "validate_se_puede_eliminar", lambda *a: None)  # ni la segunda revisión la ve
    r = m.pedir("admin", "DELETE", f"/empresas/{m.id['empresa X']}")
    assert resultado(r) == (400, {"detail": "La empresa cambió mientras se eliminaba. Intente de nuevo"})
    assert todo() == antes


def test_mientras_se_borra_nadie_le_agrega_datos(m):
    """La fila de la empresa queda bloqueada: crear un bodeguero en ella espera a que termine el borrado."""
    from app.modulos.empresas import queries
    x = m.id["empresa X"]
    with SessionLocal() as s:
        queries.bloquear(s, x)
        with engine.connect() as c:
            c.execute(text("SET SESSION innodb_lock_wait_timeout = 1"))
            with pytest.raises(Exception, match="Lock wait timeout"):
                c.execute(text("INSERT INTO usuarios (nombre, correo, contrasena, rol_id, empresa_id) VALUES ('L', 'l@l.com', 'x', :r, :e)"),
                          {"r": m.rol["bodeguero"], "e": x})
        s.rollback()


def test_el_delete_bloquea_antes_de_revisar(m, monkeypatch):
    """Si revisara antes de bloquear, alguien podría agregarle datos entre la revisión y el borrado."""
    from app.modulos.empresas import queries
    x, pasos = m.id["empresa X"], []
    bloquear, revisar = queries.bloquear, services.validate_se_puede_eliminar
    monkeypatch.setattr(queries, "bloquear", lambda db, i: (pasos.append(("bloquear", i)), bloquear(db, i))[1])
    monkeypatch.setattr(services, "validate_se_puede_eliminar", lambda db, i: (pasos.append(("revisar", i)), revisar(db, i))[1])
    assert resultado(m.pedir("admin", "DELETE", f"/empresas/{x}")) == FACTURAS
    assert pasos == [("bloquear", x), ("revisar", x)]


def test_eliminar_id_invalido(api, h):
    assert resultado(api.delete("/empresas/99999", headers=h)) == NO_EXISTE
    r = api.delete("/empresas/abc", headers=h)
    assert (r.status_code, r.json()["errores"]) == (422, {"empresa_id": "tiene un formato inválido"})


# ===== SOLO ADMIN =====

def test_nadie_mas_puede(m):
    """Ni con todos los permisos del sistema (los tienen en este escenario), ni sobre su propia empresa."""
    antes = todo()
    for quien in ("X", "Y", "bX", "bV", "c1", "sin"):
        for e in (m.id["empresa X"], m.id["empresa Y"], 99999):
            for metodo, ruta, cuerpo in (("GET", "", None), ("PUT", "", CAMBIOS), ("PUT", "", {"nit": "mal"}), ("DELETE", "", None)):
                assert resultado(m.pedir(quien, metodo, f"/empresas/{e}{ruta}", cuerpo)) == SIN_PERMISO, (quien, metodo, e)
        for cuerpo in (EMPRESA, {}):  # el 403 va antes que el 422
            assert resultado(m.pedir(quien, "POST", "/empresas", cuerpo)) == SIN_PERMISO
    assert todo() == antes


def test_sin_sesion(api):
    for metodo, ruta in (("GET", "/empresas/1"), ("POST", "/empresas"), ("PUT", "/empresas/1"), ("DELETE", "/empresas/1")):
        assert resultado(api.request(metodo, ruta, json=EMPRESA)) == (401, {"detail": "No ha iniciado sesión"})


def test_cors_permite_los_metodos(api):
    for metodo in ("POST", "PUT", "DELETE"):
        r = api.options("/empresas/1", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": metodo})
        assert r.status_code == 200 and metodo in r.headers["access-control-allow-methods"]


def test_no_hay_permisos_de_empresas():
    """Contrato, 6: depende solo del rol admin."""
    assert not any(n.startswith("empresas") for n in NOMBRES)
