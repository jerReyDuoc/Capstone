"""HU-41: registro de tratamiento de la propia plataforma (RAT y RoPA de ComplianceAI)

  plataforma_informe    una fila por emisión del RAT o del RoPA de la plataforma: código verificable, versión,
                        huella, si es oficial, cifras y los dos archivos (PDF y Excel, cifrados en STORAGE_DIR).
  plataforma_registro   fila única con los datos de contacto de Therion Labs para el RoPA (un JSON cifrado en
                        reposo con la subclave "ropa" de ENTITY_MAP_KEY).

En PostgreSQL trg_plataforma_informe_inmutable impide borrar una emisión y cambiar lo que la identifica
(tipo, versión, huella, oficial y fecha; el código y los archivos, una vez asignados al emitir).

El rol complianceia_app recibe los permisos por los DEFAULT PRIVILEGES que dejó la migración de HU-09.

Si tu head no es c5e8a2d7f3b1 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: d7e3f1a9b2c4
Revises: c5e8a2d7f3b1
Create Date: 2026-11-13 02:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7e3f1a9b2c4'
down_revision: Union[str, None] = 'c5e8a2d7f3b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "plataforma_informe",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(length=10), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=False),
        sa.Column("oficial", sa.Boolean(), nullable=False),
        sa.Column("motivos_borrador", sa.JSON(), nullable=False),
        sa.Column("actividades", sa.Integer(), nullable=False),
        sa.Column("resumen", sa.JSON(), nullable=False),
        sa.Column("aviso_version", sa.String(length=40), nullable=False),
        sa.Column("archivo_pdf", sa.String(length=500), nullable=False),
        sa.Column("archivo_xlsx", sa.String(length=500), nullable=False),
        sa.Column("hash_pdf", sa.String(length=64), nullable=False),
        sa.Column("hash_xlsx", sa.String(length=64), nullable=False),
        sa.Column("nombre_pdf", sa.String(length=120), nullable=False),
        sa.Column("nombre_xlsx", sa.String(length=120), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("emitido_por_admin_id", sa.Integer(), sa.ForeignKey("usuarios_admin.id_admin"), nullable=True),
        sa.UniqueConstraint("codigo", name="uq_plataforma_informe_codigo"),
        sa.CheckConstraint("tipo IN ('rat', 'ropa')", name="ck_plataforma_informe_tipo"),
        sa.CheckConstraint("version >= 1", name="ck_plataforma_informe_version"),
        sa.CheckConstraint("actividades >= 0", name="ck_plataforma_informe_actividades"),
    )
    op.create_index("ix_plataforma_informe_tipo", "plataforma_informe", ["tipo"])

    op.create_table(
        "plataforma_registro",
        sa.Column("id", sa.Integer(), primary_key=True),
        # JSON con los datos de contacto, cifrado en reposo (TextoCifradoRopa, prefijo enc:v1:)
        sa.Column("ropa_datos", sa.Text(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por_admin_id", sa.Integer(), sa.ForeignKey("usuarios_admin.id_admin"), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_plataforma_registro_unica"),
    )

    if _es_postgres():
        op.execute("""
        CREATE OR REPLACE FUNCTION plataforma_informe_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'plataforma_informe: una emision del registro de la plataforma no se borra (HU-41)';
            END IF;
            -- Al emitir, el código y los archivos se asignan juntos una sola vez (la fila nace sin ellos)
            IF NEW.tipo IS DISTINCT FROM OLD.tipo
               OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.huella IS DISTINCT FROM OLD.huella
               OR NEW.oficial IS DISTINCT FROM OLD.oficial
               OR NEW.fecha IS DISTINCT FROM OLD.fecha
               OR (OLD.codigo IS NOT NULL AND (
                      NEW.codigo IS DISTINCT FROM OLD.codigo
                   OR NEW.archivo_pdf IS DISTINCT FROM OLD.archivo_pdf
                   OR NEW.archivo_xlsx IS DISTINCT FROM OLD.archivo_xlsx
                   OR NEW.hash_pdf IS DISTINCT FROM OLD.hash_pdf
                   OR NEW.hash_xlsx IS DISTINCT FROM OLD.hash_xlsx
                   OR NEW.nombre_pdf IS DISTINCT FROM OLD.nombre_pdf
                   OR NEW.nombre_xlsx IS DISTINCT FROM OLD.nombre_xlsx)) THEN
                RAISE EXCEPTION 'plataforma_informe: la emision % no se puede modificar (HU-41)', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_plataforma_informe_inmutable
        BEFORE UPDATE OR DELETE ON plataforma_informe
        FOR EACH ROW EXECUTE FUNCTION plataforma_informe_inmutable()
        """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_plataforma_informe_inmutable ON plataforma_informe")
        op.execute("DROP FUNCTION IF EXISTS plataforma_informe_inmutable()")
    op.drop_table("plataforma_registro")
    op.drop_index("ix_plataforma_informe_tipo", table_name="plataforma_informe")
    op.drop_table("plataforma_informe")
