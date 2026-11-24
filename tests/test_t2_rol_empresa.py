# T2: rol empresa (plantilla exacta, migración 007 idempotente y bloqueos 403)
import pytest
from conftest import RAIZ, SessionLocal, correr_script, entrar
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import seed
from app.core.deps import no_empresa
from app.core.permisos import PLANTILLAS
from app.modulos import Permiso, Rol, Usuario

MIGRACION = RAIZ / "migraciones" / "007_rol_empresa.py"
ESPERADOS = {
    "tipos_view", "tipos_create", "tipos_edit", "tipos_delete",
    "bodegas_view", "bodegas_create", "bodegas_edit", "bodegas_delete",
    "usuarios_view", "usuarios_create", "usuarios_edit", "usuarios_delete",
    "facturas_view", "facturas_create", "facturas_edit", "facturas_delete",
    "facturas_entregar", "facturas_recibir", "facturas_pdf",
    "estadisticas_view",
}
SIN_PERMISO = {"detail": "No tiene permiso para esta acción"}
BODEGA = {"nombre": "Central", "codigo": "b-1", "direccion": "C1", "ciudad": "Bog", "departamento": "Cun",
          "telefono": "6015551234", "correo": "b@b.com", "recibe_nombre": "A", "recibe_documento": "123",
          "recibe_cargo": "J", "recibe_telefono": "3001234567"}


def permisos_del_rol(db, nombre="empresa") -> set[str]:
    db.expire_all()
    return {p.nombre for p in db.query(Rol).filter(Rol.nombre == nombre).one().permisos}


# ===== EL ROL Y SU PLANTILLA =====

def test_plantilla_exacta():
    assert set(PLANTILLAS["empresa"]) == ESPERADOS and len(PLANTILLAS["empresa"]) == len(ESPERADOS)


def test_seed_crea_el_rol_una_sola_vez(base_nueva, db):
    seed.main(); seed.main()
    assert db.query(Rol).filter(Rol.nombre == "empresa").count() == 1
    assert permisos_del_rol(db) == ESPERADOS


def test_aparece_en_get_roles_por_nombre(api):
    roles = {r["nombre"]: r for r in api.get("/roles?limit=100", headers=entrar(api, "admin@entrega.com", "Admin123*")).json()["data"]}
    assert {p["nombre"] for p in roles["empresa"]["permisos"]} == ESPERADOS


# ===== MIGRACIÓN 007 =====

@pytest.fixture
def base_sin_rol(base_nueva, db):
    """Base como estaba antes de T2: con sus datos, pero sin el rol empresa."""
    seed.main()
    rol = db.query(Rol).filter(Rol.nombre == "empresa").one()
    rol.permisos = []
    db.delete(rol); db.commit()


def test_migracion_crea_el_rol_y_se_puede_repetir(base_sin_rol, db):
    for salida in ("[creado]", "[ya existía]", "[ya existía]"):
        r = correr_script(MIGRACION)
        assert r.returncode == 0 and salida in r.stdout, r.stdout + r.stderr
    db.rollback()
    assert db.query(Rol).filter(Rol.nombre == "empresa").count() == 1
    assert permisos_del_rol(db) == ESPERADOS


def test_migracion_no_toca_otros_roles_ni_usuarios(base_sin_rol, db):
    bodeguero = db.query(Rol).filter(Rol.nombre == "bodeguero").one()
    bodeguero.permisos = [p for p in bodeguero.permisos if p.nombre != "tipos_delete"]  # el admin se lo quitó
    db.commit()
    foto = lambda: ({r.nombre: {p.nombre for p in r.permisos} for r in db.query(Rol) if r.nombre != "empresa"},
                    {u.correo: {p.nombre for p in u.permisos} for u in db.query(Usuario)})
    antes = foto()
    assert correr_script(MIGRACION).returncode == 0
    db.rollback(); db.expire_all()
    assert foto() == antes and "tipos_delete" not in antes[0]["bodeguero"]


def test_migracion_no_usa_un_id_fijo(base_sin_rol, db):
    db.add_all([Rol(nombre=f"otro{i}") for i in range(5)]); db.commit()
    assert correr_script(MIGRACION).returncode == 0
    db.rollback()
    assert db.query(Rol).filter(Rol.nombre == "empresa").one().id > 4


def test_migracion_normaliza_el_nombre_y_conserva_extras(base_sin_rol, db):
    extra = db.query(Permiso).filter(Permiso.nombre == "facturas_aceptar").one()
    db.add(Rol(nombre="Empresa", permisos=[extra])); db.commit()
    r = correr_script(MIGRACION)
    assert r.returncode == 0 and "[ATENCIÓN]" in r.stdout and "facturas_aceptar" in r.stdout
    db.rollback(); db.expire_all()
    assert [x.nombre for x in db.query(Rol).filter(Rol.nombre == "empresa")] == ["empresa"]
    assert permisos_del_rol(db) == ESPERADOS | {"facturas_aceptar"}


def test_migracion_avisa_si_faltan_permisos(base_nueva, db):
    r = correr_script(MIGRACION)
    assert r.returncode != 0 and "Faltan permisos" in r.stderr
    assert db.query(Rol).count() == 0


@pytest.mark.parametrize("vieja", ["002_permisos_catalogo_y_usuarios.py", "004_permiso_estadisticas.py"])
def test_migraciones_viejas_funcionan_sin_el_rol(base_sin_rol, db, vieja):
    r = correr_script(RAIZ / "migraciones" / vieja)
    assert r.returncode == 0, r.stdout + r.stderr


# ===== BLOQUEOS =====

def crear_usuario(rol_nombre, correo, todos=False):
    """Crea el usuario en la base. Con todos=True le asigna TODOS los permisos (el bloqueo debe ganar)."""
    from app.core.security import hash_password
    with SessionLocal() as s:
        rol = s.query(Rol).filter(Rol.nombre == rol_nombre).one()
        u = Usuario(nombre=rol_nombre, correo=correo, contrasena=hash_password("Temp1234*"), rol_id=rol.id,
                    permisos=s.query(Permiso).all() if todos else list(rol.permisos))
        s.add(u); s.commit()
        return u.id


@pytest.fixture
def empresa(api):
    """Sesión de un usuario empresa con todos los permisos del sistema asignados."""
    crear_usuario("empresa", "empresa@x.com", todos=True)
    return entrar(api, "empresa@x.com", "Temp1234*")


BLOQUEADOS = [
    # gestión de permisos y roles (ver y cambiar)
    ("GET", "/permisos"), ("GET", "/permisos/1"), ("POST", "/permisos"), ("PUT", "/permisos/1"), ("DELETE", "/permisos/1"),
    ("GET", "/roles"), ("GET", "/roles/1"), ("POST", "/roles"), ("PUT", "/roles/1"), ("PUT", "/roles/1/permisos"), ("DELETE", "/roles/1"),
    ("GET", "/usuarios/1/permisos"), ("PUT", "/usuarios/1/permisos"), ("POST", "/usuarios/1/permisos/1"),
    ("DELETE", "/usuarios/1/permisos/1"),
    # facturas
    ("POST", "/facturas/1/aceptar"), ("POST", "/facturas/1/rechazar"),
    # TEMPORAL: hasta limitarlo a los bodegueros de su empresa
    ("POST", "/usuarios"), ("PUT", "/usuarios/1"), ("DELETE", "/usuarios/1"),
]


def test_empresa_recibe_403_en_todo_lo_bloqueado(api, empresa):
    cuerpos = (None, {"nombre": "x", "permisos_ids": [1], "motivo": "x", "firma": "x"})  # 403 antes que 422
    fallos = []
    for metodo, ruta in BLOQUEADOS:
        for cuerpo in cuerpos:
            r = api.request(metodo, ruta, headers=empresa, json=cuerpo)
            if (r.status_code, r.json()) != (403, SIN_PERMISO):
                fallos.append((metodo, ruta, r.status_code, r.text[:80]))
    assert fallos == []


def test_sin_sesion_sigue_siendo_401(api):
    assert [(m, r) for m, r in BLOQUEADOS if api.request(m, r).status_code != 401] == []


def test_empresa_no_puede_escalar_a_admin(api, empresa):
    with SessionLocal() as s:
        admin_rol = s.query(Rol).filter(Rol.nombre == "admin").one().id
        yo = s.query(Usuario).filter(Usuario.correo == "empresa@x.com").one().id
        antes = s.query(Usuario).count()
    nuevo = {"nombre": "x", "correo": "nuevo@x.com", "contrasena": "Temp1234*", "rol_id": admin_rol}
    assert api.post("/usuarios", headers=empresa, json=nuevo).status_code == 403
    assert api.put(f"/usuarios/{yo}", headers=empresa, json={"rol_id": admin_rol}).status_code == 403
    assert api.put("/usuarios/1", headers=empresa, json={"contrasena": "Hackeado1*"}).status_code == 403
    entrar(api, "admin@entrega.com", "Admin123*")  # la contraseña del admin no cambió
    with SessionLocal() as s:
        assert s.query(Usuario).count() == antes and s.get(Usuario, yo).rol.nombre == "empresa"


def test_regla_lista_para_empresas():
    """/empresas aún no existe: se prueba la regla que se le conectará, en una app mínima con sesión simulada."""
    from types import SimpleNamespace

    from app.core.deps import get_current_user
    router = APIRouter(prefix="/empresas", dependencies=[Depends(no_empresa)])

    @router.get("")
    @router.patch("/1/estado")
    def ok():
        return {}

    mini = FastAPI(); mini.include_router(router)
    cliente = TestClient(mini)
    for rol, codigo in (("empresa", 403), ("admin", 200)):
        mini.dependency_overrides[get_current_user] = lambda rol=rol: SimpleNamespace(rol=SimpleNamespace(nombre=rol))
        assert cliente.get("/empresas").status_code == cliente.patch("/empresas/1/estado").status_code == codigo


# ===== LO QUE SÍ PUEDE Y LOS DEMÁS ROLES =====

def test_empresa_si_puede_lo_de_su_plantilla(api):
    crear_usuario("empresa", "e2@x.com")
    h = entrar(api, "e2@x.com", "Temp1234*")
    assert {p["nombre"] for p in api.get("/me", headers=h).json()["permisos"]} == ESPERADOS
    for ruta in ("/tipos", "/bodegas", "/usuarios", "/facturas", "/facturas/clientes", "/estadisticas/resumen"):
        assert api.get(ruta, headers=h).status_code == 200, ruta
    b = api.post("/bodegas", headers=h, json=BODEGA); assert b.status_code == 201, b.text
    t = api.post("/tipos", headers=h, json={"nombre": "Arroz"}); assert t.status_code == 201, t.text
    c = api.get("/facturas/clientes", headers=h).json()["data"][0]
    f = api.post("/facturas", headers=h, json={
        "cliente_id": c["id"], "bodega_id": b.json()["id"], "forma_pago": "contado", "medio_pago": "efectivo",
        "detalle": [{"tipo_id": t.json()["id"], "descripcion": "x", "unidad_medida": "UND", "cantidad": 1, "precio_unitario": 100,
                     "descuento_porcentaje": 0, "iva_porcentaje": 0}]})
    assert f.status_code == 201, f.text
    i = f.json()["id"]
    assert api.put(f"/facturas/{i}", headers=h, json={"observaciones": "x"}).status_code == 200
    assert api.get(f"/facturas/{i}/pdf", headers=h).status_code == 200
    assert api.post(f"/facturas/{i}/entregar", headers=h).status_code == 200
    assert api.post(f"/facturas/{i}/aceptar", headers=h, json={"firma": "x"}).status_code == 403


def test_los_demas_roles_no_cambian(api):
    admin = entrar(api, "admin@entrega.com", "Admin123*")
    for ruta in ("/permisos", "/roles", "/usuarios", "/usuarios/1/permisos"):
        assert api.get(ruta, headers=admin).status_code == 200, ruta
    rol = next(r["id"] for r in api.get("/roles", headers=admin).json()["data"] if r["nombre"] == "empresa")
    r = api.post("/usuarios", headers=admin, json={"nombre": "E", "correo": "e3@x.com", "contrasena": "Temp1234*", "rol_id": rol})
    assert r.status_code == 201 and {p["nombre"] for p in r.json()["permisos"]} == ESPERADOS
    with SessionLocal() as s:  # un rol cualquiera con el permiso sigue entrando
        s.add(Rol(nombre="GERENTE", permisos=s.query(Permiso).filter(Permiso.nombre.in_(["roles_view", "permisos_view"])).all())); s.commit()
    crear_usuario("GERENTE", "g@x.com")
    g = entrar(api, "g@x.com", "Temp1234*")
    assert api.get("/roles", headers=g).status_code == api.get("/permisos", headers=g).status_code == 200
    assert api.get("/usuarios", headers=g).status_code == 403
