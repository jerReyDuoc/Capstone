"""
HU-34 criterio 5 · Versiones del mapa de datos.

Cada cambio guarda una instantánea COMPLETA del mapa (elementos y flujos) con su huella
SHA-256 y la lista de diferencias con la versión anterior. Así se puede:
  - ver qué cambió y cuándo (historial legible para el usuario);
  - volver a una versión anterior (la restauración es, a su vez, una versión nueva: nada se
    sobrescribe ni se pierde);
  - demostrar ante un auditor qué decía el mapa en una fecha (la huella cambia si cambia
    cualquier dato).
"""
from __future__ import annotations

import hashlib
import json

from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos.modelo import CAMPOS_ELEMENTO, CAMPOS_FLUJO, Elemento, Flujo

FORMATO_INSTANTANEA = 1

ETIQUETA_CAMPO = {
    "tipo": "tipo", "subtipo": "categoría", "nombre": "nombre", "descripcion": "descripción",
    "proveedor": "proveedor", "pais": "país", "responsable": "responsable interno",
    "categorias_datos": "categorías de datos", "categorias_titulares": "categorías de titulares",
    "nna_declarado": "datos de niños, niñas y adolescentes", "rol_tercero": "rol del tercero",
    "contrato_firmado": "contrato", "pendiente_revision": "revisión", "origen_id": "origen", "destino_id": "destino",
    "finalidad": "finalidad", "frecuencia": "frecuencia", "medio": "medio", "cifrado": "cifrado",
    "garantia": "garantía de transferencia",
}
NOMBRE_TIPO = {"sistema": "el sistema", "base_datos": "la base de datos", "tercero": "el tercero"}


def instantanea(elementos: list[Elemento], flujos: list[Flujo]) -> dict:
    return {
        "formato": FORMATO_INSTANTANEA,
        "catalogo": cat.VERSION_CATALOGO,
        "elementos": [e.como_dict() for e in sorted(elementos, key=lambda x: x.id or 0)],
        "flujos": [f.como_dict() for f in sorted(flujos, key=lambda x: x.id or 0)],
    }


def huella(inst: dict) -> str:
    """SHA-256 del contenido (sin la versión del catálogo ni el formato: solo los datos)."""
    datos = {"elementos": inst.get("elementos", []), "flujos": inst.get("flujos", [])}
    canonico = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def desde_instantanea(inst: dict) -> tuple[list[Elemento], list[Flujo]]:
    return ([Elemento.desde_dict(e) for e in inst.get("elementos", [])],
            [Flujo.desde_dict(f) for f in inst.get("flujos", [])])


def _nombre_flujo(f: dict, nombres: dict[int, str]) -> str:
    return f"{nombres.get(f['origen_id'], '?')} → {nombres.get(f['destino_id'], '?')}"


def diferencias(antes: dict | None, despues: dict) -> list[dict]:
    """
    Cambios entre dos instantáneas: [{entidad, operacion, id, nombre, campos}], donde operacion es
    creado | editado | eliminado y `campos` los campos que cambiaron (solo en las ediciones).
    """
    antes = antes or {"elementos": [], "flujos": []}
    cambios: list[dict] = []
    nombres = {e["id"]: e["nombre"] for e in antes.get("elementos", [])}
    nombres.update({e["id"]: e["nombre"] for e in despues.get("elementos", [])})
    for entidad, campos in (("elemento", CAMPOS_ELEMENTO), ("flujo", CAMPOS_FLUJO)):
        clave = "elementos" if entidad == "elemento" else "flujos"
        a = {x["id"]: x for x in antes.get(clave, [])}
        d = {x["id"]: x for x in despues.get(clave, [])}

        def nombre(x: dict, entidad: str = entidad) -> str:
            return x["nombre"] if entidad == "elemento" else _nombre_flujo(x, nombres)

        for i in sorted(d.keys() - a.keys()):
            cambios.append({"entidad": entidad, "operacion": "creado", "id": i, "nombre": nombre(d[i]),
                            "tipo": d[i].get("tipo"), "campos": []})
        for i in sorted(a.keys() & d.keys()):
            distintos = [c for c in campos if a[i].get(c) != d[i].get(c)]
            if distintos:
                cambios.append({"entidad": entidad, "operacion": "editado", "id": i, "nombre": nombre(d[i]),
                                "tipo": d[i].get("tipo"), "campos": distintos})
        for i in sorted(a.keys() - d.keys()):
            cambios.append({"entidad": entidad, "operacion": "eliminado", "id": i, "nombre": nombre(a[i]),
                            "tipo": a[i].get("tipo"), "campos": []})
    return cambios


def describir(cambios: list[dict]) -> str:
    """Resumen en lenguaje simple de un conjunto de cambios (para el historial)."""
    if not cambios:
        return "Sin cambios en el contenido."
    if len(cambios) == 1:
        c = cambios[0]
        sujeto = NOMBRE_TIPO.get(c.get("tipo") or "", "el elemento") if c["entidad"] == "elemento" else "el flujo"
        if c["operacion"] == "creado":
            return f"Se agregó {sujeto} «{c['nombre']}»."
        if c["operacion"] == "eliminado":
            return f"Se eliminó {sujeto} «{c['nombre']}»."
        campos = [ETIQUETA_CAMPO.get(x, x) for x in c["campos"]]
        lista = ", ".join(campos[:-1]) + (" y " if len(campos) > 1 else "") + campos[-1]
        return f"Se editó {sujeto} «{c['nombre']}» ({lista})."
    partes = []
    for op, participio in (("creado", "agregado"), ("editado", "editado"), ("eliminado", "eliminado")):
        for entidad, singular, plural in (("elemento", "elemento", "elementos"), ("flujo", "flujo", "flujos")):
            n = sum(1 for c in cambios if c["operacion"] == op and c["entidad"] == entidad)
            if n:
                partes.append(f"{n} {singular if n == 1 else plural} {participio}{'' if n == 1 else 's'}")
    texto = ", ".join(partes[:-1]) + (" y " if len(partes) > 1 else "") + partes[-1]
    return f"Cambios en el mapa: {texto}."
