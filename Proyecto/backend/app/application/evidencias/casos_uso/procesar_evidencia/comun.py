"""Constantes y helpers compartidos del procesamiento de evidencias."""
import logging

from app.application.ai.verificacion_salida_evidencias import ALUCINACION, FUGA, INYECCION, SINTAXIS
from app.domain.models.respuesta import EstadoClasificacion

logger = logging.getLogger("evidencias")
NOMBRE_TEXTO_ANONIMIZADO = "evidencia_anonimizada.txt"

# HU-07: lo que ve la organización cuando la verificación retiene la propuesta del modelo
MENSAJE_VERIFICACION = {
    ALUCINACION: "El análisis automático incluyó datos que no aparecen en tu documento (por ejemplo, fechas, "
                 "cifras o citas).",
    FUGA: "El análisis automático incluyó información que no debía mostrarse, así que lo ocultamos.",
    INYECCION: "El análisis automático pudo verse influido por instrucciones escritas dentro del documento.",
    SINTAXIS: "El análisis automático llegó con un formato que no pudimos validar.",
}
PENDIENTE_REVISION = " Para cuidar la calidad del resultado, esta pregunta quedó pendiente de revisión por nuestro equipo."
CONTROL_SIN_CAMBIO = " El control conserva su estado actual mientras nuestro equipo revisa la evidencia."
AVISO_VERIFICACION = ("Aviso: al revisar el análisis automático encontramos puntos que nuestro equipo revisará; "
                      "el resultado podría ajustarse.")

# HU-17: orden de "mejora" de un control en la remediación (no_aplica no es una mejora)
RANGO_REMEDIACION = {
    EstadoClasificacion.NO_CUMPLIDO.value: 0,
    EstadoClasificacion.REQUIERE_REVISION.value: 0,
    EstadoClasificacion.PARCIALMENTE_CUMPLIDO.value: 1,
    EstadoClasificacion.CUMPLIDO.value: 2,
}
def _texto_alerta(result) -> str:
    """Lo que dijo el modelo, para el Oficial de Cumplimiento (RegistrarEventoSeguridad lo anonimiza)."""
    conf = getattr(result, "confianza", None)
    conf_txt = f"{conf:.2f}" if isinstance(conf, (int, float)) and not isinstance(conf, bool) else "sin dato"
    return (f"Propuesta de la IA: {getattr(result, 'clasificacion', None)} (confianza {conf_txt}). "
            f"{getattr(result, 'justificacion', '') or ''}")


# T-13: la respuesta cambió mientras se validaba la evidencia; la clasificación de la IA no se aplica
AVISO_RESPUESTA_CAMBIADA = "Tu respuesta cambió mientras revisábamos el documento; vuelve a subirlo."
