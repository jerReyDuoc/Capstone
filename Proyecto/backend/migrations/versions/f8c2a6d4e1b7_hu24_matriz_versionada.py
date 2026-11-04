"""HU-24: matriz normativa editable por el admin, con versionado

  - matriz_version           cada versión con su contenido completo (JSON) y huella SHA-256;
                             estados borrador | publicada | reemplazada (a lo más un borrador
                             y exactamente una publicada, por índices únicos parciales)
  - regla_aplicabilidad      el árbol de aplicabilidad vigente como dato (antes fijo en
                             app/application/filters/control_tree.py)
  - preguntas_filtro.es_compuerta   F1 = compuerta ("¿usa IA?")
  - activo en matriz_controles, catalogo_brechas y ruta_formativa: retirar no borra
  - evaluacion.matriz_version_id    con qué versión se respondió (la fija POST /completar)

Siembra la versión inicial con lo que hoy hay en la BD y el árbol de control_tree.py, y
deja en ella a las evaluaciones ya cerradas (antes de HU-24 la matriz no era editable, así
que es la misma con que se respondieron). Su version_texto se calcula igual que HU-21
("<MATRIZ_VERSION>+<huella>"), así coincide con lo ya impreso en los informes.

En PostgreSQL un trigger impide cambiar el contenido de una versión publicada o reemplazada
y borrarla, también con el rol de la API (HU-09). El rol complianceia_app recibe los
permisos de las tablas nuevas por ALTER DEFAULT PRIVILEGES.

Si tu head no es b6d2f9a4c8e1 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: f8c2a6d4e1b7
Revises: b6d2f9a4c8e1
Create Date: 2026-11-04 12:00:00

"""
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8c2a6d4e1b7'
down_revision: Union[str, None] = 'b6d2f9a4c8e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Copia de la semilla de app/application/filters/control_tree.py (una migración no debe
# cambiar si mañana alguien edita ese archivo).
_CONTROLES_BASE = [
    "DAT-001", "DAT-003", "DAT-004", "DAT-005", "DAT-006", "DAT-010",
    "GOB-001", "GOB-002", "GOB-003", "GOB-004", "GOB-005", "GOB-007",
    "GOB-009", "GOB-010",
    "RIE-001", "RIE-003", "RIE-004", "RIE-008", "RIE-010",
    "SEG-006", "SEG-007", "SEG-009",
]
_CONTROLES_POR_FILTRO = {
    "F2": ["DAT-002", "DAT-009"],
    "F3": ["DAT-007", "DAT-008", "GOB-008", "SEG-008"],
    "F4": ["RIE-002", "SEG-001", "SEG-002", "SEG-005"],
    "F5": ["RIE-009", "SEG-003", "SEG-004"],
    "F6": ["RIE-005", "RIE-006", "SEG-010"],
    "F7": ["RIE-007", "GOB-006"],
}
_COMPUERTAS = ["F1"]


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _offline() -> bool:
    from alembic import context
    return context.is_offline_mode()


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _huella_hu21(filas) -> str:
    """Igual que app/application/informes/ficha.py:huella_matriz (HU-21)."""
    normalizadas = sorted(json.dumps([("" if v is None else str(v)) for v in f], ensure_ascii=False) for f in filas)
    return hashlib.sha256("\n".join(normalizadas).encode("utf-8")).hexdigest()


def upgrade() -> None:
    # ------------------------------------------------------------ 1. columnas nuevas
    for tabla in ("matriz_controles", "catalogo_brechas", "ruta_formativa"):
        op.add_column(tabla, sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("preguntas_filtro", sa.Column("es_compuerta", sa.Boolean(), nullable=False,
                                                server_default=sa.false()))

    # ------------------------------------------------------------ 2. tablas nuevas
    op.create_table(
        "matriz_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("etiqueta", sa.String(length=30), nullable=True),
        sa.Column("estado", sa.String(length=15), nullable=False),
        sa.Column("contenido", sa.JSON(), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=True),
        sa.Column("version_texto", sa.String(length=40), nullable=True),
        sa.Column("nota_cambio", sa.String(length=1000), nullable=True),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("creado_por_admin_id", sa.Integer(), nullable=True),
        sa.Column("publicado_por_admin_id", sa.Integer(), nullable=True),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=False),
        sa.Column("fecha_publicacion", sa.DateTime(), nullable=True),
        sa.CheckConstraint("estado IN ('borrador', 'publicada', 'reemplazada')", name="ck_matriz_version_estado"),
        sa.CheckConstraint("estado = 'borrador' OR (etiqueta IS NOT NULL AND huella IS NOT NULL "
                           "AND version_texto IS NOT NULL)", name="ck_matriz_version_publicada_completa"),
        sa.ForeignKeyConstraint(["base_version_id"], ["matriz_version.id"]),
        sa.ForeignKeyConstraint(["creado_por_admin_id"], ["usuarios_admin.id_admin"]),
        sa.ForeignKeyConstraint(["publicado_por_admin_id"], ["usuarios_admin.id_admin"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("etiqueta", name="uq_matriz_version_etiqueta"),
    )
    op.create_index("ix_matriz_version_estado", "matriz_version", ["estado"], unique=False)
    # Una sola publicada y a lo más un borrador
    op.create_index("uq_matriz_version_una_publicada", "matriz_version", ["estado"], unique=True,
                    postgresql_where=sa.text("estado = 'publicada'"), sqlite_where=sa.text("estado = 'publicada'"))
    op.create_index("uq_matriz_version_un_borrador", "matriz_version", ["estado"], unique=True,
                    postgresql_where=sa.text("estado = 'borrador'"), sqlite_where=sa.text("estado = 'borrador'"))

    op.create_table(
        "regla_aplicabilidad",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("pregunta_filtro_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["control_id"], ["matriz_controles.id_control"]),
        sa.ForeignKeyConstraint(["pregunta_filtro_id"], ["preguntas_filtro.id_pregunta"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("control_id", "pregunta_filtro_id", name="uq_regla_aplicabilidad"),
    )
    op.create_index("ix_regla_aplicabilidad_control_id", "regla_aplicabilidad", ["control_id"], unique=False)

    op.add_column("evaluacion", sa.Column("matriz_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_evaluacion_matriz_version", "evaluacion", "matriz_version",
                          ["matriz_version_id"], ["id"])
    op.create_index("ix_evaluacion_matriz_version_id", "evaluacion", ["matriz_version_id"], unique=False)

    if not _offline():
        _sembrar_version_inicial()

    if _es_postgres():
        _instalar_trigger()


def _sembrar_version_inicial() -> None:
    bind = op.get_bind()
    sql = lambda q, **p: bind.execute(sa.text(q), p)  # noqa: E731

    # ---- compuerta y árbol de control_tree.py
    for codigo in _COMPUERTAS:
        sql("UPDATE preguntas_filtro SET es_compuerta = true WHERE codigo = :c", c=codigo)
    ids_control = {
        fila[1]: fila[0] for fila in sql("SELECT id_control, codigo_control FROM matriz_controles "
                                         "WHERE codigo_control IS NOT NULL").fetchall()
    }
    ids_pregunta = {fila[1]: fila[0] for fila in sql("SELECT id_pregunta, codigo FROM preguntas_filtro").fetchall()}
    reglas: list[tuple[int, int | None]] = []
    for codigo in _CONTROLES_BASE:
        if codigo in ids_control:
            reglas.append((ids_control[codigo], None))
    for filtro, codigos in _CONTROLES_POR_FILTRO.items():
        if filtro not in ids_pregunta:
            continue
        for codigo in codigos:
            if codigo in ids_control:
                reglas.append((ids_control[codigo], ids_pregunta[filtro]))
    for control_id, pregunta_id in reglas:
        sql("INSERT INTO regla_aplicabilidad (control_id, pregunta_filtro_id) VALUES (:c, :p)",
            c=control_id, p=pregunta_id)

    # ---- versión inicial con el contenido actual
    n_controles = sql("SELECT count(*) FROM matriz_controles").scalar() or 0
    if not n_controles:
        return  # BD sin semillas: la primera versión la crea el mantenedor al publicar

    from app.domain.matriz.contenido import construir, huella  # lógica pura, sin BD ni config

    def filas(q):
        return [dict(r._mapping) for r in sql(q).fetchall()]

    contenido = construir(
        dominios=filas("SELECT id, nombre_dominio FROM dominio"),
        rutas=filas("SELECT id, nombre, dominio_id, nivel, objetivo, objetivos_especificos, contenidos, horas, "
                    "modalidad, publico_objetivo, activo FROM ruta_formativa"),
        brechas=filas("SELECT id_brecha, codigo_brecha, categoria, comportamiento_detectado, criticidad, "
                      "accion_sistema, ruta_formativa_id, activo FROM catalogo_brechas"),
        controles=filas("SELECT id_control, codigo_control, framework_fuente, articulo_referencia, tipo_fuente, "
                        "obligacion, pregunta_evaluacion, aplicabilidad, evidencia_esperada, criticidad, "
                        "recomendacion, test_asociado, dominio_id, catalogo_brechas_id_brecha, activo "
                        "FROM matriz_controles"),
        preguntas=filas("SELECT id_pregunta, codigo, orden, pregunta, descripcion, activa, es_compuerta "
                        "FROM preguntas_filtro"),
        reglas=reglas,
    )
    etiqueta = (os.getenv("MATRIZ_VERSION") or "2026.1").strip()[:30] or "2026.1"
    filas_hu21 = sql("SELECT id_control, codigo_control, dominio_id, pregunta_evaluacion, aplicabilidad, "
                     "criticidad, obligacion, catalogo_brechas_id_brecha FROM matriz_controles").fetchall()
    version_texto = f"{etiqueta}+{_huella_hu21(tuple(f) for f in filas_hu21)[:8]}"
    ahora = _ahora()
    tabla = sa.table(
        "matriz_version",
        sa.column("etiqueta"), sa.column("estado"), sa.column("contenido", sa.JSON()), sa.column("huella"),
        sa.column("version_texto"), sa.column("nota_cambio"), sa.column("revision"),
        sa.column("fecha_creacion"), sa.column("fecha_actualizacion"), sa.column("fecha_publicacion"),
    )
    bind.execute(tabla.insert().values(
        etiqueta=etiqueta, estado="publicada", contenido=contenido, huella=huella(contenido),
        version_texto=version_texto, revision=1,
        nota_cambio="Versión inicial: matriz sembrada por las migraciones (HU-24).",
        fecha_creacion=ahora, fecha_actualizacion=ahora, fecha_publicacion=ahora,
    ))
    v1 = sql("SELECT id FROM matriz_version WHERE estado = 'publicada'").scalar()
    sql("UPDATE evaluacion SET matriz_version_id = :v WHERE estado_progreso IN ('completada', 'cerrada')", v=v1)


def _instalar_trigger() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION matriz_version_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.estado <> 'borrador' THEN
                    RAISE EXCEPTION 'HU-24: la version % de la matriz ya se publico y no se puede borrar', OLD.etiqueta;
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.estado <> 'borrador' THEN
                IF NEW.contenido::text IS DISTINCT FROM OLD.contenido::text
                   OR NEW.huella IS DISTINCT FROM OLD.huella
                   OR NEW.etiqueta IS DISTINCT FROM OLD.etiqueta
                   OR NEW.version_texto IS DISTINCT FROM OLD.version_texto THEN
                    RAISE EXCEPTION 'HU-24: la version % de la matriz ya se publico: su contenido no cambia', OLD.etiqueta;
                END IF;
                IF OLD.estado = 'reemplazada' AND NEW.estado <> 'reemplazada' THEN
                    RAISE EXCEPTION 'HU-24: una version reemplazada no vuelve a publicarse (crea un borrador desde ella)';
                END IF;
                IF NEW.estado = 'borrador' THEN
                    RAISE EXCEPTION 'HU-24: una version publicada no vuelve a borrador';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_matriz_version_inmutable
        BEFORE UPDATE OR DELETE ON matriz_version
        FOR EACH ROW EXECUTE FUNCTION matriz_version_inmutable()
    """)


def downgrade() -> None:
    if _es_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_matriz_version_inmutable ON matriz_version")
        op.execute("DROP FUNCTION IF EXISTS matriz_version_inmutable()")
    op.drop_index("ix_evaluacion_matriz_version_id", table_name="evaluacion")
    op.drop_constraint("fk_evaluacion_matriz_version", "evaluacion", type_="foreignkey")
    op.drop_column("evaluacion", "matriz_version_id")
    op.drop_index("ix_regla_aplicabilidad_control_id", table_name="regla_aplicabilidad")
    op.drop_table("regla_aplicabilidad")
    op.drop_index("uq_matriz_version_un_borrador", table_name="matriz_version")
    op.drop_index("uq_matriz_version_una_publicada", table_name="matriz_version")
    op.drop_index("ix_matriz_version_estado", table_name="matriz_version")
    op.drop_table("matriz_version")
    op.drop_column("preguntas_filtro", "es_compuerta")
    # Al volver atrás, los elementos retirados reaparecen (las tablas no guardaban el estado)
    for tabla in ("ruta_formativa", "catalogo_brechas", "matriz_controles"):
        op.drop_column(tabla, "activo")
