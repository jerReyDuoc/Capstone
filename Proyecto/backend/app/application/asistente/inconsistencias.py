"""
HU-39 criterio 2 · Inconsistencias y nivel de riesgo, calculados por el BACKEND (no por el modelo).

El modelo explica; el sistema decide. Con las mismas funciones que usan el mapa (HU-34), el RAT (HU-35)
y la matriz de riesgos (HU-36) se calcula, sobre un mapa "virtual" (lo que existe + lo propuesto):

  sensible_sin_base           una actividad usa datos sensibles y no tiene base para tratarlos
  transferencia_sin_garantia  un flujo envía datos fuera de Chile sin una garantía válida
  actividad_sin_plazo         una categoría de datos de una actividad no tiene plazo de conservación
  flujo_sin_actividad         un flujo del mapa no pertenece a ninguna actividad (app/domain/rat/cobertura.py)

y el riesgo inherente de cada actividad propuesta (app/domain/rat/riesgos.py: probabilidad × impacto).
Lógica pura y determinista: se prueba sin BD ni LLM.
"""
from __future__ import annotations

from app.application.asistente.anclaje import parsear_ref
from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos import analisis as am
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import analisis as rat_an
from app.domain.rat import cobertura, riesgos
from app.domain.rat.modelo import completar

SEVERIDAD = {"sensible_sin_base": "Alta", "transferencia_sin_garantia": "Alta",
             "actividad_sin_plazo": "Media", "flujo_sin_actividad": "Media"}
CODIGOS = tuple(SEVERIDAD)


def _item(codigo: str, texto: str, referencia: dict | None = None, severidad: str | None = None) -> dict:
    return {"codigo": codigo, "severidad": severidad or SEVERIDAD[codigo], "texto": texto, "referencia": referencia}


class MapaVirtual:
    """El mapa real más los elementos y flujos propuestos (con ids negativos) para calcular derivados."""

    def __init__(self, elementos: list[Elemento], flujos: list[Flujo], propuestas: list[dict],
                 alias: dict[str, int] | None = None):
        self.elementos = list(elementos)
        self.flujos = list(flujos)
        # clave de la propuesta -> id virtual (o el id real si ya se aceptó: `alias`)
        self.ids: dict[str, int] = dict(alias or {})
        siguiente = -1
        for p in (x for x in propuestas if x["tipo"] == "elemento"):
            d = p["payload"]
            self.elementos.append(Elemento(
                id=siguiente, tipo=d.get("tipo") or "sistema", nombre=d.get("nombre") or "", subtipo=d.get("subtipo"),
                pais=d.get("pais"), categorias_datos=list(d.get("categorias_datos") or []),
                categorias_titulares=list(d.get("categorias_titulares") or []), rol_tercero=d.get("rol_tercero"),
                contrato_firmado=d.get("contrato_firmado")))
            self.ids[p["clave"]] = siguiente
            siguiente -= 1
        for p in (x for x in propuestas if x["tipo"] == "flujo"):
            d = p["payload"]
            o, de = self.resolver(d.get("origen")), self.resolver(d.get("destino"))
            if o is None or de is None:
                continue
            self.flujos.append(Flujo(
                id=siguiente, origen_id=o, destino_id=de, finalidad=d.get("finalidad"),
                categorias_datos=list(d.get("categorias_datos") or []),
                categorias_titulares=list(d.get("categorias_titulares") or []), garantia=d.get("garantia"),
                cifrado=d.get("cifrado")))
            self.ids[p["clave"]] = siguiente
            siguiente -= 1
        self.por_id = {e.id: e for e in self.elementos}
        self.flujo_por_id = {f.id: f for f in self.flujos}

    def resolver(self, ref: str | None) -> int | None:
        p = parsear_ref(ref)
        if p is None:
            return None
        return p[1] if p[0] == "id" else self.ids.get(p[1])

    def contenido_actividad(self, payload: dict) -> dict:
        """El contenido de RAT de una actividad propuesta, con sus referencias como ids (reales o virtuales)."""
        c = completar({k: v for k, v in payload.items() if k not in ("elementos", "flujos")})
        elementos, flujos = [], []
        for ref in payload.get("elementos") or []:
            e = self.por_id.get(self.resolver(ref))
            if e is not None:
                elementos.append({"id": e.id, "categorias_datos": list(e.categorias_datos),
                                  "categorias_titulares": list(e.categorias_titulares)})
        for ref in payload.get("flujos") or []:
            f = self.flujo_por_id.get(self.resolver(ref))
            if f is not None:
                flujos.append({"id": f.id, "categorias_datos": list(f.categorias_datos),
                               "categorias_titulares": list(f.categorias_titulares)})
        c["elementos"], c["flujos"] = elementos, flujos
        return c


def _de_actividad(nombre: str, contenido: dict, elementos: list[Elemento], flujos: list[Flujo],
                  referencia: dict | None) -> tuple[list[dict], str | None]:
    deriv = rat_an.derivados(contenido, elementos, flujos)
    compl = rat_an.completitud(contenido, deriv)
    salida: list[dict] = []
    if deriv["hay_sensibles"] and not contenido.get("base_sensibles"):
        sensibles = ", ".join(t["nombre"].lower() for t in deriv["tipos_datos"] if t["sensible"])
        salida.append(_item("sensible_sin_base",
                            f"«{nombre}» usa datos sensibles ({sensibles}) y no indica la base que permite tratarlos. "
                            "Elige una base para datos sensibles (por ejemplo, una obligación laboral o el "
                            "consentimiento expreso).", referencia))
    sin_garantia = [t for t in deriv["transferencias"] if not t["garantia_valida"]]
    if sin_garantia:
        paises = ", ".join(sorted({t["pais_nombre"] for t in sin_garantia}))
        salida.append(_item("transferencia_sin_garantia",
                            f"«{nombre}» envía datos fuera de Chile ({paises}) sin una garantía registrada. Agrega en el "
                            "mapa la garantía del envío (por ejemplo, cláusulas contractuales tipo).", referencia,
                            "Crítica" if deriv["hay_sensibles"] else None))
    conservacion = compl["campos"].get("conservacion") or {}
    if deriv["tipos_datos"] and not conservacion.get("completo", True):
        salida.append(_item("actividad_sin_plazo",
                            f"«{nombre}»: {conservacion.get('faltante') or 'falta el plazo de conservación.'} Indica "
                            "cuánto tiempo guardas cada dato y desde cuándo se cuenta.", referencia))
    nivel = None
    if deriv["elementos"] or deriv["flujos"]:
        nivel = riesgos.evaluar(0, nombre, contenido, deriv, faltantes=len(compl["faltantes"])).nivel
    return salida, nivel


def evaluar_propuestas(nuevas: list[dict], pendientes: list[dict], elementos: list[Elemento], flujos: list[Flujo],
                       actividades: list[dict], alias: dict[str, int] | None = None) -> dict[str, dict]:
    """
    {clave: {"inconsistencias": [...], "riesgo": nivel | None}} para cada propuesta de `nuevas`.
    `nuevas` y `pendientes` (sugeridas): [{"tipo", "clave", "payload"}]. `actividades`: [{"estado", "contenido"}]
    del RAT. `alias`: {clave: id real} de las propuestas ya aceptadas (sus "nuevo:<clave>" apuntan al mapa).
    """
    todas = list(pendientes) + list(nuevas)
    mv = MapaVirtual(elementos, flujos, todas, alias)
    cubiertos_reales = cobertura.flujos_cubiertos(actividades)
    cubiertos_propuestos = {mv.resolver(r) for p in todas if p["tipo"] == "actividad"
                            for r in p["payload"].get("flujos") or []}
    salida: dict[str, dict] = {}
    for p in nuevas:
        ref = {"tipo": "propuesta", "clave": p["clave"]}
        items: list[dict] = []
        nivel = None
        if p["tipo"] == "flujo":
            vid = mv.ids.get(p["clave"])
            f = mv.flujo_por_id.get(vid)
            if f is not None:
                d = am.derivados_flujo(f, mv.por_id)
                if d.internacional and not d.garantia_valida:
                    items.append(_item("transferencia_sin_garantia",
                                       f"Este envío sale de Chile ({cat.nombre_pais(d.pais_destino)}) sin una garantía "
                                       "registrada. Indica la garantía (por ejemplo, cláusulas contractuales tipo) o "
                                       "confirma que el país tiene un nivel adecuado de protección.", ref,
                                       "Crítica" if f.sensibles or f.incluye_nna else None))
                if vid not in cubiertos_propuestos and vid not in cubiertos_reales:
                    items.append(_item("flujo_sin_actividad",
                                       "Este envío todavía no forma parte de ninguna actividad del registro. Acepta o crea "
                                       "la actividad que lo usa.", ref))
        elif p["tipo"] == "actividad":
            contenido = mv.contenido_actividad(p["payload"])
            items, nivel = _de_actividad(p["payload"].get("nombre") or "La actividad", contenido,
                                         mv.elementos, mv.flujos, ref)
        salida[p["clave"]] = {"inconsistencias": items, "riesgo": nivel}
    return salida


def globales(elementos: list[Elemento], flujos: list[Flujo], actividades: list[dict]) -> list[dict]:
    """
    Revisión del registro ACTUAL (lo ya guardado): las cuatro inconsistencias del criterio 2.
    `actividades`: [{"id", "nombre", "estado", "contenido"}] del RAT.
    """
    salida: list[dict] = []
    por_id = {e.id: e for e in elementos}
    for f in flujos:
        d = am.derivados_flujo(f, por_id)
        if d.internacional and not d.garantia_valida:
            o, de = por_id.get(f.origen_id), por_id.get(f.destino_id)
            salida.append(_item("transferencia_sin_garantia",
                                f"El envío de «{o.nombre if o else '?'}» a «{de.nombre if de else '?'}» sale de Chile "
                                f"({cat.nombre_pais(d.pais_destino)}) sin una garantía registrada.",
                                {"tipo": "flujo", "id": f.id}, "Crítica" if f.sensibles or f.incluye_nna else None))
    for f in cobertura.flujos_sin_actividad(flujos, actividades):
        o, de = por_id.get(f.origen_id), por_id.get(f.destino_id)
        salida.append(_item("flujo_sin_actividad",
                            f"El envío de «{o.nombre if o else '?'}» a «{de.nombre if de else '?'}» no forma parte de "
                            "ninguna actividad del registro.", {"tipo": "flujo", "id": f.id}))
    for a in actividades:
        if a.get("estado") == cobertura.ARCHIVADA:
            continue
        items, _ = _de_actividad(a.get("nombre") or "La actividad", completar(a.get("contenido")), elementos, flujos,
                                 {"tipo": "actividad", "id": a.get("id")})
        # La transferencia ya se informa por flujo
        salida += [i for i in items if i["codigo"] != "transferencia_sin_garantia"]
    orden = {"Crítica": 0, "Alta": 1, "Media": 2, "Baja": 3}
    return sorted(salida, key=lambda i: (orden.get(i["severidad"], 9), CODIGOS.index(i["codigo"])))
