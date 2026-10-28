"""HU-30: vigencia del contrato de la empresa cliente

  - empresa.estado_contrato               activo | suspendido | terminado (lo fija el admin)
  - empresa.fecha_suspension / motivo_suspension
  - empresa.fecha_terminacion / motivo_terminacion
  - empresa.fecha_actualizacion_contrato
  - solicitudes_arcop.Usuario_definitivo_id   el usuario de la empresa cliente también es
                                              titular ARCOP (derechos disponibles siempre)

Las empresas existentes quedan 'activo': su situación se sigue calculando con sus fechas,
así que nada cambia para ellas al aplicar la migración.

Revision ID: a4c7e2f9d1b3
Revises: e9b4c2d7a1f6
Create Date: 2026-10-28 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4c7e2f9d1b3'
down_revision: Union[str, None] = 'e9b4c2d7a1f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MOTIVOS = "('no_pago', 'solicitud_cliente', 'incumplimiento', 'fin_acuerdo', 'otro')"
_UN_TITULAR_HU08 = '("Usuario_temporal_id" IS NULL) <> ("Evaluacion_id" IS NULL)'
_UN_TITULAR_HU30 = (
    '(CASE WHEN "Usuario_temporal_id" IS NULL THEN 0 ELSE 1 END'
    ' + CASE WHEN "Evaluacion_id" IS NULL THEN 0 ELSE 1 END'
    ' + CASE WHEN "Usuario_definitivo_id" IS NULL THEN 0 ELSE 1 END) = 1'
)


def upgrade() -> None:
    with op.batch_alter_table('empresa') as t:
        t.add_column(sa.Column('estado_contrato', sa.String(length=15), nullable=False, server_default='activo'))
        t.add_column(sa.Column('fecha_suspension', sa.DateTime(), nullable=True))
        t.add_column(sa.Column('motivo_suspension', sa.String(length=20), nullable=True))
        t.add_column(sa.Column('fecha_terminacion', sa.DateTime(), nullable=True))
        t.add_column(sa.Column('motivo_terminacion', sa.String(length=20), nullable=True))
        t.add_column(sa.Column('fecha_actualizacion_contrato', sa.DateTime(), nullable=True))
        t.create_check_constraint('ck_empresa_estado_contrato',
                                  "estado_contrato IN ('activo', 'suspendido', 'terminado')")
        t.create_check_constraint('ck_empresa_motivo_suspension',
                                  f"motivo_suspension IS NULL OR motivo_suspension IN {_MOTIVOS}")
        t.create_check_constraint('ck_empresa_motivo_terminacion',
                                  f"motivo_terminacion IS NULL OR motivo_terminacion IN {_MOTIVOS}")

    with op.batch_alter_table('solicitudes_arcop') as t:
        t.add_column(sa.Column('Usuario_definitivo_id', sa.Integer(), nullable=True))
        t.create_foreign_key('fk_solicitudes_arcop_usuario_definitivo', 'usuario_definitivo',
                             ['Usuario_definitivo_id'], ['id'])
        t.create_index('ix_solicitudes_arcop_Usuario_definitivo_id', ['Usuario_definitivo_id'], unique=False)
        t.drop_constraint('ck_solicitudes_arcop_un_titular', type_='check')
        t.create_check_constraint('ck_solicitudes_arcop_un_titular', _UN_TITULAR_HU30)


def downgrade() -> None:
    # Las solicitudes de usuarios definitivos no caben en el esquema anterior
    op.execute('DELETE FROM eventos_solicitud_arcop WHERE "Solicitudes_arcop_id_solicitud" IN '
               '(SELECT id_solicitud FROM solicitudes_arcop WHERE "Usuario_definitivo_id" IS NOT NULL)')
    op.execute('DELETE FROM solicitudes_arcop WHERE "Usuario_definitivo_id" IS NOT NULL')
    with op.batch_alter_table('solicitudes_arcop') as t:
        t.drop_constraint('ck_solicitudes_arcop_un_titular', type_='check')
        t.create_check_constraint('ck_solicitudes_arcop_un_titular', _UN_TITULAR_HU08)
        t.drop_index('ix_solicitudes_arcop_Usuario_definitivo_id')
        t.drop_constraint('fk_solicitudes_arcop_usuario_definitivo', type_='foreignkey')
        t.drop_column('Usuario_definitivo_id')

    with op.batch_alter_table('empresa') as t:
        t.drop_constraint('ck_empresa_motivo_terminacion', type_='check')
        t.drop_constraint('ck_empresa_motivo_suspension', type_='check')
        t.drop_constraint('ck_empresa_estado_contrato', type_='check')
        t.drop_column('fecha_actualizacion_contrato')
        t.drop_column('motivo_terminacion')
        t.drop_column('fecha_terminacion')
        t.drop_column('motivo_suspension')
        t.drop_column('fecha_suspension')
        t.drop_column('estado_contrato')
