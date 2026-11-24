# T1: modelo de datos multiempresa (migración 005, modelos, backfill 006 y que los endpoints sigan igual)
import importlib.util

import pytest
from conftest import RAIZ, Base, SessionLocal, correr_script, correr_sql, engine, entrar, vaciar_base
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.modulos import ESTADOS_EMPRESA, Bodega, Empresa, Orden, Rol, Tipo, Usuario

TABLAS = ("usuarios", "bodegas", "tipos", "ordenes")
MIGRACION = RAIZ / "migraciones" / "005_empresas.sql"
BACKFILL = RAIZ / "migraciones" / "006_backfill_empresas.py"

_spec = importlib.util.spec_from_file_location("backfill", BACKFILL)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def estructura() -> dict:
    """Columnas, llaves foráneas y únicos de cada tabla (sin los nombres de las restricciones)."""
    i, res = inspect(engine), {}
    for t in sorted(i.get_table_names()):
        res[t] = {
            "columnas": {c["name"]: (str(c["type"]).split(" COLLATE")[0], c["nullable"]) for c in i.get_columns(t)},
            "foraneas": sorted((tuple(f["constrained_columns"]), f["referred_table"], f["options"].get("ondelete"))
                               for f in i.get_foreign_keys(t)),
            "unicos": sorted(tuple(u["column_names"]) for u in i.get_indexes(t) if u["unique"]),
            "checks": sorted(c["name"] for c in i.get_check_constraints(t)),
        }
    return res


# ===== MIGRACIÓN 005 =====

def test_migracion_deja_la_misma_estructura_que_los_modelos(base_antes_de_005):
    correr_sql(MIGRACION)
    migrada = estructura()
    vaciar_base()
    Base.metadata.create_all(bind=engine)
    assert migrada == estructura()


def test_migracion_agrega_empresa_id_nullable_con_fk(base_antes_de_005):
    correr_sql(MIGRACION)
    e = estructura()
    for t in TABLAS:
        assert e[t]["columnas"]["empresa_id"][1] is True
        assert (("empresa_id",), "empresas", None) in e[t]["foraneas"]


def test_migracion_no_cambia_los_datos_existentes(base_antes_de_005):
    with engine.begin() as c:
        c.execute(text("INSERT INTO roles (id, nombre) VALUES (2, 'bodeguero')"))
        c.execute(text("INSERT INTO usuarios (id, nombre, correo, contrasena, rol_id) VALUES (7, 'Ana', 'a@a.com', 'x', 2)"))
        c.execute(text("INSERT INTO bodegas (id, nombre, bodeguero_id) VALUES (3, 'B', 7)"))
        c.execute(text("INSERT INTO tipos (id, nombre, bodega_id) VALUES (4, 'T', 3)"))
        antes = {t: c.execute(text(f"SELECT * FROM {t}")).mappings().all() for t in ("usuarios", "bodegas", "tipos")}
    correr_sql(MIGRACION)
    with engine.connect() as c:
        for t, filas in antes.items():
            despues = [dict(f) for f in c.execute(text(f"SELECT * FROM {t}")).mappings().all()]
            assert [f.pop("empresa_id") for f in despues] == [None] * len(filas)
            assert despues == [dict(f) for f in filas]


# ===== MODELO =====

def test_empresa_nueva_queda_pendiente(base_nueva, db):
    e = Empresa(razon_social="Andina")
    db.add(e); db.commit(); db.refresh(e)
    assert (e.estado, e.motivo_rechazo, e.nit) == ("pendiente", None, None)
    assert e.creado_en is not None and e.actualizado_en is not None


@pytest.mark.parametrize("estado", ESTADOS_EMPRESA)
def test_estados_validos(base_nueva, db, estado):
    db.add(Empresa(razon_social="X", estado=estado)); db.commit()


@pytest.mark.parametrize("estado", ["otra", "", "ACTIVO"])
def test_estado_invalido_lo_rechaza_la_base(base_nueva, db, estado):
    db.add(Empresa(razon_social="X", estado=estado))
    with pytest.raises((IntegrityError, OperationalError)):
        db.commit()


def test_nit_unico_sin_contar_el_digito(base_nueva, db):
    db.add(Empresa(razon_social="A", nit="900123456", dv="1")); db.commit()
    db.add(Empresa(razon_social="B", nit="900123456", dv="2"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_varias_empresas_sin_nit(base_nueva, db):
    db.add_all([Empresa(razon_social="A"), Empresa(razon_social="B")]); db.commit()
    assert db.query(Empresa).count() == 2


def test_empresa_id_debe_existir(base_nueva, db):
    db.add(Bodega(nombre="B", empresa_id=999))
    with pytest.raises(IntegrityError):
        db.commit()


def test_no_se_borra_una_empresa_con_datos(base_nueva, db):
    e = Empresa(razon_social="A"); db.add(e); db.flush()
    db.add(Bodega(nombre="B", empresa_id=e.id)); db.commit()
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM empresas")); db.commit()


# ===== BACKFILL 006 =====

def factura(db, numero, bodega, cliente, bodeguero):
    o = Orden(prefijo="FE", consecutivo=numero, numero=f"FE-{numero:04d}", bodega_id=bodega.id, cliente_id=cliente.id,
              bodeguero_id=bodeguero.id, emisor_datos={"nit": "900000000"}, adquiriente_datos={"nombre": "C"})
    db.add(o); db.flush()
    return o


@pytest.fixture
def datos_viejos(base_nueva, db):
    """Datos anteriores a las empresas (todo con empresa_id NULL)."""
    roles = {n: Rol(nombre=n) for n in ("admin", "bodeguero", "cliente", "GERENTE")}
    db.add_all(roles.values()); db.flush()
    u = {n: Usuario(nombre=n, correo=f"{n}@x.com", contrasena="x", rol_id=r.id) for n, r in roles.items()}
    db.add_all(u.values()); db.flush()
    b1, b2 = Bodega(nombre="B1", bodeguero_id=u["bodeguero"].id), Bodega(nombre="B2")
    db.add_all([b1, b2]); db.flush()
    db.add_all([Tipo(nombre="T1", bodega_id=b1.id), Tipo(nombre="T2", bodega_id=b2.id), Tipo(nombre="General")])
    factura(db, 1, b1, u["cliente"], u["bodeguero"]); factura(db, 2, b2, u["cliente"], u["admin"])
    db.commit()


def empresas_de(db, modelo, campo):
    db.expire_all()
    return {getattr(x, campo): x.empresa_id for x in db.query(modelo).all()}


def test_backfill_asigna_la_empresa_del_emisor(datos_viejos, db):
    cambios = backfill.rellenar(db); db.commit()
    assert list(cambios.values()) == [1, 2, 2, 2]
    e = db.query(Empresa).one()
    assert (e.razon_social, e.nit, e.dv, e.estado) == ("Empresa Demo S.A.S.", "900000000", "1", "activa")
    assert empresas_de(db, Usuario, "nombre") == {"admin": None, "bodeguero": e.id, "cliente": None, "GERENTE": None}
    assert empresas_de(db, Bodega, "nombre") == {"B1": e.id, "B2": e.id}
    assert empresas_de(db, Tipo, "nombre") == {"T1": e.id, "T2": e.id, "General": None}
    assert empresas_de(db, Orden, "numero") == {"FE-0001": e.id, "FE-0002": e.id}
    assert set(backfill.revisar(db).values()) == {0}


def test_backfill_se_puede_repetir(datos_viejos, db):
    backfill.rellenar(db); db.commit()
    assert set(backfill.rellenar(db).values()) == {0}
    assert db.query(Empresa).count() == 1


def test_backfill_no_pisa_lo_ya_asignado_y_respeta_al_dueno(datos_viejos, db):
    otra = Empresa(razon_social="Otra", estado="activa"); db.add(otra); db.flush()
    db.query(Usuario).filter(Usuario.nombre == "bodeguero").one().empresa_id = otra.id
    db.commit(); otra_id = otra.id
    backfill.rellenar(db); db.commit()
    demo = db.query(Empresa).filter(Empresa.nit == "900000000").one().id
    assert empresas_de(db, Bodega, "nombre") == {"B1": otra_id, "B2": demo}  # B1 sigue a su bodeguero
    assert empresas_de(db, Tipo, "nombre") == {"T1": otra_id, "T2": demo, "General": None}
    assert empresas_de(db, Orden, "numero") == {"FE-0001": otra_id, "FE-0002": demo}
    assert set(backfill.revisar(db).values()) == {0}


def test_backfill_no_toca_fechas_ni_datos_de_la_factura(datos_viejos, db):
    foto = lambda: [dict(f) for f in db.execute(text("SELECT * FROM ordenes ORDER BY id")).mappings()]
    db.execute(text("UPDATE ordenes SET actualizado_en = '2020-01-01'")); db.commit()
    antes = foto()
    backfill.rellenar(db); db.commit()
    despues = foto()
    for f in antes + despues:
        f.pop("empresa_id")
    assert antes == despues


def test_script_por_defecto_solo_simula(datos_viejos, db):
    r = correr_script(BACKFILL)
    assert r.returncode == 0 and "Simulación" in r.stdout, r.stdout + r.stderr
    assert db.query(Empresa).count() == 0
    assert set(empresas_de(db, Bodega, "nombre").values()) == {None}
    db.add(Empresa(razon_social="Primera")); db.commit()
    assert db.query(Empresa).one().id == 1  # la simulación no gastó ningún id


def test_script_aplica(datos_viejos, db):
    r = correr_script(BACKFILL, "--aplicar")
    assert r.returncode == 0 and "Backfill aplicado" in r.stdout, r.stdout + r.stderr
    db.rollback()
    assert None not in empresas_de(db, Bodega, "nombre").values()


def test_script_con_empresa_existente(datos_viejos, db):
    e = Empresa(razon_social="Mia", estado="activa"); db.add(e); db.commit(); eid = e.id
    assert correr_script(BACKFILL, "--empresa-id", str(eid), "--aplicar").returncode == 0
    db.rollback()
    assert db.query(Empresa).count() == 1 and set(empresas_de(db, Bodega, "nombre").values()) == {eid}


def test_script_con_empresa_inexistente_no_cambia_nada(datos_viejos, db):
    r = correr_script(BACKFILL, "--empresa-id", "999", "--aplicar")
    assert r.returncode != 0 and "No existe la empresa" in r.stderr
    assert set(empresas_de(db, Bodega, "nombre").values()) == {None}


def test_script_no_guarda_si_quedan_datos_cruzados(datos_viejos, db):
    a, b = Empresa(razon_social="A", estado="activa"), Empresa(razon_social="B", estado="activa")
    db.add_all([a, b]); db.flush()
    db.query(Usuario).filter(Usuario.nombre == "bodeguero").one().empresa_id = a.id
    db.query(Bodega).filter(Bodega.nombre == "B1").one().empresa_id = b.id  # cruzada con su bodeguero
    db.commit()
    r = correr_script(BACKFILL, "--aplicar")
    assert r.returncode == 1 and "datos cruzados" in r.stdout, r.stdout + r.stderr
    db.rollback()
    assert empresas_de(db, Bodega, "nombre")["B2"] is None


# ===== LOS ENDPOINTS SIGUEN IGUAL =====

def test_endpoints_existentes_funcionan_sin_empresa(api):
    admin, bod = entrar(api, "admin@entrega.com", "Admin123*"), entrar(api, "bodeguero@entrega.com", "Bodega123*")
    r = api.post("/bodegas", headers=bod, json={
        "nombre": "Central", "codigo": "b-1", "direccion": "C1", "ciudad": "Bog", "departamento": "Cun", "telefono": "6015551234",
        "correo": "b@b.com", "recibe_nombre": "A", "recibe_documento": "123", "recibe_cargo": "J", "recibe_telefono": "3001234567"})
    assert r.status_code == 201, r.text
    bodega = r.json()
    t = api.post("/tipos", headers=bod, json={"nombre": "Arroz"}).json()
    cliente = api.get("/facturas/clientes", headers=bod).json()["data"][0]
    r = api.post("/facturas", headers=bod, json={
        "cliente_id": cliente["id"], "bodega_id": bodega["id"], "forma_pago": "contado", "medio_pago": "efectivo",
        "detalle": [{"tipo_id": t["id"], "descripcion": "Arroz", "unidad_medida": "UND", "cantidad": 2, "precio_unitario": 1000,
                     "descuento_porcentaje": 0, "iva_porcentaje": 19}]})
    assert r.status_code == 201 and r.json()["numero"] == "FE-0001", r.text
    for ruta in ("/usuarios", "/bodegas", "/tipos", "/facturas", "/roles", "/permisos", "/me", "/estadisticas/resumen"):
        r = api.get(ruta, headers=admin)
        assert r.status_code == 200, ruta
    with SessionLocal() as s:
        assert {m.__name__: s.query(m).first().empresa_id for m in (Bodega, Tipo, Orden)} == {"Bodega": None, "Tipo": None, "Orden": None}
