"""
HU-15 · Agente IA Tutor del panel de formación.

Como Oficial de Cumplimiento o Encargado de Datos, quiero interactuar con un Agente IA
Tutor especializado dentro de cada ruta formativa, para recibir orientaciones paso a paso,
explicaciones normativas adaptadas y recomendaciones contextuales que me permitan cerrar
las brechas de gobernanza identificadas.

  C1  Carga AISLADA del contexto: solo las brechas no conformes (no cumplido y
      parcialmente cumplido) de la evaluación más reciente de LA empresa del token
      (app/application/tutor/contexto_tutor.py). Se recarga en cada mensaje.
  C2  Explicaciones y planes de acción por nivel (Inicial, Intermedio, Avanzado). Por
      defecto el nivel de la ruta (la del módulo desde el que se abrió, o la de la brecha
      más prioritaria); el usuario lo puede cambiar.
  C3  Asistencia conversacional en tiempo real en el panel de formación: respuesta
      síncrona (la UI muestra "escribiendo…"), con la salida ya validada y anclada antes de
      mostrarse.

Reglas:
  - Solo el usuario definitivo con contrato VIGENTE (lo exige la ruta con
    empresa_con_servicio, HU-30).
  - El LLM no toca la BD: este caso de uso carga el contexto, llama al agente (LangGraph)
    y persiste. El agente bloquea el prompt injection ANTES del LLM y del NER.
  - En mensaje_tutor solo queda texto anonimizado (el mismo que vio el LLM; la respuesta
    del tutor se vuelve a anonimizar). Un mensaje bloqueado no guarda su texto.
  - Cuota diaria por empresa (TUTOR_MENSAJES_DIA_EMPRESA, 60 por defecto) + ráfaga por
    minuto + cuota global del LLM. Si el servicio de IA falla, la cuota se devuelve.
  - Toda acción queda en la bitácora (HU-09) sin el texto de los mensajes.

HU-18 (el agente cumple los mismos estándares que el sistema exige a las empresas):
  - El filtro de entrada clasifica el ataque (inyeccion, jailbreak, fuga_prompt,
    delimitadores, codificado, uso_indebido) y bloquea SIN llamar al NER ni al LLM; mira
    también los dos mensajes anteriores del usuario (ataques en varios turnos). Un
    antecedente de la empresa con inyección se omite en vez de bloquear todo.
  - La salida se valida: si filtra el system prompt (canario) se reemplaza por un rechazo.
  - TODA interacción queda en la bitácora inmutable (cadena de hashes): mensajes, bloqueos,
    salidas bloqueadas y también los rechazos (cuota, validación, conversación ajena), con la
    categoría, las entidades enmascaradas y una huella HMAC del mensaje, nunca su texto.
  - Abuso reiterado: desde el TUTOR_BLOQUEOS_ADVERTENCIA-ésimo bloqueo (3) en
    TUTOR_VENTANA_BLOQUEOS_MIN (10) minutos se muestra una advertencia y se alerta al Oficial
    de Cumplimiento con un evento de seguridad. No bloquea el tutor (decisión del equipo, 28-oct).
"""
from app.application.tutor.casos_uso.tutor_ia.casos import TutorIA
from app.application.tutor.casos_uso.tutor_ia.comun import (
    ADVERTENCIA_ABUSO, MAX_TITULO, RESPUESTA_BLOQUEADO, RESPUESTA_ETICA, SUGERENCIAS_BLOQUEO, SUGERENCIAS_ETICA,
    TEXTO_BLOQUEADO_USUARIO, TutorError, _ahora, _iso, _nivel, conversacion_a_dict, mensaje_a_dict, respuesta_de_bloqueo,
)

__all__ = [
    "ADVERTENCIA_ABUSO", "MAX_TITULO", "RESPUESTA_BLOQUEADO", "RESPUESTA_ETICA", "SUGERENCIAS_BLOQUEO",
    "SUGERENCIAS_ETICA", "TEXTO_BLOQUEADO_USUARIO", "TutorError", "TutorIA", "_ahora", "_iso", "_nivel",
    "conversacion_a_dict", "mensaje_a_dict", "respuesta_de_bloqueo",
]
