"""
HU-15 · Agente de IA orquestado con LangGraph.

    START ─▶ guardia ─┬─(bloqueado)─────────────────────────────────────────────▶ END
                      ├─(skill = validar_evidencia)─▶ validar_evidencia ───────────────▶ END
                      └─(skill = tutor)─▶ tutor ─▶ validar_salida ─▶ anclar_contexto ─▶ END

  - HU-18: "guardia" usa el filtro de entrada del agente (categorías de ataque, varios
    turnos, antecedentes neutralizados) y genera el canario; "validar_salida" bloquea la
    respuesta si filtra el system prompt y limpia código, enlaces y contenido fuera de alcance.

  - El router es DETERMINISTA (decisión del PO, 28-oct): la skill la elige el caso de uso,
    no un LLM. No hay llamadas extra para clasificar intenciones.
  - Cada skill llama al AIGateway con su TareaIA: sanitización NER, mapa de entidades,
    prompt versionado, schema y métricas siguen en un solo lugar (R1-R6).
  - El LLM no tiene herramientas: no lee ni escribe la BD. Recibe datos de solo lectura
    que arma la capa de aplicación y devuelve una salida estructurada.
  - Sin checkpointer: el grafo no guarda estado entre ejecuciones. El historial del tutor
    vive en nuestras tablas (mensaje_tutor), ya anonimizado.
"""
from app.application.ai.agente.grafo import AgenteIA, SalidaAgente, SkillIA

__all__ = ["AgenteIA", "SalidaAgente", "SkillIA"]
