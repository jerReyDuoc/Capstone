"""HU-37: informe RoPA desde el registro de actividades (PDF y XLSX)

  ropa_datos           una fila por empresa: contacto de la empresa, delegado de protección de datos y el
                       contacto de cada organización por cuenta de la cual actúa como encargada (un JSON
                       cifrado en reposo con la subclave "ropa" de ENTITY_MAP_KEY).
  ropa_informe         una fila por emisión del informe RoPA: código verificable, versión, huella, partes
                       incluidas, conteos y los documentos guardados en "Mis documentos".
  documento_empresa    admite los tipos ropa_pdf y ropa_xlsx.

En PostgreSQL trg_ropa_informe_inmutable impide cambiar lo que identifica a una emisión (código una vez
asignado, versión, huella, partes, fecha y empresa) y borrarla. Sus documentos sí pueden quedar en NULL
(la empresa los elimina de "Mis documentos": ON DELETE SET NULL) y se asignan una sola vez al emitir.

El rol complianceia_app recibe los permisos por los DEFAULT PRIVILEGES que dejó la migración de HU-09.

Si tu head no es a3f9c1e7b5d2 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: c5e8a2d7f3b1
Revises: a3f9c1e7b5d2
Create Date: 2026-11-13 01:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5e8a2d7f3b1'
down_revision: Union[str, None] = 'a3f9c1e7b5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIPOS_ANTES = "tipo IN ('informe_pdf', 'borrador', 'rat_pdf', 'rat_xlsx')"
_TIPOS_AHORA = "tipo IN ('informe_pdf', 'borrador', 'rat_pdf', 'rat_xlsx', 'ropa_pdf', 'ropa_xlsx')"


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("documento_empresa") as t:
        t.drop_constraint("ck_documento_empresa_tipo", type_="check")
        t.create_check_constraint("ck_documento_empresa_tipo", _TIPOS_AHORA)

    op.create_table(
        "ropa_datos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        # JSON con los datos de contacto, cifrado en reposo (TextoCifradoRopa, prefijo enc:v1:)
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.UniqueConstraint("empresa_id", name="uq_ropa_datos_empresa"),
    )

    op.create_table(
        "ropa_informe",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=False),
        sa.Column("partes", sa.JSON(), nullable=False),
        sa.Column("actividades", sa.Integer(), nullable=False),
        sa.Column("resumen", sa.JSON(), nullable=False),
        sa.Column("versiones", sa.JSON(), nullable=False),
        sa.Column("aviso_version", sa.String(length=30), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("documento_pdf_id", sa.Integer(),
                  sa.ForeignKey("documento_empresa.id", ondelete="SET NULL"), nullable=True),
        sa.Column("documento_xlsx_id", sa.Integer(),
                  sa.ForeignKey("documento_empresa.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("codigo", name="uq_ropa_informe_codigo"),
        sa.CheckConstraint("version >= 1", name="ck_ropa_informe_version"),
        sa.CheckConstraint("actividades >= 0", name="ck_ropa_informe_actividades"),
    )
    op.create_index("ix_ropa_informe_empresa_id", "ropa_informe", ["empresa_id"])

    if _es_postgres():
        op.execute("""
        CREATE OR REPLACE FUNCTION ropa_informe_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'ropa_informe: una emision del informe RoPA no se borra (HU-37)';
            END IF;
            IF NEW.empresa_id IS DISTINCT FROM OLD.empresa_id
               OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.huella IS DISTINCT FROM OLD.huella
               OR NEW.partes::text IS DISTINCT FROM OLD.partes::text
               OR NEW.fecha IS DISTINCT FROM OLD.fecha
               OR (OLD.codigo IS NOT NULL AND NEW.codigo IS DISTINCT FROM OLD.codigo) THEN
                RAISE EXCEPTION 'ropa_informe: la emision % no se puede modificar (HU-37)', OLD.id;
            END IF;
            IF (OLD.documento_pdf_id IS NOT NULL AND NEW.documento_pdf_id IS NOT NULL
                    AND NEW.documento_pdf_id <> OLD.documento_pdf_id)
               OR (OLD.documento_xlsx_id IS NOT NULL AND NEW.documento_xlsx_id IS NOT NULL
                    AND NEW.documento_xlsx_id <> OLD.documento_xlsx_id) THEN
                RAISE EXCEPTION 'ropa_informe: los documentos de la emision % no se reemplazan (HU-37)', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_ropa_informe_inmutable
        BEFORE UPDATE OR DELETE ON ropa_informe
        FOR EACH ROW EXECUTE FUNCTION ropa_informe_inmutable()
        """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_ropa_informe_inmutable ON ropa_informe")
        op.execute("DROP FUNCTION IF EXISTS ropa_informe_inmutable()")
    op.drop_index("ix_ropa_informe_empresa_id", table_name="ropa_informe")
    op.drop_table("ropa_informe")
    op.drop_table("ropa_datos")
    # Los documentos RoPA no caben en la restricción anterior: se eliminan antes de restaurarla
    op.execute("DELETE FROM documento_empresa WHERE tipo IN ('ropa_pdf', 'ropa_xlsx')")
    with op.batch_alter_table("documento_empresa") as t:
        t.drop_constraint("ck_documento_empresa_tipo", type_="check")
        t.create_check_constraint("ck_documento_empresa_tipo", _TIPOS_ANTES)
