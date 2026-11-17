"""
Revisión de la salida de la guía de registro antes de mostrarla (mismos estándares que el tutor, HU-18).

  fuga_canario / fuga_prompt   la salida filtró el system prompt: se reemplaza por una respuesta fija.
  codigo / url                 se quitan del texto (la guía no programa ni da enlaces).

Además se acota: la respuesta a ~900 caracteres y como máximo 2 sugerencias. Lógica pura.
"""
from __future__ import annotations

import re

from app.application.ai.agente import salida_tutor as validacion
from app.application.ai.schemas.guia_registro import GuiaRegistroRespuesta

BLOQUEANTES = validacion.PROBLEMAS_BLOQUEANTES
MAX_CARACTERES_RESPUESTA = 900
MAX_SUGERENCIAS = 2
RESPUESTA_BLOQUEADA = ("No puedo compartir cómo funciono por dentro. Sí puedo explicarte cómo completar tu mapa de "
                       "datos y tu registro de actividades.")
SUGERENCIAS_BLOQUEADA = ["¿Por dónde empiezo?", "¿Qué es una actividad de tratamiento?"]
_MARCADORES = re.compile(
    r"<\s*/?\s*(mensaje_usuario|historial|registro_empresa)\s*>|═{5,}|reglas de seguridad \(por encima|"
    r"c[óo]digo de control interno|datos del sistema, confiables|c[óo]mo se hace en la pantalla",
    re.IGNORECASE,
)


def problemas(r: GuiaRegistroRespuesta, canario: str | None, system_prompt: str) -> list[str]:
    """Problemas de la salida, en orden estable. No modifica nada."""
    return validacion.problemas_en_textos([r.respuesta or "", *r.sugerencias], canario, system_prompt,
                                          marcadores=_MARCADORES)


def _limpiar(texto: str | None) -> str:
    return validacion.sin_enlaces(validacion.sin_codigo(texto or "")).strip()


def _acotar(texto: str, maximo: int = MAX_CARACTERES_RESPUESTA) -> str:
    """Corta en el último fin de frase antes del máximo (nunca a media palabra)."""
    t = re.sub(r"\n{3,}", "\n\n", texto.strip())
    if len(t) <= maximo:
        return t
    corte = t[:maximo]
    fin = max(corte.rfind(". "), corte.rfind(".\n"), corte.rfind("? "), corte.rfind("! "))
    return corte[: fin + 1].strip() if fin > maximo // 3 else corte.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def respuesta_bloqueada() -> GuiaRegistroRespuesta:
    return GuiaRegistroRespuesta(fuera_de_alcance=True, respuesta=RESPUESTA_BLOQUEADA,
                                 sugerencias=list(SUGERENCIAS_BLOQUEADA))


def aplicar(r: GuiaRegistroRespuesta, encontrados: list[str]) -> tuple[GuiaRegistroRespuesta, str | None]:
    """(respuesta que se puede mostrar, motivo si se bloqueó entera). Siempre la deja corta."""
    if BLOQUEANTES & set(encontrados):
        return respuesta_bloqueada(), "fuga_prompt"
    respuesta = r.respuesta or ""
    sugerencias = list(r.sugerencias)
    if {"codigo", "url"} & set(encontrados):
        respuesta = _limpiar(respuesta)
        sugerencias = [_limpiar(s) for s in sugerencias]
    sugerencias = [s.strip() for s in sugerencias if s and s.strip()][:MAX_SUGERENCIAS]
    return r.model_copy(update={"respuesta": _acotar(respuesta), "sugerencias": [s[:140] for s in sugerencias]}), None
