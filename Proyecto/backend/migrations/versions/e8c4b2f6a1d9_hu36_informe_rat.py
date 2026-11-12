"""HU-36: informe del registro de actividades de tratamiento (PDF y XLSX)

  rat_informe          una fila por emisión del informe: código verificable, versión del RAT, huella,
                       si salió como borrador, resumen y los documentos guardados en "Mis documentos".
  documento_empresa    admite los tipos rat_pdf y rat_xlsx (además de informe_pdf y borrador).

En PostgreSQL trg_rat_informe_inmutable impide cambiar lo que identifica a una emisión (código una vez
asignado, versión, huella, borrador, fecha y empresa) y borrarla. Sus documentos sí pueden quedar en NULL
(la empresa los elimina de "Mis documentos": ON DELETE SET NULL) y se asignan una sola vez al emitir.

El rol complianceia_app recibe los permisos por los DEFAULT PRIVILEGES que dejó la migración de HU-09.
Sin datos personales: cifras, códigos y huellas.

Si tu head no es d1e5b8a3c7f2 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: e8c4b2f6a1d9
Revises: d1e5b8a3c7f2
Create Date: 2026-11-12 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8c4b2f6a1d9'
down_revision: Union[str, None] = 'd1e5b8a3c7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIPOS_ANTES = "tipo IN ('informe_pdf', 'borrador')"
_TIPOS_AHORA = "tipo IN ('informe_pdf', 'borrador', 'rat_pdf', 'rat_xlsx')"


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table("documento_empresa") as t:
        t.drop_constraint("ck_documento_empresa_tipo", type_="check")
        t.create_check_constraint("ck_documento_empresa_tipo", _TIPOS_AHORA)

    op.create_table(
        "rat_informe",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=True),
        sa.Column("version_rat", sa.Integer(), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=False),
        sa.Column("borrador", sa.Boolean(), nullable=False),
        sa.Column("motivos_borrador", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("codigo", name="uq_rat_informe_codigo"),
        sa.CheckConstraint("version_rat >= 1", name="ck_rat_informe_version"),
        sa.CheckConstraint("actividades >= 0", name="ck_rat_informe_actividades"),
    )
    op.create_index("ix_rat_informe_empresa_id", "rat_informe", ["empresa_id"])

    if _es_postgres():
        op.execute("""
        CREATE OR REPLACE FUNCTION rat_informe_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'rat_informe: una emision del informe del registro no se borra (HU-36)';
            END IF;
            IF NEW.empresa_id IS DISTINCT FROM OLD.empresa_id
               OR NEW.version_rat IS DISTINCT FROM OLD.version_rat
               OR NEW.huella IS DISTINCT FROM OLD.huella
               OR NEW.borrador IS DISTINCT FROM OLD.borrador
               OR NEW.fecha IS DISTINCT FROM OLD.fecha
               OR (OLD.codigo IS NOT NULL AND NEW.codigo IS DISTINCT FROM OLD.codigo) THEN
                RAISE EXCEPTION 'rat_informe: la emision % no se puede modificar (HU-36)', OLD.id;
            END IF;
            IF (OLD.documento_pdf_id IS NOT NULL AND NEW.documento_pdf_id IS NOT NULL
                    AND NEW.documento_pdf_id <> OLD.documento_pdf_id)
               OR (OLD.documento_xlsx_id IS NOT NULL AND NEW.documento_xlsx_id IS NOT NULL
                    AND NEW.documento_xlsx_id <> OLD.documento_xlsx_id) THEN
                RAISE EXCEPTION 'rat_informe: los documentos de la emision % no se reemplazan (HU-36)', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_rat_informe_inmutable
        BEFORE UPDATE OR DELETE ON rat_informe
        FOR EACH ROW EXECUTE FUNCTION rat_informe_inmutable()
        """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_rat_informe_inmutable ON rat_informe")
        op.execute("DROP FUNCTION IF EXISTS rat_informe_inmutable()")
    op.drop_index("ix_rat_informe_empresa_id", table_name="rat_informe")
    op.drop_table("rat_informe")
    # Los documentos del RAT no caben en la restricción anterior: se eliminan antes de restaurarla
    op.execute("DELETE FROM documento_empresa WHERE tipo IN ('rat_pdf', 'rat_xlsx')")
    with op.batch_alter_table("documento_empresa") as t:
        t.drop_constraint("ck_documento_empresa_tipo", type_="check")
        t.create_check_constraint("ck_documento_empresa_tipo", _TIPOS_ANTES)
