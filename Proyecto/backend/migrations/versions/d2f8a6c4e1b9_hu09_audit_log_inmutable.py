"""HU-09: audit_log inmutable (append-only), IP obligatoria, sellos por lote y Auditor Externo

  - bitacora_auditoria -> audit_log (RENAME: se conservan filas, cadena HMAC e índices)
  - audit_log.ip + CHECK (NOT VALID) de campos obligatorios: ip, resultado y actor
  - triggers que impiden UPDATE, DELETE y TRUNCATE en audit_log y audit_log_sello
    (el de HU-27 no cubría TRUNCATE: un trigger por fila no se dispara con TRUNCATE)
  - audit_log_sello   sellos SHA-256 por lote (verificación de integridad en lote)
  - usuario_auditor   cuentas del Auditor Externo (rol auditor_externo)
  - sesion_usuario.actor_rol admite 'auditor_externo'
  - rol de PostgreSQL DB_APP_USER (complianceia_app por defecto) con el que se conectan la
    API y el worker: NO es dueño de las tablas y en audit_log/audit_log_sello solo tiene
    SELECT e INSERT (criterio 1: sin permisos UPDATE/DELETE). Las migraciones siguen
    corriendo con el dueño (POSTGRES_USER).

El rol se crea solo si quien migra puede crear roles (superusuario o CREATEROLE). En una BD
administrada sin ese permiso se omite con un aviso: hay que crearlo a mano (ver
Extras/Cambios/backend/CAMBIOS_HU09.md).

Revision ID: d2f8a6c4e1b9
Revises: a7c4e2f9d1b3
Create Date: 2026-11-01 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2f8a6c4e1b9'
down_revision: Union[str, None] = 'a7c4e2f9d1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLAS_INMUTABLES = ("audit_log", "audit_log_sello")


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _offline() -> bool:
    from alembic import context
    return context.is_offline_mode()


def _rol_app() -> tuple[str, str]:
    from app.core.config import settings
    return settings.DB_APP_USER, settings.DB_APP_PASSWORD


def upgrade() -> None:
    # ------------------------------------------------------------ 1. renombrar la tabla
    op.rename_table('bitacora_auditoria', 'audit_log')
    if _es_postgres():
        op.execute('ALTER SEQUENCE IF EXISTS bitacora_auditoria_id_seq RENAME TO audit_log_id_seq')
        op.execute('ALTER INDEX IF EXISTS ix_bitacora_auditoria_fecha RENAME TO ix_audit_log_fecha')
        op.execute('ALTER INDEX IF EXISTS ix_bitacora_auditoria_accion RENAME TO ix_audit_log_accion')
        op.execute('ALTER INDEX IF EXISTS ix_bitacora_auditoria_hash RENAME TO ix_audit_log_hash')
        op.execute('ALTER INDEX IF EXISTS bitacora_auditoria_pkey RENAME TO audit_log_pkey')
        # El trigger de HU-27 se reemplaza por uno con el nombre nuevo (más el de TRUNCATE)
        op.execute('DROP TRIGGER IF EXISTS trg_bitacora_auditoria_solo_insercion ON audit_log')
        op.execute('DROP FUNCTION IF EXISTS bitacora_auditoria_solo_insercion()')

    # ------------------------------------------------------------ 2. IP y campos obligatorios
    with op.batch_alter_table('audit_log') as t:
        t.add_column(sa.Column('ip', sa.String(length=64), nullable=True))
    if _es_postgres():
        # NOT VALID: rigen para toda fila NUEVA. Las filas anteriores a HU-09 no tienen IP y
        # no se pueden (ni deben) modificar: el log es inmutable.
        op.execute("ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_ip_obligatoria "
                   "CHECK (ip IS NOT NULL AND length(ip) > 0) NOT VALID")
        op.execute("ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_resultado "
                   "CHECK (resultado IN ('ok', 'rechazado', 'error', 'omitido')) NOT VALID")
        op.execute("ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_actor "
                   "CHECK (actor_rol IN ('anonimo', 'sistema') OR actor_id IS NOT NULL) NOT VALID")

    # ------------------------------------------------------------ 3. sellos por lote
    op.create_table(
        'audit_log_sello',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('desde_id', sa.Integer(), nullable=False),
        sa.Column('hasta_id', sa.Integer(), nullable=False),
        sa.Column('cantidad', sa.Integer(), nullable=False),
        sa.Column('hash_lote', sa.String(length=64), nullable=False),
        sa.Column('sello_anterior', sa.String(length=64), nullable=False),
        sa.Column('sello', sa.String(length=64), nullable=False),
        sa.Column('firma', sa.String(length=64), nullable=False),
        sa.Column('algoritmo', sa.String(length=20), nullable=False, server_default='sha256-v1'),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('desde_id', name='uq_audit_log_sello_desde'),
        sa.UniqueConstraint('hasta_id', name='uq_audit_log_sello_hasta'),
        sa.UniqueConstraint('sello', name='uq_audit_log_sello_sello'),
        sa.CheckConstraint('hasta_id >= desde_id AND cantidad > 0', name='ck_audit_log_sello_rango'),
    )

    # ------------------------------------------------------------ 4. Auditor Externo
    op.create_table(
        'usuario_auditor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('organizacion', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=200), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_expiracion', sa.DateTime(), nullable=False),
        sa.Column('creado_por_admin_id', sa.Integer(), nullable=True),
        sa.Column('ultimo_acceso', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['creado_por_admin_id'], ['usuarios_admin.id_admin']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    if _es_postgres():
        op.execute('CREATE UNIQUE INDEX uq_usuario_auditor_email_lower ON usuario_auditor (lower(email))')

    with op.batch_alter_table('sesion_usuario') as t:
        t.drop_constraint('ck_sesion_usuario_rol', type_='check')
        t.create_check_constraint('ck_sesion_usuario_rol',
                                  "actor_rol IN ('admin_therion', 'cliente', 'auditor_externo')")

    if not _es_postgres():
        return

    # ------------------------------------------------------------ 5. inmutabilidad (triggers)
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_solo_insercion() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% es de solo inserción (HU-09): % no permitido', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql
    """)
    for tabla in _TABLAS_INMUTABLES:
        op.execute(f"""
            CREATE TRIGGER trg_{tabla}_solo_insercion
            BEFORE UPDATE OR DELETE ON {tabla}
            FOR EACH ROW EXECUTE FUNCTION audit_log_solo_insercion()
        """)
        op.execute(f"""
            CREATE TRIGGER trg_{tabla}_sin_truncate
            BEFORE TRUNCATE ON {tabla}
            FOR EACH STATEMENT EXECUTE FUNCTION audit_log_solo_insercion()
        """)
        op.execute(f'REVOKE UPDATE, DELETE, TRUNCATE ON {tabla} FROM PUBLIC')

    # ------------------------------------------------------------ 6. rol de la aplicación
    if _offline():
        return
    _crear_rol_app()


def _crear_rol_app() -> None:
    bind = op.get_bind()
    usuario, password = _rol_app()
    puede = bind.execute(sa.text(
        "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")).scalar()
    if not puede:
        print(f"[HU-09] AVISO: {bind.execute(sa.text('SELECT current_user')).scalar()} no puede crear roles: "
              f"crea '{usuario}' a mano (ver CAMBIOS_HU09.md). Los triggers de solo inserción ya rigen.")
        return
    dueno = bind.execute(sa.text("SELECT current_user")).scalar()
    if usuario == dueno:
        print(f"[HU-09] AVISO: DB_APP_USER es el mismo dueño de las tablas ({dueno}); no se restringen permisos.")
        return
    bd = bind.execute(sa.text("SELECT current_database()")).scalar()
    q = bind.dialect.identifier_preparer.quote
    rol, base = q(usuario), q(bd)
    existe = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": usuario}).scalar()
    # La contraseña va como literal escapado (CREATE/ALTER ROLE no acepta parámetros)
    literal = "'" + password.replace("'", "''") + "'"
    if existe:
        op.execute(f"ALTER ROLE {rol} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                   f"NOBYPASSRLS PASSWORD {literal}")
    else:
        op.execute(f"CREATE ROLE {rol} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                   f"NOBYPASSRLS PASSWORD {literal}")
    op.execute(f"GRANT CONNECT ON DATABASE {base} TO {rol}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {rol}")
    op.execute(f"REVOKE CREATE ON SCHEMA public FROM {rol}")
    # Todas las tablas actuales: CRUD (sin TRUNCATE, REFERENCES ni TRIGGER)...
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {rol}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {rol}")
    # ...salvo el log inmutable: solo leer y agregar (criterio 1)
    for tabla in _TABLAS_INMUTABLES:
        op.execute(f"REVOKE ALL ON {tabla} FROM {rol}")
        op.execute(f"GRANT SELECT, INSERT ON {tabla} TO {rol}")
    # Las migraciones no son de la app: alembic_version solo se lee (alembic current)
    op.execute(f"REVOKE ALL ON alembic_version FROM {rol}")
    op.execute(f"GRANT SELECT ON alembic_version TO {rol}")
    # Tablas y secuencias que creen migraciones futuras (con este mismo dueño)
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {rol}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {rol}")


def downgrade() -> None:
    if _es_postgres() and not _offline():
        usuario, _ = _rol_app()
        bind = op.get_bind()
        if bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": usuario}).scalar():
            rol = bind.dialect.identifier_preparer.quote(usuario)
            op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {rol}")
            op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {rol}")
            # El rol no se borra (puede tener conexiones abiertas): se le quitan los permisos
            op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {rol}")
            op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {rol}")
    if _es_postgres():
        for tabla in _TABLAS_INMUTABLES:
            op.execute(f'DROP TRIGGER IF EXISTS trg_{tabla}_solo_insercion ON {tabla}')
            op.execute(f'DROP TRIGGER IF EXISTS trg_{tabla}_sin_truncate ON {tabla}')
        op.execute('DROP FUNCTION IF EXISTS audit_log_solo_insercion()')

    op.execute("DELETE FROM sesion_usuario WHERE actor_rol = 'auditor_externo'")
    with op.batch_alter_table('sesion_usuario') as t:
        t.drop_constraint('ck_sesion_usuario_rol', type_='check')
        t.create_check_constraint('ck_sesion_usuario_rol', "actor_rol IN ('admin_therion', 'cliente')")
    if _es_postgres():
        op.execute('DROP INDEX IF EXISTS uq_usuario_auditor_email_lower')
    op.drop_table('usuario_auditor')
    op.drop_table('audit_log_sello')

    if _es_postgres():
        for ck in ("ck_audit_log_ip_obligatoria", "ck_audit_log_resultado", "ck_audit_log_actor"):
            op.execute(f'ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS {ck}')
    with op.batch_alter_table('audit_log') as t:
        t.drop_column('ip')   # la IP se pierde al bajar (la cadena HMAC de esas filas deja de verificar)

    op.rename_table('audit_log', 'bitacora_auditoria')
    if _es_postgres():
        op.execute('ALTER SEQUENCE IF EXISTS audit_log_id_seq RENAME TO bitacora_auditoria_id_seq')
        op.execute('ALTER INDEX IF EXISTS ix_audit_log_fecha RENAME TO ix_bitacora_auditoria_fecha')
        op.execute('ALTER INDEX IF EXISTS ix_audit_log_accion RENAME TO ix_bitacora_auditoria_accion')
        op.execute('ALTER INDEX IF EXISTS ix_audit_log_hash RENAME TO ix_bitacora_auditoria_hash')
        op.execute('ALTER INDEX IF EXISTS audit_log_pkey RENAME TO bitacora_auditoria_pkey')
        op.execute("""
            CREATE OR REPLACE FUNCTION bitacora_auditoria_solo_insercion() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'bitacora_auditoria es de solo inserción (HU-09)';
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER trg_bitacora_auditoria_solo_insercion
            BEFORE UPDATE OR DELETE ON bitacora_auditoria
            FOR EACH ROW EXECUTE FUNCTION bitacora_auditoria_solo_insercion()
        """)
