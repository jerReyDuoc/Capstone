"""HU-27: empresa, usuario definitivo, activación, solicitud de contratación y bitácora

Crea:
  - empresa                  razón social, RUT (único), rubro y fechas del contrato
  - usuario_definitivo       uno por empresa, rol único 'cliente', email único, hash de
                             contraseña (NULL hasta activar) y estado
  - token_activacion         enlace de activación de un solo uso (solo el SHA-256)
  - solicitud_contratacion   base mínima de HU-31 (una evaluación por solicitud)
  - bitacora_auditoria       base mínima de HU-09 (solo inserción; trigger en PostgreSQL)
y agrega evaluacion.empresa_id y evaluacion.fecha_migracion.

Si tu head no es a9d3e5f7c1b2 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: b7e4d2a9c6f1
Revises: a9d3e5f7c1b2
Create Date: 2026-10-26 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e4d2a9c6f1'
down_revision: Union[str, None] = 'a9d3e5f7c1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        'empresa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('razon_social', sa.String(length=150), nullable=False),
        sa.Column('rut', sa.String(length=12), nullable=False),
        sa.Column('rubro_id', sa.Integer(), nullable=False),
        sa.Column('fecha_inicio_contrato', sa.Date(), nullable=False),
        sa.Column('fecha_termino_contrato', sa.Date(), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('creada_por_admin_id', sa.Integer(), nullable=True),
        sa.CheckConstraint('fecha_termino_contrato >= fecha_inicio_contrato', name='ck_empresa_fechas_contrato'),
        sa.ForeignKeyConstraint(['rubro_id'], ['rubro.id']),
        sa.ForeignKeyConstraint(['creada_por_admin_id'], ['usuarios_admin.id_admin']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rut'),
    )

    op.create_table(
        'usuario_definitivo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=200), nullable=True),
        sa.Column('rol', sa.String(length=20), nullable=False, server_default='cliente'),
        sa.Column('estado', sa.String(length=25), nullable=False, server_default='pendiente_activacion'),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_activacion', sa.DateTime(), nullable=True),
        sa.Column('ultimo_acceso', sa.DateTime(), nullable=True),
        sa.CheckConstraint("rol = 'cliente'", name='ck_usuario_definitivo_rol'),
        sa.CheckConstraint("estado IN ('pendiente_activacion', 'activo', 'bloqueado')",
                           name='ck_usuario_definitivo_estado'),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresa.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('empresa_id'),   # un usuario por empresa (decisión del PO)
        sa.UniqueConstraint('email'),
    )
    if _es_postgres():
        # El email se guarda en minúsculas; el índice funcional evita duplicados aunque
        # alguien inserte a mano con mayúsculas.
        op.execute('CREATE UNIQUE INDEX uq_usuario_definitivo_email_lower ON usuario_definitivo (lower(email))')

    op.create_table(
        'token_activacion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_definitivo_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_expiracion', sa.DateTime(), nullable=False),
        sa.Column('fecha_uso', sa.DateTime(), nullable=True),
        sa.Column('fecha_revocacion', sa.DateTime(), nullable=True),
        sa.Column('creado_por_admin_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_definitivo_id'], ['usuario_definitivo.id']),
        sa.ForeignKeyConstraint(['creado_por_admin_id'], ['usuarios_admin.id_admin']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_token_activacion_usuario_definitivo_id', 'token_activacion', ['usuario_definitivo_id'])

    op.create_table(
        'solicitud_contratacion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('evaluacion_id', sa.Integer(), nullable=False),
        sa.Column('nombre_contacto', sa.String(length=120), nullable=True),
        sa.Column('email_contacto', sa.String(length=100), nullable=True),
        sa.Column('telefono_contacto', sa.String(length=30), nullable=True),
        sa.Column('razon_social_declarada', sa.String(length=150), nullable=True),
        sa.Column('autoriza_migracion', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('consentimiento_version', sa.String(length=20), nullable=True),
        sa.Column('fecha_autorizacion', sa.DateTime(), nullable=True),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='pendiente'),
        sa.Column('empresa_id', sa.Integer(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_actualizacion', sa.DateTime(), nullable=True),
        sa.Column('fecha_migracion', sa.DateTime(), nullable=True),
        sa.CheckConstraint("estado IN ('pendiente', 'contratada', 'migrada', 'descartada')",
                           name='ck_solicitud_contratacion_estado'),
        sa.ForeignKeyConstraint(['evaluacion_id'], ['evaluacion.id']),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresa.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('evaluacion_id'),
    )

    op.create_table(
        'bitacora_auditoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.Column('actor_rol', sa.String(length=20), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('accion', sa.String(length=60), nullable=False),
        sa.Column('entidad', sa.String(length=40), nullable=False),
        sa.Column('entidad_id', sa.Integer(), nullable=True),
        sa.Column('resultado', sa.String(length=10), nullable=False),
        sa.Column('detalle', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_bitacora_auditoria_fecha', 'bitacora_auditoria', ['fecha'])
    op.create_index('ix_bitacora_auditoria_accion', 'bitacora_auditoria', ['accion'])
    if _es_postgres():
        # Solo inserción: ni la aplicación ni un UPDATE/DELETE manual pueden alterar la bitácora.
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

    op.add_column('evaluacion', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('evaluacion', sa.Column('fecha_migracion', sa.DateTime(), nullable=True))
    op.create_foreign_key('fk_evaluacion_empresa', 'evaluacion', 'empresa', ['empresa_id'], ['id'])
    op.create_index('ix_evaluacion_empresa_id', 'evaluacion', ['empresa_id'])


def downgrade() -> None:
    op.drop_index('ix_evaluacion_empresa_id', table_name='evaluacion')
    op.drop_constraint('fk_evaluacion_empresa', 'evaluacion', type_='foreignkey')
    op.drop_column('evaluacion', 'fecha_migracion')
    op.drop_column('evaluacion', 'empresa_id')

    if _es_postgres():
        op.execute('DROP TRIGGER IF EXISTS trg_bitacora_auditoria_solo_insercion ON bitacora_auditoria')
        op.execute('DROP FUNCTION IF EXISTS bitacora_auditoria_solo_insercion()')
    op.drop_index('ix_bitacora_auditoria_accion', table_name='bitacora_auditoria')
    op.drop_index('ix_bitacora_auditoria_fecha', table_name='bitacora_auditoria')
    op.drop_table('bitacora_auditoria')

    op.drop_table('solicitud_contratacion')
    op.drop_index('ix_token_activacion_usuario_definitivo_id', table_name='token_activacion')
    op.drop_table('token_activacion')
    if _es_postgres():
        op.execute('DROP INDEX IF EXISTS uq_usuario_definitivo_email_lower')
    op.drop_table('usuario_definitivo')
    op.drop_table('empresa')
