# Configuración de las pruebas. Usan SIEMPRE una base aparte (la del .env + "_test"), nunca la real.
import os
import subprocess
import sys
from pathlib import Path

import pymysql
import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parent.parent
_url = make_url(dotenv_values(RAIZ / ".env")["DATABASE_URL"])
_url = _url.set(database=f"{_url.database}_test")

# Antes de importar la app: load_dotenv no pisa las variables que ya existen
os.environ["DATABASE_URL"] = _url.render_as_string(hide_password=False)
sys.path.insert(0, str(RAIZ))

with pymysql.connect(host=_url.host, port=_url.port or 3306, user=_url.username, password=_url.password or "") as _con:
    _con.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{_url.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

import app.modulos  # noqa: E402,F401  (registra todos los modelos)
from app.config.database import Base, SessionLocal, engine  # noqa: E402

assert engine.url.database.endswith("_test"), "Las pruebas solo pueden correr en una base que termine en _test"


def vaciar_base() -> None:
    """Borra todas las tablas de la base de pruebas."""
    assert engine.url.database.endswith("_test")
    with engine.begin() as con:
        con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        for (tabla,) in con.exec_driver_sql("SHOW TABLES").all():
            con.exec_driver_sql(f"DROP TABLE `{tabla}`")
        con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")


def correr_sql(ruta: Path) -> None:
    """Ejecuta un archivo .sql (instrucciones separadas por ;, sin los comentarios)."""
    texto = "\n".join(l for l in ruta.read_text(encoding="utf-8").splitlines() if not l.strip().startswith("--"))
    with engine.begin() as con:
        con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        for instruccion in filter(None, (i.strip() for i in texto.split(";"))):
            con.exec_driver_sql(instruccion)
        con.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")


@pytest.fixture
def base_nueva():
    """Base creada desde los modelos, vacía."""
    vaciar_base()
    Base.metadata.create_all(bind=engine)
    yield
    vaciar_base()


@pytest.fixture
def base_antes_de_005():
    """Base con la estructura anterior a la migración 005, vacía."""
    vaciar_base()
    correr_sql(RAIZ / "tests" / "datos" / "esquema_antes_005.sql")
    yield
    vaciar_base()


@pytest.fixture
def db():
    sesion = SessionLocal()
    yield sesion
    sesion.rollback()
    sesion.close()


def correr_script(ruta: Path, *args: str) -> subprocess.CompletedProcess:
    """Corre un script como lo haría una persona (hereda DATABASE_URL: la base de pruebas)."""
    return subprocess.run([sys.executable, str(ruta), *args], capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


@pytest.fixture
def api(base_nueva):
    """Cliente HTTP de la app, con la base recién sembrada (admin, bodeguero y cliente de prueba)."""
    from fastapi.testclient import TestClient

    from app.config import seed
    from app.config.main import app
    seed.main()
    with TestClient(app) as cliente:
        yield cliente


def entrar(api, correo: str, clave: str) -> dict:
    """Inicia sesión y devuelve el header Authorization."""
    r = api.post("/login", json={"correo": correo, "contrasena": clave})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}
