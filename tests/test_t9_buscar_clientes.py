# T9: GET /clientes/buscar (contrato, sección 4) y /facturas/clientes en desuso pero funcionando.
import pytest
from conftest import SessionLocal
from test_t7_aislamiento import datos_factura, foto, m  # noqa: F401  (m es el fixture)

from app.config.main import app
from app.core.permisos import PLANTILLAS
from app.modulos import Permiso, Usuario

RUTA = "/clientes/buscar"
CORTA = "debe tener al menos 3 caracteres"
SIN_PERMISO = {"detail": "No tiene permiso para esta acción"}


def agregar(m, rol, nombre, correo, empresa=None, **c):
    """Crea el usuario directo en la base (sin poder iniciar sesión: aquí solo importa si aparece en la búsqueda)."""
    with SessionLocal() as s:
        u = Usuario(nombre=nombre, correo=correo, contrasena="x", rol_id=m.rol[rol], empresa_id=empresa, **c)
        s.add(u); s.commit()
        return u.id


@pytest.fixture
def clientes(m):
    return {
        "maria": agregar(m, "cliente", "María Gómez", "mgomez@correo.com", tipo_documento="CC", numero_documento="9876504321"),
        "mario": agregar(m, "cliente", "Mario Gomezcaceres", "mario@otro.com", tipo_documento="PA", numero_documento="AB998877"),
        "raro": agregar(m, "cliente", "Cien 100% algodon_puro", "raro@otro.com"),
        "inactivo": agregar(m, "cliente", "María Gómez Inactiva", "inactiva@correo.com", numero_documento="5550001112", estado=False),
    }


def buscar(m, q, quien="admin", **p):
    """Ids encontrados, en el orden en que llegan."""
    r = m.pedir(quien, "GET", RUTA, q=q, limit=100, **p)
    assert r.status_code == 200, (quien, q, r.text)
    assert r.json()["total"] == len(r.json()["data"])
    return [c["id"] for c in r.json()["data"]]


# ===== q: OBLIGATORIO Y DE MÍNIMO 3 (eran 5; el front pidió bajarlo) =====

def test_q_de_menos_de_3_recibe_422(m, clientes):
    for q in ("", " ", "a", "Ma", "ma ", "  Ma  ", "     ", "\t\n   ", "ñá", "98"):
        for quien in ("admin", "X", "bX"):
            r = m.pedir(quien, "GET", RUTA, q=q)
            assert (r.status_code, r.json()) == (422, {"detail": f"q: {CORTA}", "errores": {"q": CORTA}}), (quien, q)


def test_q_es_obligatorio(m):
    r = m.pedir("admin", "GET", RUTA)
    assert (r.status_code, r.json()) == (422, {"detail": "q: es obligatorio", "errores": {"q": "es obligatorio"}})
    assert m.pedir("admin", "GET", RUTA, page=1, limit=10).status_code == 422


def test_con_3_justos_ya_busca(m, clientes):
    assert set(buscar(m, "Mar")) == {clientes["maria"], clientes["mario"]}  # por nombre
    assert buscar(m, "  Mar  ") == buscar(m, "Mar")                          # los espacios de los lados no cuentan
    assert buscar(m, "AB9") == [clientes["mario"]]                           # por documento
    assert buscar(m, "mgo") == [clientes["maria"]]                           # por correo
    assert buscar(m, "Mario") == [clientes["mario"]]


# ===== QUÉ BUSCA Y QUÉ DEVUELVE =====

def test_busca_por_nombre_documento_y_correo(m, clientes):
    maria, mario = clientes["maria"], clientes["mario"]
    for q in ("María Gómez", "maria gomez", "MARÍA G", "ría Gó", "9876504321", "504321", "mgomez@correo.com", "MGOMEZ@"):
        assert buscar(m, q) == [maria], q
    for q in ("ab998877", "AB9988", "mario@otro", "caceres"):
        assert buscar(m, q) == [mario], q
    assert buscar(m, "gomez") == [maria, mario] or buscar(m, "gomez") == [mario, maria]
    assert buscar(m, "no existe nadie") == []


def test_ordena_por_nombre(m, clientes):
    otros = [agregar(m, "cliente", f"Zapatería {n}", f"z{i}@z.com") for i, n in enumerate("CAB")]
    assert buscar(m, "Zapater") == [otros[1], otros[2], otros[0]]


def test_cada_fila_trae_solo_los_4_campos_del_contrato(m, clientes):
    r = m.pedir("X", "GET", RUTA, q="9876504321")
    assert r.json() == {"total": 1, "page": 1, "limit": 10, "data": [
        {"id": clientes["maria"], "nombre": "María Gómez", "tipo_documento": "CC", "numero_documento": "9876504321"}]}
    r = m.pedir("X", "GET", RUTA, q="raro@otro.com")  # se encuentra por correo, pero el correo no se muestra
    assert r.json()["data"] == [{"id": clientes["raro"], "nombre": "Cien 100% algodon_puro", "tipo_documento": None, "numero_documento": None}]


def test_solo_clientes_activos(m, clientes):
    for q in ("María Gómez Inactiva", "5550001112", "inactiva@correo.com"):
        assert buscar(m, q) == [], q


def test_los_comodines_de_sql_no_traen_todo(m, clientes):
    """Con "%%%%%" se podrían listar todos y el mínimo de 5 no serviría de nada."""
    for q in ("%%%%%", "_____", "%_%_%", "%%%%%%%%%%", "/////", "\\\\\\\\\\", "' OR 1=1 -- ", "a%b%c", "M_ría Gómez"):
        assert buscar(m, q) == [], q
    assert buscar(m, "100% a") == buscar(m, "algodon_puro") == [clientes["raro"]]  # como texto normal sí se encuentran


# ===== PAGINACIÓN =====

def test_paginacion(m):
    ids = [agregar(m, "cliente", "Repetido SAS", f"rep{i}@r.com") for i in range(23)]  # mismo nombre: el orden debe ser estable
    vistos = []
    for pagina, cuantos in ((1, 10), (2, 10), (3, 3), (4, 0)):
        r = m.pedir("X", "GET", RUTA, q="repetido", page=pagina).json()
        assert (r["total"], r["page"], r["limit"], len(r["data"])) == (23, pagina, 10, cuantos)
        vistos += [c["id"] for c in r["data"]]
    assert vistos == ids  # ni repetidos ni faltantes
    r = m.pedir("X", "GET", RUTA, q="repetido", page=2, limit=20).json()
    assert (r["total"], r["page"], r["limit"], [c["id"] for c in r["data"]]) == (23, 2, 20, ids[20:])
    for p, mensaje in (({"page": 0}, "page: debe ser mayor o igual a 1"), ({"page": -1}, "page: debe ser mayor o igual a 1"),
                       ({"limit": 0}, "limit: debe ser mayor o igual a 1"), ({"limit": 101}, "limit: debe ser menor o igual a 100"),
                       ({"page": "x"}, "page: tiene un formato inválido")):
        r = m.pedir("X", "GET", RUTA, q="repetido", **p)
        assert (r.status_code, r.json()["detail"]) == (422, mensaje)


# ===== AISLAMIENTO POR EMPRESA =====

def test_nunca_salen_los_usuarios_de_las_empresas(m):
    """Ni bodegueros, ni usuarios empresa, ni admins: ni los ajenos ni los propios."""
    for rol, e in (("bodeguero", "X"), ("bodeguero", "Y"), ("bodeguero", None), ("empresa", "X"), ("empresa", "Y"), ("admin", None)):
        agregar(m, rol, "Secreto Interno", f"secreto-{rol}-{e}@s.com".lower(), m.id.get(f"empresa {e}"),
                numero_documento=f"777{len(rol)}{ord((e or 'Z'))}")
    for quien in ("admin", "X", "Y", "bX", "bY", "bV"):
        for q in ("Secreto", "secreto-", "@s.com", "admin@entrega.com", "by@t.com", "bx@t.com"):
            assert buscar(m, q, quien) == [], (quien, q)


def test_todos_los_que_facturan_encuentran_los_mismos_clientes(m, clientes):
    """Los clientes no pertenecen a ninguna empresa (contrato, 3.2): tener facturas en una no los esconde de las otras."""
    for q, esperado in (("María Gómez", [clientes["maria"]]), ("c1@t.com", [m.id["usuario c1"]]), ("c2@t.com", [m.id["usuario c2"]])):
        for quien in ("admin", "X", "Y", "bX", "bX2", "bY", "bV"):
            assert buscar(m, q, quien) == esperado, (quien, q)


def test_empresa_id_no_cambia_nada(m, clientes):
    for quien in ("admin", "X", "bX"):
        for e in (m.id["empresa X"], m.id["empresa Y"], 99999, "abc"):
            assert buscar(m, "María Gómez", quien, empresa_id=e) == [clientes["maria"]], (quien, e)


def test_lo_que_se_encuentra_se_puede_facturar(m, clientes):
    for quien in ("X", "bX"):
        (i,) = buscar(m, "9876504321", quien)
        assert m.crear("/facturas", quien, datos_factura(i, m.id["bodega bX"], m.id["tipo bX"]))


# ===== PERMISOS =====

def test_permisos(m, clientes):
    r = m.api.get(RUTA, params={"q": "María Gómez"})
    assert r.status_code == 401
    with SessionLocal() as s:  # sin facturas_create, aunque tengan todos los demás
        sin = s.query(Permiso).filter(Permiso.nombre != "facturas_create").all()
        for c in ("X", "bX", "c1"):
            s.get(Usuario, m.id[f"usuario {c}"]).permisos = sin
        s.commit()
    for quien in ("X", "bX", "c1"):
        for q in ("María Gómez", "a", None):  # el 403 sale antes que el 422
            r = m.pedir(quien, "GET", RUTA, **({"q": q} if q is not None else {}))
            assert (r.status_code, r.json()) == (403, SIN_PERMISO), (quien, q)
    assert buscar(m, "María Gómez", "Y") == buscar(m, "María Gómez", "admin") == [clientes["maria"]]


def test_las_plantillas_son_las_del_contrato():
    assert {rol for rol, permisos in PLANTILLAS.items() if "facturas_create" in permisos} == {"admin", "bodeguero", "empresa"}


def test_una_empresa_suspendida_no_busca(m, clientes):
    assert m.pedir("admin", "PATCH", f"/empresas/{m.id['empresa X']}/estado", {"estado": "suspendida"}).status_code == 200
    for quien in ("X", "bX"):
        assert m.pedir(quien, "GET", RUTA, q="María Gómez").status_code == 403
    assert buscar(m, "María Gómez", "Y") == [clientes["maria"]]


def test_no_modifica_nada(m, clientes):
    antes = foto()
    buscar(m, "María Gómez", "X")
    assert foto() == antes


# ===== /facturas/clientes: EN DESUSO, PERO IGUAL QUE ANTES =====

def test_el_viejo_sigue_igual(m, clientes):
    todos = [clientes["maria"], clientes["mario"], clientes["raro"], m.id["usuario c1"], m.id["usuario c2"]]
    for quien in ("admin", "X", "Y", "bX", "bV"):
        assert set(todos) <= m.ids(quien, "/facturas/clientes")              # sin q: el listado abierto
        assert clientes["inactivo"] not in m.ids(quien, "/facturas/clientes")
        assert m.ids(quien, "/facturas/clientes", q="Mar") == {clientes["maria"], clientes["mario"]}  # corto: no da 422
        assert m.ids(quien, "/facturas/clientes", q="9876504321") == {clientes["maria"]}
    r = m.pedir("X", "GET", "/facturas/clientes", q="9876504321").json()
    assert r == m.pedir("X", "GET", RUTA, q="9876504321").json()             # mismo formato que el nuevo
    assert m.api.get("/facturas/clientes").status_code == 401


def test_solo_el_viejo_esta_marcado_como_deprecated():
    marcados = {(ruta, metodo) for ruta, ops in app.openapi()["paths"].items() for metodo, op in ops.items() if op.get("deprecated")}
    assert marcados == {("/facturas/clientes", "get")}
