import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptRenderizado:
    system: str
    user: str
    version: str


# HU-07 · Saneamiento de entrada (OWASP LLM01). Lo que no se ve en pantalla no debe llegar al
# modelo: caracteres de ancho cero, controles bidireccionales (RLO/LRI...), caracteres "tag"
# (U+E0000) y controles C0. Se conservan el salto de línea y el tabulador.
_INVISIBLES = re.compile(r"[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000E0000-\U000E007F]")
_CONTROLES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# El separador de secciones de los prompts (═══) y los marcadores de turno de otros modelos:
# dentro de un texto no confiable no pueden simular el inicio de una sección del sistema.
_SEPARADOR = re.compile(r"[═━]{3,}")
_TURNOS = re.compile(r"\[/?INST\]|<<\s*/?\s*SYS\s*>>|<\|[a-z_]{2,20}\|>", re.IGNORECASE)


def sanear_texto_no_confiable(texto: str | None) -> str:
    """Quita caracteres invisibles y de control, y neutraliza separadores y marcadores de turno."""
    t = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    t = _INVISIBLES.sub("", t)
    t = _CONTROLES.sub("", t)
    t = _SEPARADOR.sub("===", t)
    return _TURNOS.sub("[marcador omitido]", t)


def escapar_para_prompt(texto: str | None) -> str:
    """Sanea el texto no confiable (HU-07) y escapa < y > para que no pueda cerrar los
    delimitadores (<justificacion_usuario>, <evidencia_adjunta>) del prompt."""
    return sanear_texto_no_confiable(texto).replace("<", "&lt;").replace(">", "&gt;")
