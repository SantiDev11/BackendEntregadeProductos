# Módulos de la aplicación: cada carpeta agrupa todo lo de un módulo
# (models, schemas, queries, helpers y router).
#
# Aquí se importan TODOS los modelos para que SQLAlchemy los registre juntos: las relaciones entre
# módulos se escriben por nombre (relationship("Rol")) y necesitan que todas las clases estén cargadas.
from app.modulos.empresas.models import Empresa, ESTADOS_EMPRESA  # noqa: F401
from app.modulos.tipos.models import Tipo  # noqa: F401
from app.modulos.bodegas.models import Bodega  # noqa: F401
from app.modulos.permisos.models import Permiso  # noqa: F401
from app.modulos.roles.models import Rol, rol_permiso  # noqa: F401
from app.modulos.usuarios.models import Usuario, usuario_permisos  # noqa: F401
from app.modulos.facturas.models import ConsecutivoFactura, Orden, OrdenDetalle, ESTADOS_ORDEN  # noqa: F401
