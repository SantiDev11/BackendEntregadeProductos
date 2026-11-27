# BackendEntregadeProductos

API REST para la **entrega de productos con factura electrónica simulada**.

Hay cuatro roles:
- El **admin** gestiona todo y aprueba las empresas.
- La **empresa** se registra y, cuando el admin la aprueba, gestiona lo suyo (los filtros por empresa están en desarrollo).
- El **bodeguero** maneja sus bodegas, su catálogo de tipos y emite facturas.
- El **cliente** recibe las facturas y las acepta con su firma o las rechaza.

Hecho con **FastAPI + SQLAlchemy + MySQL**. Lo consume un frontend en Vue.

## Tecnologías

| Para qué | Librería |
|---|---|
| API | FastAPI + Uvicorn |
| Base de datos | MySQL 8 (Laragon) con SQLAlchemy 2 y PyMySQL |
| Validación | Pydantic v2 |
| Autenticación | JWT (python-jose, HS256): acceso de 60 min y refresh de 7 días. Contraseñas con bcrypt (passlib) |
| PDF de la factura | fpdf2 + Pillow |

## Instalación (Windows / PowerShell)

1. **Crear la base de datos** en MySQL (las tablas las crea la app sola):

   ```sql
   CREATE DATABASE entrega_productos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

2. **Entorno virtual y dependencias:**

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Variables de entorno:** copia `.env.example` a `.env` y ajusta los valores.

   ```powershell
   Copy-Item .env.example .env
   ```

   | Variable | Ejemplo |
   |---|---|
   | `DATABASE_URL` | `mysql+pymysql://root:@localhost:3306/entrega_productos` |
   | `SECRET_KEY` | una clave larga y secreta para firmar los tokens |
   | `REFRESH_TOKEN_EXPIRE_DAYS` | `7` (opcional: días que dura el refresh token) |

4. **Datos iniciales (seed):**
   - Crea las tablas, los roles, el catálogo de 30 permisos y los usuarios de prueba.
   - Se puede correr varias veces: lo que ya existe no se duplica.

   ```powershell
   python -m app.config.seed
   ```

5. **Levantar el servidor:**

   ```powershell
   uvicorn app.config.main:app --reload
   ```

   - Para que otro equipo de la red (por ejemplo, el frontend) pueda llamarlo: `uvicorn app.config.main:app --reload --host 0.0.0.0 --port 8000`. Hay que permitir el puerto 8000 en el firewall.
   - La URL del frontend tiene que estar en `allow_origins` del CORS en `app/config/main.py`.

Documentación interactiva: **http://localhost:8000/docs**

## Usuarios de prueba (creados por el seed)

| Rol | Correo | Contraseña |
|---|---|---|
| admin | admin@entrega.com | Admin123* |
| bodeguero | bodeguero@entrega.com | Bodega123* |
| cliente | cliente@entrega.com | Cliente123* |

> Son solo para desarrollo: cámbialos antes de usar el sistema en serio.

## Estructura

```
app/
├── config/            # configuración y arranque
│   ├── main.py        # crea la app, CORS, /docs y registra los routers
│   ├── database.py    # conexión a MySQL (lee DATABASE_URL del .env)
│   └── seed.py        # datos iniciales
├── core/              # código compartido
│   ├── deps.py        # usuario del token y require_permiso(...)
│   ├── jwt.py         # crear y leer tokens
│   ├── security.py    # hash de contraseñas
│   ├── permisos.py    # catálogo de permisos y plantillas por rol
│   ├── errors.py      # formato de los 422 en español y errores base (error_400, error_404...)
│   └── docs.py        # formato de los errores en /docs y página /docs ordenada
└── modulos/           # un módulo por recurso
    ├── auth/  tipos/  bodegas/  permisos/  roles/  usuarios/  facturas/  estadisticas/
    ├── empresas/  registro/  clientes/
    └── comun/         # mixin de estado y auditoría
migraciones/           # cambios para bases de datos que ya existían
tests/                 # pruebas automáticas (pytest)
```

Cada módulo tiene estos archivos:

| Archivo | Contenido |
|---|---|
| `router.py` | Solo las rutas y su documentación; cada endpoint llama a `services` |
| `services.py` | La lógica de cada endpoint (crear, editar, eliminar...) |
| `helpers.py` | Validaciones y reglas (comprueban y lanzan el error que corresponde) |
| `errors.py` | Los mensajes de error, una función por error (`raise errors.bodega_no_encontrada()`) y los ejemplos de error de /docs |
| `queries.py` | Consultas a la base de datos |
| `schemas.py` | Entrada y salida (Pydantic), con los validadores que necesita el módulo |
| `models.py` | Tablas |

Flujo de una petición: `router` → `services` → `helpers` (valida, y si algo falla lanza un error de `errors`) → `queries` (BD).

## Endpoints

Todos, menos `POST /login`, `POST /refresh` y `POST /register`, piden `Authorization: Bearer <token>`.

| Módulo | Rutas |
|---|---|
| Auth | `POST /login` (con correo o número de documento), `POST /refresh`, `POST /register`, `GET /me` |
| Empresas (solo admin) | `GET /empresas?q=&estado=&page=&limit=`, `POST /empresas`, `GET/PUT/DELETE /empresas/{id}`, `PATCH /empresas/{id}/estado` |
| Tipos | `GET/POST /tipos`, `GET/PUT/DELETE /tipos/{id}`, `PATCH /tipos/{id}/estado` |
| Bodegas | `GET/POST /bodegas`, `GET/PUT/DELETE /bodegas/{id}`, `PATCH /bodegas/{id}/estado` |
| Permisos | `GET/POST /permisos`, `GET/PUT/DELETE /permisos/{id}` |
| Roles | `GET/POST /roles`, `GET/PUT/DELETE /roles/{id}`, `PUT /roles/{id}/permisos`, `PATCH /roles/{id}/estado` |
| Usuarios | `GET/POST /usuarios`, `GET/PUT/DELETE /usuarios/{id}`, `PATCH /usuarios/{id}/estado`, `GET/PUT /usuarios/{id}/permisos`, `POST/DELETE /usuarios/{id}/permisos/{permiso_id}` |
| Clientes | `GET /clientes/buscar?q=&page=&limit=` (`q` de mínimo 3 caracteres) |
| Facturas | `GET/POST /facturas`, `GET /facturas/clientes` (en desuso: usar `/clientes/buscar`), `GET/PUT/DELETE /facturas/{id}`, `GET /facturas/{id}/pdf`, `POST /facturas/{id}/entregar`, `.../aceptar`, `.../rechazar`, `.../recibir` |
| Estadísticas | `GET /estadisticas/resumen?fecha_inicio=AAAA-MM-DD&fecha_fin=AAAA-MM-DD` y los filtros de cada rol |

`PATCH /{id}/estado` recibe `{"estado": true}` o `{"estado": false}` y exige el permiso `*_edit` del módulo. El `PUT` también acepta `estado`.

Los listados son paginados: `?page=1&limit=10` (máximo 100) y responden `{"data": [...], "total": n, "page": p, "limit": l}`.

## Flujo típico

1. El bodeguero inicia sesión (`POST /login`) y crea su bodega (`POST /bodegas`).
2. Crea los tipos de su catálogo (`POST /tipos`).
3. Crea la factura para un cliente (`POST /facturas`). Queda en `emitida`.
4. La entrega al cliente (`POST /facturas/{id}/entregar`).
5. El cliente la acepta con su firma (`POST /facturas/{id}/aceptar`) o la rechaza (`POST /facturas/{id}/rechazar`).
6. Si la aceptó, el bodeguero la marca como recibida (`POST /facturas/{id}/recibir`).
7. Cualquiera de los dos puede descargar el PDF (`GET /facturas/{id}/pdf`).

## Reglas principales

### Permisos
- Se comprueban **por usuario**, en la tabla `usuario_permisos`.
- Al crear un usuario se le copian los permisos de la plantilla de su rol. Después el admin puede agregarle o quitarle permisos.
- El rol `admin` siempre pasa.

### Empresas y registro
- `POST /register` es público. Con `tipo: "cliente"` la cuenta queda activa; con `tipo: "empresa"` crea la empresa `pendiente` y su usuario.
- El admin también puede crear una empresa ya `activa`, con su usuario (`POST /empresas`), editarla, y eliminarla solo si no tiene datos.
- **Estados:** `pendiente` → `activa` o `rechazada` (con motivo). Una `activa` puede pasar a `suspendida`, y una `suspendida` o `rechazada` a `activa`.
- Mientras la empresa no esté `activa`, sus usuarios reciben **403** en el login, en `/refresh` y con cualquier token.
- `POST /login` y `GET /me` traen `empresa` (`{id, razon_social, estado}`) o `null`.
- Al crear bodegueros, usuarios empresa o bodegas, el admin debe enviar `empresa_id` (número; **422** si falta o no existe, **400** si la empresa no está `activa`). Lo que crea una empresa queda en la empresa del token: el `empresa_id` del cuerpo se ignora.
- El rol `empresa` nunca gestiona permisos ni roles, ni acepta o rechaza facturas, aunque le asignen el permiso.

### Campos numéricos
- Los ids, cantidades, precios y porcentajes se envían como número (`10`, no `"10"`).
- Los teléfonos van como texto, pero solo con dígitos (7 a 15).
- Los documentos van como texto, con **letras y números** (hasta 30), porque los extranjeros pueden llevar letras. Sin espacios ni símbolos.

### Bodegas
- El admin ve todas. Los demás usuarios solo ven las suyas.

### Tipos
- Cada bodega tiene su propio catálogo, y el nombre es único dentro de cada bodega.
- Un bodeguero solo ve y edita los tipos de sus bodegas.

### Facturas
- **Quién ve qué:**
  - El admin ve todas.
  - El bodeguero solo ve las que creó.
  - El cliente ve las que creó y las que llevan su `cliente_id`, menos las que siguen en `emitida`.
  - Si la factura no es del usuario, la respuesta es **404**.
- **Estados:** `emitida` → `entregada` → `firmada` (el cliente la acepta y firma) → `recibida`. El cliente también puede pasarla a `rechazada`.
- **Datos de la factura:**
  - La numeración es `FE-0001`, `FE-0002`, … **por empresa**: dos empresas pueden tener `FE-0001`. La clave es `id`, nunca `numero`.
    Un número ya usado no se repite dentro de su empresa, aunque la factura se elimine o se creen varias a la vez.
  - El listado y el detalle traen `empresa_id` y `empresa_nombre` (`null` si la factura no tiene empresa).
  - Para rechazarla, `motivo_rechazo` es obligatorio, de 10 a 255 caracteres.
  - Los totales y el IVA los calcula el servidor.
  - El CUFE es **simulado** (SHA-384) y la factura trae un QR.
  - El emisor (JSON y PDF) es la empresa de la factura: razón social, NIT, dirección, teléfono y correo. Se copia al emitirla,
    así que si la empresa cambia sus datos, la factura conserva los de ese momento.
  - Las facturas sin empresa salen con el emisor por defecto, ficticio, de `app/modulos/facturas/emisor.py`.

### Estadísticas
- Un solo endpoint, `GET /estadisticas/resumen`, con el permiso `estadisticas_view`.
- Un panel por rol, todos con la misma forma: `kpis`, `desglose_principal`, `serie_temporal`, `alertas_detalle` y `filtros_disponibles`. Por defecto, el mes actual.
- Cuenta las facturas con la misma regla de dueño de `GET /facturas`. Los filtros que no son del rol se ignoran: el alcance sale del token.
- `desde`, `hasta`, `tarjetas` y `series` están en desuso, pero siguen funcionando hasta que el frontend confirme.

### Errores
- Siempre en español, con la forma `{"detail": "..."}`.
- Los de validación (422) además traen `errores`, por campo:

  ```json
  {"detail": "nombre: es obligatorio", "errores": {"nombre": "es obligatorio"}}
  ```

## Pruebas

Usan una base aparte, `entrega_productos_test`, que se crea sola y queda vacía al terminar. Nunca tocan la base real.

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

## Migraciones

Una base de datos **nueva** no las necesita: la app crea las tablas con el esquema actual.

Si la base ya existía de una versión anterior, aplica **en orden** los archivos de `migraciones/` que te falten, antes de arrancar la app:

```powershell
# .sql: con el cliente de MySQL de Laragon. .py: con el entorno virtual activo
Get-Content migraciones\001_usuario_permisos.sql | mysql -u root entrega_productos
python migraciones\002_permisos_catalogo_y_usuarios.py
Get-Content migraciones\003_tipos_por_bodega.sql | mysql -u root entrega_productos
python migraciones\004_permiso_estadisticas.py
Get-Content migraciones\005_empresas.sql | mysql -u root entrega_productos
python migraciones\006_backfill_empresas.py            # opcional: solo muestra qué haría; con --aplicar lo guarda
python migraciones\007_rol_empresa.py
Get-Content migraciones\008_numeracion_por_empresa.sql | mysql -u root entrega_productos
python migraciones\009_emisor_por_empresa.py           # opcional: solo muestra qué haría; con --aplicar lo guarda
Get-Content migraciones\010_desactivado_por_empresa.sql | mysql -u root entrega_productos
Get-Content migraciones\011_desactivado_por_rol.sql | mysql -u root entrega_productos
```
