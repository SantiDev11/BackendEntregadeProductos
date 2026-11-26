# T12: huecos de seguridad encontrados en la verificación final (T11).
# 1) el refresh token no sirve como token de acceso; 2) quien no es admin no puede volverse admin, ni tocar a uno;
# 3) cambiar el rol no deja a un bodeguero o usuario empresa sin empresa.
from datetime import datetime, timedelta, timezone

import pytest
from conftest import SessionLocal, entrar
from jose import jwt
from test_t7_aislamiento import CLAVE, empresa_de, foto, m  # noqa: F401  (m es el fixture)
from test_t11_contrato import EXIGE, SOLO_ADMIN, SOLO_SESION, peticion

from app.core.jwt import ALGORITHM, SECRET_KEY, create_refresh_token
from app.core.permisos import PLANTILLAS
from app.core.security import hash_password
from app.modulos import Empresa, Permiso, Rol, Usuario

SIN_PERMISO = (403, {"detail": "No tiene permiso para esta acción"})
INVALIDO = (401, {"detail": "Token inválido o vencido"})


def resultado(r):
    return r.status_code, r.json()


# ===== 1. TOKENS =====

def test_el_refresh_no_sirve_como_token_de_acceso(m):
    for quien in ("admin", "usuario X", "usuario bX", "usuario c1"):
        refresco = {"Authorization": "Bearer " + create_refresh_token(1 if quien == "admin" else m.id[quien])}
        for endpoint in set(EXIGE) | SOLO_ADMIN | SOLO_SESION:
            assert resultado(peticion(m.api, endpoint, refresco)) == INVALIDO, (quien, endpoint)


def test_el_flujo_normal_de_tokens_sigue_igual(api):
    s = api.post("/login", json={"correo": "admin@entrega.com", "contrasena": "Admin123*"}).json()
    acceso = lambda t: api.get("/me", headers={"Authorization": f"Bearer {t}"})
    assert acceso(s["access_token"]).status_code == 200 and resultado(acceso(s["refresh_token"])) == INVALIDO
    r = api.post("/refresh", json={"refresh_token": s["refresh_token"]})
    assert r.status_code == 200 and acceso(r.json()["access_token"]).status_code == 200
    assert resultado(acceso(r.json()["refresh_token"])) == INVALIDO
    assert api.post("/refresh", json={"refresh_token": s["access_token"]}).status_code == 401  # y al revés tampoco
    d = api.post("/login/docs", data={"username": "admin@entrega.com", "password": "Admin123*"}).json()
    assert acceso(d["access_token"]).status_code == 200


def test_tokens_de_acceso_anteriores_y_tipos_raros(api):
    en_una_hora = datetime.now(timezone.utc) + timedelta(hours=1)
    firmar = lambda **c: jwt.encode({"sub": "1", "exp": en_una_hora, **c}, SECRET_KEY, algorithm=ALGORITHM)
    ver = lambda t: api.get("/me", headers={"Authorization": f"Bearer {t}"}).status_code
    assert ver(firmar(rol="admin")) == 200  # emitido antes del cambio: las sesiones abiertas no se caen
    assert [ver(firmar(type=t)) for t in ("access", "refresh", "Access", "", None, "otro", 1)] == [200, 401, 401, 401, 401, 401, 401]


# ===== 2. NADIE SE VUELVE ADMIN =====

@pytest.fixture
def g(m):
    """Un usuario de un rol cualquiera, sin empresa y con TODOS los permisos del sistema."""
    with SessionLocal() as s:
        rol = Rol(nombre="GERENTE")
        s.add(rol); s.flush()
        u = Usuario(nombre="G", correo="g@g.com", contrasena=hash_password(CLAVE), rol_id=rol.id, permisos=s.query(Permiso).all())
        otro = Usuario(nombre="Admin 2", correo="admin2@g.com", contrasena=hash_password(CLAVE), rol_id=m.rol["admin"])
        s.add_all([u, otro]); s.commit()
        m.id |= {"usuario g": u.id, "usuario admin2": otro.id}
        m.rol["GERENTE"] = rol.id
    m.h["g"] = entrar(m.api, "g@g.com", CLAVE)
    return m


def nuevo(rol_id, correo="malo@t.com", **c):
    return {"nombre": "Malo", "correo": correo, "contrasena": CLAVE, "rol_id": rol_id, **c}


@pytest.mark.parametrize("quien", ["g", "bV"])  # bV: bodeguero anterior a las empresas, con todos los permisos
def test_no_puede_crear_ni_convertir_a_nadie_en_admin_o_empresa(g, quien):
    antes = foto()
    for rol in ("admin", "empresa"):
        assert resultado(g.pedir(quien, "POST", "/usuarios", nuevo(g.rol[rol], empresa_id=g.id["empresa X"]))) == SIN_PERMISO
        for u in ("usuario g", "usuario c1", "usuario bV"):  # ni a sí mismo
            r = g.pedir(quien, "PUT", f"/usuarios/{g.id[u]}", {"rol_id": g.rol[rol], "empresa_id": g.id["empresa X"]})
            assert resultado(r) == SIN_PERMISO, (rol, u)
    assert foto() == antes


@pytest.mark.parametrize("quien", ["g", "bV"])
def test_no_puede_tocar_a_un_admin(g, quien):
    antes = foto()
    for u in (1, g.id["usuario admin2"]):
        for metodo, ruta, cuerpo in (("PUT", "", {"contrasena": "Hackeado1*"}), ("PUT", "", {"correo": "otro@t.com"}), ("PUT", "", {"estado": False}),
                                     ("PATCH", "/estado", {"estado": False}),
                                     ("PUT", "", {"rol_id": g.rol["cliente"]}), ("PUT", "", {}), ("DELETE", "", None),
                                     ("PUT", "/permisos", {"permisos_ids": []}), ("POST", "/permisos/1", None), ("DELETE", "/permisos/1", None)):
            assert resultado(g.pedir(quien, metodo, f"/usuarios/{u}{ruta}", cuerpo)) == SIN_PERMISO, (metodo, ruta, cuerpo)
        assert g.pedir(quien, "GET", f"/usuarios/{u}").status_code == 200  # verlo sigue igual
    assert foto() == antes
    entrar(g.api, "admin@entrega.com", "Admin123*")
    entrar(g.api, "admin2@g.com", CLAVE)


@pytest.mark.parametrize("nombre", sorted(PLANTILLAS))
def test_no_puede_renombrar_los_roles_base(g, nombre):
    """El otro camino: renombrar el rol admin y llamar "admin" al propio."""
    for otro in ("viejo", nombre.upper(), f"{nombre}2"):
        assert resultado(g.pedir("g", "PUT", f"/roles/{g.rol[nombre]}", {"nombre": otro})) == SIN_PERMISO
        assert resultado(g.pedir("g", "PUT", f"/roles/{g.rol[nombre]}", {"nombre": otro, "descripcion": "x"})) == SIN_PERMISO
    assert g.pedir("g", "PUT", f"/roles/{g.rol['GERENTE']}", {"nombre": nombre}).status_code == 400  # el nombre ya está usado
    with SessionLocal() as s:
        assert s.get(Rol, g.rol[nombre]).nombre == nombre and s.get(Rol, g.rol["GERENTE"]).nombre == "GERENTE"
    r = g.pedir("g", "PUT", f"/roles/{g.rol[nombre]}", {"nombre": nombre, "descripcion": "Otra"})  # lo demás sí se puede editar
    assert (r.status_code, r.json()["descripcion"]) == (200, "Otra")
    assert g.pedir("g", "PUT", f"/roles/{g.rol['GERENTE']}", {"nombre": "JEFE"}).status_code == 200


def test_la_cadena_completa_no_llega_a_admin(g):
    """Aunque se dé a sí mismo todos los permisos, no pasa de su rol."""
    with SessionLocal() as s:
        todos = [p.id for p in s.query(Permiso)]
        s.get(Usuario, g.id["usuario g"]).permisos = s.query(Permiso).filter(Permiso.nombre == "usuarios_edit").all()
        s.commit()
    assert g.pedir("g", "PUT", f"/usuarios/{g.id['usuario g']}/permisos", {"permisos_ids": todos}).status_code == 200
    g.pedir("g", "PUT", f"/roles/{g.rol['admin']}", {"nombre": "viejo"})
    g.pedir("g", "PUT", f"/roles/{g.rol['GERENTE']}", {"nombre": "admin"})
    g.pedir("g", "PUT", f"/usuarios/{g.id['usuario g']}", {"rol_id": g.rol["admin"]})
    g.pedir("g", "PUT", "/usuarios/1", {"contrasena": CLAVE})
    assert g.pedir("g", "GET", "/me").json()["rol"] == "GERENTE" and g.pedir("g", "GET", "/empresas").status_code == 403
    entrar(g.api, "admin@entrega.com", "Admin123*")


def test_lo_demas_lo_puede_seguir_haciendo(g):
    for rol in ("cliente", "bodeguero", "GERENTE"):
        u = g.crear("/usuarios", "g", nuevo(g.rol[rol], f"{rol}@n.com".lower()))
        assert g.pedir("g", "PUT", f"/usuarios/{u}", {"nombre": "Otro", "rol_id": g.rol["cliente"]}).status_code == 200
        assert g.pedir("g", "PUT", f"/usuarios/{u}/permisos", {"permisos_ids": [1]}).status_code == 200
        assert g.pedir("g", "DELETE", f"/usuarios/{u}").status_code == 204


def test_el_admin_si_puede(g):
    for rol in ("admin", "cliente"):
        assert g.crear("/usuarios", "admin", nuevo(g.rol[rol], f"{rol}@n.com"))
    i = g.id["usuario admin2"]
    assert g.pedir("admin", "PUT", f"/usuarios/{i}", {"nombre": "Otro", "contrasena": "Cambiada1*"}).status_code == 200
    assert g.pedir("admin", "PUT", f"/usuarios/{i}/permisos", {"permisos_ids": [1]}).status_code == 200
    assert g.pedir("admin", "DELETE", f"/usuarios/{i}").status_code == 204
    assert g.pedir("admin", "PUT", f"/roles/{g.rol['cliente']}", {"nombre": "cliente", "descripcion": "x"}).status_code == 200


# ===== 3. CAMBIO DE ROL Y EMPRESA =====

def cambiar_rol(m, usuario, rol, quien="admin", **c):
    return m.pedir(quien, "PUT", f"/usuarios/{m.id[f'usuario {usuario}']}", {"rol_id": m.rol[rol], **c})


@pytest.mark.parametrize("rol", ["bodeguero", "empresa"])
def test_pasar_a_un_rol_con_empresa_la_exige(m, rol):
    antes = foto()
    for extra, mensaje in (({}, "es obligatorio"), ({"empresa_id": None}, "es obligatorio"), ({"empresa_id": "1"}, "debe ser un número"),
                           ({"empresa_id": 1.5}, "debe ser un número entero"), ({"empresa_id": 99999}, "la empresa indicada no existe")):
        r = cambiar_rol(m, "c1", rol, **extra)
        assert resultado(r) == (422, {"detail": f"empresa_id: {mensaje}", "errores": {"empresa_id": mensaje}}), extra
    with SessionLocal() as s:
        e = Empresa(razon_social="P", estado="suspendida")
        s.add(e); s.commit()
        i = e.id
    assert resultado(cambiar_rol(m, "c1", rol, empresa_id=i)) == (400, {"detail": "La empresa indicada no está activa"})
    assert foto() == antes
    r = cambiar_rol(m, "c1", rol, empresa_id=m.id["empresa X"])
    assert (r.status_code, r.json()["rol"], empresa_de(Usuario, m.id["usuario c1"])) == (200, rol, m.id["empresa X"])
    assert m.api.get("/me", headers=m.h["c1"]).json()["empresa"]["id"] == m.id["empresa X"]


def test_conserva_su_empresa_al_pasar_entre_bodeguero_y_empresa(m):
    for usuario, rol in (("bX", "empresa"), ("bX", "bodeguero"), ("Y", "bodeguero")):
        e = m.id["empresa X"] if usuario == "bX" else m.id["empresa Y"]
        for extra in ({}, {"empresa_id": m.id["empresa Y"] if usuario == "bX" else m.id["empresa X"]}, {"empresa_id": "abc"}):
            r = cambiar_rol(m, usuario, rol, **extra)
            assert (r.status_code, empresa_de(Usuario, m.id[f"usuario {usuario}"])) == (200, e), (usuario, rol, extra, r.text)


@pytest.mark.parametrize("rol", ["cliente", "admin"])
def test_los_roles_sin_empresa_la_pierden(m, rol):
    for usuario in ("bX", "Y"):
        r = cambiar_rol(m, usuario, rol, empresa_id=m.id["empresa X"])
        assert (r.status_code, r.json()["rol"], empresa_de(Usuario, m.id[f"usuario {usuario}"])) == (200, rol, None), r.text
        assert m.api.get("/me", headers=m.h[usuario]).json()["empresa"] is None


def test_si_el_rol_no_cambia_la_empresa_tampoco(m):
    for usuario, rol, e in (("bX", "bodeguero", m.id["empresa X"]), ("X", "empresa", m.id["empresa X"]), ("bV", "bodeguero", None), ("c1", "cliente", None)):
        for extra in ({}, {"empresa_id": m.id["empresa Y"]}, {"empresa_id": "abc"}):  # bV: los bodegueros viejos se siguen editando
            r = cambiar_rol(m, usuario, rol, nombre="Otro", **extra)
            assert (r.status_code, empresa_de(Usuario, m.id[f"usuario {usuario}"])) == (200, e), (usuario, extra, r.text)


def test_un_rol_personalizado_conserva_la_empresa(g):
    """Si la perdiera, pasaría a ver los datos que no tienen empresa."""
    assert cambiar_rol(g, "bX", "GERENTE").status_code == 200 and empresa_de(Usuario, g.id["usuario bX"]) == g.id["empresa X"]
    assert cambiar_rol(g, "c1", "GERENTE").status_code == 200 and empresa_de(Usuario, g.id["usuario c1"]) is None
    assert cambiar_rol(g, "c1", "bodeguero").status_code == 422


def test_la_empresa_sigue_sin_poder_cambiar_roles(m):
    antes = foto()
    for rol in ("cliente", "admin", "empresa"):
        assert resultado(cambiar_rol(m, "bX", rol, quien="X", empresa_id=m.id["empresa X"])) == SIN_PERMISO
    assert foto() == antes
