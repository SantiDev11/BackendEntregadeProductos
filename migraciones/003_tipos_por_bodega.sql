-- Migración 003: cada tipo pertenece a una bodega (catálogo de tipos por bodega)
-- - Agrega tipos.bodega_id (FK a bodegas). Los tipos que ya existían quedan en NULL ("sin bodega": solo los maneja el admin).
-- - El nombre deja de ser único global y pasa a ser único POR BODEGA.
--
-- Ejecutar con:
--   & "C:\laragon\bin\mysql\mysql-8.4.3-winx64\bin\mysql.exe" -u root entrega_productos -e "source migraciones/003_tipos_por_bodega.sql"

ALTER TABLE tipos
    ADD COLUMN bodega_id INT NULL AFTER nombre,
    ADD CONSTRAINT fk_tipos_bodega FOREIGN KEY (bodega_id) REFERENCES bodegas (id);

-- Nombre único por bodega (antes era único en toda la tabla)
ALTER TABLE tipos
    DROP INDEX nombre,
    ADD UNIQUE KEY uq_tipos_bodega_nombre (bodega_id, nombre);
