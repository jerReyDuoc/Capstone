"""Bloqueo preventivo y registro de eventos de seguridad de la evidencia."""
from datetime import date

from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion


class SeguridadMixin:
    """Bloqueo preventivo y registro de eventos de seguridad de la evidencia."""

    async def _bloquear_por_seguridad(
        self, respuesta: Respuesta, evidencia: Evidencia, origen: str, texto: str, control,
        regla: str | None = None,
    ) -> None:
        """
        Posible prompt injection: la evidencia se rechaza sin pasar por el LLM y la
        respuesta queda en 'requiere_revision' (cuenta como 0 puntos en el resumen)
        hasta que el Oficial de Cumplimiento la revise.
        """
        evidencia.estado_validacion = EstadoValidacion.REJECTED.value
        evidencia.clasificacion_llm = None
        evidencia.confianza = None
        evidencia.errores_validacion = [
            f"Bloqueo preventivo: posible prompt injection en la {origen}. "
            "La evidencia no fue enviada al LLM y quedó pendiente de revisión."
        ]
        evidencia.fecha_procesada = date.today()

        respuesta.estado_clasificacion_final = EstadoClasificacion.REQUIERE_REVISION.value
        respuesta.fuente_clasificacion = FuenteClasificacion.SEGURIDAD.value
        respuesta.confianza_clasificacion = None
        respuesta.fecha_validacion = date.today()
        respuesta.sincronizar_brecha(control)
        await self._registrar(respuesta, evidencia, origen, texto, control, regla)

    async def _registrar(self, respuesta, evidencia, origen: str, texto: str, control,
                         regla: str | None = None, tipo: str = "prompt_injection") -> None:
        if self.registrar_evento:
            await self.registrar_evento.execute(
                texto=texto,
                origen=origen,
                evaluacion_id=respuesta.evaluacion_id,
                matriz_control_id=getattr(control, "id_control", None),
                respuesta_id=respuesta.id,
                evidencia_id=evidencia.id_evidencia,
                tipo=tipo,
                regla=regla,
            )
