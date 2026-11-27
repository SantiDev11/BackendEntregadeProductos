# T19: suspender una empresa desactiva en cascada sus usuarios, bodegas y tipos; reactivarla devuelve solo lo que desactivó la
# suspensión. Mientras la empresa no está activa, nada suyo se puede activar. Las facturas no se tocan.
from conftest import SessionLocal, engine
from sqlalchemy import text
from test_t7_aislamiento import CLAVE, m  # noqa: F401  (m es el fixture)

from app.modulos import Empresa

SUSPENDIDA = {"detail": "Su empresa está suspendida"}


def mensaje(estado):
    return {"detail": f"No se puede activar porque la empresa está {estado}. Reactive primero la empresa"}


def estados(m, *claves):
    """{'usuario bX': True, ...} leído de la API como admin."""
    salida = {}
    for clave in claves:
        tipo, dueno = clave.split(" ")
        ruta = {"usuario": "/usuarios", "bodega": "/bodegas", "tipo": "/tipos"}[tipo]
        salida[clave] = m.pedir("admin", "GET", f"{ruta}/{m.id[clave]}").json()["estado"]
    return salida


def facturas():
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM ordenes ORDER BY id")).all()


def cambiar_empresa(m, e, estado):
    return m.pedir("admin", "PATCH", f"/empresas/{m.id[f'empresa {e}']}/estado", {"estado": estado})


DE_X = ("usuario X", "usuario bX", "usuario bX2", "bodega bX", "bodega bX2", "tipo bX", "tipo bX2")
DE_Y = ("usuario Y", "usuario bY", "bodega bY", "tipo bY")
SIN_EMPRESA = ("usuario bV", "usuario c1", "bodega bV", "tipo bV")


def test_suspender_desactiva_todo_lo_suyo_y_nada_mas(m):
    otras, antes = estados(m, *DE_Y, *SIN_EMPRESA), facturas()
    assert cambiar_empresa(m, "X", "suspendida").status_code == 200
    assert set(estados(m, *DE_X).values()) == {False}
    assert estados(m, *DE_Y, *SIN_EMPRESA) == otras  # las demás empresas y lo que no tiene empresa no cambian
    assert facturas() == antes                        # las facturas no se tocan


def refresh_de(m, quien):
    return m.api.post("/login", json={"correo": f"{quien.lower()}@t.com", "contrasena": CLAVE}).json()["refresh_token"]


def test_sus_usuarios_siguen_recibiendo_el_403_de_la_empresa(m):
    """La cascada no cambia lo que ya respondía la suspensión: 403, no 401."""
    refresh = {q: refresh_de(m, q) for q in ("X", "bX")}
    assert cambiar_empresa(m, "X", "suspendida").status_code == 200
    for quien, token in refresh.items():
        r = m.api.post("/refresh", json={"refresh_token": token})
        assert (r.status_code, r.json()) == (403, SUSPENDIDA), quien
    for quien in ("X", "bX"):
        assert (m.pedir(quien, "GET", "/me").status_code, m.pedir(quien, "GET", "/me").json()) == (403, SUSPENDIDA), quien
        r = m.api.post("/login", json={"correo": f"{quien.lower()}@t.com", "contrasena": CLAVE})
        assert (r.status_code, r.json()) == (403, SUSPENDIDA), quien
        r = m.api.post("/login", json={"correo": f"{quien.lower()}@t.com", "contrasena": "Mala1234*"})
        assert r.status_code == 401  # con la contraseña mala, el 401 de siempre (no revela que la empresa está suspendida)


def test_mientras_no_este_activa_nada_suyo_se_activa(m):
    assert cambiar_empresa(m, "X", "suspendida").status_code == 200
    for clave, ruta in (("usuario bX", "/usuarios"), ("bodega bX", "/bodegas"), ("tipo bX", "/tipos")):
        i = m.id[clave]
        for metodo, sufijo in (("PATCH", "/estado"), ("PUT", "")):
            r = m.pedir("admin", metodo, f"{ruta}/{i}{sufijo}", {"estado": True})
            assert (r.status_code, r.json()) == (400, mensaje("suspendida")), (clave, metodo)
        assert m.pedir("admin", "GET", f"{ruta}/{i}").json()["estado"] is False
    # editar otros datos sí se puede, y desactivar también
    assert m.pedir("admin", "PUT", f"/bodegas/{m.id['bodega bX']}", {"ciudad": "Cali"}).json()["ciudad"] == "Cali"
    assert m.pedir("admin", "PATCH", f"/tipos/{m.id['tipo bX']}/estado", {"estado": False}).status_code == 200


def test_tampoco_si_esta_rechazada_o_pendiente(m):
    assert m.pedir("admin", "PATCH", f"/usuarios/{m.id['usuario bY']}/estado", {"estado": False}).status_code == 200
    for estado in ("rechazada", "pendiente"):
        with SessionLocal() as s:
            s.get(Empresa, m.id["empresa Y"]).estado = estado
            s.commit()
        r = m.pedir("admin", "PATCH", f"/usuarios/{m.id['usuario bY']}/estado", {"estado": True})
        assert (r.status_code, r.json()) == (400, mensaje(estado)), estado


def test_reactivar_devuelve_solo_lo_que_desactivo_la_suspension(m):
    # antes de suspender, alguien desactivó a mano un bodeguero y un tipo
    for ruta in (f"/usuarios/{m.id['usuario bX2']}", f"/tipos/{m.id['tipo bX2']}"):
        assert m.pedir("X", "PATCH", f"{ruta}/estado", {"estado": False}).status_code == 200
    antes = facturas()
    assert cambiar_empresa(m, "X", "suspendida").status_code == 200
    # durante la suspensión, el admin desactiva a mano un bodeguero, una bodega y un tipo (ya inactivos por la suspensión),
    # con el PATCH o con el PUT
    assert m.pedir("admin", "PATCH", f"/bodegas/{m.id['bodega bX2']}/estado", {"estado": False}).status_code == 200
    assert m.pedir("admin", "PUT", f"/usuarios/{m.id['usuario bX']}", {"estado": False}).status_code == 200
    assert m.pedir("admin", "PATCH", f"/tipos/{m.id['tipo bX']}/estado", {"estado": False}).status_code == 200

    assert cambiar_empresa(m, "X", "activa").status_code == 200
    assert estados(m, *DE_X) == {"usuario X": True, "bodega bX": True,
                                 "usuario bX2": False, "tipo bX2": False,                   # desactivados a mano antes: siguen así
                                 "usuario bX": False, "bodega bX2": False, "tipo bX": False}  # desactivados a mano durante: igual
    assert facturas() == antes
    with engine.connect() as c:  # no queda ninguna marca
        for t in ("usuarios", "bodegas", "tipos"):
            assert c.execute(text(f"SELECT COUNT(*) FROM {t} WHERE desactivado_por_empresa = 1")).scalar() == 0, t
    # vuelven a entrar, y lo desactivado a mano se puede activar otra vez
    assert m.pedir("X", "GET", "/me").status_code == 200
    assert m.pedir("bX", "GET", "/me").status_code == 401  # a él lo desactivaron a mano
    assert m.pedir("X", "PATCH", f"/usuarios/{m.id['usuario bX2']}/estado", {"estado": True}).json()["estado"] is True


def test_suspender_y_reactivar_varias_veces(m):
    for _ in range(2):
        assert cambiar_empresa(m, "X", "suspendida").status_code == 200
        assert set(estados(m, *DE_X).values()) == {False}
        assert cambiar_empresa(m, "X", "activa").status_code == 200
        assert set(estados(m, *DE_X).values()) == {True}


def test_un_usuario_que_sale_de_la_empresa_no_queda_bloqueado(m):
    """Si durante la suspensión el admin lo pasa a cliente, deja de ser de la empresa: sigue inactivo (401) hasta que lo activen."""
    refresh = refresh_de(m, "bX2")
    assert cambiar_empresa(m, "X", "suspendida").status_code == 200
    r = m.pedir("admin", "PUT", f"/usuarios/{m.id['usuario bX2']}", {"rol_id": m.rol["cliente"]})
    assert (r.status_code, r.json()["empresa_id"], r.json()["estado"]) == (200, None, False)
    assert m.api.post("/login", json={"correo": "bx2@t.com", "contrasena": CLAVE}).status_code == 401
    assert m.pedir("bX2", "GET", "/me").status_code == 401                           # ni con el token que ya tenía
    assert m.api.post("/refresh", json={"refresh_token": refresh}).status_code == 401  # ni con su refresh
    assert m.pedir("admin", "PATCH", f"/usuarios/{m.id['usuario bX2']}/estado", {"estado": True}).status_code == 200
    assert m.api.post("/login", json={"correo": "bx2@t.com", "contrasena": CLAVE}).status_code == 200


def test_empresa_estado_en_los_listados(m):
    assert cambiar_empresa(m, "X", "suspendida").status_code == 200
    esperado = {**{c: "suspendida" for c in DE_X}, **{c: "activa" for c in DE_Y}, **{c: None for c in SIN_EMPRESA}}
    for ruta, t in (("/usuarios", "usuario"), ("/bodegas", "bodega"), ("/tipos", "tipo")):
        filas = {f["id"]: f["empresa_estado"] for f in m.pedir("admin", "GET", ruta, limit=100).json()["data"]}
        for clave, estado in esperado.items():
            if clave.startswith(t):
                assert filas[m.id[clave]] == estado, clave
                assert m.pedir("admin", "GET", f"{ruta}/{m.id[clave]}").json()["empresa_estado"] == estado, clave
