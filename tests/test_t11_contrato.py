# T11: lo que faltaba por probar del contrato (RESPUESTA_EMPRESAS.md y RESPUESTA_SOLO_NUMEROS.md, en el historial de git).
#
# Dónde se prueba cada parte:
#   Errores (forma de 401, 403, 404, 422)          -> aquí, test_t5, test_t7
#   1. Registro público                             -> test_t3 (repetidos, transacción, campos) y aquí (límites exactos)
#   2. Empresas, estados y motivo                   -> test_t5
#      Bloqueo por estado de la empresa             -> test_t3 y test_t4 (login, refresh) y aquí (TODOS los endpoints)
#      Los clientes siguen con sus facturas         -> aquí
#   3. Multiempresa: alcance y empresa_id           -> test_t4, test_t7, test_t8, test_t11_aislamiento
#   4. Búsqueda de clientes                         -> test_t9
#   5. Facturas: numeración, campos, motivo         -> test_t10; editar y eliminar según el estado -> aquí
#   6. Permisos: plantilla y bloqueos del rol       -> test_t2, test_t5; el permiso de cada endpoint -> aquí
#   Solo números                                    -> aquí
import pytest
from conftest import SessionLocal, entrar
from test_t2_rol_empresa import BLOQUEADOS as BLOQUEADOS_EMPRESA
from test_t3_registro import CLIENTE, EMPRESA, registrar
from test_t7_aislamiento import REVISADAS, datos_bodega, datos_factura, m  # noqa: F401  (m es el fixture)
from test_t11_aislamiento import ESTADOS, firma_png

from app.core.permisos import NOMBRES
from app.core.security import hash_password
from app.modulos import Empresa, Orden, Permiso, Rol, Usuario

SIN_PERMISO = {"detail": "No tiene permiso para esta acción"}

# ===== EL PERMISO DE CADA ENDPOINT =====

CRUD = {"GET /{0}": "view", "POST /{0}": "create", "GET /{0}/{{}}": "view", "PUT /{0}/{{}}": "edit", "DELETE /{0}/{{}}": "delete"}
EXIGE = {ruta.format(mod): f"{mod}_{accion}" for mod in ("usuarios", "bodegas", "tipos", "roles", "permisos", "facturas")
         for ruta, accion in CRUD.items()}
EXIGE |= {
    "GET /usuarios/{}/permisos": "usuarios_view", "PUT /usuarios/{}/permisos": "usuarios_edit",
    "POST /usuarios/{}/permisos/{}": "usuarios_edit", "DELETE /usuarios/{}/permisos/{}": "usuarios_edit",
    "PUT /roles/{}/permisos": "roles_edit",
    "PATCH /usuarios/{}/estado": "usuarios_edit", "PATCH /bodegas/{}/estado": "bodegas_edit", "PATCH /tipos/{}/estado": "tipos_edit",
    "PATCH /roles/{}/estado": "roles_edit",
    "GET /facturas/clientes": "facturas_create", "GET /clientes/buscar": "facturas_create", "GET /facturas/{}/pdf": "facturas_pdf",
    "POST /facturas/{}/entregar": "facturas_entregar", "POST /facturas/{}/aceptar": "facturas_aceptar",
    "POST /facturas/{}/rechazar": "facturas_rechazar", "POST /facturas/{}/recibir": "facturas_recibir",
    "GET /estadisticas/resumen": "estadisticas_view",
}
PUBLICOS = {"GET /", "POST /login", "POST /refresh", "POST /register"}
SOLO_ADMIN = {"GET /empresas", "POST /empresas", "GET /empresas/{}", "PUT /empresas/{}", "DELETE /empresas/{}", "PATCH /empresas/{}/estado",
              "GET /solo-admin"}
SOLO_SESION = {"GET /me"}


def peticion(api, endpoint, h=None):
    metodo, ruta = endpoint.split(" ")
    return api.request(metodo, ruta.replace("{}", "999999"), headers=h)


def con_permisos(uid, *, solo=None, menos=None, apagado=None):
    with SessionLocal() as s:
        todos = s.query(Permiso).all()
        s.get(Usuario, uid).permisos = [p for p in todos if (solo is None or p.nombre in solo) and p.nombre != menos]
        for p in todos:
            p.estado = p.nombre != apagado
        s.commit()


@pytest.fixture
def gerente(api):
    """Usuario de un rol cualquiera (sin reglas especiales), para probar los permisos uno por uno."""
    with SessionLocal() as s:
        rol = Rol(nombre="GERENTE")
        s.add(rol); s.flush()
        u = Usuario(nombre="G", correo="g@g.com", contrasena=hash_password("Temp1234*"), rol_id=rol.id)
        s.add(u); s.commit()
        uid = u.id
    return uid, entrar(api, "g@g.com", "Temp1234*")


def test_la_tabla_tiene_todos_los_endpoints():
    """Si alguien agrega un endpoint y no dice qué permiso exige, falla. (test_t7 compara REVISADAS con los reales)."""
    assert set(EXIGE) | PUBLICOS | SOLO_ADMIN | SOLO_SESION == set().union(*REVISADAS.values())
    assert set(EXIGE.values()) == NOMBRES  # y no hay permisos que nadie use


def test_sin_el_permiso_da_403_aunque_tenga_todos_los_demas(api, gerente):
    uid, h = gerente
    for endpoint, permiso in EXIGE.items():
        con_permisos(uid, menos=permiso)
        r = peticion(api, endpoint, h)
        assert (r.status_code, r.json()) == (403, SIN_PERMISO), endpoint


def test_con_solo_ese_permiso_si_pasa(api, gerente):
    uid, h = gerente
    for endpoint, permiso in EXIGE.items():
        con_permisos(uid, solo=[permiso])
        assert peticion(api, endpoint, h).status_code in (200, 404, 422), (endpoint, peticion(api, endpoint, h).text)


def test_un_permiso_desactivado_no_cuenta(api, gerente):
    uid, h = gerente
    for endpoint, permiso in EXIGE.items():
        con_permisos(uid, apagado=permiso)
        r = peticion(api, endpoint, h)
        assert (r.status_code, r.json()) == (403, SIN_PERMISO), endpoint


def test_los_endpoints_del_admin_dan_403_a_los_demas(api, gerente):
    con_permisos(gerente[0])
    sesiones = [gerente[1], entrar(api, "bodeguero@entrega.com", "Bodega123*"), entrar(api, "cliente@entrega.com", "Cliente123*")]
    for endpoint in SOLO_ADMIN:
        for h in sesiones:
            r = peticion(api, endpoint, h)
            assert (r.status_code, r.json()) == (403, SIN_PERMISO), endpoint


def test_sin_sesion_todo_da_401(api):
    for endpoint in set(EXIGE) | SOLO_ADMIN | SOLO_SESION:
        r = peticion(api, endpoint)
        assert (r.status_code, r.json()) == (401, {"detail": "No ha iniciado sesión"}), endpoint
        r = peticion(api, endpoint, {"Authorization": "Bearer malo"})
        assert (r.status_code, r.json()) == (401, {"detail": "Token inválido o vencido"}), endpoint


def test_el_bloqueo_del_rol_empresa_cubre_todo_permisos_y_roles():
    """Contrato, 6: cada endpoint de permisos y roles está en los bloqueados que prueba test_t2 (y /empresas, en test_t5)."""
    normal = {f"{metodo} " + "/".join("{}" if p.isdigit() else p for p in ruta.split("/")) for metodo, ruta in BLOQUEADOS_EMPRESA}
    de_permisos = {x for x in EXIGE if x.split(" ")[1].startswith(("/permisos", "/roles")) or "/permisos" in x}
    assert normal == de_permisos | {"POST /facturas/{}/aceptar", "POST /facturas/{}/rechazar"}


# ===== EMPRESA NO ACTIVA: NINGÚN ENDPOINT RESPONDE =====

@pytest.mark.parametrize("estado,detalle", [("pendiente", "Su empresa está pendiente de aprobación"), ("suspendida", "Su empresa está suspendida"),
                                            ("rechazada", "Su empresa fue rechazada: El NIT no coincide")])
def test_un_token_ya_emitido_no_sirve_en_ningun_endpoint(m, estado, detalle):
    """Contrato, 2.4: la empresa y sus bodegueros (aquí además con TODOS los permisos)."""
    with SessionLocal() as s:
        x = s.get(Empresa, m.id["empresa X"])
        x.estado, x.motivo_rechazo = estado, "El NIT no coincide" if estado == "rechazada" else None
        s.commit()
    for quien in ("X", "bX"):
        for endpoint in set(EXIGE) | SOLO_ADMIN | SOLO_SESION:
            r = peticion(m.api, endpoint, m.h[quien])
            assert (r.status_code, r.json()) == (403, {"detail": detalle}), (quien, endpoint)
    for quien in ("Y", "bY", "bV", "c1", "admin"):  # los demás siguen
        assert m.pedir(quien, "GET", "/me").status_code == 200


def test_los_clientes_siguen_con_las_facturas_de_una_empresa_suspendida(m):
    """Contrato, 2.4: siguen viendo, aceptando o rechazando las que ya recibieron; y no se borra nada."""
    for b in ("bX", "bX2"):
        assert m.pedir(b, "POST", f"/facturas/{m.id[f'factura {b}']}/entregar").status_code == 200
    assert m.pedir("admin", "PATCH", f"/empresas/{m.id['empresa X']}/estado", {"estado": "suspendida"}).status_code == 200
    a, b = m.id["factura bX"], m.id["factura bX2"]
    assert m.ids("c1", "/facturas") == {a, b}
    for f in (a, b):
        assert m.pedir("c1", "GET", f"/facturas/{f}").status_code == m.pedir("c1", "GET", f"/facturas/{f}/pdf").status_code == 200
    assert m.pedir("c1", "POST", f"/facturas/{a}/aceptar", {"firma": firma_png()}).json()["estado"] == "firmada"
    assert m.pedir("c1", "POST", f"/facturas/{b}/rechazar", {"motivo_rechazo": "Faltaron cajas"}).json()["estado"] == "rechazada"
    for t, ruta in (("bodega", "/bodegas"), ("tipo", "/tipos"), ("factura", "/facturas")):  # el admin ve que todo sigue ahí
        assert m.de(t, "bX", "bX2") <= m.ids("admin", ruta, empresa_id=m.id["empresa X"])
    assert m.pedir("bX", "POST", f"/facturas/{a}/recibir").status_code == 403
    assert m.pedir("admin", "PATCH", f"/empresas/{m.id['empresa X']}/estado", {"estado": "activa"}).status_code == 200
    assert m.pedir("bX", "POST", f"/facturas/{a}/recibir").json()["estado"] == "recibida"


# ===== FACTURAS SEGÚN SU ESTADO =====

FUERA_DE_ESTADO = {"detail": "La factura no está en un estado válido para esta acción"}


def acciones(m, f):
    """(acción, quién, método, ruta, cuerpo, estado en el que se permite)."""
    return [("editar", "bX", "PUT", f"/facturas/{f}", {"observaciones": "x"}, "emitida"),
            ("eliminar", "bX", "DELETE", f"/facturas/{f}", None, "emitida"),
            ("entregar", "bX", "POST", f"/facturas/{f}/entregar", None, "emitida"),
            ("aceptar", "c1", "POST", f"/facturas/{f}/aceptar", {"firma": firma_png()}, "entregada"),
            ("rechazar", "c1", "POST", f"/facturas/{f}/rechazar", {"motivo_rechazo": "Faltaron cajas"}, "entregada"),
            ("recibir", "bX", "POST", f"/facturas/{f}/recibir", None, "firmada")]


@pytest.mark.parametrize("estado", ESTADOS)
def test_cada_accion_solo_en_su_estado(m, estado):
    """Contrato, 5.3: editar o eliminar fuera de emitida da 400; y lo mismo con las demás acciones."""
    f = m.id["factura bX"]
    for accion, quien, metodo, ruta, cuerpo, permitido in acciones(m, f):
        with SessionLocal() as s:
            s.get(Orden, f).estado_orden = estado
            s.commit()
        if estado == permitido:
            if accion != "eliminar":  # se prueba al final: borra la factura
                assert m.pedir(quien, metodo, ruta, cuerpo).status_code == 200, accion
            continue
        for q in {quien, "X", "admin"} if quien == "bX" else {quien}:  # ni la empresa ni el admin se lo saltan
            r = m.pedir(q, metodo, ruta, cuerpo)
            if quien == "c1" and estado == "emitida":
                assert r.status_code == 404, accion  # el cliente ni siquiera ve los borradores
            else:
                assert (r.status_code, r.json()) == (400, FUERA_DE_ESTADO), (accion, q)
        with SessionLocal() as s:
            assert s.get(Orden, f).estado_orden == estado
    if estado == "emitida":
        with SessionLocal() as s:
            s.get(Orden, f).estado_orden = estado
            s.commit()
        assert m.pedir("bX", "DELETE", f"/facturas/{f}").status_code == 204


def test_solo_el_cliente_de_la_factura_acepta_o_rechaza(m):
    f = m.id["factura bX"]
    m.pedir("bX", "POST", f"/facturas/{f}/entregar")
    for ruta, cuerpo in (("aceptar", {"firma": firma_png()}), ("rechazar", {"motivo_rechazo": "Faltaron cajas"})):
        for quien, codigo, detalle in (("X", 403, SIN_PERMISO["detail"]), ("Y", 403, SIN_PERMISO["detail"]),
                                       ("admin", 403, "Solo el cliente de la factura puede aceptarla o rechazarla"),
                                       ("bX", 403, "Solo el cliente de la factura puede aceptarla o rechazarla"),
                                       ("bY", 404, "Factura no encontrada"), ("c2", 404, "Factura no encontrada")):
            r = m.pedir(quien, "POST", f"/facturas/{f}/{ruta}", cuerpo)
            assert (r.status_code, r.json()) == (codigo, {"detail": detalle}), (ruta, quien)


# ===== REGISTRO: LÍMITES EXACTOS =====

@pytest.mark.parametrize("base,campo,validos,invalidos", [
    (CLIENTE, "nombre", ["x", "x" * 100], ["", "x" * 101]),
    (CLIENTE, "numero_documento", ["1", "1" * 30], ["", "1" * 31, "1.2", "1-2"]),
    (EMPRESA, "razon_social", ["x", "x" * 100], ["", "x" * 101]),
    (EMPRESA, "representante", ["x", "x" * 100], ["", "  ", "x" * 101]),
    (EMPRESA, "direccion", ["x", "x" * 200], ["", "  ", "x" * 201]),
    (CLIENTE, "telefono", ["1234567", "1" * 15], ["123456", "1" * 16, "+573001234567", "300 123 4567"]),
    (EMPRESA, "telefono", ["1234567", "1" * 15], ["123456", "1" * 16, "+573001234567", "300 123 4567"]),
    (CLIENTE, "contrasena", ["x" * 8, "x" * 72], ["x" * 7, "x" * 73]),
    (EMPRESA, "contrasena", ["x" * 8, "x" * 72], ["x" * 7, "x" * 73]),
], ids=lambda v: v if isinstance(v, str) else None)
def test_limites_del_registro(api, base, campo, validos, invalidos):
    for valor in invalidos:
        r = registrar(api, base, **{campo: valor})
        assert r.status_code == 422 and list(r.json()["errores"]) == [campo], (campo, valor, r.text)
    for n, valor in enumerate(validos):
        unicos = {"correo": f"u{n}@x.com", **({"numero_documento": f"77{n}"} if base is CLIENTE else {"nit": f"80011122{n}-3"})}
        r = registrar(api, base, **{**unicos, campo: valor})
        assert r.status_code == 201, (campo, valor, r.text)


def test_el_documento_acepta_letras_con_cualquier_tipo(api):
    """Los extranjeros pueden tener letras en su documento."""
    for n, t in enumerate(("CC", "NIT", "CE", "PA")):
        for malo in ("AB-1", "AB 1", "AB.1", "ÑANDU1", "áb1", "AB#1", "AB_1"):
            r = registrar(api, CLIENTE, tipo_documento=t, numero_documento=malo)
            assert (r.status_code, r.json()["errores"]) == (422, {"numero_documento": DOCUMENTO}), (t, malo)
        r = registrar(api, CLIENTE, tipo_documento=t, numero_documento=f"Ex{n}Ab9", correo=f"ex{n}@x.com")
        assert r.status_code == 201, r.text
    r = registrar(api, CLIENTE, numero_documento="eX0aB9", correo="otro@x.com")  # único sin distinguir mayúsculas
    assert (r.status_code, r.json()) == (400, {"detail": "Ya existe un usuario con ese documento"})


# ===== SOLO NÚMEROS =====

NUMERO, ENTERO, DIGITOS = "debe ser un número", "debe ser un número entero", "solo puede tener números"
DOCUMENTO = "solo puede tener letras y números"
DOC_MALOS = [("10.2", DOCUMENTO), ("10-2", DOCUMENTO), ("10 2", DOCUMENTO), ("AB#1", DOCUMENTO), ("Ñ12", DOCUMENTO), ("٣٤٥", DOCUMENTO)]
LARGO_TEL, VACIO, FORMATO = "debe tener entre 7 y 15 dígitos", "no puede estar vacío", "tiene un formato inválido"
ID = [("3", NUMERO), (3.5, ENTERO), (True, NUMERO), ("", NUMERO), ([3], NUMERO)]
TELEFONO = [("300-1234", DIGITOS), ("+573001234", DIGITOS), ("300 123 4567", DIGITOS), ("abc", DIGITOS), ("123456", LARGO_TEL),
            ("1" * 16, LARGO_TEL), (3001234567, FORMATO)]


def revisar(m, quien, metodo, ruta, armar, campo, casos):
    for valor, mensaje in casos:
        r = m.pedir(quien, metodo, ruta, armar(valor))
        assert r.status_code == 422 and r.json()["errores"].get(campo) == mensaje, (ruta, campo, valor, r.text)
        assert f"{mensaje}" in r.json()["detail"]


def test_numeros_de_la_factura(m):
    base = datos_factura(m.id["usuario c1"], m.id["bodega bX"], m.id["tipo bX"])
    linea = lambda c: lambda v: {**base, "detalle": [{**base["detalle"][0], c: v}]}
    mayor0, desde0, hasta100, iva = "debe ser mayor que 0", "debe ser mayor o igual a 0", "debe ser menor o igual a 100", "debe ser 0, 5 o 19"
    decimales = "debe tener máximo 2 decimales"
    texto = [("10", NUMERO), ("", NUMERO), (True, NUMERO), ("abc", NUMERO), ([1], NUMERO)]
    por_linea = {"tipo_id": ID, "cantidad": texto + [(0, mayor0), (-1, mayor0), (1.555, decimales)],
                 "precio_unitario": texto + [(-1, desde0), (1.555, decimales)],
                 "descuento_porcentaje": texto + [(-1, desde0), (100.5, hasta100), (1.555, decimales)], "iva_porcentaje": texto + [(16, iva), (19.5, iva)]}
    for metodo, ruta in (("POST", "/facturas"), ("PUT", f"/facturas/{m.id['factura bX']}")):
        for campo in ("cliente_id", "bodega_id"):
            revisar(m, "bX", metodo, ruta, lambda v, c=campo: {**base, c: v}, campo, ID)
        for campo, casos in por_linea.items():
            revisar(m, "bX", metodo, ruta, linea(campo), f"detalle[0].{campo}", casos)
    for campo, validos in {"cantidad": [1, 1.5, 0.01], "precio_unitario": [0, 10.25], "descuento_porcentaje": [0, 100, 0.5], "iva_porcentaje": [0, 5, 19]}.items():
        for v in validos:
            assert m.pedir("bX", "POST", "/facturas", linea(campo)(v)).status_code == 201, (campo, v)


def test_numeros_del_usuario(m):
    base = {"nombre": "N", "correo": "nn@n.com", "contrasena": "Temp1234*", "rol_id": m.rol["cliente"], "tipo_documento": "CC"}
    documento = DOC_MALOS + [(102, FORMATO), ("1" * 31, "es demasiado largo")]
    for metodo, ruta in (("POST", "/usuarios"), ("PUT", f"/usuarios/{m.id['usuario c1']}")):
        for campo, casos in (("rol_id", ID), ("telefono", TELEFONO), ("numero_documento", documento)):
            revisar(m, "admin", metodo, ruta, lambda v, c=campo: {**base, c: v}, campo, casos)
    r = m.pedir("admin", "POST", "/usuarios", {**base, "telefono": "  0012345  ", "numero_documento": " 0099 "})
    assert (r.status_code, r.json().get("telefono"), r.json().get("numero_documento")) == (201, "0012345", "0099")  # conserva los ceros


def test_el_documento_no_depende_del_tipo(m):
    u = m.id["usuario c1"]
    for t in ("PA", "CC", "NIT", "CE"):  # ni al editar los dos, ni al cambiar solo el tipo
        r = m.pedir("admin", "PUT", f"/usuarios/{u}", {"tipo_documento": t, "numero_documento": f"AB99{t}"})
        assert (r.status_code, r.json().get("numero_documento")) == (200, f"AB99{t}"), r.text
        assert m.pedir("admin", "PUT", f"/usuarios/{u}", {"tipo_documento": "CC"}).json()["numero_documento"] == f"AB99{t}"
    r = m.pedir("admin", "POST", "/usuarios", {"nombre": "N", "correo": "ex@n.com", "contrasena": "Temp1234*", "rol_id": m.rol["cliente"],
                                               "tipo_documento": "CE", "numero_documento": " X1234567L "})
    assert (r.status_code, r.json()["numero_documento"]) == (201, "X1234567L")
    assert [c["id"] for c in m.pedir("bX", "GET", "/clientes/buscar", q="x1234567").json()["data"]] == [r.json()["id"]]  # y se puede buscar
    r = m.pedir("admin", "PUT", f"/usuarios/{u}", {"numero_documento": "x1234567l"})  # único sin distinguir mayúsculas
    assert (r.status_code, r.json()) == (400, {"detail": "Ya existe un usuario con ese documento"})


def test_una_factura_a_un_extranjero(m):
    """El documento con letras llega a la factura y a su PDF."""
    u = m.id["usuario c1"]
    m.pedir("admin", "PUT", f"/usuarios/{u}", {"tipo_documento": "PA", "numero_documento": "AB1234XY"})
    r = m.pedir("bX", "POST", "/facturas", datos_factura(u, m.id["bodega bX"], m.id["tipo bX"]))
    assert r.status_code == 201 and r.json()["adquiriente"]["numero_documento"] == "AB1234XY" and "DocAdq:AB1234XY" in r.json()["validacion_electronica"]["qr"]
    assert m.pedir("bX", "GET", f"/facturas/{r.json()['id']}/pdf").content.startswith(b"%PDF")


def test_borrar_telefono_y_documento(m):
    u = m.id["usuario c1"]
    r = m.pedir("admin", "PUT", f"/usuarios/{u}", {"telefono": "", "numero_documento": ""})  # "" los borra
    assert (r.json()["telefono"], r.json()["numero_documento"]) == (None, None)


def test_numeros_de_la_bodega(m):
    doc = DOC_MALOS + [("", VACIO), (123, FORMATO)]
    base = datos_bodega("NUM", empresa_id=m.id["empresa X"])
    for metodo, ruta in (("POST", "/bodegas"), ("PUT", f"/bodegas/{m.id['bodega bX']}")):
        for campo, casos in (("telefono", TELEFONO + [("", VACIO)]), ("recibe_telefono", TELEFONO + [("", VACIO)]), ("recibe_documento", doc),
                             ("bodeguero_id", ID)):
            revisar(m, "admin", metodo, ruta, lambda v, c=campo: {**base, c: v}, campo, casos)
    r = m.pedir("admin", "POST", "/bodegas", {**base, "recibe_documento": "1" * 31})
    assert r.status_code == 422 and list(r.json()["errores"]) == ["recibe_documento"]
    r = m.pedir("admin", "POST", "/bodegas", {**base, "codigo": "bod-letras", "bodeguero_id": None, "recibe_documento": " PA123x "})
    assert (r.status_code, r.json().get("codigo"), r.json().get("recibe_documento")) == (201, "BOD-LETRAS", "PA123x")  # ambos aceptan letras


def test_numeros_de_tipos_y_permisos(m):
    for metodo, ruta in (("POST", "/tipos"), ("PUT", f"/tipos/{m.id['tipo bX']}")):
        revisar(m, "admin", metodo, ruta, lambda v: {"nombre": "Z", "bodega_id": v}, "bodega_id", ID)
    for ruta in (f"/usuarios/{m.id['usuario c1']}/permisos", f"/roles/{m.rol['cliente']}/permisos"):
        for valor, mensaje in ID:
            r = m.pedir("admin", "PUT", ruta, {"permisos_ids": [1, valor]})
            assert (r.status_code, r.json()["errores"]) == (422, {"permisos_ids[1]": mensaje}), (ruta, valor)
        assert m.pedir("admin", "PUT", ruta, {"permisos_ids": [1, 2]}).status_code == 200


# ===== FORMA DE LOS ERRORES =====

def test_nunca_se_responde_409_y_los_errores_tienen_la_forma_acordada(m):
    casos = [(m.pedir("X", "POST", "/bodegas", datos_bodega("C-bX")), 400), (m.pedir("bX", "GET", "/empresas"), 403),
             (m.pedir("X", "GET", "/bodegas/999999"), 404), (m.pedir("X", "POST", "/bodegas", {}), 422),
             (registrar(m.api, CLIENTE, correo="admin@entrega.com"), 400)]
    for r, codigo in casos:
        assert r.status_code == codigo and isinstance(r.json()["detail"], str)
        assert set(r.json()) == ({"detail", "errores"} if codigo == 422 else {"detail"})
