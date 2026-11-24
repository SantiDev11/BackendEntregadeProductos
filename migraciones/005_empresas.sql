-- Migración 005: modelo de datos multiempresa (solo estructura, no cambia ningún dato).
-- Se corre UNA sola vez, ANTES de arrancar la app con los modelos nuevos:
--   Get-Content migraciones\005_empresas.sql | mysql -u root entrega_productos
--
-- 1) Crea la tabla empresas.
-- 2) Agrega empresa_id (nullable, FK a empresas) a usuarios, bodegas, tipos y ordenes (las facturas).
-- Los registros que ya existen quedan con empresa_id = NULL. Para asignarlos: 006_backfill_empresas.py

CREATE TABLE IF NOT EXISTS empresas (
    id INT NOT NULL AUTO_INCREMENT,
    razon_social VARCHAR(100) NOT NULL,
    nit VARCHAR(20) NULL,
    dv VARCHAR(1) NULL,
    correo VARCHAR(100) NULL,
    telefono VARCHAR(30) NULL,
    direccion VARCHAR(200) NULL,
    representante VARCHAR(100) NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    motivo_rechazo VARCHAR(255) NULL,
    creado_en DATETIME NOT NULL DEFAULT (NOW()),
    actualizado_en DATETIME NOT NULL DEFAULT (NOW()),
    PRIMARY KEY (id),
    UNIQUE KEY uq_empresas_nit (nit),
    KEY ix_empresas_id (id),
    KEY ix_empresas_estado (estado),
    CONSTRAINT ck_empresas_estado CHECK (estado IN ('pendiente', 'activa', 'rechazada', 'suspendida'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE usuarios ADD COLUMN empresa_id INT NULL AFTER rol_id,
    ADD CONSTRAINT fk_usuarios_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id);

ALTER TABLE bodegas ADD COLUMN empresa_id INT NULL AFTER bodeguero_id,
    ADD CONSTRAINT fk_bodegas_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id);

ALTER TABLE tipos ADD COLUMN empresa_id INT NULL AFTER bodega_id,
    ADD CONSTRAINT fk_tipos_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id);

ALTER TABLE ordenes ADD COLUMN empresa_id INT NULL AFTER bodeguero_id,
    ADD CONSTRAINT fk_ordenes_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id);

-- Para deshacerla (se pierden las empresas y las asignaciones):
--   ALTER TABLE ordenes DROP FOREIGN KEY fk_ordenes_empresa, DROP COLUMN empresa_id
--   ALTER TABLE tipos DROP FOREIGN KEY fk_tipos_empresa, DROP COLUMN empresa_id
--   ALTER TABLE bodegas DROP FOREIGN KEY fk_bodegas_empresa, DROP COLUMN empresa_id
--   ALTER TABLE usuarios DROP FOREIGN KEY fk_usuarios_empresa, DROP COLUMN empresa_id
--   DROP TABLE empresas
