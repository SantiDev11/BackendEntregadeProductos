# T17: usuarios, bodegas y tipos traen empresa_id y empresa_nombre, como las facturas (pedido del frontend).
from test_t7_aislamiento import CLAVE, datos_bodega, m  # noqa: F401  (m es el fixture)

from conftest import SessionLocal
from app.modulos import Empresa


def empresa(fila):
    return fila["empresa_id"], fila["empresa_nombre"]


def test_listados_y_detalle(m):
    esperado = {"X": (m.id["empresa X"], "Empresa X"), "Y": (m.id["empresa Y"], "Empresa Y"), None: (None, None)}
    duenos = {"bX": "X", "bX2": "X", "bY": "Y", "bV": None}
    for ruta, t in (("/usuarios", "usuario"), ("/bodegas", "bodega"), ("/tipos", "tipo")):
        filas = {f["id"]: f for f in m.pedir("admin", "GET", ruta, limit=100).json()["data"]}
        for b, e in duenos.items():
            i = m.id[f"{t} {b}"]
            assert empresa(filas[i]) == esperado[e], (ruta, b)
            assert empresa(m.pedir("admin", "GET", f"{ruta}/{i}").json()) == esperado[e], (ruta, b)
    usuarios = {f["id"]: f for f in m.pedir("admin", "GET", "/usuarios", limit=100).json()["data"]}
    assert empresa(usuarios[m.id["usuario X"]]) == esperado["X"]  # el usuario empresa
    assert empresa(usuarios[m.id["usuario c1"]]) == (None, None)  # los clientes no son de ninguna empresa
    assert empresa(usuarios[1]) == (None, None)                    # ni el admin
    # la empresa también los ve en lo suyo
    assert {empresa(f) for f in m.pedir("X", "GET", "/bodegas").json()["data"]} == {esperado["X"]}


def test_al_crear_editar_y_cambiar_estado(m):
    x = (m.id["empresa X"], "Empresa X")
    r = m.pedir("admin", "POST", "/usuarios", {"nombre": "B", "correo": "nuevo@t.com", "contrasena": CLAVE, "rol_id": m.rol["bodeguero"],
                                               "empresa_id": x[0]})
    assert r.status_code == 201 and empresa(r.json()) == x
    u = r.json()["id"]
    assert empresa(m.pedir("admin", "PUT", f"/usuarios/{u}", {"nombre": "Otro"}).json()) == x
    assert empresa(m.pedir("X", "PATCH", f"/usuarios/{u}/estado", {"estado": False}).json()) == x

    r = m.pedir("X", "POST", "/bodegas", datos_bodega("NUEVA"))
    assert r.status_code == 201 and empresa(r.json()) == x
    b = r.json()["id"]
    assert empresa(m.pedir("X", "PUT", f"/bodegas/{b}", {"ciudad": "Cali"}).json()) == x
    assert empresa(m.pedir("X", "PATCH", f"/bodegas/{b}/estado", {"estado": False}).json()) == x

    r = m.pedir("bX", "POST", "/tipos", {"nombre": "Nuevo", "bodega_id": m.id["bodega bX"]})
    assert r.status_code == 201 and empresa(r.json()) == x
    t = r.json()["id"]
    assert empresa(m.pedir("bX", "PUT", f"/tipos/{t}", {"nombre": "Otro"}).json()) == x
    assert empresa(m.pedir("bX", "PATCH", f"/tipos/{t}/estado", {"estado": False}).json()) == x
    # si el admin mueve el tipo a una bodega de otra empresa, cambia también la empresa que muestra
    r = m.pedir("admin", "PUT", f"/tipos/{t}", {"bodega_id": m.id["bodega bY"]})
    assert empresa(r.json()) == (m.id["empresa Y"], "Empresa Y")


def test_el_nombre_es_el_actual(m):
    """Si la empresa cambia de razón social, todos muestran la nueva."""
    with SessionLocal() as s:
        s.get(Empresa, m.id["empresa X"]).razon_social = "Nuevo Nombre S.A.S."
        s.commit()
    for ruta in (f"/usuarios/{m.id['usuario bX']}", f"/bodegas/{m.id['bodega bX']}", f"/tipos/{m.id['tipo bX']}"):
        assert m.pedir("admin", "GET", ruta).json()["empresa_nombre"] == "Nuevo Nombre S.A.S.", ruta
