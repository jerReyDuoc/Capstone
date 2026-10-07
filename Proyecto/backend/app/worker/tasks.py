from arq import cron
from arq.connections import RedisSettings
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.storage.local_storage import LocalFileStorage
from app.infrastructure.llm.groq_validator import GroqEvidenceValidator
from app.application.use_cases.process_evidence import ProcessEvidenceUseCase
from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase

async def process_evidence_task(ctx, evidencia_id: int):
    async with AsyncSessionLocal() as session:
        evidencia_repo = EvidenciaRepository(session)
        respuesta_repo = RespuestaRepository(session)
        storage = LocalFileStorage()
        validator = GroqEvidenceValidator()

        use_case = ProcessEvidenceUseCase(
            evidencia_repo, respuesta_repo, storage, validator
        )
        await use_case.execute(evidencia_id)

async def update_benchmark_task(ctx):
    """Recalcula la tabla benchmark con las evaluaciones completadas."""
    async with AsyncSessionLocal() as session:
        use_case = UpdateBenchmarkUseCase(session)
        result = await use_case.execute()
        print(f"[benchmark] actualizado: {result}")
        return result

class WorkerSettings:
    functions = [process_evidence_task]
    cron_jobs = [
        cron(update_benchmark_task, hour=2, minute=0),  # 02:00 UTC diario
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_tries = 3
    job_timeout = 300