"""HU-07: verificación de la salida del modelo y retención de la propuesta."""
from datetime import date

from app.application.ai.verificacion_salida_evidencias import ALUCINACION, VerificacionSalida
from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
from app.application.evidencias.casos_uso.procesar_evidencia.comun import (
    logger,
    MENSAJE_VERIFICACION,
    PENDIENTE_REVISION,
    CONTROL_SIN_CAMBIO,
)

class VerificacionMixin:
    """HU-07: verificación de la salida del modelo y retención de la propuesta."""

    # ------------------------------------------------------------------ HU-07
    def _verificar(self, result, contenido: str, justificacion: str, control, brecha,
                   declarado: str | None) -> VerificacionSalida | None:
        """Nunca rompe el flujo: si el verificador falla se registra y se sigue como antes."""
        if self.verificador is None:
            return None
        try:
            return self.verificador(result, evidencia=contenido, justificacion=justificacion, control=control,
                                    brecha=brecha, declarado=declarado)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-07: no se pudo verificar la salida del modelo (%s)", type(e).__name__)
            return None

    @staticmethod
    def _retener(verificacion: VerificacionSalida, result) -> bool:
        """
        ¿La salida tiene un hallazgo que impide usarla? Una alucinación con confianza bajo el
        umbral no se retiene: esa propuesta ya se descarta (fallback a lo declarado). Las fugas,
        las inyecciones y los errores de formato se retienen siempre (la salida se guarda y se ve).
        """
        if not verificacion.bloqueante:
            return False
        if any(h.bloqueante and h.categoria != ALUCINACION for h in verificacion.hallazgos):
            return True
        confianza = getattr(result, "confianza", None)
        return isinstance(confianza, (int, float)) and confianza >= settings.UMBRAL_CONFIANZA

    @staticmethod
    def _retener_propuesta(respuesta: Respuesta, evidencia: Evidencia, control, verificacion: VerificacionSalida,
                           remediacion: bool) -> None:
        """
        La propuesta del modelo no se aplica ni se muestra a la organización (podría ser falsa):
        la evidencia queda rechazada con un mensaje claro y la alerta lleva lo que dijo el modelo.
        En el cuestionario la pregunta queda en 'requiere_revision' (bandeja de revisión humana);
        en la remediación el control no cambia (una evidencia nueva nunca lo baja).
        """
        principal = verificacion.principal
        mensaje = MENSAJE_VERIFICACION.get(principal.categoria, MENSAJE_VERIFICACION[ALUCINACION])
        evidencia.estado_validacion = EstadoValidacion.REJECTED.value
        evidencia.clasificacion_llm = None
        evidencia.confianza = None
        evidencia.justificacion_llm = None
        evidencia.datos_extraidos = None
        evidencia.fecha_procesada = date.today()
        if remediacion:
            evidencia.errores_validacion = [mensaje + CONTROL_SIN_CAMBIO]
            return
        evidencia.errores_validacion = [mensaje + PENDIENTE_REVISION]
        respuesta.estado_clasificacion_final = EstadoClasificacion.REQUIERE_REVISION.value
        respuesta.fuente_clasificacion = FuenteClasificacion.SEGURIDAD.value
        respuesta.confianza_clasificacion = None
        respuesta.fecha_validacion = date.today()
        respuesta.sincronizar_brecha(control)
