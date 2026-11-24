# Campos de solo números en todos los formularios

El backend ahora rechaza con **422** los textos en los campos numéricos. Antes convertía `"10"` en `10`.
Aplica a facturas, usuarios, bodegas, tipos y roles. Permisos y login no tienen campos numéricos.

**Importante para el front:**

- Un `<input>` o `<select>` de HTML entrega texto. Hay que convertirlo antes de enviar (`Number(valor)` o `v-model.number`).
- Si un id opcional está vacío (por ejemplo, "sin bodega"), envíen `null` o no lo envíen. `""` da 422.
- Teléfonos y documentos **siguen siendo texto** en el JSON (`"3001234567"`), porque pueden empezar por 0. Si se envían como número, dan 422.

## 1. Se envían como número

| Formulario | Campo | Se acepta | Se rechaza |
|---|---|---|---|
| Facturas | `cliente_id`, `bodega_id`, `detalle[].tipo_id` | entero: `3` | `"3"`, `3.5`, `true`, `""` |
| Facturas | `detalle[].cantidad` | mayor que 0, hasta 2 decimales: `10`, `1.5` | `"10"`, `""`, `true` |
| Facturas | `detalle[].precio_unitario` | desde 0, hasta 2 decimales | `"3500"`, `""` |
| Facturas | `detalle[].descuento_porcentaje` | de 0 a 100, hasta 2 decimales | `"0"`, `""` |
| Facturas | `detalle[].iva_porcentaje` | `0`, `5` o `19` | `"19"` |
| Usuarios | `rol_id` | entero | `"3"` |
| Usuarios | `permisos_ids` (en `/usuarios/{id}/permisos`) | `[1, 2]` | `["1", "2"]` |
| Bodegas | `bodeguero_id` | entero o `null` | `"2"`, `""` |
| Tipos | `bodega_id` | entero o `null` | `"1"`, `""` |
| Roles | `permisos_ids` (en `/roles/{id}/permisos`) | `[1, 2]` | `["1", "2"]` |

## 2. Se envían como texto, pero solo con dígitos

| Formulario | Campo | Regla |
|---|---|---|
| Usuarios | `numero_documento` | Solo dígitos. **Solo con tipo `PA`** acepta también letras. Opcional: `""` lo borra |
| Usuarios | `telefono` | De **7 a 15** dígitos. Opcional: `""` lo borra |
| Bodegas | `telefono`, `recibe_telefono` | De **7 a 15** dígitos. Obligatorios |
| Bodegas | `recibe_documento` | Solo dígitos, hasta 30. Obligatorio |

- Ninguno acepta puntos, guiones, espacios intermedios, `+` ni letras. Los espacios al inicio y al final se quitan solos.
- **Al editar un usuario**, el documento se valida con el tipo que va a quedar guardado. Si tiene pasaporte con letras y lo pasan a `CC`, hay que enviar también el número nuevo.
- El `codigo` de la bodega **no** cambió: sigue aceptando letras (`BOD-01`).

## 3. Mensajes

Llegan en `errores`, con la ruta del campo:

```json
{
  "detail": "telefono: solo puede tener números; bodeguero_id: debe ser un número",
  "errores": {
    "telefono": "solo puede tener números",
    "bodeguero_id": "debe ser un número"
  }
}
```

En listas la ruta trae la posición: `detalle[0].cantidad`, `permisos_ids[1]`.

| Mensaje | Cuándo |
|---|---|
| `debe ser un número` | Llegó un texto, `true`/`false`, una lista, etc. |
| `debe ser un número entero` | Un id con decimales (`3.5`) |
| `solo puede tener números` | Documento o teléfono con letras o símbolos |
| `solo puede tener letras y números` | Pasaporte (`PA`) con símbolos |
| `debe tener entre 7 y 15 dígitos` | Teléfono muy corto o muy largo |

Los demás mensajes no cambian (`es obligatorio`, `no puede estar vacío`, `debe ser mayor que 0`…). Las respuestas de los `GET` son iguales.
