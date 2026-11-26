# T15: activar y desactivar con PATCH /{id}/estado en usuarios, roles, bodegas y tipos.
# El alcance de cada rol (lo ajeno da 404/403) se prueba en test_t7 y test_t11_aislamiento; el bloqueo de roles a la empresa,
# en test_t2; que solo el admin toque a un admin, en test_t12; el permiso que exige cada uno, en test_t11_contrato.
import pytest
from conftest import SessionLocal
from test_t7_aislamiento import CLAVE, datos_factura, m  # noqa: F401  (m es el fixture)

from app.modulos import Rol, Usuario
from app.modulos.facturas.errors import MSG_BODEGA, MSG_TIPOS_INACTIVOS
from app.modulos.roles.errors import MSG_BASE_NO_SE_DESACTIVA
from app.modulos.usuarios.errors import MSG_DESACTIVARSE, MSG_ROL_INACTIVO

BOOLEANO = "debe ser true o false"


def rutas(m):
    return {"usuario": f"/usuarios/{m.id['usuario bX']}", "bodega": f"/bodegas/{m.id['bodega bX']}",
            "tipo": f"/tipos/{m.id['tipo bX']}", "rol": f"/roles/{rol_nuevo(m)}"}


def rol_nuevo(m, nombre="Supervisor"):
    if f"rol {nombre}" not in m.id:
        m.id[f"rol {nombre}"] = m.crear("/roles", "admin", {"nombre": nombre})
    return m.id[f"rol {nombre}"]


def estado(m, quien, ruta, valor):
    return m.pedir(quien, "PATCH", f"{ruta}/estado", {"estado": valor})


# ===== LO COMÚN A LOS CUATRO =====

def test_desactiva_y_activa_sin_tocar_lo_demas(m):
    for nombre, ruta in rutas(m).items():
        antes = m.pedir("admin", "GET", ruta).json()
        for valor in (False, False, True, True):  # repetir el mismo estado no es error
            r = estado(m, "admin", ruta, valor)
            assert (r.status_code, r.json()["estado"]) == (200, valor), (nombre, r.text)
            assert m.pedir("admin", "GET", ruta).json()["estado"] is valor
        despues = m.pedir("admin", "GET", ruta).json()
        assert despues["actualizado_por"] == 1, nombre  # el admin de la semilla (test_t12 también usa el id 1)
        ignorar = {"estado", "actualizado_por", "actualizado_en"}
        assert {k: v for k, v in despues.items() if k not in ignorar} == {k: v for k, v in antes.items() if k not in ignorar}, nombre


@pytest.mark.parametrize("cuerpo,mensaje", [({}, "es obligatorio"), ({"estado": None}, BOOLEANO), ({"estado": "true"}, BOOLEANO),
                                            ({"estado": "false"}, BOOLEANO), ({"estado": 1}, BOOLEANO), ({"estado": 0}, BOOLEANO),
                                            ({"estado": "si"}, BOOLEANO), ({"estado": [True]}, BOOLEANO)])
def test_estado_debe_ser_true_o_false(m, cuerpo, mensaje):
    for nombre, ruta in rutas(m).items():
        r = m.pedir("admin", "PATCH", f"{ruta}/estado", cuerpo)
        assert (r.status_code, r.json()["errores"]) == (422, {"estado": mensaje}), (nombre, r.text)
        assert m.pedir("admin", "GET", ruta).json()["estado"] is True  # no cambió nada


def test_ids_que_no_existen(m):
    for ruta in ("/usuarios", "/bodegas", "/tipos", "/roles"):
        assert estado(m, "admin", f"{ruta}/999999", False).status_code == 404, ruta
        r = estado(m, "admin", f"{ruta}/abc", False)
        assert r.status_code == 422, ruta


def test_el_put_sigue_aceptando_estado(m):
    for nombre, ruta in rutas(m).items():
        assert m.pedir("admin", "PUT", ruta, {"estado": False}).json()["estado"] is False, nombre
        assert m.pedir("admin", "PUT", ruta, {"estado": True}).json()["estado"] is True, nombre


# ===== USUARIOS =====

def test_la_empresa_desactiva_a_su_bodeguero_y_este_pierde_el_acceso(m):
    u = f"/usuarios/{m.id['usuario bX']}"
    assert m.pedir("bX", "GET", "/me").status_code == 200
    assert estado(m, "X", u, False).json()["estado"] is False
    assert m.pedir("bX", "GET", "/me").status_code == 401  # su token deja de funcionar
    r = m.api.post("/login", json={"correo": "bx@t.com", "contrasena": CLAVE})
    assert r.status_code == 401
    assert estado(m, "X", u, True).status_code == 200
    assert m.api.post("/login", json={"correo": "bx@t.com", "contrasena": CLAVE}).status_code == 200


def test_nadie_se_desactiva_a_si_mismo(m):
    for quien in ("admin", "bX"):
        with SessionLocal() as s:
            yo = s.query(Usuario).filter_by(correo="admin@entrega.com" if quien == "admin" else "bx@t.com").one().id
        r = estado(m, quien, f"/usuarios/{yo}", False)
        assert (r.status_code, r.json()) == (400, {"detail": MSG_DESACTIVARSE}), quien
        assert estado(m, quien, f"/usuarios/{yo}", True).status_code == 200  # activarse sí (no cambia nada)


def test_sin_el_permiso_de_editar_da_403(m):
    from test_t11_contrato import con_permisos
    con_permisos(m.id["usuario X"], menos="usuarios_edit")
    assert estado(m, "X", f"/usuarios/{m.id['usuario bX']}", False).status_code == 403
    con_permisos(m.id["usuario X"], menos="bodegas_edit")
    assert estado(m, "X", f"/bodegas/{m.id['bodega bX']}", False).status_code == 403
    con_permisos(m.id["usuario X"], menos="tipos_edit")
    assert estado(m, "X", f"/tipos/{m.id['tipo bX']}", False).status_code == 403


# ===== ROLES =====

def test_los_roles_base_no_se_desactivan(m):
    for nombre in ("admin", "empresa", "bodeguero", "cliente"):
        for r in (estado(m, "admin", f"/roles/{m.rol[nombre]}", False), m.pedir("admin", "PUT", f"/roles/{m.rol[nombre]}", {"estado": False})):
            assert (r.status_code, r.json()) == (400, {"detail": MSG_BASE_NO_SE_DESACTIVA}), nombre
        assert estado(m, "admin", f"/roles/{m.rol[nombre]}", True).status_code == 200


def test_un_rol_inactivo_no_se_asigna(m):
    rol = rol_nuevo(m)
    nuevo = {"nombre": "N", "correo": "n1@t.com", "contrasena": CLAVE, "rol_id": rol}
    assert estado(m, "admin", f"/roles/{rol}", False).status_code == 200
    r = m.pedir("admin", "POST", "/usuarios", nuevo)
    assert (r.status_code, r.json()) == (400, {"detail": MSG_ROL_INACTIVO})
    r = m.pedir("admin", "PUT", f"/usuarios/{m.id['usuario c2']}", {"rol_id": rol})
    assert (r.status_code, r.json()) == (400, {"detail": MSG_ROL_INACTIVO})
    assert estado(m, "admin", f"/roles/{rol}", True).status_code == 200
    u = m.crear("/usuarios", "admin", nuevo)
    assert m.pedir("admin", "PUT", f"/usuarios/{m.id['usuario c2']}", {"rol_id": rol}).status_code == 200
    # quien ya lo tiene sigue igual aunque se desactive, y puede editarse sin cambiarle el rol
    assert estado(m, "admin", f"/roles/{rol}", False).status_code == 200
    assert m.pedir("admin", "PUT", f"/usuarios/{u}", {"nombre": "Otro", "rol_id": rol}).status_code == 200


# ===== BODEGAS =====

def test_la_empresa_desactiva_su_bodega_y_ya_no_se_factura_en_ella(m):
    b, c, t = m.id["bodega bX"], m.id["usuario c1"], m.id["tipo bX"]
    assert estado(m, "X", f"/bodegas/{b}", False).json()["estado"] is False
    for quien in ("bX", "X"):
        r = m.pedir(quien, "POST", "/facturas", datos_factura(c, b, t))
        assert (r.status_code, r.json()) == (400, {"detail": MSG_BODEGA}), quien
    assert m.pedir("X", "GET", f"/facturas/{m.id['factura bX']}").status_code == 200  # sus facturas siguen ahí
    assert estado(m, "bX", f"/bodegas/{b}", True).status_code == 200  # su bodeguero también puede
    assert m.pedir("bX", "POST", "/facturas", datos_factura(c, b, t)).status_code == 201


# ===== TIPOS (producto sin stock) =====

def test_un_tipo_sin_stock_no_entra_en_facturas_hasta_reactivarlo(m):
    b, c, t, f = m.id["bodega bX"], m.id["usuario c1"], m.id["tipo bX"], m.id["factura bX"]
    otro = m.crear("/tipos", "bX", {"nombre": "Otro producto"})
    assert estado(m, "X", f"/tipos/{t}", False).json()["estado"] is False
    r = m.pedir("bX", "POST", "/facturas", datos_factura(c, b, t))
    assert (r.status_code, r.json()) == (400, {"detail": MSG_TIPOS_INACTIVOS})
    # la factura que ya lo tenía se puede seguir editando con esa línea
    assert m.pedir("bX", "PUT", f"/facturas/{f}", datos_factura(c, b, t, precio=150)).status_code == 200
    assert m.pedir("bX", "PUT", f"/facturas/{f}", {"observaciones": "Sin cambios en las líneas"}).status_code == 200
    # pero no se puede agregar a otra
    otra = m.crear("/facturas", "bX", datos_factura(c, b, otro))
    r = m.pedir("bX", "PUT", f"/facturas/{otra}", datos_factura(c, b, t))
    assert (r.status_code, r.json()) == (400, {"detail": MSG_TIPOS_INACTIVOS})
    # llega stock: se reactiva y vuelve a servir
    assert estado(m, "bX", f"/tipos/{t}", True).status_code == 200
    assert m.pedir("bX", "POST", "/facturas", datos_factura(c, b, t)).status_code == 201
    assert m.pedir("bX", "PUT", f"/facturas/{otra}", datos_factura(c, b, t)).status_code == 200


def test_desactivar_con_el_put_tambien_bloquea_el_tipo(m):
    b, c, t = m.id["bodega bX"], m.id["usuario c1"], m.id["tipo bX"]
    m.pedir("bX", "PUT", f"/tipos/{t}", {"estado": False})
    assert m.pedir("bX", "POST", "/facturas", datos_factura(c, b, t)).status_code == 400
