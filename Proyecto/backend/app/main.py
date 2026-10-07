from contextlib import asynccontextmanager
from fastapi import FastAPI
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.api.routes import respuestas, evidencias, catalogos, controles, evaluaciones, filtro, reportes

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    yield
    await app.state.arq.close()

app = FastAPI(title="Validador de Evidencias con LLM", lifespan=lifespan)

app.include_router(respuestas.router)
app.include_router(evidencias.router)
app.include_router(catalogos.router)
app.include_router(controles.router)
app.include_router(evaluaciones.router)
app.include_router(filtro.router)
app.include_router(reportes.router)

@app.get("/health")
async def health():
    return {"status": "ok"}