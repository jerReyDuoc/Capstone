"""HU-35: registro de actividades de tratamiento (RAT) del cliente

  rat_actividad          ficha de trabajo de cada actividad: estado, contenido (JSON con los ids de
                         los elementos y flujos elegidos del mapa de datos de HU-34), completitud,
                         número de la versión vigente y motivos de revisión.
  rat_actividad_version  una fila por cada vez que una actividad queda vigente, con la instantánea
                         completa y su huella SHA-256.

En PostgreSQL:
  - trg_rat_actividad_version_inmutable rechaza UPDATE y DELETE: una versión vigente no se altera
    (mismo patrón que la matriz versionada, HU-24), tampoco con el rol de la API (HU-09).
  - trg_rat_actividad_vigente_inmutable rechaza cambiar el contenido de una actividad mientras está
    vigente (para editarla se abre una nueva versión, que vuelve a borrador).

El rol complianceia_app recibe los permisos por los DEFAULT PRIVILEGES que dejó la migración de HU-09.
Sin datos de titulares: el registro describe ACTIVIDADES y categorías, no personas.

Si tu head no es b9e3d7a2c5f1 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: d1e5b8a3c7f2
Revises: b9e3d7a2c5f1
Create Date: 2026-11-11 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1e5b8a3c7f2'
down_revision: Union[str, None] = 'b9e3d7a2c5f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ESTADOS = "('borrador', 'en_revision', 'vigente', 'archivada')"


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "rat_actividad",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("estado", sa.String(length=15), nullable=False, server_default="borrador"),
        sa.Column("estado_previo", sa.String(length=15), nullable=True),
        sa.Column("contenido", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completitud", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version_vigente", sa.Integer(), nullable=True),
        sa.Column("motivos_revision", sa.JSON(), nullable=False),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_vigencia", sa.DateTime(), nullable=True),
        sa.Column("fecha_archivo", sa.DateTime(), nullable=True),
        sa.CheckConstraint(f"estado IN {_ESTADOS}", name="ck_rat_actividad_estado"),
        sa.CheckConstraint(f"estado_previo IS NULL OR estado_previo IN {_ESTADOS}",
                           name="ck_rat_actividad_estado_previo"),
        sa.CheckConstraint("revision >= 1", name="ck_rat_actividad_revision"),
        sa.CheckConstraint("completitud BETWEEN 0 AND 100", name="ck_rat_actividad_completitud"),
        sa.CheckConstraint("estado <> 'vigente' OR version_vigente IS NOT NULL", name="ck_rat_actividad_vigente"),
    )
    op.create_index("ix_rat_actividad_empresa_id", "rat_actividad", ["empresa_id"])

    op.create_table(
        "rat_actividad_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actividad_id", sa.Integer(), sa.ForeignKey("rat_actividad.id"), nullable=False),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("contenido", sa.JSON(), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=False),
        sa.Column("version_mapa", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resumen", sa.String(length=300), nullable=False),
        sa.Column("cambios", sa.JSON(), nullable=False),
        sa.UniqueConstraint("actividad_id", "numero", name="uq_rat_actividad_version_numero"),
        sa.CheckConstraint("numero >= 1", name="ck_rat_actividad_version_numero"),
    )
    op.create_index("ix_rat_actividad_version_actividad_id", "rat_actividad_version", ["actividad_id"])

    if _es_postgres():
        op.execute("""
        CREATE OR REPLACE FUNCTION rat_actividad_version_inmutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'rat_actividad_version: una version vigente del registro de actividades no se puede modificar ni borrar (HU-35)';
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_rat_actividad_version_inmutable
        BEFORE UPDATE OR DELETE ON rat_actividad_version
        FOR EACH ROW EXECUTE FUNCTION rat_actividad_version_inmutable()
        """)
        op.execute("""
        CREATE OR REPLACE FUNCTION rat_actividad_vigente_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.version_vigente IS NOT NULL THEN
                    RAISE EXCEPTION 'rat_actividad: una actividad que estuvo vigente no se borra (archivala) (HU-35)';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.estado = 'vigente' AND NEW.estado = 'vigente' AND (
                   NEW.contenido::text IS DISTINCT FROM OLD.contenido::text
                OR NEW.nombre IS DISTINCT FROM OLD.nombre
                OR NEW.version_vigente IS DISTINCT FROM OLD.version_vigente) THEN
                RAISE EXCEPTION 'rat_actividad: la actividad % esta vigente; abre una nueva version para editarla (HU-35)', OLD.id;
            END IF;
            IF NEW.version_vigente IS DISTINCT FROM OLD.version_vigente
               AND OLD.version_vigente IS NOT NULL
               AND (NEW.version_vigente IS NULL OR NEW.version_vigente < OLD.version_vigente) THEN
                RAISE EXCEPTION 'rat_actividad: la version vigente de la actividad % no puede retroceder (HU-35)', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_rat_actividad_vigente_inmutable
        BEFORE UPDATE OR DELETE ON rat_actividad
        FOR EACH ROW EXECUTE FUNCTION rat_actividad_vigente_inmutable()
        """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_rat_actividad_vigente_inmutable ON rat_actividad")
        op.execute("DROP FUNCTION IF EXISTS rat_actividad_vigente_inmutable()")
        op.execute("DROP TRIGGER IF EXISTS trg_rat_actividad_version_inmutable ON rat_actividad_version")
        op.execute("DROP FUNCTION IF EXISTS rat_actividad_version_inmutable()")
    op.drop_index("ix_rat_actividad_version_actividad_id", table_name="rat_actividad_version")
    op.drop_table("rat_actividad_version")
    op.drop_index("ix_rat_actividad_empresa_id", table_name="rat_actividad")
    op.drop_table("rat_actividad")
