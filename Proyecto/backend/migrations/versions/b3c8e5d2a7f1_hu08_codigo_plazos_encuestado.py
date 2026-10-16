"""HU-08: código de seguimiento, plazos legales (prórroga) y acceso del encuestado anónimo

  1. solicitudes_arcop.codigo_seguimiento (ARC-XXXX-XXXX, único). Las solicitudes
     existentes reciben un código al azar.
  2. solicitudes_arcop.Evaluacion_id: el titular puede ser un encuestado anónimo de la
     encuesta pública (sin usuario_temporal). Usuario_temporal_id pasa a ser opcional y
     un CHECK exige exactamente uno de los dos.
  3. solicitudes_arcop.fecha_prorroga: prórroga única del plazo de respuesta.
  4. evaluacion.clave_acceso_hash: hash de la clave con que el encuestado accede.
  5. Las solicitudes ABIERTAS sin fecha límite reciben la del plazo legal por defecto
     (30 días corridos desde su creación; bloqueo: 2 días hábiles).

Revision ID: b3c8e5d2a7f1
Revises: 9a4e2c7b1f05
Create Date: 2026-10-16 15:00:00

"""
import secrets
from datetime import timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c8e5d2a7f1'
down_revision: Union[str, None] = '9a4e2c7b1f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_FINALES = ("resuelta", "rechazada", "cancelada")


def _codigo(usados: set[str]) -> str:
    while True:
        c = "".join(secrets.choice(_ALFABETO) for _ in range(8))
        codigo = f"ARC-{c[:4]}-{c[4:]}"
        if codigo not in usados:
            usados.add(codigo)
            return codigo


def _habiles(desde, dias):
    fecha = desde
    while dias > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            dias -= 1
    return fecha


def upgrade() -> None:
    op.add_column('evaluacion', sa.Column('clave_acceso_hash', sa.String(length=200), nullable=True))

    op.add_column('solicitudes_arcop', sa.Column('codigo_seguimiento', sa.String(length=20), nullable=True))
    op.add_column('solicitudes_arcop', sa.Column('Evaluacion_id', sa.Integer(), nullable=True))
    op.add_column('solicitudes_arcop', sa.Column('fecha_prorroga', sa.DateTime(), nullable=True))

    # Datos existentes: código para todas y plazo legal para las abiertas sin plazo
    conn = op.get_bind()
    filas = conn.execute(sa.text(
        'SELECT id_solicitud, tipo, estado, fecha_creacion, fecha_limite_respuesta FROM solicitudes_arcop'
    )).fetchall()
    usados: set[str] = set()
    for id_solicitud, tipo, estado, creada, limite in filas:
        valores = {"id": id_solicitud, "codigo": _codigo(usados), "limite": limite}
        if limite is None and estado not in _FINALES:
            valores["limite"] = _habiles(creada, 2) if tipo == "bloqueo" else creada + timedelta(days=30)
        conn.execute(sa.text(
            'UPDATE solicitudes_arcop SET codigo_seguimiento = :codigo, fecha_limite_respuesta = :limite '
            'WHERE id_solicitud = :id'
        ), valores)

    op.alter_column('solicitudes_arcop', 'codigo_seguimiento', existing_type=sa.String(length=20), nullable=False)
    op.create_unique_constraint('uq_solicitudes_arcop_codigo_seguimiento', 'solicitudes_arcop', ['codigo_seguimiento'])

    op.alter_column('solicitudes_arcop', 'Usuario_temporal_id', existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key('fk_solicitudes_arcop_evaluacion', 'solicitudes_arcop', 'evaluacion',
                          ['Evaluacion_id'], ['id'])
    op.create_index('ix_solicitudes_arcop_Evaluacion_id', 'solicitudes_arcop', ['Evaluacion_id'], unique=False)
    op.create_check_constraint(
        'ck_solicitudes_arcop_un_titular', 'solicitudes_arcop',
        '("Usuario_temporal_id" IS NULL) <> ("Evaluacion_id" IS NULL)',
    )


def downgrade() -> None:
    # Las solicitudes de encuestados (sin usuario_temporal) no caben en el esquema anterior
    op.execute('DELETE FROM eventos_solicitud_arcop WHERE "Solicitudes_arcop_id_solicitud" IN '
               '(SELECT id_solicitud FROM solicitudes_arcop WHERE "Usuario_temporal_id" IS NULL)')
    op.execute('DELETE FROM solicitudes_arcop WHERE "Usuario_temporal_id" IS NULL')
    op.drop_constraint('ck_solicitudes_arcop_un_titular', 'solicitudes_arcop', type_='check')
    op.drop_index('ix_solicitudes_arcop_Evaluacion_id', table_name='solicitudes_arcop')
    op.drop_constraint('fk_solicitudes_arcop_evaluacion', 'solicitudes_arcop', type_='foreignkey')
    op.alter_column('solicitudes_arcop', 'Usuario_temporal_id', existing_type=sa.Integer(), nullable=False)
    op.drop_constraint('uq_solicitudes_arcop_codigo_seguimiento', 'solicitudes_arcop', type_='unique')
    op.drop_column('solicitudes_arcop', 'fecha_prorroga')
    op.drop_column('solicitudes_arcop', 'Evaluacion_id')
    op.drop_column('solicitudes_arcop', 'codigo_seguimiento')
    op.drop_column('evaluacion', 'clave_acceso_hash')
