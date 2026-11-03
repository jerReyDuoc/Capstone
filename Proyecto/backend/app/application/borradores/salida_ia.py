"""
HU-16 · Validación y anclaje de lo que devolvió el Agente IA al adaptar un borrador.

Mismo enfoque que HU-18 para el tutor: el modelo puede equivocarse aunque el filtro de
entrada deje pasar solo instrucciones limpias, así que su salida se revisa con reglas
deterministas ANTES de entrar al documento:

  fuga_canario / fuga_prompt   la salida filtró el system prompt: se descarta TODO lo que
                               aportó el modelo y el borrador queda con la plantilla base.
  clausula_desconocida         adaptó una cláusula que no se le entregó o que es fija
                               (identificación, derechos, aprobación): se ignora.
  articulo_no_verificado       cita un artículo/cláusula que no está en las fuentes reales de
                               la plantilla: esa sección se descarta (queda el texto base).
  codigo / url / codigo_interno  se limpian (sin código, sin enlaces, sin DAT-001...).
  demasiadas_secciones         se toman las primeras MAX_SECCIONES.

Lógica pura: se prueba sin BD ni LLM.
"""
from __future__ import annotations

import re

from app.application.ai.agente import salida as validacion
from app.application.borradores.generador import (
    CODIGO_INTERNO,
    AdaptacionIA,
    ContextoBorrador,
    articulos_validos,
)
from app.application.borradores.plantillas import Plantilla
from app.application.schemas.borrador import BorradorIA

MAX_SECCIONES = 6
MAX_CHARS_SECCION = 2500
MAX_CHARS_INTRO = 1200
MAX_NOTAS = 5
MAX_CHARS_NOTA = 300
BLOQUEANTES = validacion.PROBLEMAS_BLOQUEANTES

_CITA_ARTICULO = re.compile(r"(?:art[íi]culos?|arts?\.|cl[áa]usulas?|secci[óo]n(?:es)?)\s*(\d+(?:\.\d+)*)",
                            re.IGNORECASE)
_MARCADORES_BORRADOR = re.compile(
    r"<\s*/?\s*instrucciones_empresa\s*>|═{5,}|reglas de seguridad \(prioridad|codigo de control interno|"
    r"c[óo]digo de control interno|cl[áa]usulas adaptables|datos del sistema, confiables",
    re.IGNORECASE,
)
_TITULO = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_TABLA = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


def _textos(r: BorradorIA) -> list[str]:
    return [r.introduccion or ""] + [s.texto or "" for s in r.secciones] + list(r.notas_revision)


def _articulos_ok(texto: str, validos: frozenset[str]) -> bool:
    return all(n in validos for n in _CITA_ARTICULO.findall(texto or ""))


def problemas(r: BorradorIA, *, plantilla: Plantilla, contexto: ContextoBorrador, canario: str | None,
              system_prompt: str) -> list[str]:
    """Advertencias auditables (van a la métrica de llamadas_llm). No modifica nada."""
    adv = validacion.problemas_en_textos(_textos(r), canario, system_prompt, _MARCADORES_BORRADOR)
    adaptables = {c.id for c in plantilla.clausulas if c.adaptable}
    if any((s.clausula_id or "").strip() not in adaptables for s in r.secciones):
        adv.append("clausula_desconocida")
    validos = articulos_validos(plantilla, contexto)
    if not all(_articulos_ok(t, validos) for t in _textos(r)):
        adv.append("articulo_no_verificado")
    if any(CODIGO_INTERNO.search(t) for t in _textos(r)):
        adv.append("codigo_interno")
    if len(r.secciones) > MAX_SECCIONES:
        adv.append("demasiadas_secciones")
    if not r.secciones and not (r.introduccion or "").strip():
        adv.append("sin_adaptacion")
    return adv


def _limpiar(texto: str, maximo: int) -> str:
    t = validacion.sin_codigo(texto or "")
    t = validacion.sin_enlaces(t)
    t = CODIGO_INTERNO.sub("", t)
    t = _TITULO.sub("", t)
    t = _TABLA.sub("", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) > maximo:
        corte = t[:maximo].rsplit(" ", 1)[0].rstrip(" ,;:")
        t = corte + "…"
    return t


def anclar(r: BorradorIA, *, plantilla: Plantilla, contexto: ContextoBorrador, canario: str | None,
           system_prompt: str) -> tuple[AdaptacionIA, list[str], str | None]:
    """
    Devuelve (adaptación utilizable, secciones descartadas, salida_bloqueada).
    salida_bloqueada = "fuga_prompt" si se descartó TODO por una fuga del system prompt.
    """
    encontrados = validacion.problemas_en_textos(_textos(r), canario, system_prompt, _MARCADORES_BORRADOR)
    if BLOQUEANTES.intersection(encontrados):
        return AdaptacionIA(), [s.clausula_id for s in r.secciones], "fuga_prompt"

    adaptables = {c.id for c in plantilla.clausulas if c.adaptable}
    validos = articulos_validos(plantilla, contexto)
    secciones: dict[str, str] = {}
    descartadas: list[str] = []
    for s in r.secciones:
        cid = (s.clausula_id or "").strip().strip("[]")
        if cid not in adaptables or cid in secciones or len(secciones) >= MAX_SECCIONES:
            descartadas.append(cid)
            continue
        if not _articulos_ok(s.texto, validos):
            descartadas.append(cid)
            continue
        texto = _limpiar(s.texto, MAX_CHARS_SECCION)
        if len(texto) < 20:
            descartadas.append(cid)
            continue
        secciones[cid] = texto

    intro = (r.introduccion or "").strip()
    intro = _limpiar(intro, MAX_CHARS_INTRO) if intro and _articulos_ok(intro, validos) else ""
    notas = []
    for n in r.notas_revision:
        t = _limpiar(n, MAX_CHARS_NOTA)
        if t and _articulos_ok(t, validos) and t not in notas:
            notas.append(t)
    # Orden del documento, no el del modelo
    orden = [c.id for c in plantilla.clausulas]
    secciones = {cid: secciones[cid] for cid in sorted(secciones, key=orden.index)}
    return AdaptacionIA(introduccion=intro or None, secciones=secciones, notas=tuple(notas[:MAX_NOTAS])), \
        descartadas, None
