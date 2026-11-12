import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.api.routes import respuestas, evidencias, catalogos, controles, evaluaciones, filtro, reportes, seguridad, metricas_ia, arcop, auth, encuesta_publica, informes
from app.api.routes import contratacion, admin_clientes  # HU-27 (+ bases de HU-31 y HU-09)
from app.api.routes import cliente  # HU-28: espacio de la empresa del usuario definitivo
from app.api.routes import formacion, remediacion  # HU-26 (módulos formativos) y HU-17 (remediación)
from app.api.routes import tutor  # HU-15: Agente IA Tutor del panel de formación
from app.api.routes import borradores  # HU-16: borradores de cumplimiento adaptados por el Agente IA
from app.api.routes import auditoria  # HU-09: log inmutable para el Auditor Externo
from app.api.routes import admin_matriz  # HU-24: mantenedor de la matriz normativa con versionado
from app.api.routes import admin_rubros  # correcciones 05-11: rubros desde el panel interno
from app.api.routes import admin_revision  # HU-22: bandeja de revisión del Oficial de Cumplimiento
from app.api.routes import admin_retencion  # HU-25: retención de usuarios temporales vencidos
from app.api.routes import mapa_datos  # HU-34: mapa de datos personales (base del RAT y del RoPA)
from app.api.routes import registro_actividades  # HU-35: registro de actividades de tratamiento (RAT)
from app.api.routes import informe_rat  # HU-36: informe del RAT (PDF y XLSX)
from app.api.routes import asistente_rat  # HU-39: asistente de IA para el mapa de datos y el RAT
from app.core.contexto_auditoria import ContextoAuditoriaMiddleware

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
# HU-09: la IP de cada petición queda disponible para el audit_log (criterio 2)
app.add_middleware(ContextoAuditoriaMiddleware)

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
app.include_router(cliente.router)
app.include_router(formacion.router)
app.include_router(remediacion.router)
app.include_router(tutor.router)
app.include_router(borradores.router)
app.include_router(auditoria.router)
app.include_router(auditoria.router_admin)
app.include_router(admin_matriz.router)
app.include_router(admin_rubros.router)
app.include_router(admin_revision.router)
app.include_router(admin_retencion.router)
app.include_router(mapa_datos.router)
app.include_router(registro_actividades.router)
app.include_router(informe_rat.router)
app.include_router(asistente_rat.router)

@app.get("/health")
async def health():
    return {"status": "ok"}