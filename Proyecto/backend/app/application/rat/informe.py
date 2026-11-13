"""
HU-36 · Informe del Registro de Actividades de Tratamiento (lógica PURA: sin BD, sin red, sin reportlab).

Vive en application (como app/application/informes/ficha.py, de la que toma el aviso legal y el dígito
verificador) para no hacer depender el dominio de los informes.

Arma, desde las actividades del registro, todo lo que dice el informe que la empresa presenta ante la
Agencia de Protección de Datos Personales, el certificador de su modelo de prevención de infracciones o
su directorio. El PDF (app/application/rat/pdf_rat.py), la planilla XLSX (xlsx_rat.py), el correo y la
vista previa del panel leen ESTE resultado, así todos dicen exactamente lo mismo.

Qué versión de cada actividad entra (criterio 1, "desde la versión vigente del RAT"):
  - Si la actividad tiene una versión vigente, entra esa instantánea INMUTABLE (rat_actividad_version),
    aunque después se haya abierto una nueva versión o el mapa la haya devuelto a revisión.
  - Si nunca estuvo vigente, entra su copia de trabajo (con lo que toma hoy del mapa) marcada como
    "sin versión vigente".
  - Las archivadas no entran (ya no se realizan).

Borrador (criterio 4): el informe sale como BORRADOR, con marca de agua y aviso en la portada, si alguna
actividad incluida no está vigente (en revisión, en borrador o sin versión vigente). Si todas están
vigentes, es el informe OFICIAL de esa versión del registro.

Versión del RAT y código verificable (criterio 2):
  - huella()   SHA-256 de lo que afirma el registro (versión y huella de cada actividad vigente, y la
               copia de trabajo de las que no lo están). No depende de la fecha de emisión.
  - La versión del RAT es un correlativo por empresa que sube cuando cambia la huella (lo asigna el
    caso de uso al emitir: app/application/use_cases/informe_rat.py).
  - codigo()   CIA-REG-2026-000045-K: año + número de la emisión + dígito verificador módulo 11 (el
               mismo algoritmo del código del informe de evaluación y del RUT).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime

from app.application.informes.ficha import AvisoInforme, digito_verificador
from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat
from app.domain.rat import riesgos as rg
from app.domain.rat.modelo import completar

PREFIJO_CODIGO = "CIA-REG"
FORMATO = 1

# ============================================================ aviso legal (HU-04 / HU-21)
# Mismo formato del aviso del informe de evaluación: versión impresa en cada informe, texto completo en
# la portada y una línea en el pie de TODAS las páginas. Borrador técnico para validar con asesoría legal.
AVISO_RAT = AvisoInforme(
    version="2026-11-rat-v1",
    titulo="Aviso legal",
    texto=(
        "Este informe reproduce el Registro de Actividades de Tratamiento que la propia organización elaboró y "
        "mantiene en la plataforma ComplianceIA de Therion Labs. La plataforma es una herramienta de apoyo a la "
        "gestión: ordena la información, calcula lo que se desprende del mapa de datos y propone una valoración "
        "orientativa de riesgos, pero no revisa la veracidad de lo declarado.",
        "La organización, como responsable o encargada del tratamiento, responde por la exactitud, la "
        "completitud y la actualización de este registro y por el cumplimiento de la Ley N.º 21.719 sobre "
        "protección de datos personales y su reglamento. Este documento no es una auditoría, no certifica el "
        "cumplimiento de ninguna norma y no constituye asesoría legal.",
        "Las bases de licitud, las referencias normativas y los textos de ayuda son una guía general. Antes de "
        "presentarlo ante la autoridad, un certificador o el directorio, se recomienda validarlo con el "
        "encargado de prevención o de protección de datos y con un abogado.",
    ),
    pie="La plataforma apoya la gestión del registro y no reemplaza la asesoría legal (Ley N.º 21.719).",
)

USO_PREVISTO = ("Agencia de Protección de Datos Personales · certificador del modelo de prevención de "
                "infracciones · directorio")
# Qué hacer para que el informe deje de ser borrador (portada del PDF y del XLSX). HU-41 lo reemplaza en el
# registro de la propia plataforma, que no se edita en pantalla sino en el inventario de datos.
NOTA_BORRADOR = "Para emitir el informe oficial, deja vigentes todas las actividades del registro y vuelve a generarlo."


# ============================================================ entradas
@dataclass(frozen=True)
class FuenteActividad:
    """Lo que el caso de uso lee de la BD para cada actividad NO archivada."""
    id: int
    nombre: str
    estado: str
    version_vigente: int | None
    fecha_vigencia: datetime | None
    fecha_actualizacion: datetime | None
    motivos_revision: tuple = ()
    # Versión vigente (rat_actividad_version): instantánea {actividad, mapa}, huella y fecha
    instantanea: dict | None = None
    huella_version: str | None = None
    fecha_version: datetime | None = None
    # Copia de trabajo (solo se usa si nunca estuvo vigente): contenido, derivados y completitud actuales
    contenido: dict | None = None
    derivados: dict | None = None
    completitud: dict | None = None


# ============================================================ resultado
@dataclass(frozen=True)
class ActividadInforme:
    numero: int                      # orden en el informe (1..n)
    id: int
    nombre: str
    estado: str
    estado_nombre: str
    origen: str                      # "vigente" (instantánea) | "trabajo" (sin versión vigente)
    version: int | None
    fecha_version: datetime | None
    huella_version: str | None
    pendiente: str | None            # por qué no está vigente (None si lo está)
    contenido: dict                  # rat.modelo.completar()
    mapa: dict                       # tipos_datos, titulares, bases_datos, paises, terceros, transferencias…
    faltantes: tuple = ()            # títulos de campos vacíos (solo copia de trabajo)
    riesgo: rg.RiesgoActividad | None = None

    # ---- atajos de presentación
    @property
    def sensibles(self) -> list[dict]:
        return [t for t in self.mapa.get("tipos_datos") or [] if t.get("sensible")]

    @property
    def incluye_nna(self) -> bool:
        return any(t.get("nna") for t in self.mapa.get("titulares") or [])

    @property
    def transferencias(self) -> list[dict]:
        return list(self.mapa.get("transferencias") or [])

    @property
    def decisiones(self) -> dict:
        return self.contenido.get("decisiones") or {}

    @property
    def tiene_decisiones(self) -> bool:
        return bool(self.decisiones.get("existe"))


@dataclass(frozen=True)
class InformeRat:
    empresa: str
    rut: str | None
    rubro: str | None
    generado: datetime
    actividades: tuple[ActividadInforme, ...]
    resumen: dict
    borrador: bool
    motivos_borrador: tuple[str, ...]
    huella: str
    riesgos: tuple[rg.RiesgoActividad, ...]
    aviso: AvisoInforme = AVISO_RAT
    # Los asigna el caso de uso al emitir (None en la vista previa)
    codigo: str | None = None
    version_rat: int | None = None
    archivadas: int = 0
    nota_borrador: str = NOTA_BORRADOR

    def con_emision(self, codigo: str, version_rat: int) -> "InformeRat":
        return replace(self, codigo=codigo, version_rat=version_rat)

    @property
    def estado_texto(self) -> str:
        return "Borrador" if self.borrador else "Oficial"


# ============================================================ código verificable
def codigo(emision_id: int, anio: int) -> str:
    return f"{PREFIJO_CODIGO}-{anio:04d}-{emision_id:06d}-{digito_verificador(emision_id)}"


def leer_codigo(texto: str) -> tuple[int, int] | None:
    """(año, emision_id) si el código está bien formado y el dígito cuadra; si no, None."""
    t = (texto or "").strip().upper().replace(" ", "")
    if not t.startswith(PREFIJO_CODIGO + "-"):
        return None
    partes = t[len(PREFIJO_CODIGO) + 1:].split("-")
    if len(partes) != 3:
        return None
    anio, numero, dv = partes
    if not (anio.isdigit() and len(anio) == 4 and numero.isdigit() and 6 <= len(numero) <= 9):
        return None
    if digito_verificador(int(numero)) != dv:
        return None
    return int(anio), int(numero)


def huella_legible(h: str, grupos: int = 4) -> str:
    h = (h or "").upper()[: grupos * 4]
    return " ".join(h[i:i + 4] for i in range(0, len(h), 4))


# ============================================================ armado
_ORDEN_ESTADO = {cat.VIGENTE: 0, cat.EN_REVISION: 1, cat.BORRADOR: 2}


def _mapa_de_instantanea(inst: dict) -> dict:
    m = dict((inst or {}).get("mapa") or {})
    for k in ("elementos", "flujos", "tipos_datos", "titulares", "bases_datos", "paises", "terceros", "transferencias"):
        m.setdefault(k, [])
    return m


def _pendiente(f: FuenteActividad) -> str | None:
    if f.estado == cat.VIGENTE:
        return None
    if f.version_vigente is None:
        return ("En revisión, todavía sin una versión vigente" if f.estado == cat.EN_REVISION
                else "En borrador, todavía sin una versión vigente")
    if f.estado == cat.EN_REVISION:
        if f.motivos_revision:
            return f"En revisión por un cambio en el mapa de datos (se informa la versión vigente {f.version_vigente})"
        return f"En revisión (se informa la versión vigente {f.version_vigente})"
    return f"Con una nueva versión en preparación (se informa la versión vigente {f.version_vigente})"


def _actividad(numero: int, f: FuenteActividad) -> ActividadInforme:
    if f.version_vigente is not None and f.instantanea:
        contenido = completar((f.instantanea or {}).get("actividad"))
        mapa = _mapa_de_instantanea(f.instantanea)
        origen, faltantes = "vigente", ()
    else:
        contenido = completar(f.contenido)
        mapa = _mapa_de_instantanea({"mapa": f.derivados or {}})
        origen = "trabajo"
        faltantes = tuple(x["titulo"] for x in (f.completitud or {}).get("faltantes", []))
    nombre = contenido.get("nombre") or f.nombre
    riesgo = rg.evaluar(f.id, nombre, contenido, mapa, len(faltantes))
    return ActividadInforme(
        numero=numero, id=f.id, nombre=nombre, estado=f.estado,
        estado_nombre=cat.nombre(cat.ESTADOS_POR_CODIGO, f.estado), origen=origen,
        version=f.version_vigente if origen == "vigente" else None,
        fecha_version=(f.fecha_version or f.fecha_vigencia) if origen == "vigente" else f.fecha_actualizacion,
        huella_version=f.huella_version if origen == "vigente" else None, pendiente=_pendiente(f),
        contenido=contenido, mapa=mapa, faltantes=faltantes, riesgo=riesgo)


def _huella_trabajo(a: ActividadInforme) -> str:
    texto = json.dumps({"actividad": a.contenido, "mapa": a.mapa}, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def huella(actividades: list[ActividadInforme] | tuple[ActividadInforme, ...]) -> str:
    """Lo que AFIRMA el registro (no la fecha ni la forma): igual entre dos emisiones sin cambios."""
    partes = []
    for a in sorted(actividades, key=lambda x: x.id):
        if a.origen == "vigente":
            partes.append([a.id, "vigente", a.version, a.huella_version, a.estado])
        else:
            partes.append([a.id, "trabajo", None, _huella_trabajo(a), a.estado])
    texto = json.dumps({"formato": FORMATO, "actividades": partes}, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _motivos_borrador(acts: list[ActividadInforme]) -> list[str]:
    sin_vigente = [a for a in acts if a.origen == "trabajo"]
    revision = [a for a in acts if a.origen == "vigente" and a.estado == cat.EN_REVISION]
    preparacion = [a for a in acts if a.origen == "vigente" and a.estado == cat.BORRADOR]
    motivos = []
    if sin_vigente:
        incompletas = sum(1 for a in sin_vigente if a.faltantes)
        motivos.append(
            f"{len(sin_vigente)} actividad(es) sin versión vigente"
            + (f" ({incompletas} con datos obligatorios por completar)" if incompletas else "") + ".")
    if revision:
        motivos.append(f"{len(revision)} actividad(es) en revisión: se informa su última versión vigente.")
    if preparacion:
        motivos.append(f"{len(preparacion)} actividad(es) con una nueva versión en preparación: se informa su "
                       "última versión vigente.")
    return motivos


def _resumen(acts: list[ActividadInforme], riesgos: list[rg.RiesgoActividad], archivadas: int) -> dict:
    sensibles = {t["codigo"]: t.get("nombre") or cat_mapa.nombre_dato(t["codigo"]) for a in acts for t in a.sensibles}
    transferencias = [(a, t) for a in acts for t in a.transferencias]
    unicas = {t.get("flujo_id"): t for _, t in transferencias}
    terceros = {t["id"]: t for a in acts for t in a.mapa.get("terceros") or []}
    paises_destino = sorted({t.get("pais_nombre") or cat_mapa.nombre_pais(t.get("pais_destino")) for t in unicas.values()})
    bases: dict[str, int] = {}
    for a in acts:
        b = cat.nombre(cat.BASES_POR_CODIGO, a.contenido.get("base_licitud")) or "Sin base de licitud"
        bases[b] = bases.get(b, 0) + 1
    por_estado = {e: sum(1 for a in acts if a.estado == e) for e in (cat.VIGENTE, cat.EN_REVISION, cat.BORRADOR)}
    niveles = rg.conteo_niveles(riesgos)
    return {
        "actividades": len(acts),
        "archivadas_excluidas": archivadas,
        "por_estado": por_estado,
        "sin_version_vigente": sum(1 for a in acts if a.origen == "trabajo"),
        "con_sensibles": sum(1 for a in acts if a.sensibles),
        "categorias_sensibles": sorted(sensibles.values()),
        "con_nna": sum(1 for a in acts if a.incluye_nna),
        "transferencias": len(unicas),
        "transferencias_sin_garantia": sum(1 for t in unicas.values() if not t.get("garantia_valida")),
        "actividades_con_transferencias": sum(1 for a in acts if a.transferencias),
        "paises_destino": paises_destino,
        "con_decisiones": sum(1 for a in acts if a.tiene_decisiones),
        "con_perfilamiento": sum(1 for a in acts if a.tiene_decisiones and a.decisiones.get("perfilamiento")),
        "decisiones_sin_revision_humana": sum(1 for a in acts if a.tiene_decisiones
                                              and a.decisiones.get("intervencion_humana") is not True),
        "terceros": len(terceros),
        "terceros_sin_contrato": sum(1 for t in terceros.values() if t.get("rol_tercero") in cat_mapa.ROLES_CON_CONTRATO
                                     and t.get("contrato_firmado") is not True),
        "como_encargado": sum(1 for a in acts if a.contenido.get("rol") == "encargado"),
        "bases_licitud": dict(sorted(bases.items(), key=lambda x: (-x[1], x[0]))),
        "riesgos": niveles,
        "riesgos_altos": niveles["Alto"] + niveles["Crítico"],
    }


def armar(fuentes: list[FuenteActividad], generado: datetime, empresa: str, rut: str | None = None,
          rubro: str | None = None, archivadas: int = 0) -> InformeRat:
    """El informe completo, sin código ni versión (los pone el caso de uso al emitir)."""
    ordenadas = sorted(fuentes, key=lambda f: (f.nombre or "").lower())
    acts = [_actividad(i, f) for i, f in enumerate(ordenadas, start=1)]
    riesgos = [a.riesgo for a in acts if a.riesgo is not None]
    motivos = _motivos_borrador(acts)
    return InformeRat(
        empresa=empresa, rut=rut, rubro=rubro, generado=generado, actividades=tuple(acts),
        resumen=_resumen(acts, riesgos, archivadas), borrador=bool(motivos), motivos_borrador=tuple(motivos),
        huella=huella(acts), riesgos=tuple(rg.ordenar(riesgos)), archivadas=archivadas)


# ============================================================ textos legibles (PDF y XLSX)
def _lista(nombres: list[str], vacio: str = "—") -> str:
    return ", ".join(n for n in nombres if n) or vacio


def texto_plazo(p: dict) -> str:
    if not p.get("plazo") or not p.get("unidad"):
        return "Sin plazo definido"
    unidad = cat.nombre(cat.UNIDADES_POR_CODIGO, p["unidad"])
    if p["plazo"] == 1:
        unidad = {"días": "día", "meses": "mes", "años": "año"}.get(unidad, unidad)
    desde = cat.nombre(cat.INICIOS_POR_CODIGO, p.get("desde"))
    return f"{p['plazo']} {unidad}" + (f" {desde}" if desde else "")


def texto_fuente(f: dict) -> str:
    nombre = cat.nombre(cat.FUENTES_POR_CODIGO, f.get("tipo"))
    return f"{nombre}: {f['detalle']}" if f.get("detalle") else nombre


def texto_rol(c: dict) -> str:
    rol = cat.nombre(cat.ROLES_POR_CODIGO, c.get("rol")) or "Sin indicar"
    if c.get("rol") == "encargado" and c.get("responsable_mandante"):
        rol += f", por cuenta de {c['responsable_mandante']}"
    return rol


def texto_base(c: dict) -> str:
    base = cat.nombre(cat.BASES_POR_CODIGO, c.get("base_licitud")) or "Sin indicar"
    ref = cat.BASES_POR_CODIGO.get(c.get("base_licitud") or "")
    if ref and ref.referencia:
        base += f" ({ref.referencia})"
    return base


def texto_decisiones(c: dict) -> str:
    d = c.get("decisiones") or {}
    if d.get("existe") is None:
        return "Sin indicar"
    if not d.get("existe"):
        return "No toma decisiones automatizadas ni arma perfiles."
    partes = ["Sí, con perfilamiento" if d.get("perfilamiento") else "Sí, toma decisiones automatizadas"]
    if d.get("logica"):
        partes.append(f"Lógica: {d['logica']}")
    if d.get("consecuencias"):
        partes.append(f"Efectos para las personas: {d['consecuencias']}")
    rev = d.get("intervencion_humana")
    partes.append("Una persona puede revisar la decisión." if rev is True else
                  "Sin revisión humana." if rev is False else "Revisión humana sin confirmar.")
    return " · ".join(partes)


def medidas_por_grupo(c: dict) -> dict[str, list[str]]:
    m = c.get("medidas") or {}
    salida: dict[str, list[str]] = {g: [] for g in cat.GRUPOS_MEDIDAS}
    for codigo_m in m.get("codigos") or []:
        o = cat.MEDIDAS_POR_CODIGO.get(codigo_m)
        if o:
            salida.setdefault(o.extra.get("grupo", cat.GRUPOS_MEDIDAS[0]), []).append(o.nombre)
    if m.get("otras"):
        salida.setdefault("Otras", []).append(m["otras"])
    return {k: v for k, v in salida.items() if v}


def texto_medidas(c: dict) -> str:
    grupos = medidas_por_grupo(c)
    return " · ".join(f"{g}: {', '.join(v)}" for g, v in grupos.items()) or "Sin medidas registradas"


def texto_destinatarios(a: ActividadInforme) -> str:
    terceros = a.mapa.get("terceros") or []
    if not terceros:
        return "No se comunican a terceros." if a.contenido.get("sin_destinatarios") else "Sin indicar"
    partes = []
    for t in terceros:
        rol = cat_mapa.etiqueta("rol", t.get("rol_tercero")) if t.get("rol_tercero") else ""
        txt = t.get("nombre", "?")
        extras = [x for x in (rol, cat_mapa.nombre_pais(t.get("pais")) if t.get("pais") else "") if x]
        if t.get("rol_tercero") in cat_mapa.ROLES_CON_CONTRATO:
            extras.append("con contrato" if t.get("contrato_firmado") is True else "sin contrato confirmado")
        partes.append(txt + (f" ({', '.join(extras)})" if extras else ""))
    return "; ".join(partes)


def texto_transferencias(a: ActividadInforme) -> str:
    if not a.transferencias:
        return "No hay transferencias internacionales."
    return "; ".join(
        f"{t.get('nombre', '?')} → {t.get('pais_nombre') or cat_mapa.nombre_pais(t.get('pais_destino'))}: "
        + (t.get("garantia_nombre") or "sin garantía registrada")
        + ("" if t.get("garantia_valida") else " (garantía no válida o faltante)")
        for t in a.transferencias)


def texto_ambito(a: ActividadInforme) -> str:
    paises = [p.get("nombre") or cat_mapa.nombre_pais(p.get("codigo")) for p in a.mapa.get("paises") or []]
    txt = _lista(paises, "Sin indicar")
    if a.contenido.get("ambito_nota"):
        txt += f". {a.contenido['ambito_nota']}"
    return txt


def campos_legibles(a: ActividadInforme, plazos_aparte: bool = False) -> list[tuple[str, str, str]]:
    """
    (código, título, texto) de los 13 campos del registro, en el orden del reglamento. Con
    `plazos_aparte` (PDF) la conservación se resume y el detalle va en su propia tabla.
    """
    c = a.contenido
    tipos = [f"{t.get('nombre') or cat_mapa.nombre_dato(t['codigo'])}{' (sensible)' if t.get('sensible') else ''}"
             for t in a.mapa.get("tipos_datos") or []]
    titulares = [f"{t.get('nombre') or cat_mapa.nombre_titular(t['codigo'])}{' (NNA)' if t.get('nna') else ''}"
                 for t in a.mapa.get("titulares") or []]
    base = texto_base(c)
    if c.get("interes_legitimo"):
        base += f". Interés legítimo: {c['interes_legitimo']}"
    if c.get("base_sensibles"):
        base += f". Para los datos sensibles: {cat.nombre(cat.BASES_SENSIBLES_POR_CODIGO, c['base_sensibles'])}"
    plazos = [f"{cat_mapa.nombre_dato(p['categoria'])}: {texto_plazo(p)}"
              + (f" ({p['fundamento']})" if p.get("fundamento") else "") for p in c.get("plazos") or []]
    sistemas = [f"{b.get('nombre', '?')}" for b in a.mapa.get("bases_datos") or []]
    titulos = {x.codigo: x.titulo for x in cat.CAMPOS}
    valores = {
        "finalidades": "; ".join(c.get("finalidades") or []) or "Sin indicar",
        "rol": texto_rol(c),
        "tipos_datos": _lista(tipos, "Sin indicar"),
        "titulares": _lista(titulares, "Sin indicar"),
        "bases_datos": _lista(sistemas, "Sin indicar"),
        "ambito": texto_ambito(a),
        "fuentes": "; ".join(texto_fuente(f) for f in c.get("fuentes") or []) or "Sin indicar",
        "base_licitud": base,
        "destinatarios": texto_destinatarios(a),
        "transferencias": texto_transferencias(a),
        "conservacion": ("; ".join(plazos) or "Sin indicar") if not (plazos_aparte and plazos) else
                        f"{len(plazos)} categoría(s) con su plazo: ver la tabla de plazos de conservación.",
        "decisiones": texto_decisiones(c),
        "medidas": texto_medidas(c),
    }
    orden = ("finalidades", "rol", "tipos_datos", "titulares", "bases_datos", "ambito", "fuentes", "base_licitud",
             "destinatarios", "transferencias", "conservacion", "decisiones", "medidas")
    return [(k, titulos[k], valores[k]) for k in orden]


def resumen_publico(inf: InformeRat) -> dict:
    """Vista previa para el panel (sin el contenido completo de las actividades)."""
    return {
        "borrador": inf.borrador,
        "motivos_borrador": list(inf.motivos_borrador),
        "huella": inf.huella,
        "resumen": inf.resumen,
        "actividades": [{
            "id": a.id, "numero": a.numero, "nombre": a.nombre, "estado": a.estado, "estado_nombre": a.estado_nombre,
            "origen": a.origen, "version": a.version, "pendiente": a.pendiente,
            "riesgo": {"nivel": a.riesgo.nivel, "puntaje": a.riesgo.puntaje, "probabilidad": a.riesgo.probabilidad,
                       "impacto": a.riesgo.impacto} if a.riesgo else None,
        } for a in inf.actividades],
        "mapa_calor": rg.mapa_calor(list(inf.riesgos)),
        "aviso": {"version": inf.aviso.version, "pie": inf.aviso.pie},
    }


__all__ = [
    "AVISO_RAT", "USO_PREVISTO", "NOTA_BORRADOR", "FuenteActividad", "ActividadInforme", "InformeRat", "armar", "codigo",
    "leer_codigo", "huella", "huella_legible", "campos_legibles", "resumen_publico", "texto_plazo",
    "texto_fuente", "texto_rol", "texto_base", "texto_decisiones", "texto_medidas", "medidas_por_grupo",
    "texto_destinatarios", "texto_transferencias", "texto_ambito",
]
