# T4: login y /me con la empresa del usuario
import re

import pytest
from conftest import RAIZ, SessionLocal

from app.modulos import Empresa, Usuario

BASES = {"admin": ("admin@entrega.com", "Admin123*"), "bodeguero": ("bodeguero@entrega.com", "Bodega123*"),
         "cliente": ("cliente@entrega.com", "Cliente123*")}
CLAVES_ANTERIORES = {"id", "nombre", "correo", "rol", "permisos"}
MOTIVO = "El NIT no coincide con el RUT"


def login(api, correo, clave):
    return api.post("/login", json={"correo": correo, "contrasena": clave})


def me(api, respuesta_login):
    return api.get("/me", headers={"Authorization": "Bearer " + respuesta_login.json()["access_token"]})


@pytest.fixture
def con_empresa(api):
    """Asigna una empresa a un usuario: con_empresa(rol, estado, motivo) -> id de la empresa."""
    def asignar(rol, estado, motivo=None):
        with SessionLocal() as s:
            e = Empresa(razon_social="Andina S.A.S.", nit="900123456", dv="1", estado=estado, motivo_rechazo=motivo)
            s.add(e); s.flush()
            s.query(Usuario).filter(Usuario.correo == BASES[rol][0]).one().empresa_id = e.id
            s.commit()
            return e.id
    return asignar


# ===== ESTADOS BLOQUEADOS =====

BLOQUEADOS = [("pendiente", None, "Su empresa está pendiente de aprobación"),
              ("rechazada", MOTIVO, f"Su empresa fue rechazada: {MOTIVO}"),
              ("suspendida", None, "Su empresa está suspendida")]


@pytest.mark.parametrize("estado,motivo,detalle", BLOQUEADOS, ids=[b[0] for b in BLOQUEADOS])
def test_login_bloqueado(api, con_empresa, estado, motivo, detalle):
    con_empresa("bodeguero", estado, motivo)
    r = login(api, *BASES["bodeguero"])
    assert (r.status_code, r.json()) == (403, {"detail": detalle})  # exacto: ni token ni datos del usuario
    r = login(api, BASES["bodeguero"][0], "ClaveMala1*")
    assert (r.status_code, r.json()) == (401, {"detail": "Correo o contraseña incorrectos"})


def test_los_textos_son_los_del_contrato():
    contrato = (RAIZ / "RESPUESTA_EMPRESAS.md")
    if not contrato.exists():
        pytest.skip("el contrato no está en el repo")
    textos = re.findall(r"^- `(Su empresa[^`]+)`$", contrato.read_text(encoding="utf-8"), re.M)
    assert textos == [d.replace(MOTIVO, "<motivo>") for _, _, d in BLOQUEADOS]


def test_usuario_desactivado_sigue_siendo_401(api, con_empresa):
    con_empresa("bodeguero", "suspendida")
    with SessionLocal() as s:
        s.query(Usuario).filter(Usuario.correo == BASES["bodeguero"][0]).one().estado = False
        s.commit()
    assert login(api, *BASES["bodeguero"]).status_code == 401


# ===== EMPRESA ACTIVA =====

def test_empresa_activa_en_login_y_me(api, con_empresa):
    eid = con_empresa("bodeguero", "activa")
    r = login(api, *BASES["bodeguero"])
    assert r.status_code == 200
    assert r.json()["user"]["empresa"] == {"id": eid, "razon_social": "Andina S.A.S.", "estado": "activa"}
    assert me(api, r).json() == r.json()["user"]


def test_usuario_de_empresa_registrada_y_aprobada(api):
    r = api.post("/register", json={"tipo": "empresa", "razon_social": "Nueva S.A.", "nit": "800111222-3", "telefono": "3001234567",
                                    "direccion": "C 1", "representante": "Ana", "correo": "e@nueva.com", "contrasena": "Empresa123*"})
    with SessionLocal() as s:
        s.get(Empresa, r.json()["empresa"]["id"]).estado = "activa"; s.commit()
    u = login(api, "e@nueva.com", "Empresa123*").json()["user"]
    assert u["rol"] == "empresa" and u["empresa"] == {"id": r.json()["empresa"]["id"], "razon_social": "Nueva S.A.", "estado": "activa"}


def test_me_refleja_los_cambios_sin_volver_a_entrar(api, con_empresa):
    eid = con_empresa("bodeguero", "activa")
    r = login(api, *BASES["bodeguero"])
    with SessionLocal() as s:
        s.get(Empresa, eid).razon_social = "Nombre nuevo"; s.commit()
    assert me(api, r).json()["empresa"]["razon_social"] == "Nombre nuevo"
    with SessionLocal() as s:
        s.get(Empresa, eid).estado = "suspendida"; s.commit()
    x = me(api, r)
    assert (x.status_code, x.json()) == (403, {"detail": "Su empresa está suspendida"})


# ===== SIN EMPRESA =====

@pytest.mark.parametrize("rol", BASES)
def test_sin_empresa_es_null(api, rol):
    r = login(api, *BASES[rol])
    assert r.status_code == 200
    u = r.json()["user"]
    assert "empresa" in u and u["empresa"] is None and u["rol"] == rol
    assert me(api, r).json() == u


def test_no_se_rompe_lo_que_ya_devolvia(api):
    r = login(api, *BASES["admin"])
    assert set(r.json()) == {"access_token", "refresh_token", "token_type", "user"}
    assert set(r.json()["user"]) == CLAVES_ANTERIORES | {"empresa"}  # sin empresa_id ni empresa_nombre sueltos
    assert set(r.json()["user"]["permisos"][0]) == {"id", "nombre"}
    assert api.get("/me").status_code == 401
