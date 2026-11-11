"""
HU-34 · Lo que se calcula del mapa: transferencias internacionales, resumen, completitud,
hallazgos de riesgo, filtros del mapa navegable y la base para el RAT.

Todo es puro y determinista (mismo mapa → mismo resultado), así el panel, el PDF y el correo
dicen exactamente lo mismo. Las referencias normativas son orientativas (Ley N.º 21.719);
el informe aclara que no constituye asesoría legal.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos.modelo import Elemento, Flujo

SEVERIDADES = ("Crítica", "Alta", "Media", "Baja")
_ORDEN_SEV = {s: i for i, s in enumerate(SEVERIDADES)}
# Subtipos que normalmente viven en la nube de un tercero: sin país no se sabe si hay transferencia
_SUBTIPOS_NUBE = {"saas", "colaboracion", "nube_almacenamiento", "vectorial"}


# ============================================================ transferencias
def pais_efectivo(e: Elemento | None) -> str | None:
    """País de alojamiento; los sistemas y bases internas sin país se asumen en Chile."""
    if e is None:
        return None
    if e.pais:
        return e.pais
    return None if e.es_tercero or e.subtipo in _SUBTIPOS_NUBE else cat.PAIS_LOCAL


def es_internacional(pais_origen: str | None, pais_destino: str | None) -> bool:
    """Hay transferencia internacional cuando el destino está fuera de Chile y en otro país que el origen."""
    origen = pais_origen or cat.PAIS_LOCAL
    return bool(pais_destino) and pais_destino != cat.PAIS_LOCAL and pais_destino != origen


@dataclass(frozen=True)
class DerivadosFlujo:
    internacional: bool
    pais_origen: str | None
    pais_destino: str | None
    hacia_tercero: bool
    desde_tercero: bool
    sensibles: tuple[str, ...]
    incluye_nna: bool
    garantia_valida: bool

    def como_dict(self) -> dict:
        return {"internacional": self.internacional, "pais_origen": self.pais_origen,
                "pais_destino": self.pais_destino, "hacia_tercero": self.hacia_tercero,
                "desde_tercero": self.desde_tercero, "sensibles": list(self.sensibles),
                "incluye_nna": self.incluye_nna, "garantia_valida": self.garantia_valida}


def derivados_flujo(f: Flujo, por_id: dict[int, Elemento]) -> DerivadosFlujo:
    o, d = por_id.get(f.origen_id), por_id.get(f.destino_id)
    po, pd = pais_efectivo(o), pais_efectivo(d)
    return DerivadosFlujo(
        internacional=es_internacional(po, pd), pais_origen=po, pais_destino=pd,
        hacia_tercero=bool(d and d.es_tercero), desde_tercero=bool(o and o.es_tercero),
        sensibles=tuple(f.sensibles), incluye_nna=f.incluye_nna,
        garantia_valida=f.garantia in cat.GARANTIAS_VALIDAS,
    )


def derivados_elemento(e: Elemento, flujos: list[Flujo]) -> dict:
    entrantes = [f for f in flujos if f.destino_id == e.id]
    salientes = [f for f in flujos if f.origen_id == e.id]
    return {
        "sensibles": e.sensibles, "incluye_nna": e.incluye_nna, "fuera_de_chile": e.fuera_de_chile,
        "pais_efectivo": pais_efectivo(e), "flujos_entrantes": len(entrantes), "flujos_salientes": len(salientes),
    }


# ============================================================ resumen
def resumen(elementos: list[Elemento], flujos: list[Flujo]) -> dict:
    por_id = {e.id: e for e in elementos}
    der = [derivados_flujo(f, por_id) for f in flujos]
    paises = Counter(pais_efectivo(e) for e in elementos if pais_efectivo(e))
    categorias = {c for e in elementos for c in e.categorias_datos} | {c for f in flujos for c in f.categorias_datos}
    titulares = {c for e in elementos for c in e.categorias_titulares} | {c for f in flujos for c in f.categorias_titulares}
    return {
        "sistemas": sum(e.tipo == "sistema" for e in elementos),
        "bases_datos": sum(e.tipo == "base_datos" for e in elementos),
        "terceros": sum(e.tipo == "tercero" for e in elementos),
        "elementos": len(elementos),
        "flujos": len(flujos),
        "flujos_a_terceros": sum(d.hacia_tercero for d in der),
        "transferencias_internacionales": sum(d.internacional for d in der),
        "transferencias_sin_garantia": sum(d.internacional and not d.garantia_valida for d in der),
        "elementos_con_sensibles": sum(bool(e.sensibles) for e in elementos),
        "flujos_con_sensibles": sum(bool(f.sensibles) for f in flujos),
        "elementos_con_nna": sum(e.incluye_nna for e in elementos),
        "fuera_de_chile": sum(e.fuera_de_chile for e in elementos),
        "proveedores_ia": sum(e.es_tercero and e.subtipo == "proveedor_ia" for e in elementos),
        "categorias_en_uso": len(categorias),
        "categorias_sensibles_en_uso": len(categorias & cat.CODIGOS_SENSIBLES),
        "titulares_en_uso": len(titulares),
        "paises": [{"codigo": p, "nombre": cat.nombre_pais(p), "elementos": n}
                   for p, n in sorted(paises.items(), key=lambda x: (x[0] != cat.PAIS_LOCAL, -x[1], x[0]))],
        "pendientes_revision": sum(e.pendiente_revision for e in elementos) + sum(f.pendiente_revision for f in flujos),
    }


# ============================================================ completitud
def _faltantes_elemento(e: Elemento) -> list[str]:
    falta = []
    if not e.pais and pais_efectivo(e) is None:
        falta.append("país de alojamiento")
    if e.es_tercero:
        if not e.rol_tercero:
            falta.append("rol del tercero")
        elif e.rol_tercero in cat.ROLES_CON_CONTRATO and e.contrato_firmado is None:
            falta.append("si hay contrato firmado")
    else:
        if not e.responsable:
            falta.append("responsable interno")
        if not e.categorias_datos:
            falta.append("categorías de datos")
        if not e.categorias_titulares:
            falta.append("categorías de titulares")
    if not e.subtipo:
        falta.append("categoría del elemento")
    return falta


def _faltantes_flujo(f: Flujo, d: DerivadosFlujo) -> list[str]:
    falta = []
    if not f.finalidad:
        falta.append("finalidad")
    if not f.categorias_datos:
        falta.append("categorías de datos")
    if not f.categorias_titulares:
        falta.append("categorías de titulares")
    if f.cifrado is None:
        falta.append("si viaja cifrado")
    if d.internacional and not f.garantia:
        falta.append("garantía de la transferencia")
    return falta


def completitud(elementos: list[Elemento], flujos: list[Flujo]) -> dict:
    """Porcentaje de campos clave completos y lo que falta en cada elemento y flujo."""
    por_id = {e.id: e for e in elementos}
    pendientes = []
    total = completos = 0
    # Campos que se evalúan por elemento/flujo (para el porcentaje)
    for e in elementos:
        falta = _faltantes_elemento(e)
        campos = 4 if e.es_tercero else 6
        total += campos
        completos += max(0, campos - len(falta))
        if falta or e.pendiente_revision:
            pendientes.append({"tipo": "elemento", "id": e.id, "nombre": e.nombre, "faltan": falta,
                               "por_confirmar": e.pendiente_revision})
    for f in flujos:
        d = derivados_flujo(f, por_id)
        falta = _faltantes_flujo(f, d)
        campos = 5 if d.internacional else 4
        total += campos
        completos += max(0, campos - len(falta))
        if falta or f.pendiente_revision:
            o, de = por_id.get(f.origen_id), por_id.get(f.destino_id)
            pendientes.append({"tipo": "flujo", "id": f.id,
                               "nombre": f"{o.nombre if o else '?'} → {de.nombre if de else '?'}",
                               "faltan": falta, "por_confirmar": f.pendiente_revision})
    porcentaje = round(100 * completos / total) if total else 0
    return {"porcentaje": porcentaje, "pendientes": pendientes}


# ============================================================ hallazgos de riesgo
@dataclass
class Hallazgo:
    codigo: str
    severidad: str
    titulo: str
    detalle: str
    recomendacion: str
    referencia: str
    elementos: list[int] = field(default_factory=list)
    flujos: list[int] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "severidad": self.severidad, "titulo": self.titulo, "detalle": self.detalle,
                "recomendacion": self.recomendacion, "referencia": self.referencia,
                "elementos": self.elementos, "flujos": self.flujos}


def _pl(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _lista(nombres: list[str], maximo: int = 4) -> str:
    nombres = [f"«{n}»" for n in nombres]
    if len(nombres) <= maximo:
        return ", ".join(nombres[:-1]) + (" y " if len(nombres) > 1 else "") + nombres[-1] if nombres else ""
    return ", ".join(nombres[:maximo]) + f" y {len(nombres) - maximo} más"


def hallazgos(elementos: list[Elemento], flujos: list[Flujo]) -> list[Hallazgo]:
    """Riesgos de protección de datos que se desprenden del mapa, del más grave al más leve."""
    por_id = {e.id: e for e in elementos}
    der = {f.id: derivados_flujo(f, por_id) for f in flujos}
    nombre_flujo = {f.id: f"{por_id[f.origen_id].nombre} → {por_id[f.destino_id].nombre}"
                    for f in flujos if f.origen_id in por_id and f.destino_id in por_id}
    salida: list[Hallazgo] = []

    # 1. Transferencias internacionales sin garantía (las con datos sensibles o de NNA, críticas)
    sin_garantia = [f for f in flujos if der[f.id].internacional and not der[f.id].garantia_valida]
    criticas = [f for f in sin_garantia if f.sensibles or f.incluye_nna]
    altas = [f for f in sin_garantia if f not in criticas]
    ref_ti = "Ley N.º 21.719: transferencia internacional de datos (arts. 27 y 28)"
    rec_ti = ("Documenta la garantía de cada transferencia: país con nivel adecuado de protección, cláusulas "
              "contractuales tipo, normas corporativas vinculantes o el consentimiento expreso del titular.")
    if criticas:
        salida.append(Hallazgo(
            "transferencia_sensible_sin_garantia", "Crítica",
            "Datos sensibles o de menores salen del país sin una garantía documentada",
            f"{_pl(len(criticas), 'flujo envía', 'flujos envían')} datos sensibles o de niños, niñas y "
            f"adolescentes a otro país sin garantía: {_lista([nombre_flujo.get(f.id, '?') for f in criticas])}.",
            rec_ti + " Mientras tanto, evalúa suspender o minimizar los datos que se envían.", ref_ti,
            flujos=[f.id for f in criticas]))
    if altas:
        salida.append(Hallazgo(
            "transferencia_sin_garantia", "Alta", "Transferencias internacionales sin garantía documentada",
            f"{_pl(len(altas), 'flujo envía', 'flujos envían')} datos personales fuera de Chile sin una garantía "
            "registrada: "
            f"{_lista([nombre_flujo.get(f.id, '?') for f in altas])}.",
            rec_ti, ref_ti, flujos=[f.id for f in altas]))

    # 2. Proveedores de IA que reciben datos sensibles o de NNA
    ia = [f for f in flujos if f.destino_id in por_id and por_id[f.destino_id].es_tercero
          and por_id[f.destino_id].subtipo == "proveedor_ia" and (f.sensibles or f.incluye_nna)]
    if ia:
        salida.append(Hallazgo(
            "ia_externa_con_sensibles", "Crítica", "Un proveedor de IA externo recibe datos sensibles o de menores",
            f"{_lista(sorted({por_id[f.destino_id].nombre for f in ia}))} "
            f"{'recibe' if len({f.destino_id for f in ia}) == 1 else 'reciben'} datos sensibles o de niños, niñas "
            "y adolescentes. Lo que se envía a un modelo de lenguaje puede quedar en sus registros o usarse para "
            "entrenarlo si el contrato no lo impide.",
            "Anonimiza o seudonimiza los datos antes de enviarlos, verifica que el contrato prohíba usarlos para "
            "entrenar modelos, define su plazo de retención y evalúa una evaluación de impacto (EIPD).",
            "Ley N.º 21.719 (datos sensibles, art. 16, y de NNA, art. 16 quater) · OWASP Top 10 para LLM "
            "(divulgación de información sensible)",
            elementos=sorted({f.destino_id for f in ia}), flujos=[f.id for f in ia]))

    # 3. Terceros que reciben datos sin contrato firmado
    receptores = {f.destino_id for f in flujos}
    sin_contrato = [e for e in elementos if e.es_tercero and e.id in receptores
                    and (e.rol_tercero is None or e.rol_tercero in cat.ROLES_CON_CONTRATO)
                    and e.contrato_firmado is not True]
    if sin_contrato:
        con_sensibles = any(f.sensibles for f in flujos if f.destino_id in {e.id for e in sin_contrato})
        salida.append(Hallazgo(
            "tercero_sin_contrato", "Crítica" if con_sensibles else "Alta",
            "Terceros que reciben datos sin un contrato de tratamiento confirmado",
            f"{_lista([e.nombre for e in sin_contrato])} {'recibe' if len(sin_contrato) == 1 else 'reciben'} "
            "datos personales y no hay registrado un contrato firmado que regule el tratamiento.",
            "Firma un contrato o acuerdo de tratamiento de datos que fije la finalidad, las medidas de seguridad, la "
            "confidencialidad, la prohibición de usarlos para otros fines y su devolución o eliminación al término.",
            "Ley N.º 21.719: tratamiento por un encargado (art. 15 bis)", elementos=[e.id for e in sin_contrato]))

    # 4. Datos sensibles que viajan sin cifrar
    sin_cifrar = [f for f in flujos if f.sensibles and f.cifrado is False]
    if sin_cifrar:
        salida.append(Hallazgo(
            "sensibles_sin_cifrar", "Alta", "Datos sensibles que viajan sin cifrar",
            f"{_pl(len(sin_cifrar), 'flujo con datos sensibles no está cifrado', 'flujos con datos sensibles no están cifrados')} en tránsito: "
            f"{_lista([nombre_flujo.get(f.id, '?') for f in sin_cifrar])}.",
            "Cifra el canal (TLS 1.2 o superior, SFTP o VPN) y, si es posible, también el contenido.",
            "Ley N.º 21.719: deber de adoptar medidas de seguridad (art. 14 quinquies)",
            flujos=[f.id for f in sin_cifrar]))

    # 5. Niños, niñas y adolescentes
    nna = [e for e in elementos if e.incluye_nna]
    if nna:
        salida.append(Hallazgo(
            "tratamiento_nna", "Media", "Se tratan datos de niños, niñas y adolescentes",
            f"{_lista([e.nombre for e in nna])} {'trata' if len(nna) == 1 else 'tratan'} datos de menores de 18 años.",
            "Verifica la autorización de padres, madres o representantes legales cuando corresponda, aplica el "
            "interés superior del niño y limita los datos al mínimo indispensable.",
            "Ley N.º 21.719: datos personales de niños, niñas y adolescentes (art. 16 quater)",
            elementos=[e.id for e in nna]))

    # 6. Datos sensibles sin responsable interno
    sin_resp = [e for e in elementos if e.sensibles and not e.es_tercero and not e.responsable]
    if sin_resp:
        salida.append(Hallazgo(
            "sensibles_sin_responsable", "Media", "Datos sensibles sin un responsable interno asignado",
            f"{_lista([e.nombre for e in sin_resp])} "
            f"{'guarda datos sensibles y no tiene' if len(sin_resp) == 1 else 'guardan datos sensibles y no tienen'} "
            "un cargo o área responsable.",
            "Asigna un responsable (cargo o área) que responda por los accesos, la seguridad y la conservación.",
            "Ley N.º 21.719: principio de responsabilidad (art. 3)", elementos=[e.id for e in sin_resp]))

    # 7. Elementos sin país (no se puede saber si hay transferencia)
    sin_pais = [e for e in elementos if pais_efectivo(e) is None]
    if sin_pais:
        salida.append(Hallazgo(
            "pais_sin_informar", "Media", "Elementos sin país de alojamiento",
            f"No sabemos dónde están {_lista([e.nombre for e in sin_pais])}: sin el país no se puede saber si hay "
            "transferencias internacionales.",
            "Revisa el contrato o la configuración del servicio e indica el país donde se alojan los datos.",
            "Ley N.º 21.719: transferencia internacional de datos (arts. 27 y 28)",
            elementos=[e.id for e in sin_pais]))

    # 8. Flujos con datos sensibles cuyo cifrado se desconoce
    cifrado_desconocido = [f for f in flujos if f.sensibles and f.cifrado is None]
    if cifrado_desconocido:
        salida.append(Hallazgo(
            "sensibles_cifrado_desconocido", "Media", "No se sabe si los datos sensibles viajan cifrados",
            f"{_pl(len(cifrado_desconocido), 'flujo con datos sensibles no indica si está cifrado', 'flujos con datos sensibles no indican si están cifrados')}.",
            "Confirma con el área de TI o con el proveedor cómo se protege cada envío.",
            "Ley N.º 21.719: deber de adoptar medidas de seguridad (art. 14 quinquies)",
            flujos=[f.id for f in cifrado_desconocido]))

    # 9. Información incompleta
    sin_cat = [e for e in elementos if not e.es_tercero and not e.categorias_datos]
    flujos_sin_cat = [f for f in flujos if not f.categorias_datos]
    if sin_cat or flujos_sin_cat:
        partes = []
        if sin_cat:
            partes.append(_pl(len(sin_cat), "sistema o base de datos", "sistemas o bases de datos"))
        if flujos_sin_cat:
            partes.append(_pl(len(flujos_sin_cat), "flujo", "flujos"))
        salida.append(Hallazgo(
            "sin_categorias", "Baja", "Elementos sin categorías de datos",
            f"{' y '.join(partes)} no "
            f"{'indica' if len(sin_cat) + len(flujos_sin_cat) == 1 else 'indican'} qué datos personales tratan.",
            "Completa las categorías de datos y de titulares: son la base del registro de actividades de tratamiento.",
            "Ley N.º 21.719: principio de responsabilidad (art. 3)",
            elementos=[e.id for e in sin_cat], flujos=[f.id for f in flujos_sin_cat]))

    # 10. Elementos aislados
    conectados = {f.origen_id for f in flujos} | {f.destino_id for f in flujos}
    aislados = [e for e in elementos if e.id not in conectados]
    if aislados and len(elementos) > 1:
        salida.append(Hallazgo(
            "elemento_aislado", "Baja", "Elementos sin flujos",
            f"{_lista([e.nombre for e in aislados])} no "
            f"{'envía ni recibe' if len(aislados) == 1 else 'envían ni reciben'} datos de ningún otro elemento.",
            "Agrega los flujos que corresponden o confirma que el elemento realmente no comparte datos.",
            "Buena práctica de inventario de datos", elementos=[e.id for e in aislados]))

    salida.sort(key=lambda h: (_ORDEN_SEV[h.severidad], -(len(h.elementos) + len(h.flujos))))
    return salida


def contar_hallazgos(lista: list[Hallazgo]) -> dict[str, int]:
    c = Counter(h.severidad for h in lista)
    return {s: c.get(s, 0) for s in SEVERIDADES}


# ============================================================ filtros del mapa navegable
@dataclass(frozen=True)
class FiltrosMapa:
    sensibles: bool = False
    nna: bool = False
    internacional: bool = False
    tercero: int | None = None
    pais: str | None = None
    tipo: str | None = None

    @property
    def activos(self) -> bool:
        return any((self.sensibles, self.nna, self.internacional, self.tercero, self.pais, self.tipo))

    def describir(self, por_id: dict[int, Elemento] | None = None) -> str:
        partes = []
        if self.sensibles:
            partes.append("solo datos sensibles")
        if self.nna:
            partes.append("solo datos de niños, niñas y adolescentes")
        if self.internacional:
            partes.append("solo transferencias internacionales")
        if self.tercero:
            nombre = por_id[self.tercero].nombre if por_id and self.tercero in por_id else f"#{self.tercero}"
            partes.append(f"tercero «{nombre}»")
        if self.pais:
            partes.append(f"país {cat.nombre_pais(self.pais)}")
        if self.tipo:
            partes.append(f"tipo {cat.etiqueta('tipo', self.tipo).lower()}")
        return ", ".join(partes) if partes else "sin filtros"


def parsear_filtros(sensibles=None, nna=None, internacional=None, tercero=None, pais=None, tipo=None) -> FiltrosMapa:
    def si(v) -> bool:
        return str(v).strip().lower() in ("1", "true", "si", "sí") if v is not None else False

    t = None
    if tercero not in (None, ""):
        try:
            t = int(tercero)
        except (TypeError, ValueError):
            t = None
    p = (pais or "").strip().upper() or None
    return FiltrosMapa(si(sensibles), si(nna), si(internacional), t if t and t > 0 else None,
                       p if p in cat.NOMBRE_PAIS else None, tipo if tipo in cat.TIPOS else None)


def aplicar_filtros(elementos: list[Elemento], flujos: list[Flujo],
                    filtros: FiltrosMapa) -> tuple[set[int], set[int]]:
    """
    Ids de los elementos y flujos que cumplen TODOS los filtros activos. Un flujo que cumple
    arrastra a sus dos extremos (así nunca queda una flecha suelta en el mapa).
    """
    por_id = {e.id: e for e in elementos}
    if not filtros.activos:
        return set(por_id), {f.id for f in flujos}
    der = {f.id: derivados_flujo(f, por_id) for f in flujos}
    vecinos: dict[int, set[int]] = defaultdict(set)
    for f in flujos:
        vecinos[f.origen_id].add(f.destino_id)
        vecinos[f.destino_id].add(f.origen_id)
    internacionales_por_elemento = defaultdict(bool)
    for f in flujos:
        if der[f.id].internacional:
            internacionales_por_elemento[f.origen_id] = internacionales_por_elemento[f.destino_id] = True

    def ok_elemento(e: Elemento) -> bool:
        if filtros.sensibles and not e.sensibles:
            return False
        if filtros.nna and not e.incluye_nna:
            return False
        if filtros.internacional and not (internacionales_por_elemento[e.id] or e.fuera_de_chile):
            return False
        if filtros.tercero and not (e.id == filtros.tercero or filtros.tercero in vecinos[e.id]):
            return False
        if filtros.pais and pais_efectivo(e) != filtros.pais:
            return False
        if filtros.tipo and e.tipo != filtros.tipo:
            return False
        return True

    def ok_flujo(f: Flujo) -> bool:
        d = der[f.id]
        if filtros.sensibles and not f.sensibles:
            return False
        if filtros.nna and not f.incluye_nna:
            return False
        if filtros.internacional and not d.internacional:
            return False
        if filtros.tercero and filtros.tercero not in (f.origen_id, f.destino_id):
            return False
        if filtros.pais and filtros.pais not in (d.pais_origen, d.pais_destino):
            return False
        if filtros.tipo and not any(por_id.get(x) and por_id[x].tipo == filtros.tipo
                                    for x in (f.origen_id, f.destino_id)):
            return False
        return True

    ids_flujos = {f.id for f in flujos if ok_flujo(f)}
    ids_elementos = {e.id for e in elementos if ok_elemento(e)}
    for f in flujos:
        if f.id in ids_flujos:
            ids_elementos |= {f.origen_id, f.destino_id}
    return ids_elementos & set(por_id), ids_flujos


# ============================================================ base para el RAT
def base_rat(elementos: list[Elemento], flujos: list[Flujo]) -> list[dict]:
    """
    Por categoría de datos: dónde está, de qué titulares, con quién se comparte y en qué países.
    Es la vista que después alimenta el registro de actividades de tratamiento (mismos códigos).
    """
    por_id = {e.id: e for e in elementos}
    filas: dict[str, dict] = {}

    def fila(codigo: str) -> dict:
        if codigo not in filas:
            filas[codigo] = {"codigo": codigo, "nombre": cat.nombre_dato(codigo), "sensible": cat.es_sensible(codigo),
                             "elementos": set(), "terceros": set(), "titulares": set(), "paises": set(),
                             "internacional": False}
        return filas[codigo]

    for e in elementos:
        for c in e.categorias_datos:
            r = fila(c)
            (r["terceros"] if e.es_tercero else r["elementos"]).add(e.nombre)
            r["titulares"] |= set(e.categorias_titulares)
            if pais_efectivo(e):
                r["paises"].add(pais_efectivo(e))
    for f in flujos:
        d = derivados_flujo(f, por_id)
        for c in f.categorias_datos:
            r = fila(c)
            destino = por_id.get(f.destino_id)
            if destino is not None:
                (r["terceros"] if destino.es_tercero else r["elementos"]).add(destino.nombre)
            r["titulares"] |= set(f.categorias_titulares)
            r["paises"] |= {p for p in (d.pais_origen, d.pais_destino) if p}
            r["internacional"] = r["internacional"] or d.internacional
    orden = {c.codigo: i for i, c in enumerate(cat.CATEGORIAS_DATOS)}
    salida = []
    for codigo in sorted(filas, key=lambda c: (not cat.es_sensible(c), orden.get(c, 999))):
        r = filas[codigo]
        salida.append({**r, "elementos": sorted(r["elementos"]), "terceros": sorted(r["terceros"]),
                       "titulares": [cat.nombre_titular(t) for t in sorted(r["titulares"])],
                       "paises": [cat.nombre_pais(p) for p in sorted(r["paises"], key=lambda p: (p != cat.PAIS_LOCAL, p))]})
    return salida
