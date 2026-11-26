# T8: empresa con la que nace lo que se crea. El admin la indica (empresa_id, 422 si falta o no existe, 400 si no está activa);
# a los demás se les asigna la del token y se ignora el empresa_id del body.
import pytest
from conftest import SessionLocal, entrar
from test_t7_aislamiento import CLAVE, datos_bodega, datos_factura, empresa_de, foto, m  # noqa: F401  (m es el fixture)

from app.modulos import Bodega, Empresa, Orden, Rol, Tipo, Usuario

FALTA, NUMERO, NO_EXISTE = "es obligatorio", "debe ser un número", "la empresa indicada no existe"
# Lo que el admin puede mandar mal (el body tal cual) y el mensaje que recibe
INVALIDOS = [({}, FALTA), ({"empresa_id": None}, FALTA),
             ({"empresa_id": "1"}, NUMERO), ({"empresa_id": ""}, NUMERO), ({"empresa_id": "abc"}, NUMERO), ({"empresa_id": True}, NUMERO),
             ({"empresa_id": [1]}, NUMERO), ({"empresa_id": {"id": 1}}, NUMERO), ({"empresa_id": 1.5}, "debe ser un número entero"),
             ({"empresa_id": 99999}, NO_EXISTE), ({"empresa_id": 0}, NO_EXISTE), ({"empresa_id": -1}, NO_EXISTE),
             ({"empresa_id": 10 ** 25}, NO_EXISTE)]


def datos_usuario(rol_id=None, correo="nuevo@t.com", **c):
    return {"nombre": "Nuevo", "correo": correo, "contrasena": CLAVE, **({"rol_id": rol_id} if rol_id else {}), **c}


def ajenos(m):
    """Todo lo que alguien que no es admin podría mandar en empresa_id: otra empresa, la suya, inexistente o basura."""
    return [m.id["empresa Y"], m.id["empresa X"], 99999, 0, None, "", "abc", str(m.id["empresa Y"]), True, 1.5, [1], {"id": 1}]


# ===== EL ADMIN: OBLIGATORIO =====

@pytest.mark.parametrize("que", ["bodeguero", "empresa", "bodega"])
def test_admin_sin_empresa_id_valido_recibe_422(m, que):
    antes = foto()
    for extra, mensaje in INVALIDOS:
        if que == "bodega":
            r = m.pedir("admin", "POST", "/bodegas", datos_bodega("N", **extra))
        else:
            r = m.pedir("admin", "POST", "/usuarios", datos_usuario(m.rol[que], **extra))
        assert (r.status_code, r.json()) == (422, {"detail": f"empresa_id: {mensaje}", "errores": {"empresa_id": mensaje}}), (extra, r.text)
    assert foto() == antes  # no se creó nada


def test_admin_crea_bodegueros_y_usuarios_empresa(m):
    for e in "XY":
        for rol in ("bodeguero", "empresa"):
            correo = f"{rol}{e}@t.com".lower()
            i = m.crear("/usuarios", "admin", datos_usuario(m.rol[rol], correo, empresa_id=m.id[f"empresa {e}"]))
            assert empresa_de(Usuario, i) == m.id[f"empresa {e}"]
            h = entrar(m.api, correo, CLAVE)
            assert m.api.get("/me", headers=h).json()["empresa"]["id"] == m.id[f"empresa {e}"]
            if rol == "bodeguero":
                assert i in m.ids(e, "/usuarios") and i not in m.ids("Y" if e == "X" else "X", "/usuarios")


def test_admin_crea_bodegas(m):
    for e, otra in ("XY", "YX"):
        b = m.crear("/bodegas", "admin", datos_bodega(f"N{e}", empresa_id=m.id[f"empresa {e}"]))
        assert empresa_de(Bodega, b) == m.id[f"empresa {e}"]
        assert b in m.ids(e, "/bodegas") and b not in m.ids(otra, "/bodegas")


@pytest.mark.parametrize("estado", ["pendiente", "rechazada", "suspendida"])
def test_admin_no_puede_usar_una_empresa_que_no_esta_activa(m, estado):
    """Contrato, 3.4: 400."""
    with SessionLocal() as s:
        e = Empresa(razon_social="P", estado=estado)
        s.add(e); s.commit()
        i = e.id
    antes = foto()
    peticiones = [("/usuarios", datos_usuario(m.rol["bodeguero"], empresa_id=i)), ("/usuarios", datos_usuario(m.rol["empresa"], empresa_id=i)),
                  ("/bodegas", datos_bodega("P", empresa_id=i))]
    for ruta, cuerpo in peticiones:
        r = m.pedir("admin", "POST", ruta, cuerpo)
        assert (r.status_code, r.json()) == (400, {"detail": "La empresa indicada no está activa"}), ruta
    assert foto() == antes
    with SessionLocal() as s:  # al activarse, las mismas peticiones pasan
        s.get(Empresa, i).estado = "activa"
        s.commit()
    for n, (ruta, cuerpo) in enumerate(peticiones):
        m.crear(ruta, "admin", {**cuerpo, "correo": f"p{n}@t.com"})


def test_los_roles_sin_empresa_no_revisan_el_estado(m):
    with SessionLocal() as s:
        e = Empresa(razon_social="P", estado="suspendida")
        s.add(e); s.commit()
        i = e.id
    assert empresa_de(Usuario, m.crear("/usuarios", "admin", datos_usuario(m.rol["cliente"], empresa_id=i))) is None
    assert empresa_de(Bodega, m.crear("/bodegas", "X", datos_bodega("P", empresa_id=i))) == m.id["empresa X"]  # a la empresa se le ignora


def test_la_bodega_del_admin_debe_ser_de_la_empresa_de_su_bodeguero(m):
    x, y, antes = m.id["empresa X"], m.id["empresa Y"], foto()
    for dueno, e in (("bY", x), ("bX", y), ("bV", x)):  # bV no tiene empresa
        r = m.pedir("admin", "POST", "/bodegas", datos_bodega("N", bodeguero_id=m.id[f"usuario {dueno}"], empresa_id=e))
        assert (r.status_code, r.json()) == (400, {"detail": "El bodeguero no pertenece a la empresa de la bodega"}), dueno
    # tener bodeguero no reemplaza al empresa_id
    r = m.pedir("admin", "POST", "/bodegas", datos_bodega("N", bodeguero_id=m.id["usuario bX"]))
    assert r.status_code == 422 and r.json()["errores"] == {"empresa_id": FALTA}
    assert foto() == antes
    b = m.crear("/bodegas", "admin", datos_bodega("N", bodeguero_id=m.id["usuario bX"], empresa_id=x))
    assert empresa_de(Bodega, b) == x and b in m.ids("bX", "/bodegas")


def test_los_roles_sin_empresa_no_la_piden_y_la_ignoran(m):
    with SessionLocal() as s:
        otro = Rol(nombre="GERENTE")
        s.add(otro); s.commit()
        roles = [m.rol["cliente"], m.rol["admin"], otro.id]
    for n, rol in enumerate(roles):
        for k, extra in enumerate(({}, {"empresa_id": m.id["empresa X"]}, {"empresa_id": "abc"})):
            i = m.crear("/usuarios", "admin", datos_usuario(rol, f"n{n}{k}@t.com", **extra))
            assert empresa_de(Usuario, i) is None


def test_los_demas_422_siguen_saliendo(m):
    """El empresa_id no tapa los errores que ya había."""
    r = m.pedir("admin", "POST", "/usuarios", {"empresa_id": "abc"})
    assert r.status_code == 422 and set(r.json()["errores"]) == {"nombre", "correo", "contrasena"}
    r = m.pedir("admin", "POST", "/usuarios", datos_usuario(empresa_id=m.id["empresa X"]))
    assert r.status_code == 422 and r.json()["errores"] == {"rol_id": FALTA}
    r = m.pedir("admin", "POST", "/usuarios", datos_usuario(99999, empresa_id=m.id["empresa X"]))
    assert (r.status_code, r.json()) == (400, {"detail": "El rol indicado no existe"})


# ===== LOS DEMÁS: LA DEL TOKEN =====

def test_empresa_crea_usuarios_y_bodegas_en_la_suya(m):
    for i, valor in enumerate(ajenos(m)):
        u = m.crear("/usuarios", "X", datos_usuario(None, f"n{i}@t.com", empresa_id=valor))
        b = m.crear("/bodegas", "X", datos_bodega(f"N{i}", empresa_id=valor))
        assert empresa_de(Usuario, u) == empresa_de(Bodega, b) == m.id["empresa X"], valor
    u, b = m.crear("/usuarios", "X", datos_usuario()), m.crear("/bodegas", "X", datos_bodega("SIN"))  # sin enviarlo
    assert empresa_de(Usuario, u) == empresa_de(Bodega, b) == m.id["empresa X"]
    assert len(m.ids("Y", "/usuarios")) == len(m.ids("Y", "/bodegas")) == 1  # a la otra empresa no le llegó nada


def test_empresa_crea_tipos_y_facturas_en_la_suya(m):
    b = m.id["bodega bX"]
    for i, valor in enumerate(ajenos(m)):
        t = m.crear("/tipos", "X", {"nombre": f"T{i}", "bodega_id": b, "empresa_id": valor})
        f = m.crear("/facturas", "X", {**datos_factura(m.id["usuario c1"], b, t), "empresa_id": valor})
        assert empresa_de(Tipo, t) == empresa_de(Orden, f) == m.id["empresa X"], valor


def test_bodeguero_crea_en_la_de_su_token(m):
    for quien, e in (("bX", m.id["empresa X"]), ("bY", m.id["empresa Y"]), ("bV", None)):  # bV es anterior a las empresas
        for i, valor in enumerate(ajenos(m)):
            assert empresa_de(Bodega, m.crear("/bodegas", quien, datos_bodega(f"{quien}{i}", empresa_id=valor))) == e, (quien, valor)
    u = m.crear("/usuarios", "bX", datos_usuario(None, empresa_id=m.id["empresa Y"]))  # con el permiso asignado
    assert empresa_de(Usuario, u) == m.id["empresa X"]


def test_el_body_no_le_da_empresa_a_quien_no_tiene(m):
    x, antes = m.id["empresa X"], foto()
    assert m.pedir("sin", "POST", "/usuarios", datos_usuario(empresa_id=x)).status_code == 403
    assert m.pedir("sin", "POST", "/bodegas", datos_bodega("S", empresa_id=x)).status_code == 403
    assert foto() == antes
    u = m.crear("/usuarios", "bV", datos_usuario(m.rol["bodeguero"], empresa_id=x))  # bodeguero viejo con el permiso
    assert empresa_de(Usuario, u) is None


def test_editar_no_cambia_la_empresa(m):
    for quien in ("admin", "X"):
        u, b = m.id["usuario bX"], m.id["bodega bX"]
        for ruta, modelo, i in (("/usuarios", Usuario, u), ("/bodegas", Bodega, b)):
            r = m.pedir(quien, "PUT", f"{ruta}/{i}", {"ciudad": "Cali", "empresa_id": m.id["empresa Y"]})
            assert r.status_code == 200 and empresa_de(modelo, i) == m.id["empresa X"], (quien, ruta)
