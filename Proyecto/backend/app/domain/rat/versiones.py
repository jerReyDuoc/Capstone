"""
HU-35 criterio 4 · Versiones vigentes de una actividad (mismo patrón que la matriz versionada).

Al quedar vigente se guarda una instantánea COMPLETA (lo que escribió la empresa y lo que se tomó del
mapa, con los nombres de ese momento) y su huella SHA-256 en rat_actividad_version. Esa fila no se
modifica ni se borra: en PostgreSQL lo impide un trigger (migración d1e5b8a3c7f2), también con el
rol de la API. Así se puede demostrar qué decía el registro en una fecha aunque el mapa cambie.
"""
from __future__ import annotations

import hashlib
import json

from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat
from app.domain.rat.modelo import completar

FORMATO_INSTANTANEA = 1

_CAMPOS_DERIVADOS = ("elementos", "flujos", "tipos_datos", "titulares", "bases_datos", "paises", "terceros",
                     "transferencias")

# Qué campo del registro cambia cuando cambia cada parte de la instantánea
_CAMPO_DE = {
    "nombre": "actividad", "descripcion": "actividad", "area": "actividad", "finalidades": "finalidades",
    "fuentes": "fuentes", "base_licitud": "base_licitud", "interes_legitimo": "base_licitud",
    "base_sensibles": "base_licitud", "sin_destinatarios": "destinatarios", "plazos": "conservacion",
    "decisiones": "decisiones", "medidas": "medidas", "rol": "rol", "responsable_mandante": "rol",
    "ambito_nota": "ambito", "volumen": "volumen",
    "elementos": "bases_datos", "flujos": "bases_datos", "tipos_datos": "tipos_datos", "titulares": "titulares",
    "bases_datos": "bases_datos", "paises": "ambito", "terceros": "destinatarios", "transferencias": "transferencias",
}
TITULO_CAMBIO = {"actividad": "Nombre o descripción", **{c.codigo: c.titulo for c in cat.CAMPOS},
                 "volumen": "Cantidad de personas"}


def _derivados_estables(deriv: dict) -> dict:
    """Solo lo que describe el registro (sin listas de 'disponibles' del mapa, que no son parte de él)."""
    salida = {}
    for k in _CAMPOS_DERIVADOS:
        v = deriv.get(k, [])
        if k in ("elementos", "flujos"):
            v = [{kk: vv for kk, vv in x.items() if not kk.startswith("disponibles_")} for x in v]
        salida[k] = v
    return salida


def instantanea(contenido: dict, deriv: dict) -> dict:
    return {
        "formato": FORMATO_INSTANTANEA,
        "catalogo_mapa": cat_mapa.VERSION_CATALOGO,
        "textos": cat.VERSION_TEXTOS,
        "actividad": completar(contenido),
        "mapa": _derivados_estables(deriv),
    }


def huella(inst: dict) -> str:
    """SHA-256 de lo que dice el registro (sin las versiones del catálogo ni el formato)."""
    datos = {"actividad": inst.get("actividad", {}), "mapa": inst.get("mapa", {})}
    canonico = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def diferencias(antes: dict | None, despues: dict) -> list[str]:
    """Campos del registro (códigos de catalogo.CAMPOS o "actividad") que cambiaron entre dos instantáneas."""
    if not antes:
        return []
    cambiados: list[str] = []
    for parte in ("actividad", "mapa"):
        a, d = antes.get(parte, {}) or {}, despues.get(parte, {}) or {}
        for k in sorted(set(a) | set(d)):
            if a.get(k) != d.get(k):
                campo = _CAMPO_DE.get(k)
                if campo and campo not in cambiados:
                    cambiados.append(campo)
    orden = ["actividad", *cat.CODIGOS_CAMPO, "volumen"]
    return sorted(cambiados, key=orden.index)


def describir(cambios: list[str]) -> str:
    if not cambios:
        return "Sin cambios respecto de la versión anterior."
    nombres = [TITULO_CAMBIO[c].lower() if i else TITULO_CAMBIO[c] for i, c in enumerate(cambios)]
    if len(nombres) == 1:
        return f"Cambió: {nombres[0]}."
    return "Cambiaron: " + ", ".join(nombres[:-1]) + " y " + nombres[-1] + "."
