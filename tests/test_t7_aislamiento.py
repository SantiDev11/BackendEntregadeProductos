# T7: aislamiento por empresa. Dos empresas (X, Y) más los datos viejos sin empresa (V), e intentos de cruzar TODO.
import re

import pytest
from conftest import SessionLocal, engine, entrar
from sqlalchemy import text

from app.config.main import app
from app.core.security import hash_password
from app.modulos import Bodega, Empresa, Orden, Permiso, Rol, Tipo, Usuario

CLAVE = "Temp1234*"
TABLAS = ("usuarios", "bodegas", "tipos", "ordenes", "orden_detalle", "usuario_permisos")


def datos_bodega(codigo, **c):
    return {"nombre": f"Bodega {codigo}", "codigo": codigo, "direccion": "C1", "ciudad": "Bog", "departamento": "Cun",
            "telefono": "6015551234", "correo": "b@b.com", "recibe_nombre": "A", "recibe_documento": "123", "recibe_cargo": "J",
            "recibe_telefono": "3001234567", **c}


def datos_factura(cliente, bodega, tipo, precio=100):
    return {"cliente_id": cliente, "bodega_id": bodega, "forma_pago": "contado", "medio_pago": "efectivo",
            "detalle": [{"tipo_id": tipo, "descripcion": "x", "unidad_medida": "UND", "cantidad": 1, "precio_unitario": precio,
                         "descuento_porcentaje": 0, "iva_porcentaje": 0}]}


class Mundo:
    """Todo lo de la prueba. m.h["X"] es la sesión de la empresa X; m.h["bX"] la de su bodeguero; m.id["bodega X"] un id."""

    def __init__(self, api):
        self.api, self.h, self.id = api, {"admin": entrar(api, "admin@entrega.com", "Admin123*")}, {}
        with SessionLocal() as s:
            self.rol = {r.nombre: r.id for r in s.query(Rol)}
            todos = s.query(Permiso).all()
            for e in "XY":
                emp = Empresa(razon_social=f"Empresa {e}", nit=f"90000000{e == 'X':d}", dv="1", estado="activa")
                s.add(emp); s.flush()
                self.id[f"empresa {e}"] = emp.id
            # El aislamiento debe aguantar aunque les asignen TODOS los permisos
            for clave, rol, e in (("X", "empresa", "X"), ("Y", "empresa", "Y"), ("bX", "bodeguero", "X"), ("bX2", "bodeguero", "X"),
                                  ("bY", "bodeguero", "Y"), ("bV", "bodeguero", None), ("c1", "cliente", None), ("c2", "cliente", None),
                                  ("sin", "empresa", None)):
                u = Usuario(nombre=f"U {clave}", correo=f"{clave.lower()}@t.com", contrasena=hash_password(CLAVE), rol_id=self.rol[rol],
                            empresa_id=self.id.get(f"empresa {e}"), permisos=todos)
                s.add(u); s.flush()
                self.id[f"usuario {clave}"] = u.id
            s.commit()
        for clave in ("X", "Y", "bX", "bX2", "bY", "bV", "c1", "c2", "sin"):
            self.h[clave] = entrar(api, f"{clave.lower()}@t.com", CLAVE)
        # Cada bodeguero crea por la API su bodega, su tipo y una factura para el cliente c1
        for b, precio in (("bX", 100), ("bX2", 200), ("bY", 1000), ("bV", 5000)):
            self.id[f"bodega {b}"] = self.crear("/bodegas", b, datos_bodega(f"C-{b}"))
            self.id[f"tipo {b}"] = self.crear("/tipos", b, {"nombre": f"Tipo {b}"})
            self.id[f"factura {b}"] = self.crear("/facturas", b, datos_factura(self.id["usuario c1"], self.id[f"bodega {b}"],
                                                                                self.id[f"tipo {b}"], precio))

    def crear(self, ruta, quien, cuerpo):
        r = self.api.post(ruta, headers=self.h[quien], json=cuerpo)
        assert r.status_code == 201, (ruta, quien, r.text)
        return r.json()["id"]

    def pedir(self, quien, metodo, ruta, cuerpo=None, **params):
        return self.api.request(metodo, ruta, headers=self.h[quien], json=cuerpo, params=params or None)

    def ids(self, quien, ruta, **params):
        r = self.pedir(quien, "GET", ruta, limit=100, **params)
        assert r.status_code == 200, (quien, ruta, r.text)
        assert r.json()["total"] == len(r.json()["data"])  # el total tampoco cuenta lo ajeno
        return {x["id"] for x in r.json()["data"]}

    def de(self, tipo, *claves):
        return {self.id[f"{tipo} {c}"] for c in claves}


@pytest.fixture
def m(api):
    return Mundo(api)


def foto():
    """Contenido completo de las tablas, para comprobar que un intento no cambió nada."""
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT * FROM {t} ORDER BY 1, 2")).all() for t in TABLAS}


# ===== LISTADOS =====

def test_listados_por_rol(m):
    for ruta, t in (("/bodegas", "bodega"), ("/tipos", "tipo"), ("/facturas", "factura")):
        assert m.ids("X", ruta) == m.de(t, "bX", "bX2"), ruta          # empresa: todo lo de su empresa
        assert m.ids("Y", ruta) == m.de(t, "bY"), ruta
        for b in ("bX", "bX2", "bY", "bV"):                             # bodeguero: solo lo suyo
            assert m.ids(b, ruta) == m.de(t, b), (ruta, b)
        assert m.ids("sin", ruta) == set(), ruta                        # empresa sin empresa asignada: nada (ni lo viejo)
        assert m.ids("admin", ruta) == m.de(t, "bX", "bX2", "bY", "bV"), ruta
    assert m.ids("X", "/usuarios") == m.de("usuario", "bX", "bX2")      # solo sus bodegueros, ni siquiera ella misma
    assert m.ids("Y", "/usuarios") == m.de("usuario", "bY")
    assert m.ids("bX", "/usuarios") == m.de("usuario", "bX", "bX2")
    assert m.ids("sin", "/usuarios") == set()
    assert m.de("usuario", "X", "Y", "bX", "bY", "bV", "c1", "sin") <= m.ids("admin", "/usuarios")


def test_empresa_id_solo_le_sirve_al_admin(m):
    x, y = m.id["empresa X"], m.id["empresa Y"]
    for ruta, t in (("/bodegas", "bodega"), ("/tipos", "tipo"), ("/facturas", "factura")):
        assert m.ids("admin", ruta, empresa_id=x) == m.de(t, "bX", "bX2")
        assert m.ids("admin", ruta, empresa_id=y) == m.de(t, "bY")
        assert m.ids("admin", ruta, empresa_id=99999) == set()
        for quien in ("X", "Y", "bX", "bX2", "bY", "bV", "c1", "sin"):
            for e in (x, y, 99999):
                assert m.ids(quien, ruta, empresa_id=e) == m.ids(quien, ruta), (quien, ruta, e)
    assert m.ids("admin", "/usuarios", empresa_id=x) == m.de("usuario", "X", "bX", "bX2")
    for quien in ("X", "Y", "bX", "bV", "sin"):
        assert m.ids(quien, "/usuarios", empresa_id=y) == m.ids(quien, "/usuarios"), quien


def test_los_demas_filtros_no_abren_otra_empresa(m):
    assert m.ids("X", "/bodegas", bodeguero_id=m.id["usuario bY"]) == set()
    assert m.ids("X", "/bodegas", bodeguero_id=m.id["usuario bX2"]) == m.de("bodega", "bX2")
    assert m.ids("X", "/bodegas", q="C-bY") == m.ids("X", "/tipos", q="Tipo bY") == set()
    assert m.ids("X", "/tipos", bodega_id=m.id["bodega bY"]) == m.ids("X", "/tipos", bodega_id=m.id["bodega bV"]) == set()
    assert m.ids("X", "/facturas", q="U c1") == m.de("factura", "bX", "bX2")
    for p in ({"rol": "admin"}, {"rol": "cliente"}, {"rol": "empresa"}, {"rol_id": m.rol["admin"]}, {"q": "admin"}, {"q": "by@t.com"}):
        assert m.ids("X", "/usuarios", **p) == set(), p
    assert m.ids("X", "/usuarios", rol="bodeguero") == m.de("usuario", "bX", "bX2")
    assert m.pedir("X", "GET", "/bodegas", empresa_id="abc").status_code == 422


# ===== DETALLE, EDICIÓN Y BORRADO POR ID =====

def intentos(m, dueno):
    """Todos los endpoints por id sobre los recursos de `dueno` (bX, bY, bV): (método, ruta, cuerpo, código esperado)."""
    u, b, t, f = (m.id[f"{x} {dueno}"] for x in ("usuario", "bodega", "tipo", "factura"))
    return [
        ("GET", f"/usuarios/{u}", None, 404), ("PUT", f"/usuarios/{u}", {"nombre": "HACK", "contrasena": "Hackeado1*"}, 404),
        ("DELETE", f"/usuarios/{u}", None, 404), ("PATCH", f"/usuarios/{u}/estado", {"estado": False}, 404),
        ("GET", f"/bodegas/{b}", None, 404), ("PUT", f"/bodegas/{b}", {"nombre": "HACK"}, 404), ("DELETE", f"/bodegas/{b}", None, 404),
        ("PATCH", f"/bodegas/{b}/estado", {"estado": False}, 404),
        ("GET", f"/tipos/{t}", None, 403), ("PUT", f"/tipos/{t}", {"nombre": "HACK"}, 403), ("DELETE", f"/tipos/{t}", None, 403),
        ("PATCH", f"/tipos/{t}/estado", {"estado": False}, 403),
        ("GET", f"/facturas/{f}", None, 404), ("GET", f"/facturas/{f}/pdf", None, 404), ("PUT", f"/facturas/{f}", {"observaciones": "HACK"}, 404),
        ("POST", f"/facturas/{f}/entregar", None, 404), ("POST", f"/facturas/{f}/recibir", None, 404), ("DELETE", f"/facturas/{f}", None, 404),
    ]


def permisos_de_usuario(m, dueno):
    u = m.id[f"usuario {dueno}"]
    return [("GET", f"/usuarios/{u}/permisos", None), ("PUT", f"/usuarios/{u}/permisos", {"permisos_ids": []}),
            ("POST", f"/usuarios/{u}/permisos/1", None), ("DELETE", f"/usuarios/{u}/permisos/1", None)]


@pytest.mark.parametrize("quien,ajenos", [("X", ("bY", "bV")), ("Y", ("bX", "bV")), ("sin", ("bX", "bY", "bV")), ("bX", ("bY", "bV")),
                                          ("bY", ("bX", "bV")), ("bV", ("bX", "bY"))])
def test_nadie_toca_lo_de_otra_empresa(m, quien, ajenos):
    antes, fallos = foto(), []
    for dueno in ajenos:
        for metodo, ruta, cuerpo, codigo in intentos(m, dueno):
            r = m.pedir(quien, metodo, ruta, cuerpo)
            if r.status_code != codigo:
                fallos.append((metodo, ruta, r.status_code, r.text[:90]))
        for metodo, ruta, cuerpo in permisos_de_usuario(m, dueno):
            r = m.pedir(quien, metodo, ruta, cuerpo)
            if r.status_code != (403 if quien in ("X", "Y", "sin") else 404):  # el rol empresa nunca gestiona permisos
                fallos.append((metodo, ruta, r.status_code, r.text[:90]))
    assert fallos == []
    assert foto() == antes  # ni un solo dato cambió
    for dueno in ajenos:
        entrar(m.api, f"{dueno.lower()}@t.com", CLAVE)  # la contraseña tampoco


def test_un_recurso_ajeno_responde_igual_que_uno_que_no_existe(m):
    """No debe revelarse que existe (salvo tipos, que ya usaba 403 para los ajenos)."""
    for ruta, t in (("/usuarios", "usuario"), ("/bodegas", "bodega"), ("/facturas", "factura")):
        ajeno, inexistente = (m.pedir("X", "GET", f"{ruta}/{i}") for i in (m.id[f"{t} bY"], 999999))
        assert (ajeno.status_code, ajeno.json()) == (inexistente.status_code, inexistente.json()) == (404, inexistente.json())


def test_dentro_de_la_empresa_cada_bodeguero_solo_lo_suyo(m):
    antes = foto()
    for metodo, ruta, cuerpo, codigo in (x for x in intentos(m, "bX2") if not x[1].startswith("/usuarios/")):  # sin los de usuarios
        assert m.pedir("bX", metodo, ruta, cuerpo).status_code == codigo, (metodo, ruta)
    assert foto() == antes


def test_la_empresa_si_maneja_lo_suyo(m):
    f = m.id["factura bX"]
    for ruta in (f"/usuarios/{m.id['usuario bX']}", f"/bodegas/{m.id['bodega bX']}", f"/tipos/{m.id['tipo bX']}", f"/facturas/{f}", f"/facturas/{f}/pdf"):
        assert m.pedir("X", "GET", ruta).status_code == 200, ruta
    assert m.pedir("X", "PUT", f"/bodegas/{m.id['bodega bX']}", {"ciudad": "Cali"}).json()["ciudad"] == "Cali"
    assert m.pedir("X", "PUT", f"/tipos/{m.id['tipo bX']}", {"nombre": "Nuevo"}).json()["nombre"] == "Nuevo"
    assert m.pedir("X", "PUT", f"/facturas/{f}", {"observaciones": "ok"}).status_code == 200
    assert m.pedir("X", "POST", f"/facturas/{f}/entregar").status_code == 200
    assert m.pedir("X", "DELETE", f"/facturas/{m.id['factura bX2']}").status_code == 204
    assert m.pedir("X", "DELETE", f"/tipos/{m.id['tipo bX2']}").status_code == 204
    assert m.pedir("X", "DELETE", f"/bodegas/{m.id['bodega bX2']}").status_code == 204


def test_el_admin_llega_a_todo(m):
    for dueno in ("bX", "bY", "bV"):
        for metodo, ruta, cuerpo, _ in intentos(m, dueno):
            if metodo == "GET":
                assert m.pedir("admin", metodo, ruta).status_code == 200, ruta
        assert m.pedir("admin", "PUT", f"/bodegas/{m.id[f'bodega {dueno}']}", {"ciudad": "Cali"}).status_code == 200
        assert m.pedir("admin", "PUT", f"/usuarios/{m.id[f'usuario {dueno}']}", {"ciudad": "Cali"}).status_code == 200
        assert m.pedir("admin", "PUT", f"/tipos/{m.id[f'tipo {dueno}']}", {"estado": False}).status_code == 200


# ===== CREAR Y CRUZAR REFERENCIAS =====

def empresa_de(modelo, i):
    with SessionLocal() as s:
        return s.get(modelo, i).empresa_id


def test_lo_creado_nace_en_la_empresa_del_token(m):
    x, y = m.id["empresa X"], m.id["empresa Y"]
    for modelo, t in ((Bodega, "bodega"), (Tipo, "tipo"), (Orden, "factura")):
        assert [empresa_de(modelo, m.id[f"{t} {b}"]) for b in ("bX", "bX2", "bY", "bV")] == [x, x, y, None], t
    b = m.crear("/bodegas", "X", datos_bodega("NUEVA", empresa_id=y))             # el empresa_id del cuerpo se ignora
    t = m.crear("/tipos", "X", {"nombre": "T", "bodega_id": b, "empresa_id": y})
    f = m.crear("/facturas", "X", {**datos_factura(m.id["usuario c1"], b, t), "empresa_id": y})
    assert {empresa_de(Bodega, b), empresa_de(Tipo, t), empresa_de(Orden, f)} == {x}
    assert {b} <= m.ids("X", "/bodegas") and {t} <= m.ids("X", "/tipos") and {f} <= m.ids("X", "/facturas")
    assert not {b} & m.ids("Y", "/bodegas") and not {f} & m.ids("Y", "/facturas")


def test_no_se_puede_usar_lo_de_otra_empresa_al_crear_o_editar(m):
    antes = foto()
    c, bx, tx = m.id["usuario c1"], m.id["bodega bX"], m.id["tipo bX"]
    for otra in ("bY", "bV"):
        b, t, u = m.id[f"bodega {otra}"], m.id[f"tipo {otra}"], m.id[f"usuario {otra}"]
        casos = [
            ("X", "POST", "/facturas", datos_factura(c, b, t)), ("bX", "POST", "/facturas", datos_factura(c, b, t)),   # bodega ajena
            ("X", "POST", "/facturas", datos_factura(c, bx, t)), ("bX", "POST", "/facturas", datos_factura(c, bx, t)),  # tipo ajeno
            ("X", "PUT", f"/facturas/{m.id['factura bX']}", {"bodega_id": b}),
            ("X", "PUT", f"/facturas/{m.id['factura bX']}", datos_factura(c, bx, t)),
            ("X", "POST", "/tipos", {"nombre": "Z", "bodega_id": b}),
            ("X", "POST", "/bodegas", datos_bodega("Z", bodeguero_id=u)), ("X", "PUT", f"/bodegas/{bx}", {"bodeguero_id": u}),
        ]
        for quien, metodo, ruta, cuerpo in casos:
            r = m.pedir(quien, metodo, ruta, cuerpo)
            assert r.status_code == 400, (quien, metodo, ruta, otra, r.status_code, r.text)
    assert foto() == antes
    r = m.pedir("X", "PUT", f"/tipos/{tx}", {"bodega_id": m.id["bodega bY"]})  # mover un tipo: solo admin, se ignora
    assert r.status_code == 200 and r.json()["bodega_id"] == bx


def test_empresa_elige_bodeguero_de_su_empresa(m):
    r = m.pedir("X", "POST", "/bodegas", datos_bodega("CB", bodeguero_id=m.id["usuario bX2"]))
    assert r.status_code == 201 and r.json()["bodeguero_id"] == m.id["usuario bX2"]
    assert r.json()["id"] in m.ids("bX2", "/bodegas") and r.json()["id"] not in m.ids("bX", "/bodegas")
    r = m.pedir("X", "PUT", f"/bodegas/{r.json()['id']}", {"bodeguero_id": m.id["usuario bX"]})
    assert r.status_code == 200 and r.json()["bodeguero_id"] == m.id["usuario bX"]
    r = m.pedir("X", "POST", "/bodegas", datos_bodega("SB"))
    assert r.status_code == 201 and r.json()["bodeguero_id"] is None


def test_admin_no_puede_dejar_una_bodega_cruzada(m):
    r = m.pedir("admin", "POST", "/bodegas", datos_bodega("AD", bodeguero_id=m.id["usuario bY"], empresa_id=m.id["empresa Y"]))
    assert r.status_code == 201 and empresa_de(Bodega, r.json()["id"]) == m.id["empresa Y"] and r.json()["id"] in m.ids("bY", "/bodegas")
    r = m.pedir("admin", "PUT", f"/bodegas/{m.id['bodega bX']}", {"bodeguero_id": m.id["usuario bY"]})
    assert (r.status_code, r.json()) == (400, {"detail": "El bodeguero no pertenece a la empresa de la bodega"})


def test_si_el_admin_mueve_algo_la_empresa_lo_sigue(m):
    r = m.pedir("admin", "PUT", f"/tipos/{m.id['tipo bX']}", {"bodega_id": m.id["bodega bY"]})
    assert r.status_code == 200 and empresa_de(Tipo, m.id["tipo bX"]) == m.id["empresa Y"]
    assert m.id["tipo bX"] in m.ids("Y", "/tipos") and m.id["tipo bX"] not in m.ids("X", "/tipos")
    r = m.pedir("admin", "PUT", f"/facturas/{m.id['factura bX2']}", datos_factura(m.id["usuario c1"], m.id["bodega bY"], m.id["tipo bY"]))
    assert r.status_code == 200 and empresa_de(Orden, m.id["factura bX2"]) == m.id["empresa Y"]


def test_empresa_sin_empresa_asignada_no_crea_nada(m):
    antes = foto()
    assert m.pedir("sin", "POST", "/bodegas", datos_bodega("S")).status_code == 403
    assert m.pedir("sin", "POST", "/usuarios", {"nombre": "x", "correo": "s@s.com", "contrasena": CLAVE}).status_code == 403
    assert m.pedir("sin", "POST", "/tipos", {"nombre": "S"}).status_code == 400
    assert m.pedir("sin", "POST", "/facturas", datos_factura(m.id["usuario c1"], m.id["bodega bV"], m.id["tipo bV"])).status_code == 400
    assert foto() == antes


# ===== USUARIOS: LA EMPRESA GESTIONA SUS BODEGUEROS =====

def test_empresa_crea_bodegueros_de_su_empresa(m):
    nuevo = {"nombre": "Nuevo", "correo": "n1@t.com", "contrasena": CLAVE}
    for i, extra in enumerate(({}, {"rol_id": None}, {"rol_id": m.rol["bodeguero"]}, {"empresa_id": m.id["empresa Y"]})):
        r = m.pedir("X", "POST", "/usuarios", {**nuevo, "correo": f"n{i}@t.com", **extra})
        assert r.status_code == 201 and r.json()["rol"] == "bodeguero", r.text
        assert empresa_de(Usuario, r.json()["id"]) == m.id["empresa X"]
        assert r.json()["id"] in m.ids("X", "/usuarios") and r.json()["id"] not in m.ids("Y", "/usuarios")
    assert entrar(m.api, "n0@t.com", CLAVE)


def test_empresa_no_puede_escalar(m):
    antes = foto()
    nuevo = {"nombre": "Malo", "correo": "malo@t.com", "contrasena": CLAVE}
    for rol in ("admin", "empresa", "cliente"):
        assert m.pedir("X", "POST", "/usuarios", {**nuevo, "rol_id": m.rol[rol]}).status_code == 403
        assert m.pedir("X", "PUT", f"/usuarios/{m.id['usuario bX']}", {"rol_id": m.rol[rol]}).status_code == 403
        assert m.pedir("bX", "POST", "/usuarios", {**nuevo, "rol_id": m.rol[rol]}).status_code == 403  # un bodeguero con el permiso, igual
        assert m.pedir("bX", "PUT", f"/usuarios/{m.id['usuario bX']}", {"rol_id": m.rol[rol]}).status_code == 403
    assert m.pedir("X", "POST", "/usuarios", {**nuevo, "rol_id": 99999}).status_code == 403
    for u in (1, m.id["usuario X"], m.id["usuario Y"], m.id["usuario c1"]):  # el admin, ella misma, otra empresa, un cliente
        assert m.pedir("X", "PUT", f"/usuarios/{u}", {"rol_id": m.rol["admin"], "contrasena": "Hackeado1*"}).status_code == 404
        assert m.pedir("X", "DELETE", f"/usuarios/{u}").status_code == 404
    assert foto() == antes


def test_empresa_edita_y_elimina_sus_bodegueros(m):
    u = m.id["usuario bX"]
    r = m.pedir("X", "PUT", f"/usuarios/{u}", {"nombre": "Otro", "rol_id": m.rol["bodeguero"]})
    assert r.status_code == 200 and r.json()["nombre"] == "Otro"
    r = m.pedir("X", "DELETE", f"/usuarios/{u}")  # tiene facturas
    assert r.status_code == 400
    r = m.pedir("X", "POST", "/usuarios", {"nombre": "N", "correo": "n@t.com", "contrasena": CLAVE})
    n = r.json()["id"]
    b = m.crear("/bodegas", "X", datos_bodega("DEL", bodeguero_id=n))
    r = m.pedir("X", "DELETE", f"/usuarios/{n}")
    assert (r.status_code, r.json()) == (400, {"detail": "No se puede eliminar: el usuario tiene bodegas asignadas"})
    assert m.pedir("X", "DELETE", f"/bodegas/{b}").status_code == 204
    assert m.pedir("X", "DELETE", f"/usuarios/{n}").status_code == 204


def test_rol_id_sigue_siendo_obligatorio_para_el_admin(m):
    for cuerpo in ({}, {"rol_id": None}):
        r = m.pedir("admin", "POST", "/usuarios", {"nombre": "x", "correo": "z@t.com", "contrasena": CLAVE, **cuerpo})
        assert (r.status_code, r.json()) == (422, {"detail": "rol_id: es obligatorio", "errores": {"rol_id": "es obligatorio"}})


# ===== CLIENTES =====

def test_el_cliente_ve_sus_facturas_de_cualquier_empresa_y_nada_mas(m):
    assert m.ids("c1", "/facturas") == set()  # todas están en emitida
    for b in ("bX", "bY", "bV"):
        assert m.pedir(b, "POST", f"/facturas/{m.id[f'factura {b}']}/entregar").status_code == 200
    assert m.ids("c1", "/facturas") == m.de("factura", "bX", "bY", "bV")
    assert m.ids("c2", "/facturas") == set()
    for b in ("bX", "bY", "bV"):
        f = m.id[f"factura {b}"]
        assert m.pedir("c1", "GET", f"/facturas/{f}").status_code == m.pedir("c1", "GET", f"/facturas/{f}/pdf").status_code == 200
        assert m.pedir("c2", "GET", f"/facturas/{f}").status_code == m.pedir("c2", "POST", f"/facturas/{f}/rechazar", {"motivo_rechazo": "x" * 10}).status_code == 404
    assert m.pedir("c1", "GET", f"/facturas/{m.id['factura bX2']}").status_code == 404  # sigue en emitida
    assert m.pedir("c1", "POST", f"/facturas/{m.id['factura bY']}/rechazar", {"motivo_rechazo": "No era lo pedido"}).status_code == 200
    for ruta in ("/bodegas", "/tipos"):
        assert m.ids("c1", ruta) == set()
    for otra in ("bX", "bY"):  # ni con facturas_create puede facturar desde la bodega de una empresa
        assert m.pedir("c1", "POST", "/facturas", datos_factura(m.id["usuario c2"], m.id[f"bodega {otra}"], m.id[f"tipo {otra}"])).status_code == 400


# ===== ESTADÍSTICAS =====

def panel(m, quien, **p):
    r = m.pedir(quien, "GET", "/estadisticas/resumen", **p)
    assert r.status_code == 200, r.text
    return ({t["clave"]: t["valor"] for t in r.json()["tarjetas"]},
            {s["clave"]: {d["etiqueta"]: d["valor"] for d in s["datos"]} for s in r.json()["series"]})


def test_estadisticas_por_empresa(m):
    x, y = m.id["empresa X"], m.id["empresa Y"]
    comun = {"pendientes": 0, "rechazadas": 0}
    t, s = panel(m, "X")
    assert t == {**comun, "facturas": 2, "facturado": 300, "bodegueros": 2, "bodegas": 2, "tipos": 2}
    assert s["por_bodega"] == {"Bodega C-bX": 100, "Bodega C-bX2": 200} and s["top_productos"] == {"Tipo bX": 1, "Tipo bX2": 1}
    assert set(s) == {"por_estado", "por_fecha", "por_bodega", "top_productos"} and s["por_estado"]["Emitida"] == 2
    t, s = panel(m, "Y")
    assert t == {**comun, "facturas": 1, "facturado": 1000, "bodegueros": 1, "bodegas": 1, "tipos": 1} and s["por_bodega"] == {"Bodega C-bY": 1000}
    assert panel(m, "bX")[0] == {**comun, "facturas": 1, "facturado": 100, "bodegas": 1, "tipos": 1}
    assert panel(m, "bV")[0] == {**comun, "facturas": 1, "facturado": 5000, "bodegas": 1, "tipos": 1}
    assert panel(m, "sin")[0] == {**comun, "facturas": 0, "facturado": 0, "bodegueros": 0, "bodegas": 0, "tipos": 0}
    total = panel(m, "admin")[0]
    assert (total["facturas"], total["facturado"], total["bodegas_activas"]) == (4, 6300, 4)
    assert panel(m, "admin", empresa_id=x)[0] == {**comun, "facturas": 2, "facturado": 300, "usuarios_activos": 3, "bodegas_activas": 2}
    assert panel(m, "admin", empresa_id=y)[0]["facturado"] == 1000
    for quien in ("X", "Y", "bX", "bY", "bV", "c1", "sin"):
        for e in (x, y):
            assert panel(m, quien, empresa_id=e) == panel(m, quien), quien


# ===== QUE NO SE ESCAPE NINGÚN ENDPOINT =====

# Cada ruta de la API y por qué está aislada. Si alguien agrega una y no la revisa, esta prueba falla.
REVISADAS = {
    "listado filtrado": {"GET /usuarios", "GET /bodegas", "GET /tipos", "GET /facturas", "GET /estadisticas/resumen"},
    "por id": {"GET /usuarios/{}", "PUT /usuarios/{}", "DELETE /usuarios/{}", "GET /usuarios/{}/permisos", "PUT /usuarios/{}/permisos",
               "POST /usuarios/{}/permisos/{}", "DELETE /usuarios/{}/permisos/{}", "GET /bodegas/{}", "PUT /bodegas/{}", "DELETE /bodegas/{}",
               "GET /tipos/{}", "PUT /tipos/{}", "DELETE /tipos/{}", "GET /facturas/{}", "GET /facturas/{}/pdf", "PUT /facturas/{}",
               "DELETE /facturas/{}", "POST /facturas/{}/entregar", "POST /facturas/{}/aceptar", "POST /facturas/{}/rechazar",
               "POST /facturas/{}/recibir", "PATCH /usuarios/{}/estado", "PATCH /bodegas/{}/estado", "PATCH /tipos/{}/estado"},
    "crea en la empresa del token": {"POST /usuarios", "POST /bodegas", "POST /tipos", "POST /facturas"},
    "sin datos de empresas": {"GET /", "POST /login", "POST /refresh", "POST /register", "GET /me", "GET /solo-admin",
                              "GET /clientes/buscar", "GET /facturas/clientes"},  # los clientes no pertenecen a ninguna empresa
    "solo admin": {"GET /empresas", "POST /empresas", "GET /empresas/{}", "PUT /empresas/{}", "DELETE /empresas/{}", "PATCH /empresas/{}/estado"},
    "bloqueado al rol empresa": {"GET /permisos", "POST /permisos", "GET /permisos/{}", "PUT /permisos/{}", "DELETE /permisos/{}",
                                 "GET /roles", "POST /roles", "GET /roles/{}", "PUT /roles/{}", "DELETE /roles/{}", "PUT /roles/{}/permisos",
                                 "PATCH /roles/{}/estado"},
}


def test_todos_los_endpoints_estan_revisados():
    reales = {f"{metodo.upper()} {re.sub(r'{[^}]+}', '{}', ruta)}" for ruta, ops in app.openapi()["paths"].items() for metodo in ops}
    revisadas = set().union(*REVISADAS.values())
    assert reales - revisadas == set(), "hay endpoints sin revisar"
    assert revisadas - reales == set(), "hay endpoints que ya no existen"
