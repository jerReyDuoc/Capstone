"""HU-40: revisión interna del registro de actividades (modo de auditoría interna del cliente)

  rat_revision            revisiones de la empresa: en curso (lo verificado) o revisada (versión del RAT, huella,
                          fecha, nombre y cargo de quien revisó y la copia de la lista de verificación).
  rat_observacion         observaciones por actividad, elemento o flujo; se cierran al corregir.
  rat_revision_config     plazo de la revisión periódica, aviso previo y recordatorio por correo.
  rat_paquete_evidencia   paquetes de evidencia exportados (código verificable y SHA-256).
  rat_informe.revision_id la revisión que dejó constancia de la versión que reproduce el informe.

En PostgreSQL:
  trg_rat_revision_inmutable       una revisión no se borra; una vez revisada no cambia (solo se le asigna una
                                   vez el informe emitido con la marca).
  trg_rat_observacion_inmutable    una observación no se borra y lo observado (objeto, criterio, texto,
                                   apertura) no cambia.
  trg_rat_paquete_inmutable        un paquete no se borra ni cambia una vez que tiene código.
  trg_rat_informe_inmutable        ahora también protege revision_id.

El rol complianceia_app recibe los permisos por los DEFAULT PRIVILEGES que dejó la migración de HU-09.

Si tu head no es d7e3f1a9b2c4 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: b3e9d5a1c7f4
Revises: d7e3f1a9b2c4
Create Date: 2026-11-13 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3e9d5a1c7f4'
down_revision: Union[str, None] = 'd7e3f1a9b2c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


_INFORME_ANTES = """
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
"""

_INFORME_AHORA = _INFORME_ANTES.replace(
    "       OR NEW.fecha IS DISTINCT FROM OLD.fecha\n",
    "       OR NEW.fecha IS DISTINCT FROM OLD.fecha\n       OR NEW.revision_id IS DISTINCT FROM OLD.revision_id\n")


def upgrade() -> None:
    op.create_table(
        "rat_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=10), nullable=False),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=False),
        sa.Column("iniciada_por_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("verificaciones", sa.JSON(), nullable=False),
        sa.Column("fecha_revision", sa.DateTime(), nullable=True),
        sa.Column("revisado_por_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("revisor_nombre", sa.String(length=120), nullable=True),
        sa.Column("revisor_cargo", sa.String(length=120), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("version_rat", sa.Integer(), nullable=True),
        sa.Column("huella", sa.String(length=64), nullable=True),
        sa.Column("version_mapa", sa.Integer(), nullable=True),
        sa.Column("resumen", sa.JSON(), nullable=False),
        sa.Column("lista", sa.JSON(), nullable=False),
        sa.Column("informe_id", sa.Integer(), nullable=True),     # sin FK: evita el ciclo con rat_informe
        sa.UniqueConstraint("empresa_id", "numero", name="uq_rat_revision_numero"),
        sa.CheckConstraint("estado IN ('en_curso', 'revisada')", name="ck_rat_revision_estado"),
        sa.CheckConstraint("numero >= 1", name="ck_rat_revision_numero"),
        sa.CheckConstraint("estado <> 'revisada' OR (version_rat IS NOT NULL AND huella IS NOT NULL "
                           "AND fecha_revision IS NOT NULL AND revisor_nombre IS NOT NULL)",
                           name="ck_rat_revision_revisada"),
    )
    op.create_index("ix_rat_revision_empresa_id", "rat_revision", ["empresa_id"])
    op.create_index("ux_rat_revision_en_curso", "rat_revision", ["empresa_id"], unique=True,
                    postgresql_where=sa.text("estado = 'en_curso'"), sqlite_where=sa.text("estado = 'en_curso'"))

    op.create_table(
        "rat_observacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("revision_id", sa.Integer(), sa.ForeignKey("rat_revision.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("objeto_tipo", sa.String(length=10), nullable=False),
        sa.Column("objeto_id", sa.Integer(), nullable=True),
        sa.Column("objeto_clave", sa.String(length=40), nullable=False),
        sa.Column("objeto_nombre", sa.String(length=200), nullable=False),
        sa.Column("criterio", sa.String(length=40), nullable=True),
        sa.Column("prioridad", sa.String(length=10), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("estado", sa.String(length=10), nullable=False),
        sa.Column("fecha_apertura", sa.DateTime(), nullable=False),
        sa.Column("abierta_por_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("huella_apertura", sa.String(length=64), nullable=True),
        sa.Column("fecha_cierre", sa.DateTime(), nullable=True),
        sa.Column("cerrada_por_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("nota_cierre", sa.Text(), nullable=True),
        sa.Column("huella_cierre", sa.String(length=64), nullable=True),
        sa.Column("objeto_cambio", sa.Boolean(), nullable=True),
        sa.Column("reaperturas", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("empresa_id", "numero", name="uq_rat_observacion_numero"),
        sa.CheckConstraint("estado IN ('abierta', 'cerrada')", name="ck_rat_observacion_estado"),
        sa.CheckConstraint("prioridad IN ('alta', 'media', 'baja')", name="ck_rat_observacion_prioridad"),
        sa.CheckConstraint("objeto_tipo IN ('actividad', 'elemento', 'flujo', 'registro')",
                           name="ck_rat_observacion_objeto"),
        sa.CheckConstraint("estado <> 'cerrada' OR (fecha_cierre IS NOT NULL AND nota_cierre IS NOT NULL)",
                           name="ck_rat_observacion_cierre"),
    )
    op.create_index("ix_rat_observacion_empresa_id", "rat_observacion", ["empresa_id"])
    op.create_index("ix_rat_observacion_revision_id", "rat_observacion", ["revision_id"])

    op.create_table(
        "rat_revision_config",
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), primary_key=True),
        sa.Column("plazo_meses", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("aviso_dias", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("recordatorio_correo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ultimo_recordatorio", sa.DateTime(), nullable=True),
        sa.Column("etapa_recordatorio", sa.String(length=40), nullable=True),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.CheckConstraint("plazo_meses BETWEEN 1 AND 36", name="ck_rat_revision_config_plazo"),
        sa.CheckConstraint("aviso_dias BETWEEN 0 AND 90", name="ck_rat_revision_config_aviso"),
    )

    op.create_table(
        "rat_paquete_evidencia",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("revision_id", sa.Integer(), sa.ForeignKey("rat_revision.id"), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("huella_manifiesto", sa.String(length=64), nullable=False),
        sa.Column("archivos", sa.Integer(), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.UniqueConstraint("codigo", name="uq_rat_paquete_codigo"),
        sa.UniqueConstraint("sha256", name="uq_rat_paquete_sha256"),
    )
    op.create_index("ix_rat_paquete_evidencia_empresa_id", "rat_paquete_evidencia", ["empresa_id"])

    with op.batch_alter_table("rat_informe") as t:
        t.add_column(sa.Column("revision_id", sa.Integer(), nullable=True))
        t.create_foreign_key("fk_rat_informe_revision", "rat_revision", ["revision_id"], ["id"])

    if _es_postgres():
        op.execute(_INFORME_AHORA)
        op.execute("""
        CREATE OR REPLACE FUNCTION rat_revision_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'rat_revision: una revision interna no se borra (HU-40)';
            END IF;
            IF OLD.estado = 'revisada' THEN
                -- Solo se asigna una vez el informe emitido con la marca
                IF NEW.informe_id IS DISTINCT FROM OLD.informe_id AND OLD.informe_id IS NULL THEN
                    IF (to_jsonb(NEW) - 'informe_id') = (to_jsonb(OLD) - 'informe_id') THEN
                        RETURN NEW;
                    END IF;
                END IF;
                IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
                    RAISE EXCEPTION 'rat_revision: la revision % ya quedo registrada y no se modifica (HU-40)', OLD.id;
                END IF;
            END IF;
            IF NEW.empresa_id IS DISTINCT FROM OLD.empresa_id OR NEW.numero IS DISTINCT FROM OLD.numero
               OR NEW.fecha_inicio IS DISTINCT FROM OLD.fecha_inicio THEN
                RAISE EXCEPTION 'rat_revision: la revision % no cambia de empresa, numero ni inicio (HU-40)', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_rat_revision_inmutable
        BEFORE UPDATE OR DELETE ON rat_revision
        FOR EACH ROW EXECUTE FUNCTION rat_revision_inmutable()
        """)
        op.execute("""
        CREATE OR REPLACE FUNCTION rat_observacion_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'rat_observacion: una observacion de la revision no se borra (HU-40)';
            END IF;
            IF NEW.empresa_id IS DISTINCT FROM OLD.empresa_id OR NEW.revision_id IS DISTINCT FROM OLD.revision_id
               OR NEW.numero IS DISTINCT FROM OLD.numero OR NEW.objeto_tipo IS DISTINCT FROM OLD.objeto_tipo
               OR NEW.objeto_id IS DISTINCT FROM OLD.objeto_id OR NEW.objeto_clave IS DISTINCT FROM OLD.objeto_clave
               OR NEW.objeto_nombre IS DISTINCT FROM OLD.objeto_nombre OR NEW.criterio IS DISTINCT FROM OLD.criterio
               OR NEW.texto IS DISTINCT FROM OLD.texto OR NEW.fecha_apertura IS DISTINCT FROM OLD.fecha_apertura
               OR NEW.huella_apertura IS DISTINCT FROM OLD.huella_apertura THEN
                RAISE EXCEPTION 'rat_observacion: lo observado en % no se modifica (HU-40)', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_rat_observacion_inmutable
        BEFORE UPDATE OR DELETE ON rat_observacion
        FOR EACH ROW EXECUTE FUNCTION rat_observacion_inmutable()
        """)
        op.execute("""
        CREATE OR REPLACE FUNCTION rat_paquete_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'rat_paquete_evidencia: un paquete de evidencia no se borra (HU-40)';
            END IF;
            IF OLD.codigo IS NOT NULL AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
                RAISE EXCEPTION 'rat_paquete_evidencia: el paquete % no se modifica (HU-40)', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_rat_paquete_inmutable
        BEFORE UPDATE OR DELETE ON rat_paquete_evidencia
        FOR EACH ROW EXECUTE FUNCTION rat_paquete_inmutable()
        """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_rat_paquete_inmutable ON rat_paquete_evidencia")
        op.execute("DROP FUNCTION IF EXISTS rat_paquete_inmutable()")
        op.execute("DROP TRIGGER IF EXISTS trg_rat_observacion_inmutable ON rat_observacion")
        op.execute("DROP FUNCTION IF EXISTS rat_observacion_inmutable()")
        op.execute("DROP TRIGGER IF EXISTS trg_rat_revision_inmutable ON rat_revision")
        op.execute("DROP FUNCTION IF EXISTS rat_revision_inmutable()")
        op.execute(_INFORME_ANTES)
    with op.batch_alter_table("rat_informe") as t:
        t.drop_constraint("fk_rat_informe_revision", type_="foreignkey")
        t.drop_column("revision_id")
    op.drop_index("ix_rat_paquete_evidencia_empresa_id", table_name="rat_paquete_evidencia")
    op.drop_table("rat_paquete_evidencia")
    op.drop_table("rat_revision_config")
    op.drop_index("ix_rat_observacion_revision_id", table_name="rat_observacion")
    op.drop_index("ix_rat_observacion_empresa_id", table_name="rat_observacion")
    op.drop_table("rat_observacion")
    op.drop_index("ux_rat_revision_en_curso", table_name="rat_revision")
    op.drop_index("ix_rat_revision_empresa_id", table_name="rat_revision")
    op.drop_table("rat_revision")
