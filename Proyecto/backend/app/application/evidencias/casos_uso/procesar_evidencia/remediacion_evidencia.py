"""Remediación de evidencias (HU-17): cierre, rechazo y decisión que solo puede mejorar el control."""
from datetime import date

from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import Respuesta, FuenteClasificacion
from app.application.evidencias.casos_uso.procesar_evidencia.comun import logger, RANGO_REMEDIACION


class RemediacionMixin:
    """Remediación de evidencias (HU-17): cierre, rechazo y decisión que solo puede mejorar el control."""

    async def _cerrar_remediacion(self, evidencia: Evidencia, previo: str | None) -> None:
        """HU-17 C3: si el control mejoró, recalcula el puntaje global y el radar."""
        respuesta = await self.respuesta_repo.get(evidencia.respuesta_id)
        actual = (respuesta.estado_clasificacion_final or respuesta.estado_clasificacion) if respuesta else None
        evidencia.estado_resultante = actual
        await self.evidencia_repo.update(evidencia)
        antes = await self._leer_puntaje(respuesta.evaluacion_id) if respuesta is not None else None
        despues = antes
        if respuesta is not None and actual != previo and self.recalcular is not None:
            try:
                await self.recalcular(respuesta.evaluacion_id)
                despues = await self._leer_puntaje(respuesta.evaluacion_id)
            except Exception as e:  # noqa: BLE001 - el estado ya quedó; el resumen se puede regenerar
                logger.error("HU-17: no se pudo recalcular el resumen de la evaluación %s (%s)",
                             respuesta.evaluacion_id, type(e).__name__)
        if antes is not None or despues is not None:
            evidencia.puntaje_previo, evidencia.puntaje_resultante = antes, despues
            await self.evidencia_repo.update(evidencia)
        if self.auditar is not None:
            try:
                await self.auditar(evidencia, respuesta)
            except Exception as e:  # noqa: BLE001
                logger.error("HU-17: no se pudo auditar la remediación %s (%s)", evidencia.id_evidencia, type(e).__name__)
    async def _leer_puntaje(self, evaluacion_id: int | None) -> float | None:
        if self.puntaje_actual is None or evaluacion_id is None:
            return None
        try:
            return await self.puntaje_actual(evaluacion_id)
        except Exception:  # noqa: BLE001 - es informativo
            return None
    async def _rechazar_remediacion(self, respuesta, evidencia: Evidencia, origen: str, texto: str, control,
                                    regla: str | None = None) -> Evidencia:
        """
        HU-17: posible prompt injection en una remediación. La evidencia se rechaza sin pasar
        por el LLM y se registra el evento, pero la respuesta NO cambia (a diferencia del
        cuestionario, donde queda en revisión): una evidencia nueva nunca baja un control.
        """
        evidencia.estado_validacion = EstadoValidacion.REJECTED.value
        evidencia.clasificacion_llm = None
        evidencia.confianza = None
        evidencia.errores_validacion = [
            f"Bloqueo preventivo: posible prompt injection en la {origen}. La evidencia no fue "
            "enviada al LLM y el control conserva su estado."
        ]
        evidencia.fecha_procesada = date.today()
        await self._registrar(respuesta, evidencia, origen, texto, control, regla)
        return await self.evidencia_repo.update(evidencia)
    @staticmethod
    def _decidir_remediacion(respuesta: Respuesta, control, evidencia: Evidencia, result) -> None:
        """
        HU-17: la evidencia de remediación solo puede MEJORAR el control.

          - LLM inseguro (confianza < UMBRAL_CONFIANZA)  -> rechazada, el control no cambia.
          - LLM clasifica mejor que el estado vigente     -> el control toma esa clasificación
            (fuente llm), se sincroniza la brecha y luego se recalcula el puntaje.
          - igual o peor                                  -> rechazada ("no demuestra avance").
        No hay fallback a la declaración de la empresa: decide el LLM o no cambia nada.
        """
        evidencia.estado_resultante = None
        actual = respuesta.estado_clasificacion_final or respuesta.estado_clasificacion
        if result.confianza < settings.UMBRAL_CONFIANZA:
            evidencia.estado_validacion = EstadoValidacion.REJECTED.value
            evidencia.errores_validacion = list(result.errores or []) + [
                "La IA no tuvo suficiente certeza para cambiar el estado del control. Revisa que la "
                "evidencia muestre lo que pide el control y vuelve a subirla."
            ]
            return
        if RANGO_REMEDIACION.get(result.clasificacion, -1) <= RANGO_REMEDIACION.get(actual, 0):
            evidencia.estado_validacion = EstadoValidacion.REJECTED.value
            evidencia.errores_validacion = list(result.errores or []) + [
                "La evidencia no demuestra un avance respecto del estado actual del control."
            ]
            return
        respuesta.estado_clasificacion_final = result.clasificacion
        respuesta.fuente_clasificacion = FuenteClasificacion.LLM.value
        respuesta.confianza_clasificacion = result.confianza
        respuesta.fecha_validacion = date.today()
        respuesta.sincronizar_brecha(control)
        evidencia.estado_validacion = EstadoValidacion.VALIDATED.value
