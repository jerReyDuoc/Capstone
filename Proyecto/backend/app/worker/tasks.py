from arq import cron, func
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
from app.core.contexto_auditoria import ORIGEN_WORKER, fijar_origen_por_defecto

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

        def auditar_supresion(evidencia):
            BitacoraRepository(session).registrar(
                accion=Accion.EVIDENCIA_ORIGINAL_SUPRIMIDO, entidad="evidencias", entidad_id=evidencia.id_evidencia,
                actor_rol=ROL_SISTEMA, detalle={"motivo": "hu06_solo_texto_anonimizado"},
            )

        use_case = ProcessEvidenceUseCase(
            evidencia_repo, respuesta_repo, storage, validator,
            guard=guard,
            registrar_evento=RegistrarEventoSeguridad(EventoSeguridadRepository(session), guard),
            anonimizador=crear_anonimizador(),
            recalcular=recalcular,
            puntaje_actual=puntaje_actual,
            auditar=auditar,
            auditar_supresion=auditar_supresion,
        )
        await use_case.execute(evidencia_id)

async def update_benchmark_task(ctx):
    """Recalcula la tabla benchmark con las evaluaciones completadas."""
    async with AsyncSessionLocal() as session:
        use_case = UpdateBenchmarkUseCase(session)
        result = await use_case.execute()
        print(f"[benchmark] actualizado: {result}")
        return result

async def aplicar_retencion_task(ctx, origen: str = "cron", admin_id: int | None = None):
    """T-06 / HU-25: anonimiza los datos personales cuyo plazo de conservación venció.

    Lo corre el cron diario (origen "cron") y, cuando el Oficial de Privacidad pide una
    ejecución desde /admin/retencion, la API la encola con origen "manual" y su id (queda
    como actor en el audit_log). Sin plazos configurados no anonimiza nada, pero la
    ejecución igual queda registrada (HU-25 criterio 3)."""
    from app.core.autenticacion import Actor, Rol
    actor = Actor(id=admin_id, rol=Rol.ADMIN_THERION.value) if origen == "manual" and admin_id else None
    async with AsyncSessionLocal() as session:
        resultado = await AplicarRetencionUseCase(
            session, storage=crear_storage_evidencias(), origen=origen, actor=actor,
        ).execute()
        return resultado.como_dict()

async def sellar_audit_log_task(ctx):
    """HU-09 criterio 3: sella en lotes (hash SHA-256 encadenado) las filas nuevas del audit_log."""
    from app.infrastructure.repositories.audit_log_lotes import sellar_pendientes
    async with AsyncSessionLocal() as session:
        nuevos = await sellar_pendientes(session)
        await session.commit()
        return {"lotes_sellados": len(nuevos), "hasta_id": nuevos[-1].hasta_id if nuevos else None}


async def startup(ctx):
    """Carga el motor NER al iniciar: si falta spaCy/modelo, el worker no arranca
    (mejor fallar al inicio que en cada evidencia)."""
    # HU-09: lo que el worker registre fuera de una petición HTTP queda con origen "sistema:worker"
    fijar_origen_por_defecto(ORIGEN_WORKER)
    if settings.SANITIZER_ENABLED:
        from app.infrastructure.security.ner_sanitizer import cargar_spacy
        cargar_spacy()


class WorkerSettings:
    # HU-25: aplicar_retencion_task también se encola a mano (con un timeout más largo). La API
    # la encola con un id fijo para no acumular duplicados; keep_result=0 libera ese id al
    # terminar (el resultado ya queda en el audit_log).
    functions = [process_evidence_task,
                 func(aplicar_retencion_task, timeout=settings.RETENCION_TIMEOUT_S, keep_result=0)]
    on_startup = startup
    cron_jobs = [
        cron(update_benchmark_task, hour=2, minute=0),  # 02:00 UTC diario
        # T-06 / HU-25: diario a RETENCION_HORA_UTC (03:00 UTC por defecto); unique evita duplicados
        cron(aplicar_retencion_task, hour=settings.RETENCION_HORA_UTC, minute=0,
             timeout=settings.RETENCION_TIMEOUT_S, unique=True),
        # HU-09: sellado por lote del audit_log cada AUDIT_SELLO_CADA_MIN minutos
        cron(sellar_audit_log_task, minute=set(range(0, 60, settings.AUDIT_SELLO_CADA_MIN)), run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_tries = 3
    job_timeout = 300