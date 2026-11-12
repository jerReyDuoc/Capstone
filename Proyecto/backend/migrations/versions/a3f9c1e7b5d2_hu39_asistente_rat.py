"""HU-39: asistente de IA para el mapa de datos, el RAT y los informes

  asistente_sesion      entrevista guiada por áreas (banco de preguntas determinista)
  asistente_mensaje     turnos de la entrevista, SOLO texto anonimizado
  asistente_documento   metadatos y huella de los documentos analizados (el archivo no se guarda)
  asistente_propuesta   propuestas de la IA y la decisión del usuario (Human-in-the-Loop), con modelo,
                        versión del prompt y traza de la llamada
  mapa_elemento / mapa_flujo   origen admite 'ia' y se agrega propuesta_ia_id
  rat_actividad         origen ('manual' | 'ia') y propuesta_ia_id

En PostgreSQL trg_asistente_propuesta_decision impide borrar propuestas y modificar una ya decidida
(aceptada, editada o descartada): es la prueba de qué sugirió la IA y qué decidió la persona.

El rol complianceia_app recibe los permisos por los DEFAULT PRIVILEGES que dejó la migración de HU-09.

Si tu head no es e8c4b2f6a1d9 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: a3f9c1e7b5d2
Revises: e8c4b2f6a1d9
Create Date: 2026-11-12 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f9c1e7b5d2'
down_revision: Union[str, None] = 'e8c4b2f6a1d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGENES_ANTES = "origen IN ('manual', 'plantilla', 'evaluacion')"
_ORIGENES_AHORA = "origen IN ('manual', 'plantilla', 'evaluacion', 'ia')"


def _en(valores) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "asistente_sesion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("area_actual", sa.String(length=20), nullable=False),
        sa.Column("paso", sa.Integer(), nullable=False),
        sa.Column("areas_completadas", sa.JSON(), nullable=False),
        sa.Column("estado", sa.String(length=15), nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.CheckConstraint(f"area_actual IN {_en(('personas', 'clientes', 'proveedores', 'marketing', 'ti', 'ia'))}",
                           name="ck_asistente_sesion_area"),
        sa.CheckConstraint("estado IN ('activa', 'cerrada')", name="ck_asistente_sesion_estado"),
        sa.CheckConstraint("paso >= 0", name="ck_asistente_sesion_paso"),
    )
    op.create_index("ix_asistente_sesion_empresa_id", "asistente_sesion", ["empresa_id"])

    op.create_table(
        "asistente_mensaje",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sesion_id", sa.Integer(), sa.ForeignKey("asistente_sesion.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rol", sa.String(length=15), nullable=False),
        sa.Column("area", sa.String(length=20), nullable=True),
        sa.Column("pregunta_codigo", sa.String(length=40), nullable=True),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("bloqueado", sa.Boolean(), nullable=False),
        sa.Column("motivo_bloqueo", sa.String(length=30), nullable=True),
        sa.Column("motivo_sin_ia", sa.String(length=30), nullable=True),
        sa.Column("traza_id", sa.String(length=32), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.CheckConstraint("rol IN ('asistente', 'usuario')", name="ck_asistente_mensaje_rol"),
    )
    op.create_index("ix_asistente_mensaje_sesion_id", "asistente_mensaje", ["sesion_id"])

    op.create_table(
        "asistente_documento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("sesion_id", sa.Integer(), sa.ForeignKey("asistente_sesion.id", ondelete="SET NULL"), nullable=True),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=False),
        sa.Column("tipo_archivo", sa.String(length=5), nullable=False),
        sa.Column("tipo_documento", sa.String(length=25), nullable=False),
        sa.Column("huella_sha256", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("regla_detector", sa.String(length=60), nullable=True),
        sa.Column("lineas_omitidas", sa.Integer(), nullable=False),
        sa.Column("pasajes_total", sa.Integer(), nullable=True),
        sa.Column("pasajes_usados", sa.Integer(), nullable=True),
        sa.Column("entidades_anonimizadas", sa.Integer(), nullable=False),
        sa.Column("motivo_sin_ia", sa.String(length=30), nullable=True),
        sa.Column("traza_id", sa.String(length=32), nullable=True),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.CheckConstraint("tipo_archivo IN ('pdf', 'docx', 'txt')", name="ck_asistente_documento_tipo_archivo"),
        sa.CheckConstraint("tipo_documento IN ('politica', 'contrato_proveedor', 'aviso', 'otro')",
                           name="ck_asistente_documento_tipo"),
        sa.CheckConstraint(
            f"estado IN {_en(('listo', 'bloqueado', 'ilegible', 'rechazado_pii', 'sin_texto', 'sin_ia'))}",
            name="ck_asistente_documento_estado"),
    )
    op.create_index("ix_asistente_documento_empresa_id", "asistente_documento", ["empresa_id"])

    op.create_table(
        "asistente_propuesta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("sesion_id", sa.Integer(), sa.ForeignKey("asistente_sesion.id", ondelete="SET NULL"), nullable=True),
        sa.Column("documento_id", sa.Integer(), sa.ForeignKey("asistente_documento.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("origen", sa.String(length=15), nullable=False),
        sa.Column("area", sa.String(length=20), nullable=True),
        sa.Column("tipo", sa.String(length=15), nullable=False),
        sa.Column("clave", sa.String(length=60), nullable=False),
        sa.Column("estado", sa.String(length=15), nullable=False),
        sa.Column("payload_propuesto", sa.JSON(), nullable=False),
        sa.Column("payload_final", sa.JSON(), nullable=True),
        sa.Column("campos_editados", sa.JSON(), nullable=True),
        sa.Column("explicaciones", sa.JSON(), nullable=False),
        sa.Column("inconsistencias", sa.JSON(), nullable=False),
        sa.Column("riesgo_nivel", sa.String(length=10), nullable=True),
        sa.Column("confianza", sa.String(length=10), nullable=False),
        sa.Column("modelo", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("traza_id", sa.String(length=32), nullable=True),
        sa.Column("version_mapa_base", sa.Integer(), nullable=False),
        sa.Column("entidad_destino", sa.String(length=20), nullable=True),
        sa.Column("entidad_destino_id", sa.Integer(), nullable=True),
        sa.Column("decidido_por", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("fecha_decision", sa.DateTime(), nullable=True),
        sa.Column("motivo_descarte", sa.String(length=20), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.CheckConstraint("origen IN ('entrevista', 'documento', 'sin_ia')", name="ck_asistente_propuesta_origen"),
        sa.CheckConstraint("tipo IN ('elemento', 'flujo', 'actividad')", name="ck_asistente_propuesta_tipo"),
        sa.CheckConstraint(f"estado IN {_en(('sugerida', 'aceptada', 'editada', 'descartada', 'caducada'))}",
                           name="ck_asistente_propuesta_estado"),
        sa.CheckConstraint("confianza IN ('alta', 'media', 'baja')", name="ck_asistente_propuesta_confianza"),
        sa.CheckConstraint("motivo_descarte IS NULL OR motivo_descarte IN ('no_aplica', 'incorrecta', 'duplicada', "
                           "'otro')", name="ck_asistente_propuesta_motivo"),
        sa.CheckConstraint("estado NOT IN ('aceptada', 'editada') OR entidad_destino_id IS NOT NULL",
                           name="ck_asistente_propuesta_destino"),
        sa.UniqueConstraint("empresa_id", "clave", name="uq_asistente_propuesta_clave"),
    )
    op.create_index("ix_asistente_propuesta_empresa_id", "asistente_propuesta", ["empresa_id"])

    for tabla in ("mapa_elemento", "mapa_flujo"):
        with op.batch_alter_table(tabla) as t:
            t.drop_constraint(f"ck_{tabla}_origen", type_="check")
            t.create_check_constraint(f"ck_{tabla}_origen", _ORIGENES_AHORA)
            t.add_column(sa.Column("propuesta_ia_id", sa.Integer(), nullable=True))
            t.create_foreign_key(f"fk_{tabla}_propuesta_ia", "asistente_propuesta", ["propuesta_ia_id"], ["id"],
                                 ondelete="SET NULL")

    with op.batch_alter_table("rat_actividad") as t:
        t.add_column(sa.Column("origen", sa.String(length=10), nullable=False, server_default="manual"))
        t.add_column(sa.Column("propuesta_ia_id", sa.Integer(), nullable=True))
        t.create_check_constraint("ck_rat_actividad_origen", "origen IN ('manual', 'ia')")
        t.create_foreign_key("fk_rat_actividad_propuesta_ia", "asistente_propuesta", ["propuesta_ia_id"], ["id"],
                             ondelete="SET NULL")

    if _es_postgres():
        op.execute("""
        CREATE OR REPLACE FUNCTION asistente_propuesta_decision() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'asistente_propuesta: las propuestas del asistente no se borran (HU-39)';
            END IF;
            IF OLD.estado IN ('aceptada', 'editada', 'descartada') THEN
                -- Una decidida solo admite que se suelten sus referencias (ON DELETE SET NULL)
                IF NEW.estado IS DISTINCT FROM OLD.estado
                   OR NEW.payload_propuesto IS DISTINCT FROM OLD.payload_propuesto
                   OR NEW.payload_final IS DISTINCT FROM OLD.payload_final
                   OR NEW.modelo IS DISTINCT FROM OLD.modelo
                   OR NEW.prompt_version IS DISTINCT FROM OLD.prompt_version
                   OR NEW.entidad_destino_id IS DISTINCT FROM OLD.entidad_destino_id
                   OR NEW.decidido_por IS DISTINCT FROM OLD.decidido_por
                   OR NEW.fecha_decision IS DISTINCT FROM OLD.fecha_decision THEN
                    RAISE EXCEPTION 'asistente_propuesta: una propuesta decidida no se modifica (HU-39)';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
        op.execute("""
        CREATE TRIGGER trg_asistente_propuesta_decision
        BEFORE UPDATE OR DELETE ON asistente_propuesta
        FOR EACH ROW EXECUTE FUNCTION asistente_propuesta_decision();
        """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_asistente_propuesta_decision ON asistente_propuesta")
        op.execute("DROP FUNCTION IF EXISTS asistente_propuesta_decision()")
    with op.batch_alter_table("rat_actividad") as t:
        t.drop_constraint("fk_rat_actividad_propuesta_ia", type_="foreignkey")
        t.drop_constraint("ck_rat_actividad_origen", type_="check")
        t.drop_column("propuesta_ia_id")
        t.drop_column("origen")
    for tabla in ("mapa_elemento", "mapa_flujo"):
        op.execute(f"UPDATE {tabla} SET origen = 'manual' WHERE origen = 'ia'")
        with op.batch_alter_table(tabla) as t:
            t.drop_constraint(f"fk_{tabla}_propuesta_ia", type_="foreignkey")
            t.drop_column("propuesta_ia_id")
            t.drop_constraint(f"ck_{tabla}_origen", type_="check")
            t.create_check_constraint(f"ck_{tabla}_origen", _ORIGENES_ANTES)
    for tabla in ("asistente_propuesta", "asistente_documento", "asistente_mensaje", "asistente_sesion"):
        op.drop_table(tabla)
