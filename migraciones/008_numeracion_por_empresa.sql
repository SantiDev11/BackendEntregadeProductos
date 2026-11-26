-- Migración 008: numeración de las facturas por empresa (solo estructura, no cambia ningún dato).
-- Se corre UNA sola vez, después de 005_empresas.sql:
--   Get-Content migraciones\008_numeracion_por_empresa.sql | mysql -u root entrega_productos
--
-- 1) El número deja de ser único en todo el sistema y pasa a serlo dentro de cada empresa (FE-0001 en cada una).
--    La columna serie la calcula MySQL (la empresa, o 0 si no tiene): un índice único no compara los NULL entre sí.
-- 2) Crea el contador de cada empresa. Queda vacío: la app lo inicia con el último número ya guardado.
-- Las facturas que ya existen conservan su número.

ALTER TABLE ordenes
    ADD COLUMN serie INT GENERATED ALWAYS AS (COALESCE(empresa_id, 0)) VIRTUAL AFTER empresa_id,
    DROP INDEX numero,
    DROP INDEX uq_ordenes_prefijo_consecutivo,
    ADD CONSTRAINT uq_ordenes_serie_consecutivo UNIQUE (serie, prefijo, consecutivo);

CREATE TABLE IF NOT EXISTS consecutivos_factura (
    serie INT NOT NULL,
    prefijo VARCHAR(10) NOT NULL,
    ultimo INT NOT NULL,
    PRIMARY KEY (serie, prefijo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Para deshacerla (falla si dos empresas ya tienen el mismo número):
--   ALTER TABLE ordenes ADD UNIQUE KEY uq_ordenes_prefijo_consecutivo (prefijo, consecutivo), ADD UNIQUE KEY numero (numero),
--       DROP INDEX uq_ordenes_serie_consecutivo, DROP COLUMN serie
--   DROP TABLE consecutivos_factura
