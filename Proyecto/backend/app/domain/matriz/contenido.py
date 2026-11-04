"""
HU-24 · Contenido de una versión de la matriz normativa (lógica pura, sin BD).

Una versión es un documento JSON con TODO lo que define el autodiagnóstico:

    {
      "esquema": 1,
      "dominios":         [{id, nombre_dominio}],                      (solo lectura)
      "rutas":            [{id, nombre, dominio_id, nivel, ..., activo}],
      "brechas":          [{id, codigo_brecha, ..., ruta_formativa_id, activo}],
      "controles":        [{id, codigo_control, ..., dominio_id, brecha_id, activo,
                            aplica_siempre, filtros: [id de pregunta de filtro]}],
      "preguntas_filtro": [{id, codigo, orden, pregunta, descripcion, activa, es_compuerta}]
    }

Las reglas de aplicabilidad viven dentro de cada control (`aplica_siempre` y `filtros`):
el control aplica si la organización pasó las compuertas y (aplica_siempre o respondió SÍ
a alguno de sus filtros). Es el mismo árbol que estaba fijo en control_tree.py, ahora como
dato editable.

Los elementos retirados NO se borran: quedan con activo=false (las respuestas, brechas y
avances de evaluaciones anteriores los siguen referenciando por id). Los nuevos que aún no
se publican llevan id negativo; al publicar reciben su id real.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

ESQUEMA = 1

# Entidades editables y, de cada una, su clave de "activo" y el campo que la identifica
# ante una persona (código o nombre).
ENTIDADES: dict[str, dict[str, str]] = {
    "controles": {"activo": "activo", "etiqueta": "codigo_control", "codigo": "codigo_control"},
    "brechas": {"activo": "activo", "etiqueta": "codigo_brecha", "codigo": "codigo_brecha"},
    "rutas": {"activo": "activo", "etiqueta": "nombre", "codigo": ""},
    "preguntas_filtro": {"activo": "activa", "etiqueta": "codigo", "codigo": "codigo"},
}
ORDEN_ENTIDADES = ("rutas", "brechas", "controles", "preguntas_filtro")

# Tipos: "str" (con largo máximo), "int", "bool", "ref:<entidad>" (id de otra entidad o
# None), "refs:<entidad>" (lista de ids). requerido = no puede quedar vacío en un elemento
# activo (lo revisa validacion.py; la edición solo normaliza).
@dataclass(frozen=True)
class Campo:
    tipo: str
    largo: int = 0
    requerido: bool = False


TEXTO_LARGO = 5000

CAMPOS: dict[str, dict[str, Campo]] = {
    "controles": {
        "codigo_control": Campo("str", 20, True),
        "framework_fuente": Campo("str", 50),
        "articulo_referencia": Campo("str", 100),
        "tipo_fuente": Campo("str", 50),
        "obligacion": Campo("str", 200),
        "pregunta_evaluacion": Campo("str", 500, True),
        "aplicabilidad": Campo("str", 100),
        "evidencia_esperada": Campo("str", TEXTO_LARGO),
        "criticidad": Campo("str", 10, True),
        "recomendacion": Campo("str", TEXTO_LARGO),
        "test_asociado": Campo("str", 100),
        "dominio_id": Campo("ref:dominios", requerido=True),
        "brecha_id": Campo("ref:brechas"),
        "aplica_siempre": Campo("bool"),
        "filtros": Campo("refs:preguntas_filtro"),
    },
    "brechas": {
        "codigo_brecha": Campo("str", 20, True),
        "categoria": Campo("str", 50),
        "comportamiento_detectado": Campo("str", TEXTO_LARGO, True),
        "criticidad": Campo("str", 10, True),
        "accion_sistema": Campo("str", 100),
        "ruta_formativa_id": Campo("ref:rutas"),
    },
    "rutas": {
        "nombre": Campo("str", 100, True),
        "dominio_id": Campo("ref:dominios"),
        "nivel": Campo("str", 15),
        "objetivo": Campo("str", TEXTO_LARGO),
        "objetivos_especificos": Campo("str", TEXTO_LARGO),
        "contenidos": Campo("str", TEXTO_LARGO),
        "horas": Campo("int"),
        "modalidad": Campo("str", 50),
        "publico_objetivo": Campo("str", 150),
    },
    "preguntas_filtro": {
        "codigo": Campo("str", 10, True),
        "orden": Campo("int", requerido=True),
        "pregunta": Campo("str", 500, True),
        "descripcion": Campo("str", 500),
        "es_compuerta": Campo("bool"),
    },
}

CRITICIDADES = ("Crítica", "Alta", "Media", "Baja")
NIVELES = ("Inicial", "Intermedio", "Avanzado")


def vacio() -> dict:
    return {"esquema": ESQUEMA, "dominios": [], "rutas": [], "brechas": [], "controles": [], "preguntas_filtro": []}


def copiar(contenido: Mapping) -> dict:
    return copy.deepcopy(dict(contenido))


def por_id(contenido: Mapping, entidad: str) -> dict[int, dict]:
    return {int(x["id"]): x for x in contenido.get(entidad, [])}


def esta_activo(entidad: str, item: Mapping) -> bool:
    return bool(item.get(ENTIDADES[entidad]["activo"], True)) if entidad in ENTIDADES else True


def activos(contenido: Mapping, entidad: str) -> list[dict]:
    return [x for x in contenido.get(entidad, []) if esta_activo(entidad, x)]


def etiqueta(entidad: str, item: Mapping) -> str:
    clave = ENTIDADES.get(entidad, {}).get("etiqueta") or "nombre_dominio"
    valor = item.get(clave)
    return str(valor) if valor not in (None, "") else f"#{item.get('id')}"


# --------------------------------------------------------------------- normalización y huella
def _orden_canonico(contenido: Mapping) -> dict:
    """Mismo contenido → mismo JSON: listas ordenadas por id, filtros ordenados y sin repetir."""
    salida: dict[str, Any] = {"esquema": int(contenido.get("esquema", ESQUEMA))}
    for entidad in ("dominios", *ORDEN_ENTIDADES):
        filas = []
        for x in sorted(contenido.get(entidad, []), key=lambda f: int(f["id"])):
            fila = dict(x)
            if entidad == "controles":
                fila["filtros"] = sorted({int(i) for i in (fila.get("filtros") or [])})
                fila["aplica_siempre"] = bool(fila.get("aplica_siempre"))
            filas.append(fila)
        salida[entidad] = filas
    return salida


def canonico(contenido: Mapping) -> str:
    return json.dumps(_orden_canonico(contenido), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def huella(contenido: Mapping) -> str:
    """SHA-256 del contenido canónico. Cualquier cambio de texto, regla o estado la cambia."""
    return hashlib.sha256(canonico(contenido).encode("utf-8")).hexdigest()


def version_texto(etiqueta_version: str, huella_hex: str) -> str:
    """Lo que se guarda en evaluacion.version_matriz e imprime el informe (HU-21)."""
    return f"{(etiqueta_version or 'sin-etiqueta').strip()}+{huella_hex[:8]}"


def normalizar(contenido: Mapping) -> dict:
    return _orden_canonico(contenido)


# --------------------------------------------------------------------- árbol de aplicabilidad
@dataclass(frozen=True)
class ArbolAplicabilidad:
    """
    Reglas de aplicabilidad de una versión, por CÓDIGO (como las responde el filtro).

    compuertas: preguntas de filtro que, si no se responden SÍ, dejan sin controles a la
                organización (F1 "¿usa IA?").
    base:       controles que aplican siempre que se pasen las compuertas.
    por_filtro: controles que se suman al responder SÍ a cada pregunta de filtro.
    """
    compuertas: frozenset[str]
    base: frozenset[str]
    por_filtro: Mapping[str, frozenset[str]] = field(default_factory=dict)
    origen: str = "bd"

    def aplicables(self, respuestas: Mapping[str, bool]) -> list[str]:
        if any(not respuestas.get(c, False) for c in self.compuertas):
            return []
        aplicables = set(self.base)
        for codigo, controles in self.por_filtro.items():
            if respuestas.get(codigo, False):
                aplicables.update(controles)
        return sorted(aplicables)

    def como_dict(self) -> dict:
        return {
            "compuertas": sorted(self.compuertas),
            "base": sorted(self.base),
            "por_filtro": {k: sorted(v) for k, v in sorted(self.por_filtro.items())},
            "origen": self.origen,
        }


def arbol(contenido: Mapping) -> ArbolAplicabilidad:
    preguntas = {int(p["id"]): p for p in activos(contenido, "preguntas_filtro")}
    compuertas = frozenset(p["codigo"] for p in preguntas.values() if p.get("es_compuerta") and p.get("codigo"))
    base: set[str] = set()
    por_filtro: dict[str, set[str]] = {}
    for c in activos(contenido, "controles"):
        codigo = c.get("codigo_control")
        if not codigo:
            continue
        if c.get("aplica_siempre"):
            base.add(codigo)
        for pid in c.get("filtros") or []:
            p = preguntas.get(int(pid))
            if p is not None and p.get("codigo"):
                por_filtro.setdefault(p["codigo"], set()).add(codigo)
    return ArbolAplicabilidad(
        compuertas=compuertas, base=frozenset(base),
        por_filtro={k: frozenset(v) for k, v in por_filtro.items()},
    )


def resumen(contenido: Mapping) -> dict:
    """Conteos para el listado de versiones."""
    return {
        entidad: {"activos": len(activos(contenido, entidad)), "total": len(contenido.get(entidad, []))}
        for entidad in ORDEN_ENTIDADES
    }


# --------------------------------------------------------------------- armado desde filas
def construir(*, dominios: Iterable[Mapping], rutas: Iterable[Mapping], brechas: Iterable[Mapping],
              controles: Iterable[Mapping], preguntas: Iterable[Mapping],
              reglas: Iterable[tuple[int, int | None]]) -> dict:
    """
    Arma el contenido desde las filas de las tablas (la migración y el repositorio lo usan).

    reglas: pares (id_control, id_pregunta_filtro | None). None = aplica siempre.
    Las filas son mapeos con los nombres de columna del modelo; `catalogo_brechas_id_brecha`
    se publica como `brecha_id`.
    """
    siempre: set[int] = set()
    filtros: dict[int, set[int]] = {}
    for control_id, pregunta_id in reglas:
        if pregunta_id is None:
            siempre.add(int(control_id))
        else:
            filtros.setdefault(int(control_id), set()).add(int(pregunta_id))

    def _activo(f: Mapping, clave: str = "activo") -> bool:
        v = f.get(clave)
        return True if v is None else bool(v)

    contenido = vacio()
    contenido["dominios"] = [{"id": int(d["id"]), "nombre_dominio": d.get("nombre_dominio")} for d in dominios]
    contenido["rutas"] = [
        {"id": int(r["id"]), **{k: r.get(k) for k in CAMPOS["rutas"]}, "activo": _activo(r)} for r in rutas
    ]
    contenido["brechas"] = [
        {"id": int(b["id_brecha"] if "id_brecha" in b else b["id"]),
         **{k: b.get(k) for k in CAMPOS["brechas"]}, "activo": _activo(b)}
        for b in brechas
    ]
    filas_control = []
    for c in controles:
        cid = int(c["id_control"] if "id_control" in c else c["id"])
        fila = {"id": cid}
        for k in CAMPOS["controles"]:
            if k == "brecha_id":
                fila[k] = c.get("catalogo_brechas_id_brecha", c.get("brecha_id"))
            elif k == "aplica_siempre":
                fila[k] = cid in siempre
            elif k == "filtros":
                fila[k] = sorted(filtros.get(cid, set()))
            else:
                fila[k] = c.get(k)
        fila["activo"] = _activo(c)
        filas_control.append(fila)
    contenido["controles"] = filas_control
    contenido["preguntas_filtro"] = [
        {"id": int(p["id_pregunta"] if "id_pregunta" in p else p["id"]),
         **{k: (bool(p.get(k)) if k == "es_compuerta" else p.get(k)) for k in CAMPOS["preguntas_filtro"]},
         "activa": _activo(p, "activa")}
        for p in preguntas
    ]
    return normalizar(contenido)


def reglas_de(contenido: Mapping) -> list[tuple[int, int | None]]:
    """Inverso de construir(): filas de regla_aplicabilidad (solo controles activos)."""
    filas: list[tuple[int, int | None]] = []
    for c in activos(contenido, "controles"):
        if c.get("aplica_siempre"):
            filas.append((int(c["id"]), None))
        for pid in sorted({int(i) for i in (c.get("filtros") or [])}):
            filas.append((int(c["id"]), pid))
    return filas
