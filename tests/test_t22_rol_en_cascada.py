# T22 (pedido del frontend): desactivar un rol desactiva en cascada a sus usuarios; reactivarlo devuelve solo a los que
# desactivó el rol. Convive con la cascada de la empresa (T19): un usuario vuelve a activo solo cuando no lo frena ninguna.
# Borrar un rol con usuarios sigue dando 400: nunca se borran usuarios ni quedan sin rol.
from conftest import SessionLocal, engine, entrar
from sqlalchemy import text
from test_t7_aislamiento import CLAVE, m  # noqa: F401  (m es el fixture)

from app.modulos import Empresa

ROL_INACTIVO = {"detail": "No se puede activar porque su rol está inactivo. Reactive primero el rol"}


def usuario(i):
    with engine.connect() as c:
        return c.execute(text("SELECT estado, rol_id, desactivado_por_rol, desactivado_por_empresa FROM usuarios WHERE id = :i"),
                         {"i": i}).mappings().first()


def activo(i):
    return bool(usuario(i)["estado"])


def rol_estado(m, rol, estado, quien="admin"):
    return m.pedir(quien, "PATCH", f"/roles/{rol}/estado", {"estado": estado})


def supervisores(m):
    """Un rol propio con dos usuarios: s1 activo y s2 desactivado a mano antes."""
    rol = m.crear("/roles", "admin", {"nombre": "Supervisor"})
    s1 = m.crear("/usuarios", "admin", {"nombre": "S1", "correo": "s1@t.com", "contrasena": CLAVE, "rol_id": rol})
    s2 = m.crear("/usuarios", "admin", {"nombre": "S2", "correo": "s2@t.com", "contrasena": CLAVE, "rol_id": rol})
    assert m.pedir("admin", "PATCH", f"/usuarios/{s2}/estado", {"estado": False}).status_code == 200
    return rol, s1, s2


def test_desactivar_el_rol_desactiva_a_sus_usuarios_y_reactivarlo_devuelve_solo_esos(m):
    rol, s1, s2 = supervisores(m)
    token = entrar(m.api, "s1@t.com", CLAVE)
    otros = {u: activo(m.id[f"usuario {u}"]) for u in ("X", "bX", "c1")}
    assert rol_estado(m, rol, False).json()["estado"] is False
    assert not activo(s1) and not activo(s2)
    assert usuario(s1)["rol_id"] == rol  # no se borra ni se queda sin rol
    assert m.api.get("/me", headers=token).status_code == 401  # su token deja de servir
    assert {u: activo(m.id[f"usuario {u}"]) for u in ("X", "bX", "c1")} == otros  # los de otros roles no cambian
    assert rol_estado(m, rol, True).json()["estado"] is True
    assert activo(s1) and not activo(s2)  # s2 estaba inactivo desde antes: sigue así
    assert usuario(s1)["desactivado_por_rol"] == 0 and m.api.get("/me", headers=token).status_code == 200


def test_mientras_el_rol_este_inactivo_sus_usuarios_no_se_activan(m):
    rol, s1, _ = supervisores(m)
    assert rol_estado(m, rol, False).status_code == 200
    for metodo, ruta in (("PATCH", f"/usuarios/{s1}/estado"), ("PUT", f"/usuarios/{s1}")):
        r = m.pedir("admin", metodo, ruta, {"estado": True})
        assert (r.status_code, r.json()) == (400, ROL_INACTIVO), metodo
    # desactivarlo a mano durante la desactivación del rol: al reactivar el rol sigue inactivo
    assert m.pedir("admin", "PATCH", f"/usuarios/{s1}/estado", {"estado": False}).status_code == 200
    assert rol_estado(m, rol, True).status_code == 200
    assert not activo(s1)
    assert m.pedir("admin", "PATCH", f"/usuarios/{s1}/estado", {"estado": True}).status_code == 200  # ahora sí


def test_cambiarle_el_rol_lo_saca_de_la_espera(m):
    rol, s1, _ = supervisores(m)
    assert rol_estado(m, rol, False).status_code == 200
    r = m.pedir("admin", "PUT", f"/usuarios/{s1}", {"rol_id": m.rol["cliente"]})
    assert (r.status_code, r.json()["estado"]) == (200, False)  # sigue inactivo hasta que lo activen
    assert usuario(s1)["desactivado_por_rol"] == 0
    assert rol_estado(m, rol, True).status_code == 200
    assert not activo(s1)  # ya no es de ese rol: reactivarlo no lo toca
    assert m.pedir("admin", "PATCH", f"/usuarios/{s1}/estado", {"estado": True}).status_code == 200


def test_no_se_desactiva_el_rol_admin_ni_el_propio(m):
    r = rol_estado(m, m.rol["admin"], False)
    assert (r.status_code, r.json()) == (400, {"detail": "El rol admin no se puede desactivar"})
    r = rol_estado(m, m.rol["bodeguero"], False, quien="bV")  # bV es bodeguero y tiene todos los permisos
    assert (r.status_code, r.json()) == (400, {"detail": "No puede desactivar su propio rol"})
    assert activo(m.id["usuario bV"]) and activo(m.id["usuario bX"])
    r = m.pedir("bV", "PUT", f"/roles/{m.rol['bodeguero']}", {"estado": False})
    assert r.status_code == 400  # tampoco con el PUT


def test_desactivar_bodeguero_suelta_sus_bodegas(m):
    with engine.connect() as c:
        antes = c.execute(text("SELECT * FROM ordenes ORDER BY id")).all()
    assert rol_estado(m, m.rol["bodeguero"], False).status_code == 200
    for b in ("bX", "bX2", "bY", "bV"):
        assert not activo(m.id[f"usuario {b}"]), b
        assert m.pedir("admin", "GET", f"/bodegas/{m.id[f'bodega {b}']}").json()["bodeguero_id"] is None, b
        assert m.pedir("admin", "GET", f"/bodegas/{m.id[f'bodega {b}']}").json()["estado"] is True, b  # no se desactivan
    assert activo(m.id["usuario X"]) and activo(m.id["usuario c1"])
    with engine.connect() as c:
        assert c.execute(text("SELECT * FROM ordenes ORDER BY id")).all() == antes  # las facturas no cambian
    assert rol_estado(m, m.rol["bodeguero"], True).status_code == 200
    assert activo(m.id["usuario bX"])
    assert m.pedir("admin", "GET", f"/bodegas/{m.id['bodega bX']}").json()["bodeguero_id"] is None  # no vuelven solas


# ===== CON LA CASCADA DE LA EMPRESA =====

def empresa_estado(m, e, estado):
    assert m.pedir("admin", "PATCH", f"/empresas/{m.id[f'empresa {e}']}/estado", {"estado": estado}).status_code == 200


def test_reactivar_el_rol_con_la_empresa_suspendida(m):
    bx = m.id["usuario bX"]
    assert rol_estado(m, m.rol["bodeguero"], False).status_code == 200
    empresa_estado(m, "X", "suspendida")
    assert rol_estado(m, m.rol["bodeguero"], True).status_code == 200
    assert not activo(bx)                       # lo sigue frenando la empresa
    assert activo(m.id["usuario bV"])           # el que no tiene empresa sí vuelve
    empresa_estado(m, "X", "activa")
    assert activo(bx) and usuario(bx)["desactivado_por_rol"] == 0 and usuario(bx)["desactivado_por_empresa"] == 0


def test_reactivar_la_empresa_con_el_rol_inactivo(m):
    bx = m.id["usuario bX"]
    empresa_estado(m, "X", "suspendida")
    assert rol_estado(m, m.rol["bodeguero"], False).status_code == 200
    empresa_estado(m, "X", "activa")
    assert not activo(bx)                       # lo sigue frenando el rol
    assert activo(m.id["usuario X"])            # el usuario empresa sí vuelve
    assert rol_estado(m, m.rol["bodeguero"], True).status_code == 200
    assert activo(bx) and usuario(bx)["desactivado_por_rol"] == 0 and usuario(bx)["desactivado_por_empresa"] == 0


def test_reactivar_el_rol_con_la_empresa_pendiente(m):
    """Una empresa que no está activa (aquí, pendiente) frena la reactivación; al aprobarla, vuelve."""
    by = m.id["usuario bY"]
    assert rol_estado(m, m.rol["bodeguero"], False).status_code == 200
    with SessionLocal() as s:
        s.get(Empresa, m.id["empresa Y"]).estado = "pendiente"
        s.commit()
    assert rol_estado(m, m.rol["bodeguero"], True).status_code == 200
    assert not activo(by)
    empresa_estado(m, "Y", "activa")
    assert activo(by)


# ===== BORRAR UN ROL =====

def test_un_rol_con_usuarios_no_se_borra(m):
    rol, s1, s2 = supervisores(m)
    for estado in (True, False):  # ni activo ni inactivo
        assert rol_estado(m, rol, estado).status_code == 200
        r = m.pedir("admin", "DELETE", f"/roles/{rol}")
        assert (r.status_code, r.json()) == (400, {"detail": "No se puede eliminar: hay usuarios con este rol. "
                                                             "Desactívelo o asigne otro rol a sus usuarios"})
        assert usuario(s1)["rol_id"] == rol and usuario(s2)["rol_id"] == rol
    for u in (s1, s2):  # con otro rol, ya se puede borrar
        assert m.pedir("admin", "PUT", f"/usuarios/{u}", {"rol_id": m.rol["cliente"]}).status_code == 200
    assert m.pedir("admin", "DELETE", f"/roles/{rol}").status_code == 204
    assert usuario(s1) is not None and usuario(s2) is not None
