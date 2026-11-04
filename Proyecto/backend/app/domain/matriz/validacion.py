"""
HU-24 · Revisión del borrador antes de publicar (lógica pura).

Errores: impiden publicar (la matriz quedaría inconsistente para el cuestionario, el
puntaje o el plan formativo). Advertencias: se muestran y se pueden publicar igual.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from app.domain.matriz.contenido import (
    CAMPOS, CRITICIDADES, ENTIDADES, NIVELES, activos, etiqueta, por_id,
)
from app.domain.matriz.edicion import PATRON_CODIGO

ERROR = "error"
ADVERTENCIA = "advertencia"


def _sin_tilde(texto: str) -> str:
    return texto.lower().replace("í", "i").strip()


_CRITICIDADES = {_sin_tilde(c) for c in CRITICIDADES}
_NIVELES = {_sin_tilde(n) for n in NIVELES}


def _criticidad_ok(valor) -> bool:
    # Las semillas antiguas pueden venir en minúsculas ("alta"): se aceptan igual
    return _sin_tilde(str(valor)) in _CRITICIDADES


def _nivel_ok(valor) -> bool:
    return _sin_tilde(str(valor)) in _NIVELES


@dataclass(frozen=True)
class Problema:
    nivel: str          # error | advertencia
    codigo: str
    mensaje: str
    entidad: str | None = None
    id: int | None = None

    def como_dict(self) -> dict:
        return asdict(self)


def validar(contenido: Mapping) -> list[Problema]:
    p: list[Problema] = []

    def err(codigo, mensaje, entidad=None, item=None):
        p.append(Problema(ERROR, codigo, mensaje, entidad, int(item["id"]) if item else None))

    def adv(codigo, mensaje, entidad=None, item=None):
        p.append(Problema(ADVERTENCIA, codigo, mensaje, entidad, int(item["id"]) if item else None))

    dominios = por_id(contenido, "dominios")
    rutas_activas = {int(r["id"]) for r in activos(contenido, "rutas")}
    brechas_activas = {int(b["id"]) for b in activos(contenido, "brechas")}
    preguntas_activas = {int(q["id"]): q for q in activos(contenido, "preguntas_filtro")}

    # ---- requeridos y códigos (todas las entidades activas)
    for entidad in ENTIDADES:
        vistos: dict[str, dict] = {}
        clave_codigo = ENTIDADES[entidad]["codigo"]
        for item in activos(contenido, entidad):
            nombre = etiqueta(entidad, item)
            for campo, spec in CAMPOS[entidad].items():
                if spec.requerido and item.get(campo) in (None, ""):
                    err("CAMPO_REQUERIDO", f"{nombre}: falta '{campo}'.", entidad, item)
            if clave_codigo and item.get(clave_codigo):
                codigo = str(item[clave_codigo]).upper()
                if not PATRON_CODIGO[entidad].match(codigo):
                    err("CODIGO_INVALIDO", f"{nombre}: el código no tiene un formato válido.", entidad, item)
                if codigo in vistos:
                    err("CODIGO_DUPLICADO", f"El código {codigo} está repetido entre elementos activos.", entidad, item)
                vistos[codigo] = item

    # ---- controles
    controles = activos(contenido, "controles")
    if not controles:
        err("SIN_CONTROLES", "La matriz debe tener al menos un control activo.")
    for c in controles:
        nombre = etiqueta("controles", c)
        if c.get("dominio_id") is not None and int(c["dominio_id"]) not in dominios:
            err("DOMINIO_INVALIDO", f"{nombre}: la dimensión no existe.", "controles", c)
        if c.get("criticidad") and not _criticidad_ok(c["criticidad"]):
            err("CRITICIDAD_INVALIDA", f"{nombre}: criticidad inválida.", "controles", c)
        if c.get("brecha_id") is None:
            adv("CONTROL_SIN_BRECHA", f"{nombre}: sin brecha asociada; si no se cumple, no se recomendará una ruta.",
                "controles", c)
        elif int(c["brecha_id"]) not in brechas_activas:
            err("BRECHA_INACTIVA", f"{nombre}: su brecha está retirada o no existe.", "controles", c)
        filtros = [int(f) for f in (c.get("filtros") or [])]
        inactivos = [f for f in filtros if f not in preguntas_activas]
        if inactivos:
            err("FILTRO_INACTIVO", f"{nombre}: usa preguntas de filtro retiradas o inexistentes.", "controles", c)
        if not c.get("aplica_siempre") and not filtros:
            adv("CONTROL_NUNCA_APLICA", f"{nombre}: no tiene reglas de aplicabilidad, nunca se mostrará en el "
                                        "cuestionario.", "controles", c)

    # ---- brechas
    for b in activos(contenido, "brechas"):
        nombre = etiqueta("brechas", b)
        if b.get("criticidad") and not _criticidad_ok(b["criticidad"]):
            err("CRITICIDAD_INVALIDA", f"{nombre}: criticidad inválida.", "brechas", b)
        if b.get("ruta_formativa_id") is None:
            adv("BRECHA_SIN_RUTA", f"{nombre}: sin ruta formativa; el plan de estudio no tendrá qué recomendar.",
                "brechas", b)
        elif int(b["ruta_formativa_id"]) not in rutas_activas:
            err("RUTA_INACTIVA", f"{nombre}: su ruta formativa está retirada o no existe.", "brechas", b)

    # ---- rutas
    for r in activos(contenido, "rutas"):
        nombre = etiqueta("rutas", r)
        if r.get("dominio_id") is not None and int(r["dominio_id"]) not in dominios:
            err("DOMINIO_INVALIDO", f"{nombre}: la dimensión no existe.", "rutas", r)
        if r.get("nivel") and not _nivel_ok(r["nivel"]):
            err("NIVEL_INVALIDO", f"{nombre}: nivel inválido.", "rutas", r)
        if r.get("horas") is not None and int(r["horas"]) < 0:
            err("HORAS_INVALIDAS", f"{nombre}: las horas no pueden ser negativas.", "rutas", r)

    # ---- preguntas de filtro (el árbol)
    if not preguntas_activas:
        err("SIN_FILTRO", "El cuestionario necesita al menos una pregunta de filtro activa.")
    ordenes: dict[int, str] = {}
    usadas = {int(f) for c in controles for f in (c.get("filtros") or [])}
    for q in preguntas_activas.values():
        nombre = etiqueta("preguntas_filtro", q)
        if q.get("orden") is not None:
            o = int(q["orden"])
            if o in ordenes:
                err("ORDEN_DUPLICADO", f"{nombre} y {ordenes[o]} tienen el mismo orden ({o}).", "preguntas_filtro", q)
            ordenes[o] = nombre
        if not q.get("es_compuerta") and int(q["id"]) not in usadas:
            adv("FILTRO_SIN_EFECTO", f"{nombre}: ninguna regla la usa; responderla no cambia el cuestionario.",
                "preguntas_filtro", q)
    if preguntas_activas and not any(q.get("es_compuerta") for q in preguntas_activas.values()):
        adv("SIN_COMPUERTA", "No hay pregunta de compuerta: los controles base se aplicarán a cualquier "
                             "organización, incluso si no usa IA.")

    # ---- dimensiones sin controles (el puntaje de esa dimensión quedaría vacío)
    con_controles = {int(c["dominio_id"]) for c in controles if c.get("dominio_id") is not None}
    for d in dominios.values():
        if int(d["id"]) not in con_controles:
            adv("DIMENSION_VACIA", f"La dimensión {etiqueta('dominios', d)} quedará sin controles activos.",
                "dominios", d)
    return p


def errores(problemas: list[Problema]) -> list[Problema]:
    return [x for x in problemas if x.nivel == ERROR]
