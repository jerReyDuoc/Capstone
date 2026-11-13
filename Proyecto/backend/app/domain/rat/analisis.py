"""
HU-35 · Lo que una actividad toma del mapa de datos y su completitud.

Criterio 2 — sin doble ingreso: la actividad solo guarda los ids de los sistemas, bases, terceros y
flujos que eligió del mapa (y el subconjunto de categorías que usa). Los tipos de datos, titulares,
países, terceros destinatarios y transferencias internacionales se CALCULAN aquí con el mapa actual,
así que un cambio en el mapa se refleja solo (y la actividad pasa a revisión: app/application/rat).

Criterio 3 — completitud: 13 campos (los 11 del reglamento, las medidas de seguridad y el rol).
Algunos son condicionales: el interés legítimo solo si esa es la base, la base para datos sensibles
solo si hay sensibles, la garantía solo si hay transferencias, la lógica solo si hay decisiones
automatizadas y la organización mandante solo si la empresa es encargada. "No aplica" (sin
destinatarios, sin decisiones automatizadas) se responde de forma explícita y cuenta como completo.
"""
from __future__ import annotations

from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.mapa_datos import analisis as am
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import catalogo as cat
from app.domain.rat.modelo import completar

_ORDEN_DATOS = {c.codigo: i for i, c in enumerate(cat_mapa.CATEGORIAS_DATOS)}
_ORDEN_TITULARES = {c.codigo: i for i, c in enumerate(cat_mapa.CATEGORIAS_TITULARES)}


def _ordenar_datos(codigos) -> list[str]:
    return sorted(set(codigos), key=lambda c: (not cat_mapa.es_sensible(c), _ORDEN_DATOS.get(c, 999)))


def _efectivas(elegidas: list[str], disponibles: list[str]) -> list[str]:
    """Las categorías elegidas que el elemento o flujo del mapa todavía tiene."""
    d = set(disponibles)
    return [c for c in elegidas if c in d]


def nombre_flujo(f: Flujo, por_id: dict[int, Elemento]) -> str:
    o, d = por_id.get(f.origen_id), por_id.get(f.destino_id)
    return f"{o.nombre if o else '?'} → {d.nombre if d else '?'}"


def derivados(contenido: dict, elementos: list[Elemento], flujos: list[Flujo]) -> dict:
    """Todo lo que la actividad obtiene del mapa (con los nombres actuales)."""
    c = completar(contenido)
    por_id = {e.id: e for e in elementos}
    flujo_por_id = {f.id: f for f in flujos}

    sel_elementos, sel_flujos, faltan = [], [], []
    datos: set[str] = set()
    titulares: set[str] = set()
    paises: set[str] = set()
    terceros: dict[int, dict] = {}
    transferencias: list[dict] = []
    fuera_sin_flujo: list[dict] = []

    for item in c["elementos"]:
        e = por_id.get(item["id"])
        if e is None:
            faltan.append({"tipo": "elemento", "id": item["id"]})
            continue
        cd = _efectivas(item["categorias_datos"], e.categorias_datos)
        ct = _efectivas(item["categorias_titulares"], e.categorias_titulares)
        datos |= set(cd)
        titulares |= set(ct)
        pais = am.pais_efectivo(e)
        if pais:
            paises.add(pais)
        sel_elementos.append({
            "id": e.id, "tipo": e.tipo, "nombre": e.nombre, "pais": pais, "categorias_datos": _ordenar_datos(cd),
            "categorias_titulares": sorted(ct, key=lambda t: _ORDEN_TITULARES.get(t, 999)),
            "disponibles_datos": list(e.categorias_datos), "disponibles_titulares": list(e.categorias_titulares),
            "sensibles": cat_mapa.sensibles_de(cd), "rol_tercero": e.rol_tercero,
        })
        if e.es_tercero:
            terceros[e.id] = {"id": e.id, "nombre": e.nombre, "pais": pais, "rol_tercero": e.rol_tercero,
                              "contrato_firmado": e.contrato_firmado}

    for item in c["flujos"]:
        f = flujo_por_id.get(item["id"])
        if f is None:
            faltan.append({"tipo": "flujo", "id": item["id"]})
            continue
        cd = _efectivas(item["categorias_datos"], f.categorias_datos)
        ct = _efectivas(item["categorias_titulares"], f.categorias_titulares)
        datos |= set(cd)
        titulares |= set(ct)
        d = am.derivados_flujo(f, por_id)
        for p in (d.pais_origen, d.pais_destino):
            if p:
                paises.add(p)
        destino = por_id.get(f.destino_id)
        if destino is not None and destino.es_tercero:
            terceros.setdefault(destino.id, {"id": destino.id, "nombre": destino.nombre, "pais": d.pais_destino,
                                             "rol_tercero": destino.rol_tercero,
                                             "contrato_firmado": destino.contrato_firmado})
        nombre = nombre_flujo(f, por_id)
        sel_flujos.append({
            "id": f.id, "nombre": nombre, "origen_id": f.origen_id, "destino_id": f.destino_id,
            "categorias_datos": _ordenar_datos(cd),
            "categorias_titulares": sorted(ct, key=lambda t: _ORDEN_TITULARES.get(t, 999)),
            "disponibles_datos": list(f.categorias_datos), "disponibles_titulares": list(f.categorias_titulares),
            "internacional": d.internacional, "pais_origen": d.pais_origen, "pais_destino": d.pais_destino,
            "garantia": f.garantia, "garantia_valida": d.garantia_valida,
        })
        if d.internacional:
            transferencias.append({"flujo_id": f.id, "nombre": nombre, "pais_destino": d.pais_destino,
                                   "pais_nombre": cat_mapa.nombre_pais(d.pais_destino), "garantia": f.garantia,
                                   "garantia_nombre": cat_mapa.etiqueta("garantia", f.garantia) if f.garantia else "",
                                   "garantia_valida": d.garantia_valida})

    # Elementos elegidos fuera de Chile sin un flujo internacional elegido que llegue a ellos (aviso)
    destinos_con_flujo = {flujo_por_id[t["flujo_id"]].destino_id for t in transferencias}
    for e in sel_elementos:
        if e["pais"] and e["pais"] != cat_mapa.PAIS_LOCAL and e["id"] not in destinos_con_flujo:
            fuera_sin_flujo.append({"id": e["id"], "nombre": e["nombre"], "pais": e["pais"],
                                    "pais_nombre": cat_mapa.nombre_pais(e["pais"])})

    # HU-38: sistemas, bases o proveedores con IA que usa la actividad (elegidos o extremos de un flujo
    # elegido). No es parte de la instantánea (versiones._CAMPOS_DERIVADOS).
    ia = sistemas_ia_en({"elementos": sel_elementos, "flujos": sel_flujos}, elementos)

    datos_ord = _ordenar_datos(datos)
    titulares_ord = sorted(titulares, key=lambda t: _ORDEN_TITULARES.get(t, 999))
    return {
        "elementos": sel_elementos,
        "flujos": sel_flujos,
        "no_encontrados": faltan,
        "tipos_datos": [{"codigo": x, "nombre": cat_mapa.nombre_dato(x), "sensible": cat_mapa.es_sensible(x)}
                        for x in datos_ord],
        "hay_sensibles": any(cat_mapa.es_sensible(x) for x in datos_ord),
        "titulares": [{"codigo": t, "nombre": cat_mapa.nombre_titular(t),
                       "nna": t in cat_mapa.CODIGOS_TITULARES_NNA} for t in titulares_ord],
        "incluye_nna": bool(cat_mapa.titulares_nna(titulares_ord)),
        "bases_datos": [{"id": e["id"], "nombre": e["nombre"], "tipo": e["tipo"]} for e in sel_elementos
                        if e["tipo"] in ("sistema", "base_datos")],
        "paises": [{"codigo": p, "nombre": cat_mapa.nombre_pais(p)}
                   for p in sorted(paises, key=lambda p: (p != cat_mapa.PAIS_LOCAL, p))],
        "terceros": sorted(terceros.values(), key=lambda t: t["nombre"].lower()),
        "transferencias": transferencias,
        "fuera_de_chile_sin_flujo": fuera_sin_flujo,
        "sistemas_ia": ia,
    }


def sistemas_ia_en(mapa: dict, elementos: list[Elemento]) -> list[dict]:
    """
    HU-38: los sistemas con IA de lo que la actividad toma del mapa (derivados o la instantánea de una
    versión vigente, que guarda los ids), según el subtipo ACTUAL de cada elemento en el mapa.
    """
    por_id = {e.id: e for e in elementos}
    ids = [x.get("id") for x in mapa.get("elementos") or []]
    ids += [i for x in mapa.get("flujos") or [] for i in (x.get("origen_id"), x.get("destino_id"))]
    salida: dict[int, dict] = {}
    for i in ids:
        e = por_id.get(i)
        if e is not None and e.subtipo in cat_mapa.SUBTIPOS_IA and e.id not in salida:
            salida[e.id] = {"id": e.id, "nombre": e.nombre,
                            "subtipo_nombre": cat_mapa.etiqueta_subtipo(e.tipo, e.subtipo)}
    return sorted(salida.values(), key=lambda x: x["nombre"].lower())


# ============================================================ completitud
def _estado(completo: bool, faltante: str | None = None, aplica: bool = True) -> dict:
    return {"completo": completo, "faltante": None if completo else faltante, "aplica": aplica}


def completitud(contenido: dict, deriv: dict) -> dict:
    """
    {porcentaje, completos, total, campos: {codigo: {completo, faltante, aplica, titulo, paso}},
     faltantes: [{codigo, titulo, paso, mensaje}], puede_quedar_vigente, advertencias: [texto]}
    """
    c = completar(contenido)
    no_encontrados = deriv["no_encontrados"]
    aviso_mapa = ("Algo que elegiste ya no está en el mapa de datos: quítalo o elige otro."
                  if no_encontrados else None)
    r: dict[str, dict] = {}

    sin_categorias = [x["nombre"] for x in deriv["elementos"] + deriv["flujos"] if not x["categorias_datos"]]
    if not deriv["tipos_datos"]:
        r["tipos_datos"] = _estado(False, "Elige del mapa los sistemas o flujos y qué datos usa la actividad.")
    elif no_encontrados:
        r["tipos_datos"] = _estado(False, aviso_mapa)
    else:
        r["tipos_datos"] = _estado(True)

    r["ambito"] = _estado(bool(deriv["paises"]),
                          "Indica en el mapa el país de los sistemas elegidos." if deriv["elementos"] or deriv["flujos"]
                          else "Elige del mapa los sistemas de la actividad para calcular en qué países se tratan.")

    if not deriv["bases_datos"]:
        r["bases_datos"] = _estado(False, "Elige al menos un sistema o una base de datos del mapa.")
    elif any(x["tipo"] == "elemento" for x in no_encontrados):
        r["bases_datos"] = _estado(False, aviso_mapa)
    else:
        r["bases_datos"] = _estado(True)

    r["titulares"] = _estado(bool(deriv["titulares"]),
                             "Elige de quiénes son los datos (en cada sistema o flujo elegido).")

    r["finalidades"] = _estado(bool(c["finalidades"]), "Escribe al menos una finalidad.")
    r["fuentes"] = _estado(bool(c["fuentes"]), "Indica al menos una fuente de los datos.")

    base = c["base_licitud"]
    if not base:
        r["base_licitud"] = _estado(False, "Elige la base de licitud.")
    elif base == cat.INTERES_LEGITIMO and not c["interes_legitimo"]:
        r["base_licitud"] = _estado(False, "Describe el interés legítimo y cómo lo ponderaste con los derechos de "
                                           "las personas.")
    elif deriv["hay_sensibles"] and not c["base_sensibles"]:
        r["base_licitud"] = _estado(False, "La actividad usa datos sensibles: indica la base que permite tratarlos.")
    else:
        r["base_licitud"] = _estado(True)

    if deriv["terceros"]:
        r["destinatarios"] = _estado(True)
    else:
        r["destinatarios"] = _estado(bool(c["sin_destinatarios"]),
                                     "Elige del mapa los terceros que reciben los datos o confirma que no se "
                                     "comparten con nadie.")

    sin_garantia = [t["nombre"] for t in deriv["transferencias"] if not t["garantia_valida"]]
    if not (deriv["elementos"] or deriv["flujos"]):
        r["transferencias"] = _estado(False, "Elige del mapa los sistemas y flujos de la actividad para saber si los "
                                             "datos salen de Chile.")
    elif sin_garantia:
        r["transferencias"] = _estado(False, "Registra en el mapa la garantía de "
                                             + ("la transferencia " if len(sin_garantia) == 1 else "las transferencias ")
                                             + ", ".join(sin_garantia[:3]) + ("…" if len(sin_garantia) > 3 else "") + ".")
    elif any(x["tipo"] == "flujo" for x in no_encontrados):
        r["transferencias"] = _estado(False, aviso_mapa)
    else:
        r["transferencias"] = _estado(True, aplica=bool(deriv["transferencias"]))

    categorias = [t["codigo"] for t in deriv["tipos_datos"]]
    plazos = {p["categoria"]: p for p in c["plazos"]}
    sin_plazo = [cat_mapa.nombre_dato(x) for x in categorias
                 if not (plazos.get(x) and plazos[x].get("plazo") and plazos[x].get("unidad"))]
    if not categorias:
        r["conservacion"] = _estado(False, "Primero elige los datos de la actividad; luego indica cuánto se guarda cada uno.")
    elif sin_plazo:
        r["conservacion"] = _estado(False, "Falta el plazo de: " + ", ".join(sin_plazo[:4])
                                    + ("…" if len(sin_plazo) > 4 else "") + ".")
    else:
        r["conservacion"] = _estado(True)

    d = c["decisiones"]
    if d["existe"] is None:
        r["decisiones"] = _estado(False, "Indica si la actividad toma decisiones automatizadas o arma perfiles.")
    elif d["existe"] and not d["logica"]:
        r["decisiones"] = _estado(False, "Explica la lógica de la decisión automatizada o del perfilamiento.")
    else:
        r["decisiones"] = _estado(True, aplica=bool(d["existe"]))

    m = c["medidas"]
    r["medidas"] = _estado(bool(m["codigos"] or m["otras"]), "Marca al menos una medida de seguridad.")

    if not c["rol"]:
        r["rol"] = _estado(False, "Indica si tu empresa es responsable o encargada.")
    elif c["rol"] == "encargado" and not c["responsable_mandante"]:
        r["rol"] = _estado(False, "Indica por cuenta de qué organización trata los datos tu empresa.")
    else:
        r["rol"] = _estado(True)

    campos = {}
    faltantes = []
    for campo in cat.CAMPOS:
        e = {**r[campo.codigo], "titulo": campo.titulo, "paso": campo.paso}
        campos[campo.codigo] = e
        if not e["completo"]:
            faltantes.append({"codigo": campo.codigo, "titulo": campo.titulo, "paso": campo.paso,
                              "mensaje": e["faltante"]})
    completos = len(cat.CAMPOS) - len(faltantes)

    advertencias: list[str] = []
    if sin_categorias:
        advertencias.append("No elegiste qué datos usa la actividad en: " + ", ".join(sin_categorias[:4])
                            + ("…" if len(sin_categorias) > 4 else "") + ".")
    for e in deriv["fuera_de_chile_sin_flujo"]:
        advertencias.append(f"{e['nombre']} está en {e['pais_nombre']}: si los datos viajan hasta allí, elige o "
                            "registra en el mapa ese flujo para documentar la transferencia y su garantía.")
    if deriv["incluye_nna"]:
        advertencias.append("La actividad incluye datos de niños, niñas o adolescentes: su interés superior debe "
                            "guiar el tratamiento.")
    if deriv["hay_sensibles"] and c["base_licitud"] == cat.INTERES_LEGITIMO:
        advertencias.append("El interés legítimo no basta para tratar datos sensibles: revisa la base para esos datos.")
    if c["decisiones"]["existe"] and c["decisiones"]["intervencion_humana"] is None:
        advertencias.append("Indica si una persona puede revisar las decisiones automatizadas: los titulares pueden "
                            "pedirlo.")
    sin_contrato = [t["nombre"] for t in deriv["terceros"] if t.get("rol_tercero") == "encargado"
                    and t.get("contrato_firmado") is not True]
    if sin_contrato:
        advertencias.append("Revisa el contrato de tratamiento con: " + ", ".join(sin_contrato[:4]) + ".")

    return {
        "porcentaje": round(100 * completos / len(cat.CAMPOS)),
        "completos": completos,
        "total": len(cat.CAMPOS),
        "campos": campos,
        "faltantes": faltantes,
        "puede_quedar_vigente": not faltantes,
        "advertencias": advertencias,
    }


def completitud_global(porcentajes: list[int]) -> dict:
    """Promedio de las actividades consideradas (sin las archivadas: el llamador las excluye)."""
    if not porcentajes:
        return {"porcentaje": 0, "actividades": 0, "completas": 0}
    return {"porcentaje": round(sum(porcentajes) / len(porcentajes)), "actividades": len(porcentajes),
            "completas": sum(1 for p in porcentajes if p == 100)}
