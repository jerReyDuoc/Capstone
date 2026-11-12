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

from app.application.ai.agente import salida as validacion
from app.application.schemas.asistente_rat import AsistenteRatRespuesta, PropuestaIA

BLOQUEANTES = validacion.PROBLEMAS_BLOQUEANTES
RESUMEN_BLOQUEADO = ("No pude procesar esta parte de forma segura. Sigue con la siguiente pregunta o completa "
                     "este dato a mano.")
_MARCADORES = re.compile(
    r"<\s*/?\s*(respuesta_usuario|documento_empresa|mapa_empresa)\s*>|═{5,}|reglas de seguridad \(por encima|"
    r"c[óo]digo de control interno|datos del sistema, confiables|propuestas pendientes \(se pueden",
    re.IGNORECASE,
)
_CAMPOS_TEXTO = ("nombre", "descripcion", "proveedor", "responsable", "finalidad", "area", "interes_legitimo")


def _textos_propuesta(p: PropuestaIA) -> list[str]:
    salida = [getattr(p, c) or "" for c in _CAMPOS_TEXTO]
    salida += list(p.finalidades) + [e.texto or "" for e in p.explicaciones]
    salida += [pl.fundamento or "" for pl in p.plazos]
    return salida


def textos_de(r: AsistenteRatRespuesta) -> list[str]:
    salida = [r.resumen or ""] + list(r.preguntas_pendientes) + [i.texto or "" for i in r.inconsistencias]
    for p in r.propuestas:
        salida += _textos_propuesta(p)
    return salida


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


def _limpiar_propuesta(p: PropuestaIA) -> PropuestaIA:
    cambios: dict = {c: _limpiar(getattr(p, c)) for c in _CAMPOS_TEXTO if getattr(p, c) is not None}
    cambios["nombre"] = cambios.get("nombre") or p.nombre
    cambios["finalidades"] = [x for x in (_limpiar(f) for f in p.finalidades) if x]
    cambios["explicaciones"] = [e.model_copy(update={"texto": _limpiar(e.texto) or ""}) for e in p.explicaciones]
    cambios["plazos"] = [pl.model_copy(update={"fundamento": _limpiar(pl.fundamento)}) for pl in p.plazos]
    return p.model_copy(update=cambios)


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
            "propuestas": [_limpiar_propuesta(p) for p in data.propuestas],
        })
    if "alcance" in encontrados:
        data = data.model_copy(update={"propuestas": [], "inconsistencias": []})
    return data, None
