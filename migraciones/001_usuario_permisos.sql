-- Migración 001: permisos por usuario
-- Crea la tabla usuario_permisos y copia a cada usuario los permisos que hoy tiene su rol,
-- para que nadie pierda acceso. Se puede ejecutar varias veces sin duplicar (IF NOT EXISTS / INSERT IGNORE).
--
-- Ejecutar con:
--   & "C:\laragon\bin\mysql\mysql-8.4.3-winx64\bin\mysql.exe" -u root entrega_productos -e "source migraciones/001_usuario_permisos.sql"

-- 1) Tabla intermedia usuario <-> permiso (la pareja es única por ser la llave primaria)
CREATE TABLE IF NOT EXISTS usuario_permisos (
    usuario_id INT NOT NULL,
    permiso_id INT NOT NULL,
    PRIMARY KEY (usuario_id, permiso_id),
    CONSTRAINT fk_usuario_permisos_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE,
    CONSTRAINT fk_usuario_permisos_permiso FOREIGN KEY (permiso_id) REFERENCES permisos (id)
) DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 2) Copiar los permisos actuales de cada rol a los usuarios que tienen ese rol
INSERT IGNORE INTO usuario_permisos (usuario_id, permiso_id)
SELECT u.id, rp.permiso_id
FROM usuarios u
JOIN rol_permiso rp ON rp.rol_id = u.rol_id;
