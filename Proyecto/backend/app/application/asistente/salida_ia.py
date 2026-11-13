"""
HU-39 · Revisión de la salida del asistente antes de anclarla y guardarla (mismos estándares que HU-18).

  fuga_canario / fuga_prompt   la salida filtró el system prompt: se descartan TODAS las propuestas y
                               el usuario sigue con la entrevista (o a mano).
  codigo / url                 se limpian de todos los textos (el asistente no programa ni da enlaces).
  alcance                      "fuera_de_alcance" con propuestas: se quitan las propuestas.

Lógica pura: se prueba sin BD ni LLM.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from app.application.ai.agente import salida as validacion
from app.application.schemas.asistente_rat import AsistenteRatRespuesta

BLOQUEANTES = validacion.PROBLEMAS_BLOQUEANTES
RESUMEN_BLOQUEADO = ("No pude procesar esta parte de forma segura. Sigue con la siguiente pregunta o completa "
                     "este dato a mano.")
_MARCADORES = re.compile(
    r"<\s*/?\s*(respuesta_usuario|documento_empresa|mapa_empresa)\s*>|═{5,}|reglas de seguridad \(por encima|"
    r"c[óo]digo de control interno|datos del sistema, confiables|propuestas pendientes \(se pueden",
    re.IGNORECASE,
)


def _textos(valor) -> list[str]:
    """Todos los textos de un objeto de la salida, recorriendo sus bloques y listas."""
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, BaseModel):
        return [t for v in valor.__dict__.values() for t in _textos(v)]
    if isinstance(valor, (list, tuple)):
        return [t for v in valor for t in _textos(v)]
    return []


def textos_de(r: AsistenteRatRespuesta) -> list[str]:
    return _textos(r)


def problemas(r: AsistenteRatRespuesta, canario: str | None, system_prompt: str) -> list[str]:
    """Problemas de la salida, en orden estable. No modifica nada."""
    encontrados = validacion.problemas_en_textos(textos_de(r), canario, system_prompt, marcadores=_MARCADORES)
    if r.fuera_de_alcance and r.propuestas:
        encontrados.append("alcance")
    return encontrados


def _limpiar(texto: str | None) -> str | None:
    if texto is None:
        return None
    return validacion.sin_enlaces(validacion.sin_codigo(texto)).strip()


def _limpio(valor):
    """Copia con código y enlaces quitados de todos los textos (los códigos de catálogo no se tocan)."""
    if isinstance(valor, str):
        return _limpiar(valor) or ""
    if isinstance(valor, BaseModel):
        return valor.model_copy(update={k: _limpio(v) for k, v in valor.__dict__.items()})
    if isinstance(valor, list):
        return [_limpio(v) for v in valor]
    return valor


def respuesta_bloqueada() -> AsistenteRatRespuesta:
    return AsistenteRatRespuesta(fuera_de_alcance=True, resumen=RESUMEN_BLOQUEADO, propuestas=[],
                                 inconsistencias=[], preguntas_pendientes=[])


def aplicar(r: AsistenteRatRespuesta, encontrados: list[str]) -> tuple[AsistenteRatRespuesta, str | None]:
    """(respuesta que se puede usar, motivo si se bloqueó entera)."""
    if BLOQUEANTES & set(encontrados):
        return respuesta_bloqueada(), "fuga_prompt"
    data = r
    if {"codigo", "url"} & set(encontrados):
        data = data.model_copy(update={
            "resumen": _limpiar(data.resumen) or "",
            "preguntas_pendientes": [x for x in (_limpiar(q) for q in data.preguntas_pendientes) if x],
            "inconsistencias": [i.model_copy(update={"texto": _limpiar(i.texto) or ""}) for i in data.inconsistencias],
            "propuestas": [_limpio(p) for p in data.propuestas],
        })
    if "alcance" in encontrados:
        data = data.model_copy(update={"propuestas": [], "inconsistencias": []})
    return data, None
