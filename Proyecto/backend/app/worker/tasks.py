from arq import cron
from arq.connections import RedisSettings
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.storage.local_storage import LocalFileStorage
from app.infrastructure.llm.factory import crear_validador_evidencias
from app.application.use_cases.process_evidence import ProcessEvidenceUseCase
from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
from app.infrastructure.security.prompt_guard import ReglasPromptGuard

async def process_evidence_task(ctx, evidencia_id: int):
    # Sesión aparte para métricas/auditoría de IA: un rollback del negocio no las borra.
    async with AsyncSessionLocal() as session, AsyncSessionLocal() as sesion_ia:
        evidencia_repo = EvidenciaRepository(session)
        respuesta_repo = RespuestaRepository(session)
        storage = LocalFileStorage()
        validator = crear_validador_evidencias(sesion_ia)  # capa de Políticas e IA
        guard = ReglasPromptGuard()

        use_case = ProcessEvidenceUseCase(
            evidencia_repo, respuesta_repo, storage, validator,
            guard=guard,
            registrar_evento=RegistrarEventoSeguridad(EventoSeguridadRepository(session), guard),
        )
        await use_case.execute(evidencia_id)

async def update_benchmark_task(ctx):
    """Recalcula la tabla benchmark con las evaluaciones completadas."""
    async with AsyncSessionLocal() as session:
        use_case = UpdateBenchmarkUseCase(session)
        result = await use_case.execute()
        print(f"[benchmark] actualizado: {result}")
        return result

async def startup(ctx):
    """Carga el motor NER al iniciar: si falta spaCy/modelo, el worker no arranca
    (mejor fallar al inicio que en cada evidencia)."""
    if settings.SANITIZER_ENABLED:
        from app.infrastructure.security.ner_sanitizer import cargar_spacy
        cargar_spacy()


class WorkerSettings:
    functions = [process_evidence_task]
    on_startup = startup
    cron_jobs = [
        cron(update_benchmark_task, hour=2, minute=0),  # 02:00 UTC diario
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_tries = 3
    job_timeout = 300