# T21 (pedido del frontend): borrar o desactivar una bodega suelta sus tipos (pasan a generales de su empresa) y su bodeguero;
# borrar o desactivar un bodeguero suelta las bodegas que tenía a cargo. Nada de eso se borra ni se desactiva.
# Borrar o desactivar un tipo no toca bodegas ni bodegueros. La empresa ve y reasigna sus tipos generales.
import pytest
from conftest import engine
from sqlalchemy import text
from test_t7_aislamiento import CLAVE, datos_bodega, datos_factura, m  # noqa: F401  (m es el fixture)


def fila(tabla, i):
    with engine.connect() as c:
        return c.execute(text(f"SELECT * FROM {tabla} WHERE id = :i"), {"i": i}).mappings().first()


def nueva_bodega(m, codigo, bodeguero="bX2"):
    """Bodega de la empresa X sin facturas, con su bodeguero y dos tipos."""
    b = m.crear("/bodegas", "X", datos_bodega(codigo, bodeguero_id=m.id[f"usuario {bodeguero}"]))
    tipos = [m.crear("/tipos", "X", {"nombre": f"{codigo} {n}", "bodega_id": b}) for n in (1, 2)]
    return b, tipos


# ===== BODEGAS =====

@pytest.mark.parametrize("como", ["PATCH", "PUT"])
def test_desactivar_una_bodega_suelta_sus_tipos_y_su_bodeguero(m, como):
    b, tipos = nueva_bodega(m, "SOL")
    if como == "PATCH":
        r = m.pedir("X", "PATCH", f"/bodegas/{b}/estado", {"estado": False})
    else:
        r = m.pedir("X", "PUT", f"/bodegas/{b}", {"estado": False})
    assert (r.status_code, r.json()["estado"], r.json()["bodeguero_id"]) == (200, False, None)
    for t in tipos:  # generales de la misma empresa, sin desactivar
        assert (fila("tipos", t)["bodega_id"], fila("tipos", t)["empresa_id"], fila("tipos", t)["estado"]) == (None, m.id["empresa X"], 1)
    u = m.pedir("admin", "GET", f"/usuarios/{m.id['usuario bX2']}").json()
    assert u["estado"] is True and m.pedir("bX2", "GET", "/me").status_code == 200  # el bodeguero sigue activo
    assert b not in {x["id"] for x in m.pedir("bX2", "GET", "/bodegas").json()["data"]}  # pero ya no es suya
    # reactivarla no le devuelve nada: se le asignan de nuevo
    r = m.pedir("X", "PATCH", f"/bodegas/{b}/estado", {"estado": True})
    assert (r.json()["estado"], r.json()["bodeguero_id"]) == (True, None)
    assert fila("tipos", tipos[0])["bodega_id"] is None


def test_borrar_una_bodega_suelta_sus_tipos(m):
    b, tipos = nueva_bodega(m, "BOR")
    assert m.pedir("X", "DELETE", f"/bodegas/{b}").status_code == 204
    assert fila("bodegas", b) is None
    for t in tipos:
        assert (fila("tipos", t)["bodega_id"], fila("tipos", t)["empresa_id"], fila("tipos", t)["estado"]) == (None, m.id["empresa X"], 1)
    assert m.pedir("bX2", "GET", "/me").status_code == 200


def test_con_facturas_la_bodega_no_se_borra(m):
    antes = (fila("bodegas", m.id["bodega bX"]), fila("tipos", m.id["tipo bX"]))
    r = m.pedir("X", "DELETE", f"/bodegas/{m.id['bodega bX']}")
    assert (r.status_code, r.json()) == (400, {"detail": "No se puede eliminar: la bodega tiene facturas. Puede desactivarla"})
    assert (fila("bodegas", m.id["bodega bX"]), fila("tipos", m.id["tipo bX"])) == antes  # no soltó nada
    # pero sí se puede desactivar, y sus facturas no cambian
    f = m.pedir("admin", "GET", f"/facturas/{m.id['factura bX']}").json()
    assert m.pedir("X", "PATCH", f"/bodegas/{m.id['bodega bX']}/estado", {"estado": False}).status_code == 200
    despues = m.pedir("admin", "GET", f"/facturas/{m.id['factura bX']}").json()
    assert {k: v for k, v in despues.items() if k != "bodega"} == {k: v for k, v in f.items() if k != "bodega"}


def test_una_bodega_que_cambia_otros_datos_no_suelta_nada(m):
    b, tipos = nueva_bodega(m, "OTR")
    assert m.pedir("X", "PUT", f"/bodegas/{b}", {"ciudad": "Cali", "estado": True}).status_code == 200
    assert fila("bodegas", b)["bodeguero_id"] == m.id["usuario bX2"] and fila("tipos", tipos[0])["bodega_id"] == b


# ===== BODEGUEROS =====

@pytest.mark.parametrize("como", ["PATCH", "PUT"])
def test_desactivar_un_bodeguero_suelta_sus_bodegas(m, como):
    b1, tipos = nueva_bodega(m, "B1")
    b2, _ = nueva_bodega(m, "B2")
    u = m.id["usuario bX2"]
    if como == "PATCH":
        r = m.pedir("X", "PATCH", f"/usuarios/{u}/estado", {"estado": False})
    else:
        r = m.pedir("X", "PUT", f"/usuarios/{u}", {"estado": False})
    assert r.status_code == 200 and r.json()["estado"] is False
    for b in (b1, b2, m.id["bodega bX2"]):  # también la que creó en el fixture
        assert (fila("bodegas", b)["bodeguero_id"], fila("bodegas", b)["estado"]) == (None, 1), b
    assert fila("tipos", tipos[0])["bodega_id"] == b1 and fila("tipos", tipos[0])["estado"] == 1  # sus tipos no cambian
    f = m.pedir("admin", "GET", f"/facturas/{m.id['factura bX2']}").json()
    assert f["estado"] == "emitida"                                                                # ni sus facturas
    assert fila("bodegas", m.id["bodega bX"])["bodeguero_id"] == m.id["usuario bX"]                # ni las de otro


def test_borrar_un_bodeguero_suelta_sus_bodegas(m):
    n = m.crear("/usuarios", "X", {"nombre": "N", "correo": "n@t.com", "contrasena": CLAVE})
    b = m.crear("/bodegas", "X", datos_bodega("DEL", bodeguero_id=n))
    assert m.pedir("X", "DELETE", f"/usuarios/{n}").status_code == 204
    assert (fila("bodegas", b)["bodeguero_id"], fila("bodegas", b)["estado"]) == (None, 1)


def test_un_bodeguero_con_facturas_no_se_borra(m):
    r = m.pedir("X", "DELETE", f"/usuarios/{m.id['usuario bX']}")
    assert (r.status_code, r.json()) == (400, {"detail": "No se puede eliminar: el usuario tiene facturas asociadas. Puede desactivarlo"})
    assert fila("bodegas", m.id["bodega bX"])["bodeguero_id"] == m.id["usuario bX"]  # no soltó nada


def test_la_suspension_de_la_empresa_no_suelta_nada(m):
    """La cascada de la suspensión es otra cosa: al reactivar la empresa todo vuelve como estaba."""
    assert m.pedir("admin", "PATCH", f"/empresas/{m.id['empresa X']}/estado", {"estado": "suspendida"}).status_code == 200
    assert m.pedir("admin", "PATCH", f"/empresas/{m.id['empresa X']}/estado", {"estado": "activa"}).status_code == 200
    assert fila("bodegas", m.id["bodega bX"])["bodeguero_id"] == m.id["usuario bX"]
    assert fila("tipos", m.id["tipo bX"])["bodega_id"] == m.id["bodega bX"]


# ===== TIPOS =====

def test_borrar_o_desactivar_un_tipo_no_toca_bodegas_ni_bodegueros(m):
    b, tipos = nueva_bodega(m, "TIP")
    assert m.pedir("X", "PATCH", f"/tipos/{tipos[0]}/estado", {"estado": False}).status_code == 200
    assert m.pedir("X", "DELETE", f"/tipos/{tipos[1]}").status_code == 204
    assert (fila("bodegas", b)["bodeguero_id"], fila("bodegas", b)["estado"]) == (m.id["usuario bX2"], 1)


# ===== LA EMPRESA Y SUS TIPOS GENERALES =====

def test_la_empresa_ve_y_reasigna_sus_tipos_generales(m):
    b, tipos = nueva_bodega(m, "GEN")
    assert m.pedir("X", "DELETE", f"/bodegas/{b}").status_code == 204
    t = tipos[0]
    assert t in {x["id"] for x in m.pedir("X", "GET", "/tipos", limit=100).json()["data"]}  # la empresa los ve
    assert m.pedir("X", "GET", f"/tipos/{t}").json()["bodega_id"] is None
    assert t not in {x["id"] for x in m.pedir("Y", "GET", "/tipos", limit=100).json()["data"]}  # otra empresa no
    assert m.pedir("Y", "GET", f"/tipos/{t}").status_code == 403
    assert m.pedir("bX", "GET", f"/tipos/{t}").status_code == 403  # ni un bodeguero (no es de sus bodegas)
    # la empresa le asigna una de sus bodegas; una de otra empresa no
    r = m.pedir("X", "PUT", f"/tipos/{t}", {"bodega_id": m.id["bodega bY"]})
    assert (r.status_code, r.json()) == (400, {"detail": "La bodega indicada no existe o no le pertenece"})
    r = m.pedir("X", "PUT", f"/tipos/{t}", {"bodega_id": m.id["bodega bX"]})
    assert (r.status_code, r.json()["bodega_id"], r.json()["empresa_id"]) == (200, m.id["bodega bX"], m.id["empresa X"])
    assert t in {x["id"] for x in m.pedir("bX", "GET", "/tipos").json()["data"]}  # ahora lo ve su bodeguero
    # un bodeguero no puede moverlo (se ignora)
    assert m.pedir("bX", "PUT", f"/tipos/{t}", {"bodega_id": m.id["bodega bX2"]}).json()["bodega_id"] == m.id["bodega bX"]


def test_un_tipo_general_solo_se_factura_en_su_empresa(m):
    b, tipos = nueva_bodega(m, "FAC")
    assert m.pedir("X", "DELETE", f"/bodegas/{b}").status_code == 204
    r = m.pedir("bY", "POST", "/facturas", datos_factura(m.id["usuario c1"], m.id["bodega bY"], tipos[0]))
    assert (r.status_code, r.json()) == (400, {"detail": "Uno o más tipos no pertenecen a la bodega de la factura"})
    assert m.pedir("bX", "POST", "/facturas", datos_factura(m.id["usuario c1"], m.id["bodega bX"], tipos[0])).status_code == 201


def test_los_nombres_de_los_generales_se_comparan_dentro_de_su_empresa(m):
    """Dos bodegas con un tipo del mismo nombre: al soltarlos quedan los dos generales; renombrar no choca con otra empresa."""
    b1, t1 = nueva_bodega(m, "N1")
    b2 = m.crear("/bodegas", "X", datos_bodega("N2"))
    repetido = m.crear("/tipos", "X", {"nombre": "N1 1", "bodega_id": b2})
    for b in (b1, b2):
        assert m.pedir("X", "PATCH", f"/bodegas/{b}/estado", {"estado": False}).status_code == 200
    assert fila("tipos", t1[0])["bodega_id"] is None and fila("tipos", repetido)["bodega_id"] is None
    # un general de la empresa Y con el mismo nombre no estorba al renombrar los de X
    by = m.crear("/bodegas", "Y", datos_bodega("NY"))
    ty = m.crear("/tipos", "Y", {"nombre": "Comun", "bodega_id": by})
    assert m.pedir("Y", "DELETE", f"/bodegas/{by}").status_code == 204
    assert m.pedir("X", "PUT", f"/tipos/{t1[1]}", {"nombre": "Comun"}).status_code == 200
    # pero dentro de la misma empresa sí: otro general de X no puede llamarse igual
    r = m.pedir("X", "PUT", f"/tipos/{t1[0]}", {"nombre": "comun"})
    assert r.status_code == 400 and fila("tipos", ty)["nombre"] == "Comun"
