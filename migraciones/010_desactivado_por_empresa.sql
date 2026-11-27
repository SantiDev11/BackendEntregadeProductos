-- Migración 010: recordar qué desactivó la suspensión de una empresa, para reactivar solo eso al reactivarla.
--
--   Get-Content migraciones\010_desactivado_por_empresa.sql | mysql -u root entrega_productos
--
-- desactivado_por_empresa = 1: el registro está inactivo porque su empresa se suspendió (no porque alguien lo desactivó).
-- Al reactivar la empresa vuelven a estar activos solo esos; los que ya estaban inactivos antes siguen así.
-- Solo agrega columnas con valor 0: no cambia ningún dato.

ALTER TABLE usuarios ADD COLUMN desactivado_por_empresa TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE bodegas ADD COLUMN desactivado_por_empresa TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE tipos ADD COLUMN desactivado_por_empresa TINYINT(1) NOT NULL DEFAULT 0;
