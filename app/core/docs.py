# Documentación de la API: página /docs ordenada y ayudas para documentar errores
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from typing import Dict, Optional

from pydantic import BaseModel, Field


# ===== RESPUESTAS DE ERROR (solo documentación) =====

class ErrorRespuesta(BaseModel):
    """Formato de todos los errores de la API: {"detail": "texto"}. Los 422 además traen "errores"."""
    detail: str = Field(description="Mensaje del error en español", examples=["Tipo no encontrado"])
    errores: Optional[Dict[str, str]] = Field(
        default=None,
        description='**Solo en los 422.** Un mensaje por campo con la ruta completa, por ejemplo '
                    '`{"cliente_id": "es obligatorio", "detalle[0].descripcion": "es obligatorio"}`.',
        examples=[{"cliente_id": "es obligatorio", "detalle[0].descripcion": "es obligatorio"}],
    )


def respuesta_error(descripcion: str, **ejemplos: str) -> dict:
    """Arma la documentación de un código de error con uno o varios ejemplos de {"detail": ...}.
    Uso: responses={404: respuesta_error("No existe", no_existe="Tipo no encontrado")}"""
    return {
        "model": ErrorRespuesta,
        "description": descripcion,
        "content": {
            "application/json": {
                "examples": {
                    nombre: {"summary": mensaje, "value": {"detail": mensaje}}
                    for nombre, mensaje in ejemplos.items()
                }
            }
        },
    }


# Errores comunes de los endpoints protegidos
ERROR_401 = respuesta_error(
    "No hay sesión o el token no es válido",
    sin_token="No ha iniciado sesión",
    token_invalido="Token inválido o vencido",
)
ERROR_403 = respuesta_error(
    "El rol del usuario no tiene permiso para esta acción",
    sin_permiso="No tiene permiso para esta acción",
)


# ===== PÁGINA /docs ORDENADA =====

# Función JavaScript que Swagger UI usa para ordenar los endpoints dentro de cada grupo.
# 1) Por método: GET primero, luego POST, PUT, PATCH y DELETE.
# 2) Si el método es igual, la ruta más corta primero (GET /tipos antes que GET /tipos/{id}).
ORDENAR_ENDPOINTS_JS = """(a, b) => {
        const orden = { get: 1, post: 2, put: 3, patch: 4, delete: 5 };
        const ma = orden[a.get("method")] || 9;
        const mb = orden[b.get("method")] || 9;
        if (ma !== mb) return ma - mb;
        const pa = a.get("path"), pb = b.get("path");
        return pa.length - pb.length || pa.localeCompare(pb);
    }"""


def configurar_docs(app: FastAPI) -> None:
    """Registra /docs usando el Swagger UI de FastAPI más el ordenamiento propio.
    Requiere crear la app con docs_url=None para que no choque con el /docs por defecto."""

    @app.get("/docs", include_in_schema=False)
    def swagger_ui():
        respuesta = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
        )
        # Se agrega operationsSorter justo antes de "presets", dentro de la configuración de Swagger UI
        html = respuesta.body.decode().replace(
            "presets: [",
            f"operationsSorter: {ORDENAR_ENDPOINTS_JS},\n    presets: [",
            1,
        )
        return HTMLResponse(html)
