# T6: flujo completo del día 1, de punta a punta.
# Levanta un servidor uvicorn DE VERDAD (en un puerto libre, con la base de pruebas) y solo usa HTTP:
# no toca la base ni llama funciones de la app, igual que haría el frontend.
import os
import socket
import subprocess
import sys
import time

import httpx2
import pytest
from conftest import RAIZ, engine

from app.config import seed

MOTIVO = "El NIT no coincide con el RUT"
EMPRESA = {"tipo": "empresa", "razon_social": "Distribuidora Andina S.A.S.", "nit": "900123456-1", "telefono": "3001234567",
           "direccion": "Calle 10 # 20-30", "representante": "Ana Torres", "correo": "empresa@andina.com",
           "contrasena": "Empresa123*"}
PENDIENTE = (403, {"detail": "Su empresa está pendiente de aprobación"})
RECHAZADA = (403, {"detail": f"Su empresa fue rechazada: {MOTIVO}"})
SUSPENDIDA = (403, {"detail": "Su empresa está suspendida"})


@pytest.fixture
def http(base_nueva):
    """Cliente HTTP contra un servidor real con la base de pruebas sembrada."""
    assert engine.url.database.endswith("_test") and os.environ["DATABASE_URL"].endswith("_test")
    seed.main()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    servidor = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.config.main:app", "--port", str(puerto)], cwd=RAIZ,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx2.Client(base_url=f"http://127.0.0.1:{puerto}", timeout=15) as cliente:
            for _ in range(80):
                try:
                    if cliente.get("/").status_code == 200:
                        break
                except httpx2.TransportError:
                    time.sleep(0.25)
            else:
                pytest.fail("el servidor no arrancó")
            yield cliente
    finally:
        if os.name == "nt":  # en Windows el python del venv lanza un proceso hijo: se cierran los dos
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(servidor.pid)], capture_output=True)
        servidor.kill()
        servidor.wait()


def resultado(r):
    return r.status_code, r.json()


def test_flujo_del_dia_1(http):
    login = lambda clave=EMPRESA["contrasena"]: http.post("/login", json={"correo": EMPRESA["correo"], "contrasena": clave})
    r = http.post("/login", json={"correo": "admin@entrega.com", "contrasena": "Admin123*"})
    assert r.status_code == 200 and r.json()["user"]["empresa"] is None
    admin = {"Authorization": "Bearer " + r.json()["access_token"]}
    estado = lambda eid, **c: http.patch(f"/empresas/{eid}/estado", headers=admin, json=c)

    # 1. Antes de registrarse no existe
    assert login().status_code == 401

    # 2. Registrar la empresa
    r = http.post("/register", json=EMPRESA)
    assert r.status_code == 201 and r.json()["estado"] == "pendiente" and "access_token" not in r.text
    eid = r.json()["empresa"]["id"]
    assert http.post("/register", json=EMPRESA).status_code == 400  # no se puede repetir

    # 3. Login -> 403 pendiente
    assert resultado(login()) == PENDIENTE
    assert login("ClaveMala1*").status_code == 401  # con la clave mala no revela el estado

    # 4. El admin la ve pendiente y la rechaza con motivo (sin motivo no puede)
    pendientes = http.get("/empresas", headers=admin, params={"estado": "pendiente", "q": "andina"}).json()
    assert pendientes["total"] == 1 and pendientes["data"][0]["id"] == eid
    assert estado(eid, estado="rechazada").status_code == 422
    r = estado(eid, estado="rechazada", motivo_rechazo=MOTIVO)
    assert (r.status_code, r.json()["estado"], r.json()["motivo_rechazo"]) == (200, "rechazada", MOTIVO)

    # 5. Login -> 403 rechazada, con el motivo
    assert resultado(login()) == RECHAZADA
    assert estado(eid, estado="suspendida").status_code == 400  # de rechazada no se pasa a suspendida

    # 6. El admin la activa (se limpia el motivo)
    r = estado(eid, estado="activa")
    assert (r.status_code, r.json()["estado"], r.json()["motivo_rechazo"]) == (200, "activa", None)

    # 7. Login OK, con user.empresa
    r = login()
    assert r.status_code == 200
    sesion, user = {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()["user"]
    refresh = r.json()["refresh_token"]
    assert (user["correo"], user["nombre"], user["rol"]) == (EMPRESA["correo"], EMPRESA["representante"], "empresa")
    assert user["empresa"] == {"id": eid, "razon_social": EMPRESA["razon_social"], "estado": "activa"}
    assert len(user["permisos"]) == 20
    assert resultado(http.get("/me", headers=sesion)) == (200, user)
    assert http.post("/refresh", json={"refresh_token": refresh}).status_code == 200
    assert http.get("/bodegas", headers=sesion).status_code == 200          # usa lo suyo...
    assert http.get("/empresas", headers=sesion).status_code == 403         # ...pero no lo del admin
    assert http.patch(f"/empresas/{eid}/estado", headers=sesion, json={"estado": "activa"}).status_code == 403

    # 8. El admin la suspende
    r = estado(eid, estado="suspendida")
    assert (r.status_code, r.json()["estado"]) == (200, "suspendida")

    # 9. Login -> 403 suspendida, y la sesión que estaba abierta deja de servir
    assert resultado(login()) == SUSPENDIDA
    assert resultado(http.get("/me", headers=sesion)) == SUSPENDIDA
    assert resultado(http.get("/bodegas", headers=sesion)) == SUSPENDIDA
    assert resultado(http.post("/refresh", json={"refresh_token": refresh})) == SUSPENDIDA

    # 10. Nada de esto afectó a los demás usuarios
    for correo, clave in (("admin@entrega.com", "Admin123*"), ("bodeguero@entrega.com", "Bodega123*"), ("cliente@entrega.com", "Cliente123*")):
        assert http.post("/login", json={"correo": correo, "contrasena": clave}).status_code == 200
