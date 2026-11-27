# T20 (pedidos del frontend):
#   - POST /login acepta el correo o el número de documento (en `correo` o en `identificador`).
#   - Los roles base se pueden desactivar, menos admin. Un rol inactivo no se asigna a usuarios nuevos, tampoco en el registro.
import pytest
from conftest import engine
from sqlalchemy import text
from test_t3_registro import CLIENTE, EMPRESA, registrar
from test_t7_aislamiento import CLAVE, m  # noqa: F401  (m es el fixture)
from test_t14_crud_empresas import EMPRESA as EMPRESA_ADMIN

from app.modulos.usuarios.errors import MSG_ROL_INACTIVO

MALAS = (401, {"detail": "Correo o contraseña incorrectos"})


def login(m, **cuerpo):
    return m.api.post("/login", json={"contrasena": CLAVE, **cuerpo})


def resultado(r):
    return r.status_code, r.json()


def con_documento(m, quien, documento):
    r = m.pedir("admin", "PUT", f"/usuarios/{m.id[f'usuario {quien}']}", {"numero_documento": documento})
    assert r.status_code == 200, r.text


# ===== LOGIN CON DOCUMENTO =====

def test_entra_con_su_documento_o_con_su_correo(m):
    con_documento(m, "bX", "AB123456")
    for cuerpo in ({"correo": "bx@t.com"}, {"correo": "AB123456"}, {"identificador": "AB123456"}, {"identificador": "bx@t.com"},
                   {"correo": "ab123456"},          # sin distinguir mayúsculas
                   {"identificador": "  AB123456 "},  # sin los espacios de los lados
                   {"correo": "BX@T.COM"}):
        r = login(m, **cuerpo)
        assert r.status_code == 200 and r.json()["user"]["id"] == m.id["usuario bX"], (cuerpo, r.text)


def test_mismo_401_con_documento_o_contrasena_malos(m):
    con_documento(m, "bX", "AB123456")
    assert resultado(login(m, correo="AB123456", contrasena="Mala1234*")) == MALAS
    assert resultado(login(m, correo="ZZ999999")) == MALAS              # documento que no existe
    assert resultado(login(m, correo="AB12345")) == MALAS               # parecido no basta
    assert resultado(login(m, identificador="nadie@t.com")) == MALAS


def test_sin_documento_solo_entra_con_el_correo(m):
    assert login(m, correo="c1@t.com").status_code == 200
    assert resultado(login(m, correo="U c1")) == MALAS  # ni con su nombre ni con nada que no sea correo o documento
    assert resultado(login(m, correo="")) [0] == 422


def test_si_llegan_los_dos_usa_identificador(m):
    con_documento(m, "bX", "AB123456")
    assert login(m, correo="otro@t.com", identificador="AB123456").json()["user"]["id"] == m.id["usuario bX"]
    assert resultado(login(m, correo="bx@t.com", identificador="NOEXISTE1")) == MALAS


def test_falta_el_identificador(m):
    for cuerpo in ({}, {"correo": None}, {"correo": None, "identificador": None}):
        r = login(m, **cuerpo)
        assert resultado(r) == (422, {"detail": "correo: es obligatorio", "errores": {"correo": "es obligatorio"}}), cuerpo
    r = login(m, correo="   ")
    assert (r.status_code, r.json()["errores"]) == (422, {"correo": "no puede estar vacío"})


def test_con_documento_tambien_aplican_los_bloqueos(m):
    con_documento(m, "bX", "AB123456")
    assert m.pedir("admin", "PATCH", f"/empresas/{m.id['empresa X']}/estado", {"estado": "suspendida"}).status_code == 200
    assert resultado(login(m, correo="AB123456")) == (403, {"detail": "Su empresa está suspendida"})
    assert resultado(login(m, correo="AB123456", contrasena="Mala1234*")) == MALAS  # sin la contraseña no revela nada
    con_documento(m, "bY", "CD654321")
    assert m.pedir("admin", "PATCH", f"/usuarios/{m.id['usuario bY']}/estado", {"estado": False}).status_code == 200
    assert resultado(login(m, correo="CD654321")) == MALAS  # usuario inactivo


def test_el_boton_authorize_de_docs_tambien(m):
    con_documento(m, "bX", "AB123456")
    r = m.api.post("/login/docs", data={"username": "AB123456", "password": CLAVE})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


# ===== ROLES BASE =====

def desactivar_rol(m, nombre, estado=False):
    r = m.pedir("admin", "PATCH", f"/roles/{m.rol[nombre]}/estado", {"estado": estado})
    assert r.status_code == 200, r.text


def contar():
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in ("usuarios", "empresas")}


def test_cliente_inactivo_cierra_el_registro_de_clientes(m):
    desactivar_rol(m, "cliente")
    antes = contar()
    assert resultado(registrar(m.api, CLIENTE)) == (400, {"detail": "No se pueden crear usuarios con el rol cliente: está inactivo"})
    r = m.pedir("admin", "POST", "/usuarios", {"nombre": "N", "correo": "n@t.com", "contrasena": CLAVE, "rol_id": m.rol["cliente"]})
    assert resultado(r) == (400, {"detail": MSG_ROL_INACTIVO})
    assert contar() == antes
    assert m.pedir("c1", "GET", "/me").status_code == 401  # los que ya son, quedan inactivos (T22)
    assert registrar(m.api, EMPRESA).status_code == 201  # el de empresas sigue abierto
    desactivar_rol(m, "cliente", True)
    assert registrar(m.api, CLIENTE).status_code == 201
    assert m.pedir("c1", "GET", "/me").status_code == 200 and login(m, correo="c1@t.com").status_code == 200  # y vuelven


def test_empresa_inactivo_cierra_el_registro_y_la_creacion_de_empresas(m):
    desactivar_rol(m, "empresa")
    antes = contar()
    assert resultado(registrar(m.api, EMPRESA)) == (400, {"detail": "No se pueden crear usuarios con el rol empresa: está inactivo"})
    r = m.pedir("admin", "POST", "/empresas", {**EMPRESA_ADMIN, "nit": "955111222-3", "correo": "nueva@x.com"})
    assert resultado(r) == (400, {"detail": "No se pueden crear usuarios con el rol empresa: está inactivo"})
    assert contar() == antes  # no queda la empresa sin su usuario
    assert m.pedir("X", "GET", "/me").status_code == 401  # sus usuarios quedan inactivos (T22)
    assert registrar(m.api, CLIENTE).status_code == 201
    desactivar_rol(m, "empresa", True)
    assert registrar(m.api, EMPRESA).status_code == 201
    assert m.pedir("X", "GET", "/me").status_code == 200  # y vuelven


def test_bodeguero_inactivo_nadie_crea_bodegueros(m):
    desactivar_rol(m, "bodeguero")
    nuevo = {"nombre": "B", "correo": "b9@t.com", "contrasena": CLAVE}
    assert resultado(m.pedir("X", "POST", "/usuarios", nuevo)) == (400, {"detail": MSG_ROL_INACTIVO})  # la empresa
    r = m.pedir("admin", "POST", "/usuarios", {**nuevo, "rol_id": m.rol["bodeguero"], "empresa_id": m.id["empresa X"]})
    assert resultado(r) == (400, {"detail": MSG_ROL_INACTIVO})                                          # ni el admin
    assert m.pedir("bX", "GET", "/me").status_code == 401  # los que ya son, quedan inactivos (T22)
    desactivar_rol(m, "bodeguero", True)
    assert m.pedir("X", "POST", "/usuarios", nuevo).status_code == 201
    assert m.pedir("bX", "GET", "/me").status_code == 200  # y vuelven
