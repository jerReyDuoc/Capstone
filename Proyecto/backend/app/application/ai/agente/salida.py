"""
HU-18 · Validación de la SALIDA del tutor (antes de mostrarla o guardarla).

El modelo puede equivocarse aunque el filtro de entrada deje pasar solo mensajes limpios:
un ataque nuevo que el filtro no conoce, o simplemente un desliz. Por eso la salida se
revisa con reglas deterministas:

  fuga_canario   cada system prompt lleva un código de control aleatorio que el modelo
                 nunca debe escribir; si aparece, el prompt se filtró.
  fuga_prompt    la respuesta reproduce frases del system prompt (ventanas de 8 palabras)
                 o sus marcadores internos (<mensaje_usuario>, "REGLAS DE SEGURIDAD"...).
  codigo         bloques de código o comandos: el tutor no programa (scope lock).
  url            enlaces: el tutor no deriva a sitios externos.
  alcance        una respuesta "fuera_de_alcance" que igual trae pasos o brechas.

Las dos fugas BLOQUEAN la respuesta completa (se reemplaza por un rechazo fijo). Lo demás
se limpia (se quita el código, el enlace o el contenido sobrante) y queda la advertencia.
"""
from __future__ import annotations

import re
import secrets
import unicodedata

from app.application.schemas.tutor import TipoRespuestaTutor, TutorRespuesta

PROBLEMAS_BLOQUEANTES = frozenset({"fuga_canario", "fuga_prompt"})

RESPUESTA_FUGA = (
    "No puedo compartir mi configuración interna ni las instrucciones con que funciono. "
    "Sí puedo ayudarte a entender y cerrar las brechas de gobernanza de tu empresa."
)
SUGERENCIAS_FUGA = ["¿Qué brecha debería cerrar primero?", "Explícame la brecha más crítica de mi evaluación."]
NOTA_CODIGO = "(Omití contenido técnico que está fuera de mi función como tutor de gobernanza.)"

_MARCADORES = re.compile(
    r"<\s*/?\s*(mensaje_usuario|historial|antecedentes_empresa)\s*>|═{5,}|reglas de seguridad \(prioridad|"
    r"contexto de la empresa \(datos del sistema|codigo de control interno|fuentes normativas \(obligatorio\)",
    re.IGNORECASE,
)
_CODIGO = re.compile(
    r"```|^\s*(def |class |import |from \w+ import|#!/|select .+ from |insert into |sudo |pip install|npm install|"
    r"<script|function\s*\(|console\.log|print\()", re.IGNORECASE | re.MULTILINE)
_BLOQUE_CODIGO = re.compile(r"```.*?(```|$)", re.DOTALL)
_URL = re.compile(r"\b(https?://|www\.)\S+", re.IGNORECASE)


def generar_canario() -> str:
    return "CNR-" + secrets.token_hex(5).upper()


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9ñ]+", " ", t).strip()


def _ventanas(texto: str, n: int = 8) -> set[str]:
    palabras = _norm(texto).split()
    return {" ".join(palabras[i:i + n]) for i in range(max(0, len(palabras) - n + 1))}


_CACHE_VENTANAS: dict[int, set[str]] = {}


def _ventanas_prompt(system: str) -> set[str]:
    clave = hash(system)
    if clave not in _CACHE_VENTANAS:
        _CACHE_VENTANAS[clave] = _ventanas(system)
    return _CACHE_VENTANAS[clave]


def textos_de(r: TutorRespuesta) -> list[str]:
    salida = [r.respuesta or ""]
    for p in r.pasos:
        salida += [p.accion or "", p.evidencia_esperada or ""]
    return salida + list(r.sugerencias)


def problemas(r: TutorRespuesta, canario: str | None, system_prompt: str) -> list[str]:
    """Problemas de la salida, en orden estable. No modifica nada."""
    textos = textos_de(r)
    unido = "\n".join(textos)
    encontrados: list[str] = []
    if canario and (canario.lower() in unido.lower() or canario.split("-")[-1].lower() in unido.lower()):
        encontrados.append("fuga_canario")
    coincidencias = _ventanas_prompt(system_prompt) & _ventanas(unido)
    if len(coincidencias) >= 3 or _MARCADORES.search(unido):
        encontrados.append("fuga_prompt")
    if any(_CODIGO.search(t) for t in textos):
        encontrados.append("codigo")
    if any(_URL.search(t) for t in textos):
        encontrados.append("url")
    if r.tipo == TipoRespuestaTutor.FUERA_DE_ALCANCE and (r.pasos or r.brechas_referenciadas):
        encontrados.append("alcance")
    return encontrados


def respuesta_bloqueada() -> TutorRespuesta:
    return TutorRespuesta(tipo=TipoRespuestaTutor.FUERA_DE_ALCANCE, respuesta=RESPUESTA_FUGA,
                          pasos=[], brechas_referenciadas=[], sugerencias=list(SUGERENCIAS_FUGA))


def _sin_codigo(texto: str) -> str:
    limpio = _BLOQUE_CODIGO.sub("", texto or "")
    limpio = "\n".join(l for l in limpio.splitlines() if not _CODIGO.search(l))
    return limpio.strip()


def aplicar(r: TutorRespuesta, encontrados: list[str]) -> TutorRespuesta:
    """Devuelve la respuesta que se puede mostrar: bloqueada (fugas) o limpia."""
    if PROBLEMAS_BLOQUEANTES & set(encontrados):
        return respuesta_bloqueada()
    data = r
    if "codigo" in encontrados:
        texto = _sin_codigo(data.respuesta)
        data = data.model_copy(update={
            "respuesta": f"{texto}\n\n{NOTA_CODIGO}".strip() if texto else NOTA_CODIGO,
            "pasos": [p.model_copy(update={"accion": _sin_codigo(p.accion) or "Paso omitido.",
                                           "evidencia_esperada": _sin_codigo(p.evidencia_esperada or "") or None})
                      for p in data.pasos],
        })
    if "url" in encontrados:
        data = data.model_copy(update={
            "respuesta": _URL.sub("[enlace omitido]", data.respuesta or ""),
            "pasos": [p.model_copy(update={"accion": _URL.sub("[enlace omitido]", p.accion or ""),
                                           "evidencia_esperada": _URL.sub("[enlace omitido]", p.evidencia_esperada)
                                           if p.evidencia_esperada else None}) for p in data.pasos],
            "sugerencias": [_URL.sub("[enlace omitido]", s) for s in data.sugerencias],
        })
    if "alcance" in encontrados:
        data = data.model_copy(update={"pasos": [], "brechas_referenciadas": []})
    return data
