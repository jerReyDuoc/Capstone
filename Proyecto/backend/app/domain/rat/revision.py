"""
HU-40 · Revisión interna del registro (lógica PURA: sin BD, sin red).

El usuario definitivo, en su función de auditoría interna, recorre una lista de verificación por actividad
del registro y por elemento y flujo del mapa de datos. Cada punto tiene:

  resultado   lo que la plataforma comprueba sola: cumple | advertencia | falla | no_aplica.
  pregunta    lo que la persona debe confirmar mirando la realidad de su empresa (la plataforma no puede
              saber si lo declarado es verdad: por eso la revisión la hace una persona).
  revisión    lo que la persona decidió: pendiente | verificado | aceptado (una falla o advertencia que se
              asume con una justificación escrita) | desactualizado (el elemento cambió después de
              verificarlo: hay que mirarlo de nuevo).

Qué revisa (criterio 1):
  Actividades   versión vigente y al día · campos obligatorios completos · base de licitud · plazos de
                conservación · transferencias internacionales con garantía · contrato con los terceros
                que tratan datos por encargo · revisión humana de las decisiones automatizadas.
  Elementos     ficha completa · confirmado por la empresa · considerado en el registro · contrato
                (terceros que tratan datos por encargo).
  Flujos        ficha completa · confirmado · transferencia con garantía · viaja cifrado · considerado en
                el registro.

Reglas para marcar la versión como revisada (criterios 2 y 3):
  - sin observaciones abiertas;
  - todos los puntos que aplican, revisados (verificados o aceptados con justificación) y al día;
  - ningún punto BLOQUEANTE en falla: una actividad sin versión vigente o con campos obligatorios vacíos no
    se puede aceptar (el informe saldría como borrador);
  - al menos una actividad en el registro.

Cada elemento revisado tiene su HUELLA (lo que dice hoy y el resultado de cada punto): si cambia después de
verificarlo, sus verificaciones quedan "desactualizadas" sin que nadie tenga que acordarse.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Iterable, Protocol

from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.mapa_datos import analisis as am
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import catalogo as cat

CUMPLE, ADVERTENCIA, FALLA, NO_APLICA = "cumple", "advertencia", "falla", "no_aplica"
RESULTADOS = (CUMPLE, ADVERTENCIA, FALLA, NO_APLICA)
PENDIENTE, VERIFICADO, ACEPTADO, DESACTUALIZADO = "pendiente", "verificado", "aceptado", "desactualizado"
DECISIONES = (VERIFICADO, ACEPTADO, PENDIENTE)

MIN_NOTA = 10
MAX_NOTA = 1000
FORMATO_HUELLA = 1


# ============================================================ criterios
@dataclass(frozen=True)
class Criterio:
    codigo: str
    titulo: str
    pregunta: str               # lo que la persona confirma (no lo puede saber la plataforma)
    bloqueante: bool = False    # una falla aquí no se puede aceptar: hay que corregirla


CRITERIOS_ACTIVIDAD: tuple[Criterio, ...] = (
    Criterio("vigencia", "Versión vigente y al día",
             "¿La actividad se sigue realizando tal como la describe su versión vigente?", bloqueante=True),
    Criterio("campos", "Campos obligatorios completos",
             "¿Lo que dice cada campo coincide con lo que de verdad hace la empresa (finalidades, datos, "
             "titulares, fuentes y medidas de seguridad)?", bloqueante=True),
    Criterio("base_licitud", "Base de licitud",
             "¿La base de licitud corresponde a cómo se obtienen y usan realmente los datos? Si es el "
             "consentimiento, ¿existe y se puede demostrar?"),
    Criterio("plazos", "Plazos de conservación",
             "¿Los datos se eliminan o anonimizan al cumplirse el plazo? ¿El fundamento del plazo es correcto?"),
    Criterio("transferencias", "Transferencias internacionales con garantía",
             "¿La garantía registrada (cláusulas, país adecuado u otra) existe y está firmada o vigente?"),
    Criterio("terceros", "Terceros con contrato",
             "¿Hay un contrato de tratamiento firmado con cada tercero que trata los datos por encargo?"),
    Criterio("decisiones", "Decisiones automatizadas",
             "¿Una persona puede revisar las decisiones automatizadas cuando el titular lo pide?"),
)

CRITERIOS_ELEMENTO: tuple[Criterio, ...] = (
    Criterio("ficha", "Ficha completa",
             "¿El país, el responsable interno y los datos que guarda el elemento son los reales?"),
    Criterio("confirmado", "Confirmado por tu empresa",
             "¿El elemento existe y se usa? Las propuestas de una plantilla o del asistente se confirman aquí."),
    Criterio("en_registro", "Considerado en el registro",
             "Si el elemento guarda o recibe datos personales, ¿alguna actividad del registro lo usa?"),
    Criterio("contrato", "Contrato de tratamiento",
             "¿El contrato con el tercero está firmado y regula el tratamiento por encargo?"),
)

CRITERIOS_FLUJO: tuple[Criterio, ...] = (
    Criterio("ficha", "Ficha completa",
             "¿La finalidad, los datos y la frecuencia del envío son los reales?"),
    Criterio("confirmado", "Confirmado por tu empresa",
             "¿Este envío de datos ocurre realmente? Las propuestas se confirman aquí."),
    Criterio("garantia", "Transferencia con garantía",
             "Si los datos salen de Chile, ¿la garantía registrada existe y está vigente?"),
    Criterio("cifrado", "Viaja protegido",
             "¿Los datos viajan cifrados o por un canal seguro?"),
    Criterio("en_registro", "Considerado en el registro",
             "¿Alguna actividad del registro explica para qué se envían estos datos?"),
)

CRITERIOS = {"actividad": {c.codigo: c for c in CRITERIOS_ACTIVIDAD},
             "elemento": {c.codigo: c for c in CRITERIOS_ELEMENTO},
             "flujo": {c.codigo: c for c in CRITERIOS_FLUJO}}

TITULO_RESULTADO = {CUMPLE: "Cumple", ADVERTENCIA: "Advertencia", FALLA: "Falla", NO_APLICA: "No aplica"}
TITULO_REVISION = {PENDIENTE: "Pendiente", VERIFICADO: "Verificado", ACEPTADO: "Aceptado con justificación",
                   DESACTUALIZADO: "Cambió desde que lo revisaste"}
TITULO_TIPO = {"actividad": "Actividad", "elemento": "Elemento del mapa", "flujo": "Flujo del mapa",
               "registro": "Registro completo"}


class ErrorRevision(ValueError):
    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


# ============================================================ entradas
class ActividadRevisable(Protocol):
    """Lo que necesita la revisión de cada actividad (lo cumple ActividadInforme de app/application/rat)."""
    id: int
    nombre: str
    estado: str
    origen: str               # "vigente" (versión fija) | "trabajo" (nunca estuvo vigente)
    version: int | None
    huella_version: str | None
    pendiente: str | None
    contenido: dict
    mapa: dict
    faltantes: tuple


@dataclass(frozen=True)
class Item:
    codigo: str
    titulo: str
    resultado: str
    detalle: str
    pregunta: str
    bloqueante: bool = False

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Objeto:
    clave: str               # "actividad:12" | "elemento:5" | "flujo:9"
    tipo: str
    id: int
    nombre: str
    subtitulo: str
    items: tuple[Item, ...]
    huella: str
    paso: int | None = None  # paso del formulario de la actividad donde se corrige (si aplica)

    def como_dict(self) -> dict:
        return {"clave": self.clave, "tipo": self.tipo, "id": self.id, "nombre": self.nombre,
                "subtitulo": self.subtitulo, "huella": self.huella, "paso": self.paso,
                "items": [i.como_dict() for i in self.items]}


def _item(criterio: Criterio, resultado: str, detalle: str) -> Item:
    return Item(criterio.codigo, criterio.titulo, resultado, detalle, criterio.pregunta, criterio.bloqueante)


def _lista(nombres: Iterable[str], maximo: int = 4) -> str:
    n = [x for x in nombres if x]
    if len(n) <= maximo:
        return ", ".join(n[:-1]) + (" y " if len(n) > 1 else "") + (n[-1] if n else "")
    return ", ".join(n[:maximo]) + f" y {len(n) - maximo} más"


def _huella(datos) -> str:
    texto = json.dumps({"formato": FORMATO_HUELLA, "datos": datos}, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ============================================================ actividades
_PASO = {"vigencia": None, "campos": 1, "base_licitud": 3, "plazos": 5, "transferencias": 4, "terceros": 4,
         "decisiones": 5}


def _faltantes_actividad(a: ActividadRevisable) -> list[str]:
    """Campos obligatorios vacíos según lo que AFIRMA la actividad (versión vigente o copia de trabajo)."""
    if a.origen == "trabajo":
        return list(a.faltantes)
    c, m = a.contenido, a.mapa
    falta = []
    if not c.get("finalidades"):
        falta.append("finalidades")
    if not m.get("tipos_datos"):
        falta.append("tipos de datos")
    if not m.get("titulares"):
        falta.append("categorías de titulares")
    if not m.get("bases_datos"):
        falta.append("sistemas y bases de datos")
    if not c.get("fuentes"):
        falta.append("fuentes de los datos")
    if not (m.get("terceros") or c.get("sin_destinatarios")):
        falta.append("terceros destinatarios")
    medidas = c.get("medidas") or {}
    if not (medidas.get("codigos") or medidas.get("otras")):
        falta.append("medidas de seguridad")
    if not c.get("rol") or (c.get("rol") == "encargado" and not c.get("responsable_mandante")):
        falta.append("rol de la empresa")
    if (c.get("decisiones") or {}).get("existe") is None:
        falta.append("decisiones automatizadas")
    return falta


def items_actividad(a: ActividadRevisable) -> list[Item]:
    K = CRITERIOS["actividad"]
    c, m = a.contenido, a.mapa
    items: list[Item] = []

    # vigencia
    if a.origen == "trabajo":
        items.append(_item(K["vigencia"], FALLA, (a.pendiente or "Todavía no tiene una versión vigente") + "."))
    elif a.estado != cat.VIGENTE:
        items.append(_item(K["vigencia"], FALLA, (a.pendiente or "No está vigente") + ". Déjala vigente otra vez."))
    else:
        items.append(_item(K["vigencia"], CUMPLE, f"Versión N.º {a.version} vigente."))

    # campos obligatorios
    falta = _faltantes_actividad(a)
    items.append(_item(K["campos"], FALLA if falta else CUMPLE,
                       ("Faltan: " + _lista(f.lower() for f in falta) + ".") if falta
                       else f"Los {len(cat.CAMPOS)} campos del registro tienen información."))

    # base de licitud
    base = c.get("base_licitud")
    sensibles = [t for t in m.get("tipos_datos") or [] if t.get("sensible")]
    nombre_base = cat.nombre(cat.BASES_POR_CODIGO, base) if base else ""
    if not base:
        items.append(_item(K["base_licitud"], FALLA, "No tiene base de licitud."))
    elif base == cat.INTERES_LEGITIMO and not c.get("interes_legitimo"):
        items.append(_item(K["base_licitud"], FALLA, "Usa el interés legítimo sin describir la ponderación."))
    elif sensibles and not c.get("base_sensibles"):
        items.append(_item(K["base_licitud"], FALLA,
                           "Trata datos sensibles sin indicar la base que permite tratarlos."))
    elif sensibles and base == cat.INTERES_LEGITIMO:
        items.append(_item(K["base_licitud"], ADVERTENCIA,
                           "El interés legítimo no basta para los datos sensibles: confirma la base de esos datos."))
    else:
        extra = (f"; para los datos sensibles: {cat.nombre(cat.BASES_SENSIBLES_POR_CODIGO, c['base_sensibles'])}"
                 if sensibles and c.get("base_sensibles") else "")
        items.append(_item(K["base_licitud"], CUMPLE, f"{nombre_base}{extra}."))

    # plazos de conservación
    categorias = [t["codigo"] for t in m.get("tipos_datos") or []]
    plazos = {p.get("categoria"): p for p in c.get("plazos") or []}
    sin_plazo = [cat_mapa.nombre_dato(x) for x in categorias
                 if not (plazos.get(x) and plazos[x].get("plazo") and plazos[x].get("unidad"))]
    sin_fundamento = [cat_mapa.nombre_dato(x) for x in categorias
                      if plazos.get(x) and plazos[x].get("plazo") and not plazos[x].get("fundamento")]
    if not categorias:
        items.append(_item(K["plazos"], FALLA, "La actividad no tiene datos elegidos: no se pueden revisar plazos."))
    elif sin_plazo:
        items.append(_item(K["plazos"], FALLA, "Sin plazo: " + _lista(sin_plazo) + "."))
    elif sin_fundamento:
        items.append(_item(K["plazos"], ADVERTENCIA,
                           f"{len(categorias)} categoría(s) con plazo; sin fundamento escrito: "
                           + _lista(sin_fundamento) + "."))
    else:
        items.append(_item(K["plazos"], CUMPLE, f"{len(categorias)} categoría(s) con plazo y fundamento."))

    # transferencias internacionales
    trans = list(m.get("transferencias") or [])
    sin_garantia = [t for t in trans if not t.get("garantia_valida")]
    if not trans:
        items.append(_item(K["transferencias"], NO_APLICA, "Los datos no salen de Chile."))
    elif sin_garantia:
        items.append(_item(K["transferencias"], FALLA, "Sin garantía válida: " + _lista(
            f"{t.get('nombre', '?')} ({t.get('pais_nombre') or cat_mapa.nombre_pais(t.get('pais_destino'))})"
            for t in sin_garantia) + "."))
    else:
        items.append(_item(K["transferencias"], CUMPLE, _lista(
            f"{t.get('pais_nombre') or cat_mapa.nombre_pais(t.get('pais_destino'))}: "
            f"{t.get('garantia_nombre') or cat_mapa.etiqueta('garantia', t.get('garantia'))}" for t in trans) + "."))

    # terceros con contrato
    terceros = list(m.get("terceros") or [])
    encargo = [t for t in terceros if t.get("rol_tercero") in cat_mapa.ROLES_CON_CONTRATO]
    sin_contrato = [t.get("nombre", "?") for t in encargo if t.get("contrato_firmado") is not True]
    if not encargo:
        items.append(_item(K["terceros"], NO_APLICA,
                           "Ningún tercero trata estos datos por encargo de tu empresa." if terceros
                           else "Los datos no se comunican a terceros."))
    elif sin_contrato:
        items.append(_item(K["terceros"], FALLA, "Sin contrato confirmado: " + _lista(sin_contrato) + "."))
    else:
        items.append(_item(K["terceros"], CUMPLE, f"{len(encargo)} tercero(s) con contrato firmado."))

    # decisiones automatizadas
    d = c.get("decisiones") or {}
    if not d.get("existe"):
        items.append(_item(K["decisiones"], NO_APLICA, "No toma decisiones automatizadas ni arma perfiles."))
    elif d.get("intervencion_humana") is not True:
        items.append(_item(K["decisiones"], ADVERTENCIA,
                           "Toma decisiones automatizadas sin revisión humana confirmada."))
    else:
        items.append(_item(K["decisiones"], CUMPLE, "Toma decisiones automatizadas y una persona puede revisarlas."))
    return items


def objeto_actividad(a: ActividadRevisable) -> Objeto:
    items = items_actividad(a)
    if a.origen == "vigente":
        base = [a.id, "vigente", a.version, a.huella_version, a.estado]
    else:
        base = [a.id, "trabajo", None, _huella({"actividad": a.contenido, "mapa": a.mapa}), a.estado]
    sub = (f"Versión N.º {a.version}" if a.version else "Sin versión vigente") + \
          (f" · {a.contenido.get('area')}" if a.contenido.get("area") else "")
    return Objeto(f"actividad:{a.id}", "actividad", a.id, a.nombre, sub, tuple(items),
                  _huella({"base": base, "items": {i.codigo: i.resultado for i in items}}))


# ============================================================ mapa de datos
def uso_en_registro(actividades: Iterable[ActividadRevisable], flujos: list[Flujo]) -> tuple[set[int], set[int]]:
    """Ids de elementos y flujos que usa alguna actividad (directamente o como extremo de un flujo elegido)."""
    por_id = {f.id: f for f in flujos}
    els: set[int] = set()
    fls: set[int] = set()
    for a in actividades:
        mapa = a.mapa or {}
        for x in mapa.get("elementos") or []:
            els.add(x.get("id"))
        for x in mapa.get("flujos") or []:
            fls.add(x.get("id"))
            f = por_id.get(x.get("id"))
            if f is not None:
                els.update((f.origen_id, f.destino_id))
    return els, fls


def objetos_mapa(elementos: list[Elemento], flujos: list[Flujo], usados_el: set[int], usados_fl: set[int]) -> list[Objeto]:
    por_id = {e.id: e for e in elementos}
    pend = {(p["tipo"], p["id"]): p for p in am.completitud(elementos, flujos)["pendientes"]}
    K, KF = CRITERIOS["elemento"], CRITERIOS["flujo"]
    salida: list[Objeto] = []
    for e in elementos:
        faltan = (pend.get(("elemento", e.id)) or {}).get("faltan") or []
        items = [
            _item(K["ficha"], FALLA if faltan else CUMPLE,
                  ("Falta: " + _lista(faltan) + ".") if faltan else "País, responsable y datos registrados."),
            _item(K["confirmado"], FALLA if e.pendiente_revision else CUMPLE,
                  "Es una propuesta que nadie ha confirmado." if e.pendiente_revision else "Confirmado."),
            _item(K["en_registro"], CUMPLE if e.id in usados_el else ADVERTENCIA,
                  "Lo usa al menos una actividad." if e.id in usados_el
                  else "Ninguna actividad lo usa: si trata datos personales, falta una actividad en el registro."),
        ]
        if e.es_tercero and e.rol_tercero in cat_mapa.ROLES_CON_CONTRATO:
            items.append(_item(K["contrato"], CUMPLE if e.contrato_firmado is True else FALLA,
                               "Contrato firmado." if e.contrato_firmado is True else "Sin contrato confirmado."))
        else:
            items.append(_item(K["contrato"], NO_APLICA, "No trata datos por encargo de tu empresa."))
        tipo = cat_mapa.etiqueta("tipo", e.tipo)
        pais = am.pais_efectivo(e)
        sub = " · ".join(x for x in (tipo, cat_mapa.nombre_pais(pais) if pais else "", e.proveedor or "") if x)
        datos = {k: v for k, v in e.como_dict().items() if k not in ("origen", "clave")}
        salida.append(Objeto(f"elemento:{e.id}", "elemento", e.id, e.nombre, sub, tuple(items),
                             _huella({"elemento": datos, "items": {i.codigo: i.resultado for i in items}})))
    for f in flujos:
        d = am.derivados_flujo(f, por_id)
        faltan = (pend.get(("flujo", f.id)) or {}).get("faltan") or []
        o, de = por_id.get(f.origen_id), por_id.get(f.destino_id)
        nombre = f"{o.nombre if o else '?'} → {de.nombre if de else '?'}"
        if d.internacional:
            garantia = (cat_mapa.etiqueta("garantia", f.garantia) if f.garantia else "sin garantía")
            item_g = _item(KF["garantia"], CUMPLE if d.garantia_valida else FALLA,
                           f"Destino {cat_mapa.nombre_pais(d.pais_destino)}: {garantia}"
                           + ("." if d.garantia_valida else " (no es una garantía válida)."))
        else:
            item_g = _item(KF["garantia"], NO_APLICA, "Los datos no salen de Chile.")
        items = [
            _item(KF["ficha"], FALLA if faltan else CUMPLE,
                  ("Falta: " + _lista(faltan) + ".") if faltan else "Finalidad, datos y medio registrados."),
            _item(KF["confirmado"], FALLA if f.pendiente_revision else CUMPLE,
                  "Es una propuesta que nadie ha confirmado." if f.pendiente_revision else "Confirmado."),
            item_g,
            _item(KF["cifrado"], CUMPLE if f.cifrado is True else ADVERTENCIA if f.cifrado is False else NO_APLICA,
                  "Viaja cifrado." if f.cifrado is True else "Viaja sin cifrar." if f.cifrado is False
                  else "Sin indicar (se revisa en la ficha completa)."),
            _item(KF["en_registro"], CUMPLE if f.id in usados_fl else ADVERTENCIA,
                  "Lo usa al menos una actividad." if f.id in usados_fl
                  else "Ninguna actividad lo usa: falta explicar para qué se envían estos datos."),
        ]
        sub = " · ".join(x for x in ("Transferencia internacional" if d.internacional else "Flujo",
                                     cat_mapa.etiqueta("frecuencia", f.frecuencia) if f.frecuencia else "") if x)
        datos = {k: v for k, v in asdict(f).items() if k not in ("origen", "clave")}
        salida.append(Objeto(f"flujo:{f.id}", "flujo", f.id, nombre, sub, tuple(items),
                             _huella({"flujo": datos, "nombres": nombre,
                                      "items": {i.codigo: i.resultado for i in items}})))
    return salida


def objetos(actividades: list[ActividadRevisable], elementos: list[Elemento], flujos: list[Flujo]) -> list[Objeto]:
    usados_el, usados_fl = uso_en_registro(actividades, flujos)
    acts = [objeto_actividad(a) for a in actividades]
    return acts + objetos_mapa(elementos, flujos, usados_el, usados_fl)


# ============================================================ verificaciones del revisor
def _requiere_revision(i: Item) -> bool:
    return i.resultado != NO_APLICA


def consolidar(objs: list[Objeto], verificaciones: dict | None) -> list[dict]:
    """Cada objeto con el estado de revisión de cada punto (lo que decidió la persona, si sigue al día)."""
    ver = verificaciones or {}
    salida = []
    for o in objs:
        guardado = ver.get(o.clave) or {}
        al_dia = guardado.get("huella") == o.huella
        items = []
        hechos = requeridos = fallas = advertencias = 0
        for i in o.items:
            v = (guardado.get("items") or {}).get(i.codigo)
            if not _requiere_revision(i):
                estado, nota, fecha = NO_APLICA, None, None
            elif v and al_dia:
                estado, nota, fecha = v.get("estado"), v.get("nota"), v.get("fecha")
            elif v:
                estado, nota, fecha = DESACTUALIZADO, v.get("nota"), v.get("fecha")
            else:
                estado, nota, fecha = PENDIENTE, None, None
            if _requiere_revision(i):
                requeridos += 1
                hechos += int(estado in (VERIFICADO, ACEPTADO))
            fallas += int(i.resultado == FALLA)
            advertencias += int(i.resultado == ADVERTENCIA)
            items.append({**i.como_dict(), "revision": estado, "nota": nota, "fecha_revision": fecha})
        salida.append({**o.como_dict(), "items": items, "revisados": hechos, "por_revisar": requeridos,
                       "completo": hechos == requeridos, "fallas": fallas, "advertencias": advertencias,
                       "bloqueos": sum(1 for i in o.items if i.bloqueante and i.resultado == FALLA)})
    return salida


def aplicar_verificacion(verificaciones: dict | None, o: Objeto, criterios: list[str] | None, decision: str,
                         nota: str | None, fecha: datetime) -> tuple[dict, list[str]]:
    """
    Registra lo que decidió la persona sobre los puntos de un objeto (todos los que aplican si `criterios` es
    None). Devuelve (verificaciones nuevas, criterios cambiados). Reglas:
      - "verificado" solo si el punto cumple o es una advertencia (la persona confirma que es así);
      - "aceptado" exige una justificación escrita y no vale para un punto bloqueante en falla;
      - "pendiente" deshace lo decidido.
    """
    if decision not in DECISIONES:
        raise ErrorRevision("DECISION_INVALIDA", "Elige verificar, aceptar con justificación o dejar pendiente.")
    nota = " ".join((nota or "").split()) or None
    if decision == ACEPTADO and (not nota or len(nota) < MIN_NOTA):
        raise ErrorRevision("JUSTIFICACION_REQUERIDA",
                            f"Para aceptar un punto escribe por qué (al menos {MIN_NOTA} caracteres).")
    if nota and len(nota) > MAX_NOTA:
        raise ErrorRevision("JUSTIFICACION_LARGA", f"La justificación admite hasta {MAX_NOTA} caracteres.")
    por_codigo = {i.codigo: i for i in o.items}
    if criterios is None:
        elegidos = [i for i in o.items if _requiere_revision(i)]
        if decision == VERIFICADO:            # "verificar todo" deja fuera las fallas (no se verifican)
            elegidos = [i for i in elegidos if i.resultado != FALLA]
    else:
        desconocidos = [c for c in criterios if c not in por_codigo]
        if desconocidos or not criterios:
            raise ErrorRevision("CRITERIO_INVALIDO", "Uno de los puntos elegidos no existe para este elemento.")
        elegidos = [por_codigo[c] for c in dict.fromkeys(criterios)]
    for i in elegidos:
        if not _requiere_revision(i):
            raise ErrorRevision("NO_APLICA", f"«{i.titulo}» no aplica a este elemento: no hay nada que revisar.")
        if decision == VERIFICADO and i.resultado == FALLA:
            raise ErrorRevision("FALLA_SIN_JUSTIFICAR",
                                f"«{i.titulo}» tiene una falla: corrígela o acéptala con una justificación.")
        if decision == ACEPTADO and i.bloqueante and i.resultado == FALLA:
            raise ErrorRevision("FALLA_BLOQUEANTE",
                                f"«{i.titulo}» no se puede aceptar: hay que corregirlo para que el registro "
                                "sea oficial.")
    if not elegidos:
        raise ErrorRevision("SIN_PUNTOS", "No hay puntos que se puedan verificar así: revisa las fallas una a una.")

    nuevas = {k: {"huella": v.get("huella"), "items": dict(v.get("items") or {})}
              for k, v in (verificaciones or {}).items()}
    actual = nuevas.get(o.clave)
    if actual is None or actual.get("huella") != o.huella:
        actual = {"huella": o.huella, "items": {}}        # cambió: lo anterior ya no vale
    for i in elegidos:
        if decision == PENDIENTE:
            actual["items"].pop(i.codigo, None)
        else:
            actual["items"][i.codigo] = {"estado": decision, "nota": nota if decision == ACEPTADO else None,
                                         "fecha": fecha.isoformat()}
    nuevas[o.clave] = actual
    return nuevas, [i.codigo for i in elegidos]


# ============================================================ requisitos para marcar y cifras
def requisitos(consolidados: list[dict], observaciones_abiertas: int, actividades: int, huella_vista: str | None = None,
               huella_actual: str | None = None) -> dict:
    """Qué falta para marcar la versión como revisada (en el orden en que conviene resolverlo)."""
    bloqueos = sum(o["bloqueos"] for o in consolidados)
    pendientes = sum(1 for o in consolidados for i in o["items"] if i["revision"] in (PENDIENTE, DESACTUALIZADO))
    desactualizados = sum(1 for o in consolidados for i in o["items"] if i["revision"] == DESACTUALIZADO)
    faltan: list[dict] = []
    if not actividades:
        faltan.append({"codigo": "SIN_ACTIVIDADES", "texto": "El registro no tiene actividades para revisar."})
    if bloqueos:
        faltan.append({"codigo": "BLOQUEOS", "cantidad": bloqueos,
                       "texto": f"{bloqueos} punto(s) que impiden un registro oficial: actividades sin versión "
                                "vigente o con campos obligatorios vacíos."})
    if observaciones_abiertas:
        faltan.append({"codigo": "OBSERVACIONES_ABIERTAS", "cantidad": observaciones_abiertas,
                       "texto": f"{observaciones_abiertas} observación(es) abierta(s): ciérralas al corregir."})
    if pendientes:
        faltan.append({"codigo": "PUNTOS_PENDIENTES", "cantidad": pendientes,
                       "texto": f"{pendientes} punto(s) de la lista sin revisar"
                                + (f" ({desactualizados} cambiaron después de revisarlos)" if desactualizados else "")
                                + "."})
    if huella_vista and huella_actual and huella_vista != huella_actual:
        faltan.append({"codigo": "REGISTRO_CAMBIO",
                       "texto": "El registro cambió mientras lo revisabas: actualiza la página y revisa lo nuevo."})
    return {"puede_marcar": not faltan, "faltan": faltan}


def resumen(consolidados: list[dict], observaciones: list[dict]) -> dict:
    items = [i for o in consolidados for i in o["items"]]
    por_tipo = {t: sum(1 for o in consolidados if o["tipo"] == t) for t in ("actividad", "elemento", "flujo")}
    aplican = [i for i in items if i["resultado"] != NO_APLICA]
    return {
        "objetos": len(consolidados),
        "por_tipo": por_tipo,
        "puntos": len(aplican),
        "revisados": sum(1 for i in aplican if i["revision"] in (VERIFICADO, ACEPTADO)),
        "verificados": sum(1 for i in aplican if i["revision"] == VERIFICADO),
        "aceptados": sum(1 for i in aplican if i["revision"] == ACEPTADO),
        "pendientes": sum(1 for i in aplican if i["revision"] in (PENDIENTE, DESACTUALIZADO)),
        "desactualizados": sum(1 for i in aplican if i["revision"] == DESACTUALIZADO),
        "por_resultado": {r: sum(1 for i in items if i["resultado"] == r) for r in RESULTADOS},
        "objetos_completos": sum(1 for o in consolidados if o["completo"]),
        "observaciones": {
            "total": len(observaciones),
            "abiertas": sum(1 for x in observaciones if x["estado"] == "abierta"),
            "cerradas": sum(1 for x in observaciones if x["estado"] == "cerrada"),
            "por_prioridad": {p: sum(1 for x in observaciones if x["prioridad"] == p and x["estado"] == "abierta")
                              for p in ("alta", "media", "baja")},
        },
        "porcentaje": round(100 * sum(1 for i in aplican if i["revision"] in (VERIFICADO, ACEPTADO)) / len(aplican))
        if aplican else 0,
    }


# ============================================================ revisión periódica (criterio 5)
def sumar_meses(d: date, meses: int) -> date:
    """d + N meses (si el día no existe en el mes de destino, el último día de ese mes)."""
    total = d.month - 1 + meses
    anio, mes = d.year + total // 12, total % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


AL_DIA, POR_VENCER, VENCIDA, SIN_REVISION, SIN_REGISTRO = "al_dia", "por_vencer", "vencida", "sin_revision", "sin_registro"


def periodicidad(hoy: date, ultima_revision: date | None, primera_vigencia: date | None, plazo_meses: int,
                 aviso_dias: int) -> dict:
    """
    Estado de la revisión periódica:
      al_dia        la última revisión está dentro del plazo;
      por_vencer    vence dentro de `aviso_dias`;
      vencida       pasó el plazo desde la última revisión (o, si nunca se revisó, desde que el registro
                    tuvo su primera actividad vigente);
      sin_revision  nunca se revisó y el registro aún está dentro del plazo inicial;
      sin_registro  todavía no hay actividades vigentes (no hay nada que revisar).
    """
    base = ultima_revision or primera_vigencia
    if base is None:
        return {"estado": SIN_REGISTRO, "vence": None, "dias": None, "base": None}
    vence = sumar_meses(base, plazo_meses)
    dias = (vence - hoy).days
    if dias < 0:
        estado = VENCIDA
    elif dias <= aviso_dias:
        estado = POR_VENCER
    else:
        estado = AL_DIA if ultima_revision else SIN_REVISION
    return {"estado": estado, "vence": vence.isoformat(), "dias": dias,
            "base": "ultima_revision" if ultima_revision else "primera_vigencia"}


def toca_recordar(estado: dict, ultimo: date | None, etapa_anterior: str | None, hoy: date,
                  repetir_dias: int) -> str | None:
    """La etapa a recordar hoy ("por_vencer:AAAA-MM-DD" o "vencida:AAAA-MM-DD") o None si no corresponde."""
    if estado["estado"] not in (POR_VENCER, VENCIDA):
        return None
    etapa = f"{estado['estado']}:{estado['vence']}"
    if etapa != etapa_anterior:
        return etapa
    if estado["estado"] == VENCIDA and ultimo is not None and (hoy - ultimo).days >= repetir_dias:
        return etapa
    return None


# ============================================================ diferencias entre versiones (criterio 4)
@dataclass(frozen=True)
class EntradaComparacion:
    """Una actividad en una versión del registro, con sus campos ya en texto legible."""
    id: int
    nombre: str
    version: int | None
    huella: str | None
    campos: dict = field(default_factory=dict)      # codigo -> (titulo, texto)


def comparar(antes: dict[int, EntradaComparacion], despues: dict[int, EntradaComparacion]) -> dict:
    agregadas, quitadas, cambiadas, iguales = [], [], [], []
    for i in sorted(set(antes) | set(despues), key=lambda x: ((despues.get(x) or antes.get(x)).nombre.lower(), x)):
        a, d = antes.get(i), despues.get(i)
        if a is None:
            agregadas.append({"id": i, "nombre": d.nombre, "version": d.version})
        elif d is None:
            quitadas.append({"id": i, "nombre": a.nombre, "version": a.version})
        elif a.version == d.version and a.huella == d.huella:
            iguales.append({"id": i, "nombre": d.nombre, "version": d.version})
        else:
            campos = []
            for codigo in dict.fromkeys([*a.campos, *d.campos]):
                ta, td = a.campos.get(codigo), d.campos.get(codigo)
                txa, txd = (ta[1] if ta else "—"), (td[1] if td else "—")
                if txa != txd:
                    campos.append({"codigo": codigo, "titulo": (td or ta)[0], "antes": txa, "despues": txd})
            if a.nombre != d.nombre:
                campos.insert(0, {"codigo": "nombre", "titulo": "Nombre", "antes": a.nombre, "despues": d.nombre})
            cambiadas.append({"id": i, "nombre": d.nombre, "version_antes": a.version, "version_despues": d.version,
                              "campos": campos})
    return {"agregadas": agregadas, "quitadas": quitadas, "cambiadas": cambiadas, "iguales": iguales,
            "sin_cambios": not (agregadas or quitadas or cambiadas),
            "totales": {"agregadas": len(agregadas), "quitadas": len(quitadas), "cambiadas": len(cambiadas),
                        "iguales": len(iguales)}}
