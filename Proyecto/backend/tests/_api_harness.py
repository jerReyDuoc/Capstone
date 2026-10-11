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

Este archivo no contiene tests (no empieza con test_).
"""
import os
from contextlib import asynccontextmanager

import httpx

from app.application.filters.control_tree import CONTROLES_BASE, CONTROLES_POR_FILTRO

TODOS_LOS_CONTROLES = sorted(set(CONTROLES_BASE).union(*CONTROLES_POR_FILTRO.values()))
DOMINIOS = {"DAT": (1, "Datos"), "GOB": (2, "Gobernanza"), "RIE": (3, "Riesgos"), "SEG": (4, "Seguridad")}

BASE_URL_LIVE = os.getenv("LATENCIA_BASE_URL")
MODO = "live" if BASE_URL_LIVE else "en_proceso"

# IDs de evaluación usados por las pruebas. En modo live deben existir en la BD
# de PRUEBAS (las pruebas reescriben su filtro y les agregan respuestas).
EVAL_ID = int(os.getenv("LATENCIA_EVALUACION_ID", "1"))
EVAL_NA_ID = int(os.getenv("LATENCIA_EVALUACION_NA_ID", "2"))


class FakeArq:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, nombre, *args, **kwargs):
        self.jobs.append((nombre, args))
        return None


async def _sembrar(Session):
    from app.domain.models import (
        CatalogoBrechas, Dominio, Evaluacion, MatrizControl, PreguntaFiltro,
        Rubro, RutaFormativa, UsuarioTemporal,
    )
    async with Session() as s:
        s.add_all([Dominio(id=i, nombre_dominio=n) for i, n in DOMINIOS.values()])
        s.add(Rubro(id=1, nombre_rubro="Retail"))
        s.add(RutaFormativa(id=1, nombre="Ruta base de gobernanza IA"))
        s.add(CatalogoBrechas(id_brecha=1, codigo_brecha="BR-001", categoria="General",
                              criticidad="alta", ruta_formativa_id=1))
        s.add(UsuarioTemporal(id=1, email="qa@example.com", rubro_id=1))
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
        async with httpx.AsyncClient(base_url=BASE_URL_LIVE, timeout=30) as c:
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
