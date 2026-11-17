"""
Validación de una evidencia (lo ejecuta el worker ARQ).

HU-06 (decisión del PO, 16-oct): el archivo llega CIFRADO desde la API. Aquí se
descifra en memoria, la capa de seguridad revisa el original y la capa de IA lo
anonimiza antes del LLM. Al terminar (con cualquier resultado) el archivo cifrado
se REEMPLAZA por solo el texto anonimizado y se borra: en disco no queda el original.
Si el motor de anonimización falla, el archivo se deja cifrado (nunca en claro).

HU-17: el texto se EXTRAE según el tipo real del archivo (PDF, DOCX o TXT) antes del NER y
del LLM, y se verifican localmente los términos del control. Las evidencias de REMEDIACIÓN
(las que sube la empresa cliente sobre una evaluación ya completada) siguen reglas propias:
nunca bajan un control, no tocan la respuesta si se bloquean por seguridad y, si mejoran el
control, se recalcula el puntaje (resumen y radar) en el mismo proceso.

HU-07: la SALIDA del modelo se verifica antes de usarla (app/application/ai/verificacion_salida_evidencias.py):
formato, afirmaciones sin respaldo en el documento (alucinaciones), fuga de datos personales o del
system prompt y señales de que una inyección llegó al modelo. Con un hallazgo grave el backend no
aplica la propuesta: la pregunta queda para revisión humana (en la remediación, el control no
cambia) y se registra una alerta de seguridad con origen "salida_llm". MODO_VERIFICACION_SALIDA=marcar
solo registra la alerta.
"""
from app.application.evidencias.casos_uso.procesar_evidencia.casos import ProcesarEvidenciaUseCase
from app.application.evidencias.casos_uso.procesar_evidencia.comun import (
    AVISO_VERIFICACION, CONTROL_SIN_CAMBIO, MENSAJE_VERIFICACION, NOMBRE_TEXTO_ANONIMIZADO, PENDIENTE_REVISION,
    RANGO_REMEDIACION, _texto_alerta, logger,
)

__all__ = [
    "AVISO_VERIFICACION", "CONTROL_SIN_CAMBIO", "MENSAJE_VERIFICACION", "NOMBRE_TEXTO_ANONIMIZADO",
    "PENDIENTE_REVISION", "ProcesarEvidenciaUseCase", "RANGO_REMEDIACION", "_texto_alerta", "logger",
]
