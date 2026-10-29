"""
Completar (finalizar) una evaluación.

Diferencia con POST /cerrar: /cerrar recalcula el resumen y deja la evaluación
abierta (sirve de vista previa y se puede llamar muchas veces). /completar es el
cierre DEFINITIVO: verifica que el cuestionario esté terminado, genera el resumen
y marca estado_progreso = 'completada' en la misma transacción. Desde ahí la
evaluación no admite respuestas, cambios de filtro ni evidencias, y entra al
benchmark (update_benchmark.py solo cuenta las 'completada').

Condiciones para completar:
  1. La evaluación existe y no está cerrada.
  2. El filtro F1–F7 está completo.
  3. Todos los controles aplicables tienen respuesta.
  4. Ninguna evidencia está pendiente o en proceso de validación por el LLM
     (si no, su resultado llegaría después del cierre y el puntaje quedaría viejo).
  5. HU-02: todo control que el usuario declaró 'requiere_revision' tiene al menos
     una evidencia, porque es el LLM quien lo resuelve con ella (sin evidencia
     quedaría en 0 puntos sin que nadie lo revise).
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.create_respuesta import (
    EvaluacionCerradaError,
    EvaluacionNoEncontradaError,
    FiltroPendienteError,
    RespuestaRechazadaError,
)
from app.application.use_cases.generate_resumen import GenerateResumenUseCase
from app.application.use_cases.progreso_cuestionario import calcular_progreso
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import EstadoClasificacion, Respuesta
from app.infrastructure.cache import catalogo_controles
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository

ESTADO_COMPLETADA = "completada"
_EVIDENCIA_SIN_TERMINAR = (EstadoValidacion.PENDING.value, EstadoValidacion.PROCESSING.value)


class CuestionarioIncompletoError(RespuestaRechazadaError):
    status_code = 409
    codigo = "CUESTIONARIO_INCOMPLETO"


class EvidenciasEnProcesoError(RespuestaRechazadaError):
    status_code = 409
    codigo = "EVIDENCIAS_EN_PROCESO"


class RevisionSinEvidenciaError(RespuestaRechazadaError):
    status_code = 409
    codigo = "REVISION_SIN_EVIDENCIA"


class CompletarEvaluacionUseCase:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, evaluacion_id: int) -> dict:
        # Bloquea la fila de la evaluación hasta el commit: dos /completar
        # simultáneos no generan el resumen dos veces (en SQLite se ignora).
        evaluacion = (await self.session.execute(
            select(Evaluacion).where(Evaluacion.id == evaluacion_id).with_for_update()
        )).scalar_one_or_none()
        if evaluacion is None:
            raise EvaluacionNoEncontradaError(f"Evaluación {evaluacion_id} no encontrada")
        if evaluacion.esta_cerrada:
            raise EvaluacionCerradaError(
                f"La evaluación {evaluacion_id} ya está cerrada ({evaluacion.estado_progreso})"
            )
        if not evaluacion.filtro_completado:
            raise FiltroPendienteError(
                "La evaluación no tiene el filtro de aplicabilidad (F1–F7) completo"
            )

        contexto = await EvaluacionRepository(self.session).get_contexto(evaluacion_id)
        catalogo = await catalogo_controles.obtener(self.session)
        filas = await RespuestaRepository(self.session).list_estado_por_evaluacion(evaluacion_id)
        progreso = calcular_progreso(contexto, catalogo, filas)
        if progreso.controles_pendientes:
            codigos = [p.codigo_control for p in progreso.pendientes]
            muestra = ", ".join(codigos[:5]) + (" …" if len(codigos) > 5 else "")
            raise CuestionarioIncompletoError(
                f"Faltan {len(codigos)} de {progreso.controles_aplicables} controles por "
                f"responder: {muestra}"
            )

        en_proceso = (await self.session.execute(
            select(func.count(Evidencia.id_evidencia))
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .where(
                Respuesta.evaluacion_id == evaluacion_id,
                Evidencia.estado_validacion.in_(_EVIDENCIA_SIN_TERMINAR),
            )
        )).scalar() or 0
        if en_proceso:
            raise EvidenciasEnProcesoError(
                f"Hay {en_proceso} evidencia(s) en validación; espera a que terminen "
                "antes de completar la evaluación"
            )

        revision = {
            r.id_respuesta: r.codigo_control for r in progreso.respondidos
            if r.estado_clasificacion == EstadoClasificacion.REQUIERE_REVISION.value
        }
        if revision:
            con_evidencia = set((await self.session.execute(
                select(Evidencia.respuesta_id).where(Evidencia.respuesta_id.in_(revision)).distinct()
            )).scalars().all())
            sin_evidencia = sorted(c for rid, c in revision.items() if rid not in con_evidencia)
            if sin_evidencia:
                raise RevisionSinEvidenciaError(
                    f"{len(sin_evidencia)} control(es) en 'requiere revisión' no tienen "
                    f"evidencia para que el LLM los clasifique: {', '.join(sin_evidencia)}. "
                    "Sube una evidencia o elige otro estado."
                )

        # El estado se fija antes de generar el resumen: GenerateResumenUseCase hace
        # el único commit, así resumen y estado quedan guardados juntos (o ninguno).
        evaluacion.estado_progreso = ESTADO_COMPLETADA
        # HU-29: fecha del historial de la empresa y de su gráfico de evolución
        evaluacion.fecha_completado = datetime.now(timezone.utc).replace(tzinfo=None)
        resumen = await GenerateResumenUseCase(self.session).execute(evaluacion_id)
        return {
            **resumen,
            "estado_progreso": ESTADO_COMPLETADA,
            "controles_aplicables": progreso.controles_aplicables,
        }
