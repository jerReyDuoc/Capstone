"""
HU-39 · Asistente de IA para armar el mapa de datos, el RAT y los informes.

Como Usuario Definitivo (cliente), quiero un agente de IA que me guíe para armar el mapa de datos, el RAT
y los informes, para completarlos sin ser experto en protección de datos y en menos tiempo.

  C1  Entrevista guiada por área (personas, clientes, proveedores, marketing, TI y uso de IA) en lenguaje
      simple (app/application/rat/asistente/banco.py). A partir de cada respuesta propone sistemas, flujos y
      actividades con sus campos pre-llenados.
  C2  Sugiere base de licitud, plazos y nivel de riesgo explicando por qué. Las inconsistencias (dato
      sensible sin base, transferencia sin garantía, actividad sin plazo, flujo sin actividad) y el riesgo
      los CALCULA el backend (app/application/rat/asistente/inconsistencias.py), no el modelo.
  C3  Lee documentos de la empresa (políticas, contratos con proveedores, avisos): extracción y RAG local
      de HU-17, detector con contexto de HU-33 (línea por línea, perfil "evidencia") y NER antes del LLM.
  C4  Human-in-the-Loop: nada entra al mapa ni al RAT sin confirmación. Cada propuesta se acepta (tal cual
      o editada) o se descarta y queda marcada con el modelo, la versión del prompt y la traza. Al aceptar
      se usan los MISMOS casos de uso del mapa (HU-34) y del RAT (HU-35): mismas validaciones, versiones,
      revisión de actividades afectadas y bitácora. Las actividades entran como borrador.
  C5  Mismos guardarraíles que el tutor (HU-18): skill "asistente_rat" del agente con scope locking,
      filtro de entrada (la respuesta se bloquea; el documento y los nombres del mapa se neutralizan línea
      por línea), canario y revisión de la salida, NER del gateway antes del LLM (R1-R6), cuota diaria por
      empresa y bitácora encadenada sin texto (solo huellas, códigos y conteos). NUNCA se envían datos de
      titulares al LLM: además del NER, las preguntas piden procesos (no personas) y un documento con
      demasiadas entidades personales (un listado de personas) se rechaza antes del LLM.
  C6  Sin IA (deshabilitada, caída o sin cuota) la entrevista sigue igual: las respuestas se guardan, se
      ofrecen las sugerencias de la evaluación y las plantillas del mapa (HU-34) y todo se completa a mano
      (misma degradación que HU-16: se avisa por qué y nada se pierde).

Solo el usuario definitivo con contrato VIGENTE (la ruta usa empresa_con_servicio, HU-30).
"""
from app.application.rat.casos_uso.asistente_rat.casos import AsistenteRat
from app.application.rat.casos_uso.asistente_rat.comun import (
    AVISOS, ESTADO_DOCUMENTO_MENSAJE, MAX_MENSAJES_VISTA, MAX_PROPUESTAS_VISTA, MENSAJE_BLOQUEO, MENSAJE_ETICA,
    MENSAJE_FALLA_IA, MENSAJES_FALLA_IA, MIN_CARACTERES_DOCUMENTO, MUESTRA_DENSIDAD, TEXTO_BLOQUEADO, TEXTO_NO_GUARDADO,
    TEXTO_OMITIDA, AsistenteError, documento_a_dict, etiqueta_ia, mensaje_a_dict, propuesta_a_dict, sesion_a_dict,
)
from app.domain.models.asistente import DECIDIDAS

__all__ = [
    "AsistenteRat", "AsistenteError", "AVISOS", "DECIDIDAS", "ESTADO_DOCUMENTO_MENSAJE", "etiqueta_ia",
    "propuesta_a_dict", "mensaje_a_dict", "documento_a_dict", "sesion_a_dict",
]
