# BackendEntregadeProductos

API REST para la **entrega de productos con factura electrónica simulada**.

Hay tres roles:
- El **admin** gestiona todo.
- El **bodeguero** maneja sus bodegas, su catálogo de tipos y emite facturas.
- El **cliente** recibe las facturas y las acepta con su firma o las rechaza.

Hecho con **FastAPI + SQLAlchemy + MySQL**. Lo consume un frontend en Vue.

## Tecnologías

| Para qué | Librería |
|---|---|
| API | FastAPI + Uvicorn |
| Base de datos | MySQL 8 (Laragon) con SQLAlchemy 2 y PyMySQL |
| Validación | Pydantic v2 |
| Autenticación | JWT (python-jose, HS256, 60 min) y contraseñas con bcrypt (passlib) |
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
    └── comun/         # mixin de estado y auditoría
migraciones/           # cambios para bases de datos que ya existían
```

Cada módulo tiene estos archivos:

| Archivo | Contenido |
|---|---|
| `router.py` | Solo las rutas y su documentación; cada endpoint llama a `services` |
| `services.py` | La lógica de cada endpoint (crear, editar, eliminar...) |
| `helpers.py` | Validaciones y reglas (comprueban y lanzan el error que corresponde) |
| `errors.py` | Los mensajes de error, una función por error (`raise errors.bodega_no_encontrada()`) y los ejemplos de error de /docs |
| `queries.py` | Consultas a la base de datos |
| `schemas.py` | Entrada y salida (Pydantic) |
| `models.py` | Tablas |

Flujo de una petición: `router` → `services` → `helpers` (valida, y si algo falla lanza un error de `errors`) → `queries` (BD).

## Endpoints

Todos, menos `POST /login`, piden `Authorization: Bearer <token>`.

| Módulo | Rutas |
|---|---|
| Auth | `POST /login`, `GET /me` |
| Tipos | `GET/POST /tipos`, `GET/PUT/DELETE /tipos/{id}` |
| Bodegas | `GET/POST /bodegas`, `GET/PUT/DELETE /bodegas/{id}` |
| Permisos | `GET/POST /permisos`, `GET/PUT/DELETE /permisos/{id}` |
| Roles | `GET/POST /roles`, `GET/PUT/DELETE /roles/{id}`, `PUT /roles/{id}/permisos` |
| Usuarios | `GET/POST /usuarios`, `GET/PUT/DELETE /usuarios/{id}`, `GET/PUT /usuarios/{id}/permisos`, `POST/DELETE /usuarios/{id}/permisos/{permiso_id}` |
| Facturas | `GET/POST /facturas`, `GET /facturas/clientes`, `GET/PUT/DELETE /facturas/{id}`, `GET /facturas/{id}/pdf`, `POST /facturas/{id}/entregar`, `.../aceptar`, `.../rechazar`, `.../recibir` |
| Estadísticas | `GET /estadisticas/resumen?desde=AAAA-MM-DD&hasta=AAAA-MM-DD` |

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
  - La numeración es `FE-0001`, `FE-0002`, …
  - Los totales y el IVA los calcula el servidor.
  - El CUFE es **simulado** (SHA-384) y la factura trae un QR.
  - Los datos del emisor son ficticios, de ejemplo, y están en `app/modulos/facturas/emisor.py`.

### Estadísticas
- Un solo endpoint, `GET /estadisticas/resumen`, con el permiso `estadisticas_view`.
- Devuelve tarjetas (números) y series (gráficos) del periodo pedido; por defecto, el mes actual.
- Cuenta las facturas con la misma regla de dueño de `GET /facturas`. Cada rol solo recibe lo que puede ver: el cliente no recibe series de bodegas ni de productos.

### Errores
- Siempre en español, con la forma `{"detail": "..."}`.
- Los de validación (422) además traen `errores`, por campo:

  ```json
  {"detail": "nombre: es obligatorio", "errores": {"nombre": "es obligatorio"}}
  ```

## Migraciones

Una base de datos **nueva** no las necesita: la app crea las tablas con el esquema actual.

Si la base ya existía de una versión anterior, aplica en orden los archivos de `migraciones/`:

```powershell
# .sql: con el cliente de MySQL de Laragon
Get-Content migraciones\003_tipos_por_bodega.sql | mysql -u root entrega_productos
# .py: con el entorno virtual activo
python migraciones\002_permisos_catalogo_y_usuarios.py
python migraciones\004_permiso_estadisticas.py
```
