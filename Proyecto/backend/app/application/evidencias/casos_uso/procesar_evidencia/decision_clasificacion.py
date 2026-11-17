"""Decisión del backend sobre la clasificación propuesta por el LLM."""
from datetime import date

from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion


class DecisionMixin:
    """Decisión del backend sobre la clasificación propuesta por el LLM."""

    async def _apply_classification_decision(
        self,
        respuesta: Respuesta,
        control,
        evidencia: Evidencia,
        result,
        evidencia_sospechosa: bool = False,
    ) -> None:
        """
        Aplica las reglas de negocio sobre el resultado del LLM.
        Esta es la capa donde el BACKEND decide, no el LLM.
        """
        # Regla 0 (seguridad): evidencia sospechosa + LLM inseguro -> NO se acepta la
        # declaración del usuario (sería justo lo que busca un ataque); queda en revisión.
        if evidencia_sospechosa and result.confianza < settings.UMBRAL_CONFIANZA:
            respuesta.estado_clasificacion_final = EstadoClasificacion.REQUIERE_REVISION.value
            respuesta.fuente_clasificacion = FuenteClasificacion.SEGURIDAD.value
            respuesta.confianza_clasificacion = result.confianza
            respuesta.fecha_validacion = date.today()
            evidencia.estado_validacion = EstadoValidacion.REJECTED.value
            respuesta.sincronizar_brecha(control)
            return

        # Regla 1: Si el LLM no está seguro, fallback al usuario
        if result.confianza < settings.UMBRAL_CONFIANZA:
            respuesta.estado_clasificacion_final = respuesta.estado_clasificacion
            respuesta.fuente_clasificacion = FuenteClasificacion.USUARIO.value
            evidencia.estado_validacion = EstadoValidacion.REJECTED.value
            respuesta.confianza_clasificacion = result.confianza
            respuesta.fecha_validacion = date.today()
            respuesta.sincronizar_brecha(control)
            return

        # Regla 2: El LLM decide la clasificación final
        respuesta.estado_clasificacion_final = result.clasificacion
        respuesta.fuente_clasificacion = FuenteClasificacion.LLM.value
        respuesta.confianza_clasificacion = result.confianza
        respuesta.fecha_validacion = date.today()
        evidencia.estado_validacion = EstadoValidacion.VALIDATED.value

        # Regla 3: BRECHA (regla de negocio, no LLM): se asigna si el estado final es
        # no_cumplido y se quita en cualquier otro (p. ej. una evidencia nueva lo mejora)
        respuesta.sincronizar_brecha(control)
