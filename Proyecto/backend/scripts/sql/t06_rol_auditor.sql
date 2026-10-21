
\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auditor_t06') THEN
        CREATE ROLE auditor_t06 LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
            CONNECTION LIMIT 3;
    END IF;
END
$$;

ALTER ROLE auditor_t06 WITH PASSWORD :clave;
-- La clave vence: la auditoría es una actividad acotada (ajustar la fecha si se extiende).
ALTER ROLE auditor_t06 VALID UNTIL '2026-12-31';

-- Toda sesión del rol es de solo lectura y no puede quedar colgada
ALTER ROLE auditor_t06 SET default_transaction_read_only = on;
ALTER ROLE auditor_t06 SET statement_timeout = '60s';
ALTER ROLE auditor_t06 SET idle_in_transaction_session_timeout = '5min';

-- Permisos mínimos: conectarse, ver el esquema y leer tablas (no secuencias ni funciones)
REVOKE ALL ON DATABASE complaince_db FROM auditor_t06;
GRANT CONNECT ON DATABASE complaince_db TO auditor_t06;
REVOKE CREATE ON SCHEMA public FROM auditor_t06;
GRANT USAGE ON SCHEMA public TO auditor_t06;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO auditor_t06;
-- Las tablas que creen migraciones futuras también quedan legibles
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO auditor_t06;

-- -----------------------------------------------------------------------------
-- Verificación (debe mostrar solo SELECT y default_transaction_read_only=on)
-- -----------------------------------------------------------------------------
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, rolvaliduntil, rolconfig
FROM pg_roles WHERE rolname = 'auditor_t06';

SELECT privilege_type, count(*) AS tablas
FROM information_schema.role_table_grants
WHERE grantee = 'auditor_t06'
GROUP BY privilege_type;
