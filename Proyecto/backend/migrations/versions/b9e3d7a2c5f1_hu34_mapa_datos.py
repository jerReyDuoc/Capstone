"""HU-34: mapa de datos personales del cliente (base del RAT y del RoPA)

  mapa_datos           uno por empresa: versión vigente (control de edición concurrente), último
                       usuario que lo cambió y sugerencias descartadas.
  mapa_elemento        sistemas, bases de datos y terceros con su tipo, proveedor, país de
                       alojamiento (ISO 3166-1 alfa-2), responsable interno (cargo o área) y las
                       categorías de datos y de titulares del catálogo común con el RAT.
  mapa_flujo           flujos entre elementos (entre sistemas, hacia terceros y transferencias
                       internacionales, que se calculan con el país de cada extremo).
  mapa_datos_version   una fila por cambio con la instantánea completa, su huella SHA-256 y las
                       diferencias. En PostgreSQL un trigger rechaza UPDATE: una versión guardada
                       no se puede alterar (el DELETE queda para una purga por retención, HU-25).

Sin datos de titulares: el mapa guarda CATEGORÍAS, no personas. El rol complianceia_app (HU-09)
recibe los permisos por los DEFAULT PRIVILEGES que dejó esa migración.

Si tu head no es e7c3a9f2b6d4 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: b9e3d7a2c5f1
Revises: e7c3a9f2b6d4
Create Date: 2026-11-11 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9e3d7a2c5f1'
down_revision: Union[str, None] = 'e7c3a9f2b6d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGENES = "('manual', 'plantilla', 'evaluacion')"
_ACCIONES = ("('elemento_creado', 'elemento_editado', 'elemento_eliminado', 'flujo_creado', 'flujo_editado', "
             "'flujo_eliminado', 'plantilla_aplicada', 'sugerencia_aceptada', 'revision_confirmada', "
             "'version_restaurada')")


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "mapa_datos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plantilla_inicial", sa.String(length=30), nullable=True),
        sa.Column("sugerencias_descartadas", sa.JSON(), nullable=True),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("empresa_id", name="uq_mapa_datos_empresa"),
        sa.CheckConstraint("version >= 0", name="ck_mapa_datos_version"),
    )

    op.create_table(
        "mapa_elemento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mapa_id", sa.Integer(), sa.ForeignKey("mapa_datos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("subtipo", sa.String(length=30), nullable=True),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.String(length=500), nullable=True),
        sa.Column("proveedor", sa.String(length=120), nullable=True),
        sa.Column("pais", sa.String(length=2), nullable=True),
        sa.Column("responsable", sa.String(length=120), nullable=True),
        sa.Column("categorias_datos", sa.JSON(), nullable=False),
        sa.Column("categorias_titulares", sa.JSON(), nullable=False),
        sa.Column("nna_declarado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rol_tercero", sa.String(length=20), nullable=True),
        sa.Column("contrato_firmado", sa.Boolean(), nullable=True),
        sa.Column("origen", sa.String(length=15), nullable=False, server_default="manual"),
        sa.Column("clave", sa.String(length=60), nullable=True),
        sa.Column("pendiente_revision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.CheckConstraint("tipo IN ('sistema', 'base_datos', 'tercero')", name="ck_mapa_elemento_tipo"),
        sa.CheckConstraint(f"origen IN {_ORIGENES}", name="ck_mapa_elemento_origen"),
        sa.CheckConstraint("pais IS NULL OR length(pais) = 2", name="ck_mapa_elemento_pais"),
        sa.CheckConstraint("tipo = 'tercero' OR (rol_tercero IS NULL AND contrato_firmado IS NULL)",
                           name="ck_mapa_elemento_rol_solo_tercero"),
        sa.UniqueConstraint("mapa_id", "clave", name="uq_mapa_elemento_clave"),
    )
    op.create_index("ix_mapa_elemento_mapa_id", "mapa_elemento", ["mapa_id"])

    op.create_table(
        "mapa_flujo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mapa_id", sa.Integer(), sa.ForeignKey("mapa_datos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origen_id", sa.Integer(), sa.ForeignKey("mapa_elemento.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destino_id", sa.Integer(), sa.ForeignKey("mapa_elemento.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finalidad", sa.String(length=300), nullable=True),
        sa.Column("categorias_datos", sa.JSON(), nullable=False),
        sa.Column("categorias_titulares", sa.JSON(), nullable=False),
        sa.Column("nna_declarado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("frecuencia", sa.String(length=20), nullable=True),
        sa.Column("medio", sa.String(length=20), nullable=True),
        sa.Column("cifrado", sa.Boolean(), nullable=True),
        sa.Column("garantia", sa.String(length=30), nullable=True),
        sa.Column("origen", sa.String(length=15), nullable=False, server_default="manual"),
        sa.Column("clave", sa.String(length=60), nullable=True),
        sa.Column("pendiente_revision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.CheckConstraint("origen_id <> destino_id", name="ck_mapa_flujo_extremos_distintos"),
        sa.CheckConstraint(f"origen IN {_ORIGENES}", name="ck_mapa_flujo_origen"),
    )
    op.create_index("ix_mapa_flujo_mapa_id", "mapa_flujo", ["mapa_id"])
    op.create_index("ix_mapa_flujo_origen_id", "mapa_flujo", ["origen_id"])
    op.create_index("ix_mapa_flujo_destino_id", "mapa_flujo", ["destino_id"])

    op.create_table(
        "mapa_datos_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mapa_id", sa.Integer(), sa.ForeignKey("mapa_datos.id"), nullable=False),
        sa.Column("empresa_id", sa.Integer(), sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("usuario_definitivo_id", sa.Integer(), sa.ForeignKey("usuario_definitivo.id"), nullable=True),
        sa.Column("accion", sa.String(length=30), nullable=False),
        sa.Column("resumen", sa.String(length=300), nullable=False),
        sa.Column("cambios", sa.JSON(), nullable=False),
        sa.Column("contenido", sa.JSON(), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=False),
        sa.Column("elementos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flujos", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("mapa_id", "numero", name="uq_mapa_datos_version_numero"),
        sa.CheckConstraint(f"accion IN {_ACCIONES}", name="ck_mapa_datos_version_accion"),
        sa.CheckConstraint("numero >= 1", name="ck_mapa_datos_version_numero"),
    )
    op.create_index("ix_mapa_datos_version_mapa_id", "mapa_datos_version", ["mapa_id"])

    if _es_postgres():
        op.execute("""
        CREATE OR REPLACE FUNCTION mapa_datos_version_inalterable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'mapa_datos_version: una versión guardada no se puede modificar (HU-34)';
        END;
        $$ LANGUAGE plpgsql
        """)
        op.execute("""
        CREATE TRIGGER trg_mapa_datos_version_inalterable
        BEFORE UPDATE ON mapa_datos_version
        FOR EACH ROW EXECUTE FUNCTION mapa_datos_version_inalterable()
        """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_mapa_datos_version_inalterable ON mapa_datos_version")
        op.execute("DROP FUNCTION IF EXISTS mapa_datos_version_inalterable()")
    op.drop_index("ix_mapa_datos_version_mapa_id", table_name="mapa_datos_version")
    op.drop_table("mapa_datos_version")
    op.drop_index("ix_mapa_flujo_destino_id", table_name="mapa_flujo")
    op.drop_index("ix_mapa_flujo_origen_id", table_name="mapa_flujo")
    op.drop_index("ix_mapa_flujo_mapa_id", table_name="mapa_flujo")
    op.drop_table("mapa_flujo")
    op.drop_index("ix_mapa_elemento_mapa_id", table_name="mapa_elemento")
    op.drop_table("mapa_elemento")
    op.drop_table("mapa_datos")
