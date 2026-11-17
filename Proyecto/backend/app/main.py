import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from arq import create_pool
from arq.connections import RedisSettings

from app.bootstrap import configurar
from app.core.config import settings
from app.api.routes import api_router
from app.api.middleware.fijar_ip_auditoria import ContextoAuditoriaMiddleware

configurar()  # raíz de composición (A-40): a nivel de módulo, no solo en lifespan

logger = logging.getLogger(__name__)


async def _precargar_motor_ner() -> None:
    """T-04: la API anonimiza los extractos de los eventos de seguridad. Si el modelo
    se cargara en esa petición, la primera bloquearía la API ~2 s. Se carga al iniciar
    (en un hilo). No es fatal: sin spaCy la API sigue funcionando como antes."""
    if not settings.SANITIZER_ENABLED:
        return
    try:
        from app.infrastructure.security.pii.sanitizador_ner import cargar_spacy
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
# HU-09: la IP de cada petición queda disponible para el audit_log (criterio 2)
app.add_middleware(ContextoAuditoriaMiddleware)

app.include_router(api_router)

@app.get("/health")
async def health():
    return {"status": "ok"}