import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.api.routes import respuestas, evidencias, catalogos, controles, evaluaciones, filtro, reportes, seguridad, metricas_ia, arcop, auth, encuesta_publica, informes
from app.api.routes import contratacion, admin_clientes  # HU-27 (+ bases de HU-31 y HU-09)

logger = logging.getLogger(__name__)


async def _precargar_motor_ner() -> None:
    """T-04: la API anonimiza los extractos de los eventos de seguridad. Si el modelo
    se cargara en esa petición, la primera bloquearía la API ~2 s. Se carga al iniciar
    (en un hilo). No es fatal: sin spaCy la API sigue funcionando como antes."""
    if not settings.SANITIZER_ENABLED:
        return
    try:
        from app.infrastructure.security.ner_sanitizer import cargar_spacy
        await asyncio.to_thread(cargar_spacy)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo precargar el motor NER en la API (%s)", type(e).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    await _precargar_motor_ner()
    yield
    await app.state.arq.close()

app = FastAPI(title="Validador de Evidencias con LLM", lifespan=lifespan)

app.include_router(respuestas.router)
app.include_router(evidencias.router)
app.include_router(catalogos.router)
app.include_router(controles.router)
app.include_router(reportes.router)
app.include_router(evaluaciones.router)
app.include_router(filtro.router)
app.include_router(seguridad.router)
app.include_router(metricas_ia.router)
app.include_router(arcop.router)
app.include_router(auth.router)
app.include_router(encuesta_publica.router)
app.include_router(informes.router)
app.include_router(contratacion.router)
app.include_router(admin_clientes.router)

@app.get("/health")
async def health():
    return {"status": "ok"}