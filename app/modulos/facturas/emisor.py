# Datos del emisor de las facturas (no hay tabla de empresa: se manejan como constantes).
# ⚠️ DATOS FICTICIOS DE EJEMPLO: cambiarlos por los datos reales de la empresa antes de entregar.

# Empresa que emite las facturas
EMISOR = {
    "nit": "900000000",  # NIT sin dígito de verificación
    "dv": "1",  # dígito de verificación del NIT
    "razon_social": "Empresa Demo S.A.S.",
    "nombre_comercial": "Entrega Demo",
    "direccion": "Calle 100 # 10-20",
    "ciudad": "Bogotá",
    "departamento": "Cundinamarca",
    "telefono": "6015550000",
    "correo": "facturacion@empresademo.com",
    "regimen": "Responsable de IVA",
    "responsabilidad_fiscal": "R-99-PN",  # código de responsabilidad fiscal (ejemplo)
}

# Numeración y valores por defecto de las facturas
PREFIJO_FACTURA = "FE"  # las facturas quedan como FE-0001, FE-0002, ...
MONEDA = "COP"  # peso colombiano
IVA_POR_DEFECTO = 19  # porcentaje de IVA cuando no se indica otro

# Resolución de facturación (ejemplo)
RESOLUCION = {
    "numero": "18760000000000",
    "fecha": "2026-01-01",
    "rango_desde": 1,
    "rango_hasta": 10000,
}

# Software con el que se generan las facturas (ejemplo)
SOFTWARE = {
    "nombre": "Entrega de Productos",
    "fabricante": "Equipo Entrega de Productos",
    "version": "1.0.0",
}
