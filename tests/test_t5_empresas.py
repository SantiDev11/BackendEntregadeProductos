# T5: /empresas (solo admin): listado, cambio de estado y permisos
from datetime import datetime

import pytest
from conftest import SessionLocal, entrar

from app.core.security import hash_password
from app.modulos import Bodega, Empresa, Orden, Permiso, Rol, Usuario

SIN_PERMISO = {"detail": "No tiene permiso para esta acción"}
MOTIVO = "El NIT no coincide con el RUT"
EMPRESA = {"tipo": "empresa", "razon_social": "Andina S.A.S.", "nit": "900123456-1", "telefono": "3001234567", "direccion": "C 1",
           "representante": "Ana Torres", "correo": "e@andina.com", "contrasena": "Empresa123*"}


@pytest.fixture
def admin(api):
    return entrar(api, "admin@entrega.com", "Admin123*")


def crear(razon="Andina S.A.S.", estado="pendiente", motivo=None, **campos) -> int:
    with SessionLocal() as s:
        e = Empresa(razon_social=razon, estado=estado, motivo_rechazo=motivo, **campos)
        s.add(e); s.commit()
        return e.id


def cambiar(api, h, eid, **cuerpo):
    return api.patch(f"/empresas/{eid}/estado", headers=h, json=cuerpo)


def en_bd(eid):
    with SessionLocal() as s:
        e = s.get(Empresa, eid)
        return e.estado, e.motivo_rechazo


# ===== LISTADO =====

def test_forma_exacta_de_cada_empresa(api, admin):
    eid = api.post("/register", json=EMPRESA).json()["empresa"]["id"]
    r = api.get("/empresas", headers=admin)
    assert r.status_code == 200 and {k: r.json()[k] for k in ("total", "page", "limit")} == {"total": 1, "page": 1, "limit": 10}
    e = r.json()["data"][0]
    assert datetime.fromisoformat(e.pop("fecha_registro"))
    assert e == {"id": eid, "razon_social": "Andina S.A.S.", "nit": "900123456-1", "correo": "e@andina.com", "telefono": "3001234567",
                 "direccion": "C 1", "representante": "Ana Torres", "estado": "pendiente", "motivo_rechazo": None,
                 "total_bodegueros": 0, "total_bodegas": 0, "total_facturas": 0}


def test_busqueda(api, admin):
    crear("Distribuidora Andina", nit="900123456", dv="1", correo="ventas@andina.com")
    crear("Pacífico Ltda", nit="800999888", dv="7", correo="info@pacifico.co")
    crear("Sin datos")
    buscar = lambda q: sorted(e["razon_social"] for e in api.get("/empresas", headers=admin, params={"q": q}).json()["data"])
    assert buscar("andina") == buscar("ANDI") == buscar("ventas@") == buscar("900123456-1") == buscar("9001234") == ["Distribuidora Andina"]
    assert buscar("pacifico") == ["Pacífico Ltda"]  # por correo, y sin distinguir tildes
    assert buscar("no existe") == []
    assert buscar("") == ["Distribuidora Andina", "Pacífico Ltda", "Sin datos"]


def test_filtro_por_estado_y_combinado(api, admin):
    for razon, estado in (("A1", "pendiente"), ("A2", "activa"), ("B1", "activa"), ("A3", "rechazada"), ("A4", "suspendida")):
        crear(razon, estado)
    ver = lambda **p: sorted(e["razon_social"] for e in api.get("/empresas", headers=admin, params=p).json()["data"])
    assert ver(estado="pendiente") == ["A1"] and ver(estado="activa") == ["A2", "B1"]
    assert ver(estado="rechazada") == ["A3"] and ver(estado=" SUSPENDIDA ") == ["A4"]
    assert ver(estado="activa", q="a2") == ["A2"] and len(ver()) == 5


def test_paginacion(api, admin):
    ids = [crear(f"E{i:02d}") for i in range(25)]
    ver = lambda **p: api.get("/empresas", headers=admin, params=p).json()
    p1, p3 = ver(), ver(page=3)
    assert (p1["total"], p1["page"], p1["limit"], len(p1["data"])) == (25, 1, 10, 10)
    assert (p3["total"], p3["page"], len(p3["data"])) == (25, 3, 5)
    todas = [e["id"] for p in (1, 2, 3) for e in ver(page=p)["data"]]
    assert todas == sorted(ids, reverse=True)  # la más reciente primero, sin repetir ni saltar
    assert len(ver(limit=100)["data"]) == 25 and ver(page=99)["data"] == [] and ver(page=99)["total"] == 25


@pytest.mark.parametrize("params,campo,mensaje", [
    ({"estado": "otra"}, "estado", "debe ser pendiente, activa, rechazada o suspendida"),
    ({"estado": ""}, "estado", "debe ser pendiente, activa, rechazada o suspendida"),
    ({"page": 0}, "page", "debe ser mayor o igual a 1"), ({"limit": 101}, "limit", "debe ser menor o igual a 100"),
    ({"limit": 0}, "limit", "debe ser mayor o igual a 1"), ({"page": "x"}, "page", "tiene un formato inválido")])
def test_parametros_invalidos(api, admin, params, campo, mensaje):
    r = api.get("/empresas", headers=admin, params=params)
    assert (r.status_code, r.json()) == (422, {"detail": f"{campo}: {mensaje}", "errores": {campo: mensaje}})


def test_totales_por_empresa(api, admin):
    a, b = crear("A", "activa"), crear("B", "activa")
    with SessionLocal() as s:
        rol = {r.nombre: r.id for r in s.query(Rol)}
        u = [Usuario(nombre=n, correo=f"{n}@x.com", contrasena="x", rol_id=rol[r], empresa_id=e)
             for n, r, e in (("b1", "bodeguero", a), ("b2", "bodeguero", a), ("b3", "bodeguero", b), ("rep", "empresa", a))]
        bod = [Bodega(nombre=f"B{i}", empresa_id=e) for i, e in enumerate((a, a, a, b, None))]
        s.add_all(u + bod); s.flush()
        cli = s.query(Usuario).filter(Usuario.correo == "cliente@entrega.com").one().id
        for i, (e, bo) in enumerate(((a, bod[0]), (a, bod[1]), (None, bod[4])), 1):
            s.add(Orden(prefijo="FE", consecutivo=i, numero=f"FE-{i}", bodega_id=bo.id, cliente_id=cli, bodeguero_id=u[0].id,
                        empresa_id=e, emisor_datos={}, adquiriente_datos={}))
        s.commit()
    totales = {e["razon_social"]: (e["total_bodegueros"], e["total_bodegas"], e["total_facturas"])
               for e in api.get("/empresas", headers=admin).json()["data"]}
    assert totales == {"A": (2, 3, 2), "B": (1, 1, 0)}  # el usuario "empresa" no cuenta como bodeguero


# ===== CAMBIO DE ESTADO =====

ESTADOS = ("pendiente", "activa", "rechazada", "suspendida")
PERMITIDOS = {("pendiente", "activa"), ("pendiente", "rechazada"), ("activa", "suspendida"), ("suspendida", "activa"), ("rechazada", "activa")}


def test_todas_las_transiciones(api, admin):
    for actual in ESTADOS:
        for nuevo in ("activa", "rechazada", "suspendida"):
            previo = MOTIVO if actual == "rechazada" else None
            eid = crear(estado=actual, motivo=previo)
            r = cambiar(api, admin, eid, estado=nuevo, motivo_rechazo="Otro motivo válido")
            if (actual, nuevo) in PERMITIDOS:
                motivo = "Otro motivo válido" if nuevo == "rechazada" else None
                assert r.status_code == 200, (actual, nuevo, r.text)
                assert (r.json()["id"], r.json()["estado"], r.json()["motivo_rechazo"]) == (eid, nuevo, motivo)
                assert en_bd(eid) == (nuevo, motivo)
            else:
                assert (r.status_code, r.json()) == (400, {"detail": f"No se puede pasar de {actual} a {nuevo}"}), (actual, nuevo)
                assert en_bd(eid) == (actual, previo)


def test_activar_limpia_el_motivo(api, admin):
    eid = crear(estado="rechazada", motivo=MOTIVO)
    r = cambiar(api, admin, eid, estado="activa")
    assert r.status_code == 200 and r.json()["motivo_rechazo"] is None and en_bd(eid) == ("activa", None)


def test_responde_con_la_misma_forma_del_listado(api, admin):
    eid = api.post("/register", json=EMPRESA).json()["empresa"]["id"]
    r = cambiar(api, admin, eid, estado=" ACTIVA ")
    assert r.status_code == 200 and r.json() == api.get("/empresas", headers=admin).json()["data"][0]


def test_motivo_de_rechazo(api, admin):
    falta, corto, largo = "es obligatorio", "debe tener al menos 10 caracteres", "es demasiado largo"
    casos = [({}, falta), ({"motivo_rechazo": None}, falta), ({"motivo_rechazo": ""}, corto), ({"motivo_rechazo": "123456789"}, corto),
             ({"motivo_rechazo": "   corto     "}, corto), ({"motivo_rechazo": " " * 30}, corto), ({"motivo_rechazo": "x" * 256}, largo),
             ({"motivo_rechazo": 1234567890}, "tiene un formato inválido")]
    eid = crear()
    for cuerpo, mensaje in casos:
        r = cambiar(api, admin, eid, estado="rechazada", **cuerpo)
        assert (r.status_code, r.json()) == (422, {"detail": f"motivo_rechazo: {mensaje}", "errores": {"motivo_rechazo": mensaje}}), cuerpo
    assert en_bd(eid) == ("pendiente", None)
    for motivo, guardado in (("x" * 10, "x" * 10), ("x" * 255, "x" * 255), (f"  {MOTIVO}  ", MOTIVO)):
        eid = crear()
        assert cambiar(api, admin, eid, estado="rechazada", motivo_rechazo=motivo).status_code == 200
        assert en_bd(eid) == ("rechazada", guardado)


def test_motivo_se_ignora_si_no_es_rechazo(api, admin):
    for motivo in ("corto", "", "x" * 300, None):
        eid = crear()
        assert cambiar(api, admin, eid, estado="activa", motivo_rechazo=motivo).status_code == 200
        assert en_bd(eid) == ("activa", None)


@pytest.mark.parametrize("cuerpo,mensaje", [({}, "es obligatorio"), ({"estado": "pendiente"}, "debe ser activa, rechazada o suspendida"),
                                            ({"estado": "otra"}, "debe ser activa, rechazada o suspendida"),
                                            ({"estado": ""}, "debe ser activa, rechazada o suspendida"),
                                            ({"estado": None}, "tiene un formato inválido"), ({"estado": True}, "tiene un formato inválido")])
def test_estado_invalido(api, admin, cuerpo, mensaje):
    eid = crear()
    r = cambiar(api, admin, eid, **cuerpo)
    assert (r.status_code, r.json()) == (422, {"detail": f"estado: {mensaje}", "errores": {"estado": mensaje}})
    assert en_bd(eid) == ("pendiente", None)


def test_no_existe_e_id_invalido(api, admin):
    r = cambiar(api, admin, 99999, estado="activa")
    assert (r.status_code, r.json()) == (404, {"detail": "Empresa no encontrada"})
    r = api.patch("/empresas/abc/estado", headers=admin, json={"estado": "activa"})
    assert r.status_code == 422 and r.json()["errores"] == {"empresa_id": "tiene un formato inválido"}


def test_flujo_completo_con_el_login(api, admin):
    eid = api.post("/register", json=EMPRESA).json()["empresa"]["id"]
    login = lambda: api.post("/login", json={"correo": EMPRESA["correo"], "contrasena": EMPRESA["contrasena"]})
    assert login().json() == {"detail": "Su empresa está pendiente de aprobación"}
    cambiar(api, admin, eid, estado="rechazada", motivo_rechazo=MOTIVO)
    assert (login().status_code, login().json()) == (403, {"detail": f"Su empresa fue rechazada: {MOTIVO}"})
    cambiar(api, admin, eid, estado="activa")
    r = login(); h = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert r.status_code == 200 and api.get("/me", headers=h).status_code == 200
    cambiar(api, admin, eid, estado="suspendida")
    assert api.get("/me", headers=h).json() == login().json() == {"detail": "Su empresa está suspendida"}
    cambiar(api, admin, eid, estado="activa")
    assert api.get("/me", headers=h).status_code == 200


# ===== PERMISOS =====

def test_solo_admin(api, admin):
    eid = crear(estado="pendiente")
    with SessionLocal() as s:
        todos = s.query(Permiso).all()
        s.add(Rol(nombre="GERENTE")); s.flush()
        for nombre in ("bodeguero", "cliente", "empresa", "GERENTE"):  # con TODOS los permisos: igual no entran
            s.add(Usuario(nombre=nombre, correo=f"{nombre}@todo.com", contrasena=hash_password("Temp1234*"), permisos=todos,
                          rol_id=s.query(Rol).filter(Rol.nombre == nombre).one().id))
        s.commit()
    for nombre in ("bodeguero", "cliente", "empresa", "GERENTE"):
        h = entrar(api, f"{nombre}@todo.com", "Temp1234*")
        for r in (api.get("/empresas", headers=h), cambiar(api, h, eid, estado="activa"), cambiar(api, h, 99999, estado="activa"),
                  cambiar(api, h, eid, estado="mal"), api.get("/empresas?page=0", headers=h)):  # 403 antes que 404 y 422
            assert (r.status_code, r.json()) == (403, SIN_PERMISO), nombre
    assert en_bd(eid) == ("pendiente", None)
    assert cambiar(api, admin, eid, estado="activa").status_code == 200


def test_sin_sesion(api):
    for r in (api.get("/empresas"), api.patch("/empresas/1/estado", json={"estado": "activa"}),
              api.get("/empresas", headers={"Authorization": "Bearer malo"})):
        assert r.status_code == 401


def test_cors_permite_patch(api):
    r = api.options("/empresas/1/estado", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH",
                                                   "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200 and "PATCH" in r.headers["access-control-allow-methods"]
