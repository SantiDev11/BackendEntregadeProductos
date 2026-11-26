# T3: POST /register (cliente y empresa), transacción y bloqueo de sesión por estado de la empresa
import pytest
from conftest import SessionLocal, entrar
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.config.main import app
from app.core.permisos import PLANTILLAS
from app.core.security import verify_password
from app.modulos import Empresa, Usuario
from app.modulos.registro import services

CLIENTE = {"tipo": "cliente", "nombre": "Juan Pérez", "tipo_documento": "CC", "numero_documento": "70203040",
           "telefono": "3001234567", "correo": "juan@cliente.com", "contrasena": "Cliente123*"}
EMPRESA = {"tipo": "empresa", "razon_social": "Distribuidora Andina S.A.S.", "nit": "900123456-1", "telefono": "3001234567",
           "direccion": "Calle 10 # 20-30", "representante": "Ana Torres", "correo": "empresa@andina.com",
           "contrasena": "Empresa123*"}
PENDIENTE = {"detail": "Su empresa está pendiente de aprobación"}


def registrar(api, base, **cambios):
    return api.post("/register", json={**base, **cambios})


def login(api, correo, clave):
    return api.post("/login", json={"correo": correo, "contrasena": clave})


def cuenta():
    with SessionLocal() as s:
        return s.query(Usuario).count(), s.query(Empresa).count()


def poner_estado(estado, motivo=None):
    with SessionLocal() as s:
        e = s.query(Empresa).one()
        e.estado, e.motivo_rechazo = estado, motivo
        s.commit()


# ===== CLIENTE =====

def test_cliente_queda_activo_y_puede_entrar(api):
    r = registrar(api, CLIENTE)
    assert r.status_code == 201, r.text
    uid = r.json()["user"]["id"]
    assert r.json() == {"message": "Cuenta creada",
                        "user": {"id": uid, "nombre": "Juan Pérez", "correo": "juan@cliente.com", "rol": "cliente"}}
    s = login(api, "juan@cliente.com", "Cliente123*")
    assert s.status_code == 200
    assert {p["nombre"] for p in s.json()["user"]["permisos"]} == set(PLANTILLAS["cliente"])
    with SessionLocal() as db:
        u = db.get(Usuario, uid)
        assert (u.estado, u.empresa_id, u.tipo_documento, u.numero_documento, u.telefono) == (True, None, "CC", "70203040", "3001234567")
        assert u.contrasena != "Cliente123*" and verify_password("Cliente123*", u.contrasena)


def test_cliente_normaliza_los_datos(api):
    r = registrar(api, CLIENTE, nombre="  Juan  ", correo="JUAN@Cliente.COM", tipo_documento="pa", numero_documento=" AB123 ",
                  telefono=" 3001234567 ")
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        u = db.get(Usuario, r.json()["user"]["id"])
        assert (u.nombre, u.correo, u.tipo_documento, u.numero_documento, u.telefono) == ("Juan", "juan@cliente.com", "PA", "AB123", "3001234567")


# ===== EMPRESA =====

def test_empresa_queda_pendiente_con_su_usuario(api):
    r = registrar(api, EMPRESA)
    assert r.status_code == 201, r.text
    eid = r.json()["empresa"]["id"]
    assert r.json() == {"message": "Registro recibido. Un administrador debe aprobar la empresa", "estado": "pendiente",
                        "empresa": {"id": eid, "razon_social": "Distribuidora Andina S.A.S.", "nit": "900123456-1", "estado": "pendiente"}}
    with SessionLocal() as db:
        e = db.get(Empresa, eid)
        assert (e.nit, e.dv, e.estado, e.motivo_rechazo) == ("900123456", "1", "pendiente", None)
        assert (e.correo, e.telefono, e.direccion, e.representante) == ("empresa@andina.com", "3001234567", "Calle 10 # 20-30", "Ana Torres")
        u = db.query(Usuario).filter(Usuario.empresa_id == eid).one()
        assert (u.nombre, u.correo, u.rol.nombre, u.estado) == ("Ana Torres", "empresa@andina.com", "empresa", True)
        assert {p.nombre for p in u.permisos} == set(PLANTILLAS["empresa"])
        assert verify_password("Empresa123*", u.contrasena)


def test_las_respuestas_no_traen_token_ni_contrasena(api):
    for base in (CLIENTE, EMPRESA):
        texto = registrar(api, base).text
        assert "token" not in texto and "contrasena" not in texto and "$2b$" not in texto


@pytest.mark.parametrize("base", [CLIENTE, EMPRESA], ids=["cliente", "empresa"])
def test_no_se_puede_elegir_rol_ni_estado(api, base):
    assert registrar(api, base, rol_id=1, rol="admin", estado="activa", empresa_id=1, permisos=[1, 2], id=1).status_code == 201
    with SessionLocal() as db:
        u = db.query(Usuario).filter(Usuario.correo == base["correo"]).one()
        assert u.rol.nombre == base["tipo"] and {p.nombre for p in u.permisos} == set(PLANTILLAS[base["tipo"]])
        assert [e.estado for e in db.query(Empresa)] == (["pendiente"] if base is EMPRESA else [])


# ===== DATOS INVÁLIDOS =====

OBLIGATORIO, VACIO, DIGITOS, LARGO = "es obligatorio", "no puede estar vacío", "solo puede tener números", "debe tener entre 7 y 15 dígitos"
NIT, CORTO, DEMASIADO, CORREO = "debe tener el formato 900123456-1", "es demasiado corto", "es demasiado largo", "formato de correo inválido"
FORMATO = "tiene un formato inválido"
COMUNES = [("correo", "no-es-correo", CORREO), ("correo", "a" * 60 + "@" + "b" * 50 + ".com", DEMASIADO), ("contrasena", "1234567", CORTO),
           ("contrasena", "x" * 73, DEMASIADO), ("telefono", "300-123", DIGITOS), ("telefono", "123456", LARGO), ("telefono", "", VACIO),
           ("telefono", 3001234567, FORMATO)]
INVALIDOS = {
    "cliente": (CLIENTE, COMUNES + [
        ("nombre", "  ", VACIO), ("nombre", "x" * 101, DEMASIADO), ("tipo_documento", "XX", "debe ser CC, NIT, CE o PA"),
        ("tipo_documento", "", VACIO), ("numero_documento", "10-AB", "solo puede tener letras y números"), ("numero_documento", "", VACIO),
        ("numero_documento", "1" * 31, DEMASIADO)]),
    "empresa": (EMPRESA, COMUNES + [
        ("razon_social", "", VACIO), ("razon_social", "x" * 101, DEMASIADO), ("representante", "x" * 101, DEMASIADO),
        ("direccion", "x" * 201, DEMASIADO), ("nit", "900123456", NIT), ("nit", "900.123.456-1", NIT), ("nit", "900123456-12", NIT),
        ("nit", "ABC123456-1", NIT), ("nit", "٩٠٠١٢٣٤٥٦-1", NIT), ("nit", "", VACIO), ("nit", 900123456, FORMATO)]),
}


@pytest.mark.parametrize("tipo", INVALIDOS)
def test_datos_invalidos(api, tipo):
    base, casos = INVALIDOS[tipo]
    antes, fallos = cuenta(), []
    for campo, valor, mensaje in casos:
        r = registrar(api, base, **{campo: valor})
        if r.status_code != 422 or r.json() != {"detail": f"{campo}: {mensaje}", "errores": {campo: mensaje}}:
            fallos.append((campo, valor, r.status_code, r.text[:150]))
    assert fallos == [] and cuenta() == antes


@pytest.mark.parametrize("base", [CLIENTE, EMPRESA], ids=["cliente", "empresa"])
def test_todos_los_campos_son_obligatorios(api, base):
    r = api.post("/register", json={"tipo": base["tipo"]})
    assert r.status_code == 422 and r.json()["errores"] == {c: OBLIGATORIO for c in base if c != "tipo"}
    for campo in base:
        if campo != "tipo":
            r = registrar(api, base, **{campo: None})
            assert r.status_code == 422 and list(r.json()["errores"]) == [campo], (campo, r.text)


@pytest.mark.parametrize("cuerpo,mensaje", [({}, OBLIGATORIO), ({"tipo": "admin"}, "debe ser cliente o empresa"),
                                            ({"tipo": ""}, "debe ser cliente o empresa"), ({"tipo": None}, "debe ser cliente o empresa")])
def test_tipo_invalido(api, cuerpo, mensaje):
    r = api.post("/register", json={k: v for k, v in {**CLIENTE, **cuerpo}.items() if not (cuerpo == {} and k == "tipo")})
    assert (r.status_code, r.json()) == (422, {"detail": f"tipo: {mensaje}", "errores": {"tipo": mensaje}})


def test_cuerpo_que_no_es_json(api):
    r = api.post("/register", content="{mal", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["detail"] == "El cuerpo de la petición no es un JSON válido"


# ===== REPETIDOS =====

def test_repetidos(api):
    assert registrar(api, CLIENTE).status_code == registrar(api, EMPRESA).status_code == 201
    antes = cuenta()
    correo, doc, nit = "Ya existe un usuario con ese correo", "Ya existe un usuario con ese documento", "Ya existe una empresa con ese NIT"
    casos = [
        (CLIENTE, {"numero_documento": "999"}, correo),
        (CLIENTE, {"numero_documento": "999", "correo": "JUAN@CLIENTE.COM"}, correo),
        (CLIENTE, {"correo": "otro@x.com"}, doc),
        (EMPRESA, {"nit": "800111222-3"}, correo),
        (EMPRESA, {"correo": "otro@x.com"}, nit),
        (EMPRESA, {"correo": "otro@x.com", "nit": "900123456-9"}, nit),       # mismo NIT con otro dígito
        (EMPRESA, {"correo": "juan@cliente.com", "nit": "800111222-3"}, correo),  # correo de un cliente
        (CLIENTE, {"correo": "empresa@andina.com", "numero_documento": "999"}, correo),  # correo de una empresa
        (CLIENTE, {"correo": "admin@entrega.com", "numero_documento": "999"}, correo),
    ]
    for base, cambios, mensaje in casos:
        r = registrar(api, base, **cambios)
        assert (r.status_code, r.json()) == (400, {"detail": mensaje}), (cambios, r.text)
    assert cuenta() == antes


# ===== TRANSACCIÓN =====

@pytest.fixture
def falla_al_crear_usuario():
    def explotar(mapper, conexion, usuario):
        raise RuntimeError("falla simulada al insertar el usuario")
    event.listen(Usuario, "before_insert", explotar)
    yield
    event.remove(Usuario, "before_insert", explotar)


def test_si_falla_el_usuario_no_queda_la_empresa(api, falla_al_crear_usuario):
    antes = cuenta()
    r = TestClient(app, raise_server_exceptions=False).post("/register", json=EMPRESA)
    assert r.status_code == 500 and cuenta() == antes == (3, 0)


def test_despues_del_fallo_se_puede_registrar(api):
    def explotar(mapper, conexion, usuario):
        raise RuntimeError("falla simulada")
    event.listen(Usuario, "before_insert", explotar)
    try:
        TestClient(app, raise_server_exceptions=False).post("/register", json=EMPRESA)
    finally:
        event.remove(Usuario, "before_insert", explotar)
    assert registrar(api, EMPRESA).status_code == 201 and cuenta() == (4, 1)


def test_si_fallan_los_permisos_no_queda_nada(api, monkeypatch):
    def explotar(*a):
        raise RuntimeError("falla simulada")
    monkeypatch.setattr(services, "rol_por_nombre", explotar)  # la empresa ya se insertó en la transacción
    antes = cuenta()
    assert TestClient(app, raise_server_exceptions=False).post("/register", json=EMPRESA).status_code == 500
    assert cuenta() == antes


@pytest.mark.parametrize("base,cambios,mensaje", [
    (CLIENTE, {"numero_documento": "999"}, "Ya existe un usuario con ese correo"),
    (CLIENTE, {"correo": "otro@x.com"}, "Ya existe un usuario con ese documento"),
    (EMPRESA, {"correo": "otro@x.com"}, "Ya existe una empresa con ese NIT"),
    (EMPRESA, {"nit": "800111222-3"}, "Ya existe un usuario con ese correo"),  # aquí la empresa ya se había insertado
], ids=["correo", "documento", "nit", "correo-empresa"])
def test_dos_registros_al_mismo_tiempo(api, monkeypatch, base, cambios, mensaje):
    """El segundo pasa la revisión previa (aún no veía al primero) y lo frena la base: debe dar 400, no 500."""
    assert registrar(api, base).status_code == 201
    antes, original, llamadas = cuenta(), services.validate_repetidos, []

    def primera_vez_no_ve_nada(db, datos):
        llamadas.append(1)
        if len(llamadas) > 1:
            original(db, datos)
    monkeypatch.setattr(services, "validate_repetidos", primera_vez_no_ve_nada)
    r = registrar(api, base, **cambios)
    assert (r.status_code, r.json()) == (400, {"detail": mensaje}) and cuenta() == antes


# ===== SESIÓN SEGÚN EL ESTADO DE LA EMPRESA =====

@pytest.mark.parametrize("estado,motivo,detalle", [
    ("pendiente", None, "Su empresa está pendiente de aprobación"),
    ("rechazada", "El NIT no coincide", "Su empresa fue rechazada: El NIT no coincide"),
    ("rechazada", None, "Su empresa fue rechazada"),
    ("suspendida", None, "Su empresa está suspendida"),
])
def test_empresa_no_activa_no_entra(api, estado, motivo, detalle):
    registrar(api, EMPRESA); poner_estado(estado, motivo)
    r = login(api, EMPRESA["correo"], EMPRESA["contrasena"])
    assert (r.status_code, r.json()) == (403, {"detail": detalle})
    r = api.post("/login/docs", data={"username": EMPRESA["correo"], "password": EMPRESA["contrasena"]})
    assert r.status_code == 403
    r = login(api, EMPRESA["correo"], "mala12345")  # con la clave mala no se revela el estado
    assert (r.status_code, r.json()) == (401, {"detail": "Correo o contraseña incorrectos"})


def test_empresa_activa_entra_y_si_la_suspenden_pierde_la_sesion(api):
    registrar(api, EMPRESA); poner_estado("activa")
    s = login(api, EMPRESA["correo"], EMPRESA["contrasena"])
    assert s.status_code == 200 and s.json()["user"]["rol"] == "empresa"
    h = {"Authorization": "Bearer " + s.json()["access_token"]}
    assert api.get("/me", headers=h).status_code == api.get("/bodegas", headers=h).status_code == 200
    assert api.post("/refresh", json={"refresh_token": s.json()["refresh_token"]}).status_code == 200
    poner_estado("suspendida")
    for r in (api.get("/me", headers=h), api.get("/bodegas", headers=h), api.post("/refresh", json={"refresh_token": s.json()["refresh_token"]})):
        assert (r.status_code, r.json()) == (403, {"detail": "Su empresa está suspendida"})
    poner_estado("activa")
    assert api.get("/me", headers=h).status_code == 200


def test_tambien_bloquea_a_los_bodegueros_de_la_empresa(api):
    registrar(api, EMPRESA)
    with SessionLocal() as db:
        db.query(Usuario).filter(Usuario.correo == "bodeguero@entrega.com").one().empresa_id = db.query(Empresa).one().id
        db.commit()
    assert (login(api, "bodeguero@entrega.com", "Bodega123*").json()) == PENDIENTE


def test_los_usuarios_sin_empresa_no_se_afectan(api):
    registrar(api, EMPRESA)
    for correo, clave in (("admin@entrega.com", "Admin123*"), ("bodeguero@entrega.com", "Bodega123*"), ("cliente@entrega.com", "Cliente123*")):
        assert api.get("/me", headers=entrar(api, correo, clave)).status_code == 200
