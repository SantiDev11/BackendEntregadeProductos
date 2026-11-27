-- Migración 011: recordar qué usuarios desactivó la desactivación de su rol, para reactivar solo esos al reactivarlo.
--
--   Get-Content migraciones\011_desactivado_por_rol.sql | mysql -u root entrega_productos
--
-- desactivado_por_rol = 1: el usuario está inactivo porque su rol se desactivó (no porque alguien lo desactivó).
-- Convive con desactivado_por_empresa (010): el usuario vuelve a activo solo cuando no lo frena ninguna de las dos.
-- Solo agrega una columna con valor 0: no cambia ningún dato.

ALTER TABLE usuarios ADD COLUMN desactivado_por_rol TINYINT(1) NOT NULL DEFAULT 0;
