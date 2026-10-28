from arq import cron
from arq.connections import RedisSettings
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.llm.factory import (
    crear_anonimizador,
    crear_storage_evidencias,
    crear_validador_evidencias,
)
from app.application.use_cases.process_evidence import ProcessEvidenceUseCase
from app.application.use_cases.generate_resumen import GenerateResumenUseCase
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO
from app.infrastructure.repositories.bitacora_repository import ROL_SISTEMA, Accion, BitacoraRepository
from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase
from app.application.use_cases.aplicar_retencion import AplicarRetencionUseCase
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
from app.infrastructure.security.prompt_guard import ReglasPromptGuard

async def process_evidence_task(ctx, evidencia_id: int):
    # Sesión aparte para métricas/auditoría de IA: un rollback del negocio no las borra.
    async with AsyncSessionLocal() as session, AsyncSessionLocal() as sesion_ia:
        evidencia_repo = EvidenciaRepository(session)
        respuesta_repo = RespuestaRepository(session)
        # HU-06: lee el archivo cifrado y, al terminar, deja solo el texto anonimizado
        storage = crear_storage_evidencias()
        validator = crear_validador_evidencias(sesion_ia)  # capa de Políticas e IA
        guard = ReglasPromptGuard()

        async def recalcular(evaluacion_id: int):
            # HU-17 C3: puntaje global y radar se recalculan con el nuevo estado del control
            resultado = await GenerateResumenUseCase(session).execute(evaluacion_id)
            if settings.BENCHMARK_AL_COMPLETAR:
                # la evaluación ya entra al benchmark de su rubro: se actualiza como al completar
                try:
                    await UpdateBenchmarkUseCase(session).execute()
                except Exception:  # noqa: BLE001 - lo repara el cron de las 02:00
                    await session.rollback()
            return resultado

        async def puntaje_actual(evaluacion_id: int):
            from app.application.use_cases.remediacion import puntaje_general_actual
            return await puntaje_general_actual(session, evaluacion_id)

        async def auditar(evidencia, respuesta):
            BitacoraRepository(session).registrar(
                accion=Accion.REMEDIACION_RESULTADO, entidad="evidencias", entidad_id=evidencia.id_evidencia,
                actor_rol=ROL_SISTEMA,
                resultado=RESULTADO_OK if evidencia.estado_validacion == "validated" else RESULTADO_RECHAZADO,
                detalle={"evaluacion_id": respuesta.evaluacion_id if respuesta else None,
                         "estado_previo": evidencia.estado_previo, "estado_resultante": evidencia.estado_resultante,
                         "estado_validacion": evidencia.estado_validacion,
                         "puntaje_previo": evidencia.puntaje_previo, "puntaje_resultante": evidencia.puntaje_resultante},
            )
            await session.commit()

        use_case = ProcessEvidenceUseCase(
            evidencia_repo, respuesta_repo, storage, validator,
            guard=guard,
            registrar_evento=RegistrarEventoSeguridad(EventoSeguridadRepository(session), guard),
            anonimizador=crear_anonimizador(),
            recalcular=recalcular,
            puntaje_actual=puntaje_actual,
            auditar=auditar,
        )
        await use_case.execute(evidencia_id)

async def update_benchmark_task(ctx):
    """Recalcula la tabla benchmark con las evaluaciones completadas."""
    async with AsyncSessionLocal() as session:
        use_case = UpdateBenchmarkUseCase(session)
        result = await use_case.execute()
        print(f"[benchmark] actualizado: {result}")
        return result

async def aplicar_retencion_task(ctx):
    """T-06: anonimiza los datos personales cuyo plazo de conservación venció.
    Sin RETENCION_* configurados no hace nada (reglas desactivadas)."""
    async with AsyncSessionLocal() as session:
        resultado = await AplicarRetencionUseCase(session, storage=crear_storage_evidencias()).execute()
        return resultado.como_dict()

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
        cron(aplicar_retencion_task, hour=3, minute=0),  # 03:00 UTC diario (T-06)
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_tries = 3
    job_timeout = 300