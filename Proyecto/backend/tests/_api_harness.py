"""
Arnés compartido para pruebas a nivel de API REST.

Dos modos:
  * EN PROCESO (por defecto): la app FastAPI real corre dentro de pytest vía
    httpx.ASGITransport, con SQLite en memoria (aiosqlite) en lugar de
    PostgreSQL y un ARQ falso en lugar de Redis. Mide el costo del código de la
    API + ORM, sin red ni motor de BD real.
  * LIVE: si existe la variable LATENCIA_BASE_URL (p.ej. http://127.0.0.1:8000),
    las peticiones van al servidor uvicorn real (PostgreSQL + Redis). Es el modo
    que vale como prueba de aceptación del requisito < 500 ms.

En modo LIVE, además:
  - Antes de medir se consulta GET /health; si el servidor no responde, la prueba
    falla con un mensaje claro en vez de errores de conexión.
  - Con LATENCIA_PREPARAR_BD=1 (por defecto en live) se conecta a PostgreSQL,
    crea las evaluaciones de prueba si no existen y borra sus datos ANTES y
    DESPUÉS de la sesión. Solo toca las evaluaciones LATENCIA_EVALUACION_ID y
    LATENCIA_EVALUACION_NA_ID (por defecto 9001 y 9002).
    La URL se toma de LATENCIA_DATABASE_URL o, si no existe, de DATABASE_URL en
    backend/.env.

Este archivo no contiene tests (no empieza con test_).
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app.application.filters.control_tree import CONTROLES_BASE, CONTROLES_POR_FILTRO

TODOS_LOS_CONTROLES = sorted(set(CONTROLES_BASE).union(*CONTROLES_POR_FILTRO.values()))
DOMINIOS = {"DAT": (1, "Datos"), "GOB": (2, "Gobernanza"), "RIE": (3, "Riesgos"), "SEG": (4, "Seguridad")}

BASE_URL_LIVE = (os.getenv("LATENCIA_BASE_URL") or "").rstrip("/") or None
MODO = "live" if BASE_URL_LIVE else "en_proceso"

# IDs de evaluación usados por las pruebas. En live se usan IDs altos para no
# chocar con evaluaciones reales.
_EVAL_DEF, _EVAL_NA_DEF = ("9001", "9002") if MODO == "live" else ("1", "2")
EVAL_ID = int(os.getenv("LATENCIA_EVALUACION_ID", _EVAL_DEF))
EVAL_NA_ID = int(os.getenv("LATENCIA_EVALUACION_NA_ID", _EVAL_NA_DEF))

PREPARAR_BD = MODO == "live" and os.getenv("LATENCIA_PREPARAR_BD", "1") == "1"
CONSERVAR_DATOS = os.getenv("LATENCIA_CONSERVAR_DATOS") == "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Credenciales del administrador sembrado en modo en proceso (solo pruebas)
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "clave-admin-solo-pruebas"


class FakeArq:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, nombre, *args, **kwargs):
        self.jobs.append((nombre, args))
        return None


# ---------------------------------------------------------------- modo live: BD
def _url_postgres() -> str:
    """URL para asyncpg (sin el '+asyncpg' de SQLAlchemy)."""
    url = os.getenv("LATENCIA_DATABASE_URL")
    if not url:
        env_file = BACKEND_DIR / ".env"
        if env_file.exists():
            for linea in env_file.read_text(encoding="utf-8").splitlines():
                linea = linea.strip()
                if linea.startswith("DATABASE_URL="):
                    url = linea.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not url:
        pytest.fail(
            "Modo live con LATENCIA_PREPARAR_BD=1: no encontré la URL de PostgreSQL. "
            "Define LATENCIA_DATABASE_URL o DATABASE_URL en backend/.env "
            "(o usa LATENCIA_PREPARAR_BD=0 y crea las evaluaciones a mano).",
            pytrace=False,
        )
    return url.replace("postgresql+asyncpg://", "postgresql://")


_SQL_LIMPIAR = [
    # orden respetando claves foráneas
    'DELETE FROM eventos_seguridad WHERE "Evaluacion_id" = ANY($1::int[]) '
    'OR "Respuestas_id_respuesta" IN (SELECT id_respuesta FROM respuestas WHERE "Evaluacion_id" = ANY($1::int[]))',
    'DELETE FROM evidencias WHERE "Respuestas_id_respuesta" IN '
    '(SELECT id_respuesta FROM respuestas WHERE "Evaluacion_id" = ANY($1::int[]))',
    'DELETE FROM resumen WHERE "Evaluacion_id" = ANY($1::int[])',
    'DELETE FROM respuestas WHERE "Evaluacion_id" = ANY($1::int[])',
    'DELETE FROM respuestas_filtro WHERE "Evaluacion_id" = ANY($1::int[])',
]


async def _con_bd(fn):
    try:
        import asyncpg
    except ImportError:
        pytest.fail("Falta asyncpg (pip install -r requirements.txt).", pytrace=False)
    try:
        conn = await asyncpg.connect(_url_postgres(), timeout=10)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"No pude conectar a PostgreSQL para preparar la prueba: {e}. "
                    "¿Está arriba 'docker compose up -d' y el puerto (5433) es correcto?",
                    pytrace=False)
    try:
        return await fn(conn)
    finally:
        await conn.close()


async def limpiar_bd():
    ids = [EVAL_ID, EVAL_NA_ID]

    async def _f(conn):
        async with conn.transaction():
            for sql in _SQL_LIMPIAR:
                await conn.execute(sql, ids)
            await conn.execute(
                "UPDATE evaluacion SET filtro_completado = false, fecha_filtro = NULL "
                "WHERE id = ANY($1::int[])", ids)
    await _con_bd(_f)


async def preparar_bd():
    async def _f(conn):
        for eid in (EVAL_ID, EVAL_NA_ID):
            await conn.execute(
                "INSERT INTO evaluacion (id, fecha_inicio, estado_progreso, filtro_completado) "
                "VALUES ($1, CURRENT_DATE, 'en_progreso', false) ON CONFLICT (id) DO NOTHING", eid)
        n_ctrl = await conn.fetchval("SELECT count(*) FROM matriz_controles")
        n_preg = await conn.fetchval("SELECT count(*) FROM preguntas_filtro WHERE activa")
        if not n_ctrl or not n_preg:
            pytest.fail(f"La BD no tiene semillas (controles={n_ctrl}, preguntas={n_preg}). "
                        "Ejecuta 'alembic upgrade head'.", pytrace=False)
    await _con_bd(_f)
    await limpiar_bd()


async def verificar_servidor():
    try:
        async with httpx.AsyncClient(base_url=BASE_URL_LIVE, timeout=5) as c:
            r = await c.get("/health")
        ok = r.status_code == 200
    except httpx.HTTPError as e:
        ok, r = False, e
    if not ok:
        pytest.fail(
            f"El servidor no responde en {BASE_URL_LIVE}/health ({r}). "
            "Levántalo en otra terminal con: uvicorn app.main:app --port 8000 "
            "(o quita LATENCIA_BASE_URL para usar el modo en proceso).",
            pytrace=False,
        )


# ---------------------------------------------------------------- en proceso: semillas
async def _sembrar(Session):
    from app.domain.models import (
        CatalogoBrechas, Dominio, Evaluacion, MatrizControl, PreguntaFiltro,
        Rubro, RutaFormativa, UsuarioAdmin, UsuarioTemporal,
    )
    from app.core.autenticacion import hash_password
    async with Session() as s:
        s.add_all([Dominio(id=i, nombre_dominio=n) for i, n in DOMINIOS.values()])
        s.add(Rubro(id=1, nombre_rubro="Retail"))
        s.add(RutaFormativa(id=1, nombre="Ruta base de gobernanza IA"))
        s.add(CatalogoBrechas(id_brecha=1, codigo_brecha="BR-001", categoria="General",
                              criticidad="alta", ruta_formativa_id=1))
        s.add(UsuarioTemporal(id=1, email="qa@example.com", rubro_id=1))
        # Segundo titular y un administrador para las pruebas ARCOP (test_solicitudes_arcop.py)
        s.add(UsuarioTemporal(id=2, email="qa2@example.com", rubro_id=1))
        s.add(UsuarioAdmin(id=1, email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD, iteraciones=1000),
                           activo=True, fecha_creacion=datetime(2026, 1, 1)))
        s.add_all([
            Evaluacion(id=i, estado_progreso="en_progreso", usuario_temporal_id=1, filtro_completado=False)
            for i in (EVAL_ID, EVAL_NA_ID)
        ])
        s.add_all([
            PreguntaFiltro(id_pregunta=i, codigo=f"F{i}", orden=i, pregunta=f"Pregunta filtro {i}", activa=True)
            for i in range(1, 8)
        ])
        s.add_all([
            MatrizControl(
                id_control=i + 1, codigo_control=c, dominio_id=DOMINIOS[c[:3]][0],
                catalogo_brechas_id_brecha=1, criticidad="alta",
                pregunta_evaluacion=f"¿Cumple la organización el control {c}?",
            )
            for i, c in enumerate(TODOS_LOS_CONTROLES)
        ])
        await s.commit()


@asynccontextmanager
async def cliente_api():
    """Entrega un httpx.AsyncClient listo, en el modo que corresponda."""
    if MODO == "live":
        await verificar_servidor()
        limites = httpx.Limits(max_connections=200, max_keepalive_connections=50)
        async with httpx.AsyncClient(base_url=BASE_URL_LIVE, timeout=30, limits=limites) as c:
            yield c
        return

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    import app.domain.models  # noqa: F401
    from app.core.database import Base, get_db
    from app.main import app

    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    await _sembrar(Session)

    async def _get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.state.arq = FakeArq()  # ASGITransport no ejecuta el lifespan (Redis)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://qa") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


def body_filtro(todas_si: bool = True) -> dict:
    return {"respuestas": [
        {"codigo": f"F{i}", "respuesta": True if i == 1 else todas_si} for i in range(1, 8)
    ]}
