"""
HU-16 · Generación del Markdown de un borrador (lógica pura, sin BD ni LLM).

Entrada:
  - la plantilla (plantillas.py),
  - el contexto de la evaluación MÁS RECIENTE de la empresa (o la elegida): puntajes por
    dimensión y brechas no conformes (no cumplido y parcial), con la fuente normativa real
    de cada control tomada de la matriz,
  - la identidad de la empresa (razón social, RUT y rubro), que escribe el backend y que el
    LLM nunca ve,
  - opcionalmente las secciones que adaptó el Agente IA, ya validadas por salida_ia.py.

Salida: un documento Markdown editable con
  - encabezado con la identificación de la empresa, el aviso de borrador y una tabla de
    control de versiones,
  - las cláusulas de la plantilla, numeradas; las que tratan un control con brecha llevan la
    "Medida prioritaria" (criterio 2: ajuste a la evaluación de la empresa) y cada una cierra
    con su fundamento normativo (Ley N.º 21.719 y estándares, con el artículo real de la matriz),
  - Anexo A: alineación con las dimensiones del modelo (puntaje, nivel, brechas abiertas y las
    secciones del documento que las abordan),
  - Anexo B: plan de implementación con las brechas que el documento ayuda a cerrar.

HU-38: con `registro` (borradores/registro.py) la PIA se pre-llena con las actividades de alto riesgo del
registro de actividades y el aviso de privacidad toma sus finalidades y bases de licitud. Esas cláusulas
llevan el texto del registro (no el que propone el Agente IA) y una nota para revisarlas.

Nunca escribe códigos internos de controles o brechas (regla de interfaz del 29-oct).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.application.borradores.plantillas import (
    DIMENSIONES,
    MARCADOR_PENDIENTE,
    VERSION_PLANTILLAS,
    Clausula,
    Plantilla,
)

ZONA = ZoneInfo("America/Santiago")
MAX_PLAN = 12
NOTA_IA = "*Sección adaptada por el Agente IA para tu empresa: revísala antes de aprobar.*"
NOTA_REGISTRO = "*Sección completada con tu registro de actividades de tratamiento: revísala antes de aprobar.*"
ETIQUETA_ESTADO = {"no_cumplido": "No cumplido", "parcialmente_cumplido": "Parcialmente cumplido"}
ETIQUETA_MADUREZ = {"inicial": "Inicial", "en_desarrollo": "En desarrollo", "gestionado": "Gestionado",
                    "optimizado": "Optimizado"}
PESO_SEVERIDAD = {"Crítica": 0, "Alta": 1, "Media": 2, "Baja": 3}
_ETIQUETA_ANON = re.compile(r"\[(RUT|NOMBRE|CORREO|TEL|DIRECCION|DATO_CODIFICADO)_ANON\]")
_DESCRIPCION_ANON = {"RUT": "RUT", "NOMBRE": "nombre", "CORREO": "correo", "TEL": "teléfono",
                     "DIRECCION": "dirección", "DATO_CODIFICADO": "dato"}
# Código de control o brecha (DAT-001, ERR-GOB-003...): no debe aparecer en el documento
CODIGO_INTERNO = re.compile(r"\b(?:ERR-)?(?:DAT|GOB|RIE|SEG)-\d{3}\b")


# ===================================================================== contexto
@dataclass(frozen=True)
class BrechaBorrador:
    control: str | None          # código interno (no se escribe en el documento)
    dimension: str
    obligacion: str
    recomendacion: str | None
    severidad: str
    estado: str
    prioridad: int


@dataclass(frozen=True)
class DimensionBorrador:
    nombre: str
    puntaje: float | None
    nivel: str | None            # inicial | en_desarrollo | gestionado | optimizado


@dataclass(frozen=True)
class ContextoBorrador:
    evaluacion_id: int | None
    fecha_evaluacion: date | None
    rubro: str | None
    puntaje_general: float | None
    nivel_general: str | None
    dimensiones: tuple[DimensionBorrador, ...] = ()
    brechas: tuple[BrechaBorrador, ...] = ()
    # control -> "Ley N.º 21.719 · Art. 15 ter" (framework y artículo de la matriz)
    fuentes: dict[str, str] = field(default_factory=dict)

    @property
    def controles_con_brecha(self) -> frozenset[str]:
        return frozenset(b.control for b in self.brechas if b.control)

    def brechas_de(self, plantilla: Plantilla) -> list[BrechaBorrador]:
        controles = plantilla.controles
        return sorted((b for b in self.brechas if b.control in controles), key=lambda b: b.prioridad)

    def huella(self) -> str:
        """Qué evaluación y qué brechas se usaron (auditoría, sin datos personales)."""
        base = {"ev": self.evaluacion_id, "b": sorted((b.control or "", b.estado) for b in self.brechas)}
        return hashlib.sha256(json.dumps(base, ensure_ascii=False).encode()).hexdigest()[:32]


def contexto_desde_evaluacion(datos, fuentes: dict[str, str] | None = None) -> ContextoBorrador:
    """`datos` es un DatosEvaluacion (app/application/informes/carga.py)."""
    from app.application.informes.analisis import ESTADOS_BRECHA, construir_brechas, nivel_madurez

    puntajes = {d.nombre: d.puntaje for d in datos.dominios if d.puntaje is not None}
    filas = {r.id: r for r in datos.respuestas}
    brechas = []
    for b in construir_brechas(datos.respuestas, puntajes):
        if b.estado not in ESTADOS_BRECHA:
            continue
        fila = filas.get(b.respuesta_id)
        brechas.append(BrechaBorrador(
            control=b.control_codigo, dimension=b.dominio,
            obligacion=(fila.control_obligacion if fila and fila.control_obligacion else b.descripcion),
            recomendacion=fila.control_recomendacion if fila else None,
            severidad=b.severidad, estado=b.estado, prioridad=b.prioridad,
        ))
    return ContextoBorrador(
        evaluacion_id=datos.evaluacion_id,
        fecha_evaluacion=datos.fecha_inicio,
        rubro=datos.rubro,
        puntaje_general=datos.puntaje_general,
        nivel_general=nivel_madurez(datos.puntaje_general) if datos.puntaje_general is not None else None,
        dimensiones=tuple(DimensionBorrador(d.nombre, d.puntaje,
                                            nivel_madurez(d.puntaje) if d.puntaje is not None else None)
                          for d in datos.dominios),
        brechas=tuple(brechas),
        fuentes=dict(fuentes or {}),
    )


@dataclass(frozen=True)
class IdentidadEmpresa:
    razon_social: str
    rut: str
    rubro: str | None = None


@dataclass(frozen=True)
class AdaptacionIA:
    """Lo que el Agente IA aportó, YA validado y anclado (salida_ia.py)."""
    introduccion: str | None = None
    secciones: dict[str, str] = field(default_factory=dict)
    notas: tuple[str, ...] = ()


# ===================================================================== helpers puros
def clausulas_prioritarias(plantilla: Plantilla, ctx: ContextoBorrador) -> list[str]:
    """Cláusulas que tratan un control con brecha en la evaluación de la empresa."""
    abiertas = ctx.controles_con_brecha
    return [c.id for c in plantilla.clausulas if abiertas.intersection(c.controles)]


def fundamento(clausula: Clausula, ctx: ContextoBorrador) -> str | None:
    """La fuente REAL de la matriz (framework · artículo) de sus controles, sin repetir."""
    fuentes: list[str] = []
    for c in clausula.controles:
        f = (ctx.fuentes.get(c) or "").strip()
        if f and f not in fuentes:
            fuentes.append(f)
    if not fuentes:
        fuentes = list(dict.fromkeys(clausula.normas))
    return "; ".join(fuentes) or None


def articulos_validos(plantilla: Plantilla, ctx: ContextoBorrador) -> frozenset[str]:
    """Números de artículo/cláusula que el LLM puede citar: los de las fuentes de la plantilla."""
    numeros: set[str] = set()
    for c in plantilla.controles:
        numeros.update(re.findall(r"\d+(?:\.\d+)*", ctx.fuentes.get(c) or ""))
    return frozenset(numeros)


def _fecha(d: date | datetime | None) -> str:
    return d.strftime("%d-%m-%Y") if d else "—"


def completar_identidad(texto: str, identidad: IdentidadEmpresa, hoy: date) -> str:
    rubro = identidad.rubro or "[COMPLETAR: rubro]"
    return (texto.replace("{{RAZON_SOCIAL}}", identidad.razon_social)
            .replace("{{RUT_EMPRESA}}", identidad.rut)
            .replace("{{RUBRO}}", rubro)
            .replace("{{FECHA}}", _fecha(hoy)))


def etiquetas_a_marcadores(texto: str) -> str:
    """[NOMBRE_ANON] (dato que el NER anonimizó antes del LLM) -> [COMPLETAR: nombre]."""
    return _ETIQUETA_ANON.sub(lambda m: f"[COMPLETAR: {_DESCRIPCION_ANON[m.group(1)]}]", texto or "")


def _puntaje(p: float | None) -> str:
    return "—" if p is None else f"{p:.1f}".replace(".", ",")


def _celda(texto: str) -> str:
    return (texto or "").replace("|", "/").replace("\n", " ").strip()


# ===================================================================== documento
def generar_markdown(
    plantilla: Plantilla,
    ctx: ContextoBorrador,
    identidad: IdentidadEmpresa,
    adaptacion: AdaptacionIA | None = None,
    ahora: datetime | None = None,
    registro=None,
) -> str:
    ahora = ahora or datetime.now(ZONA)
    hoy = ahora.date()
    adaptacion = adaptacion or AdaptacionIA()
    # HU-38: cláusulas completadas con el registro de actividades (hechos del registro: la IA no las reescribe)
    del_registro: dict[str, str] = registro.textos(plantilla.tipo.value) if registro is not None else {}
    prioritarias = set(clausulas_prioritarias(plantilla, ctx))
    numero = {c.id: i for i, c in enumerate(plantilla.clausulas, start=1)}

    partes: list[str] = [
        f"# {plantilla.titulo}",
        "",
        f"**{{{{RAZON_SOCIAL}}}}** · RUT {{{{RUT_EMPRESA}}}}" + (" · Rubro: {{RUBRO}}" if identidad.rubro else ""),
        "",
        "> **BORRADOR PARA REVISIÓN.** Generado por ComplianceAI el {{FECHA}}"
        + (f" a partir del autodiagnóstico del {_fecha(ctx.fecha_evaluacion)}" if ctx.fecha_evaluacion else "")
        + ". No constituye asesoría legal: revísalo con tu asesor legal antes de aprobarlo y completa los "
          "campos marcados con «COMPLETAR».",
        "",
        "| Versión | Estado | Aprobado por | Fecha de aprobación |",
        "|---|---|---|---|",
        "| 0.1 | Borrador en revisión | [COMPLETAR: instancia que aprueba] | [COMPLETAR: fecha] |",
        "",
    ]
    if adaptacion.introduccion:
        partes += [etiquetas_a_marcadores(adaptacion.introduccion.strip()), ""]

    for c in plantilla.clausulas:
        partes += [f"## {numero[c.id]}. {c.titulo}", ""]
        if c.id in del_registro:
            partes += [del_registro[c.id].strip(), "", NOTA_REGISTRO, ""]
            adaptado = None
        else:
            adaptado = adaptacion.secciones.get(c.id) if c.adaptable else None
            partes += [etiquetas_a_marcadores(adaptado.strip()) if adaptado else c.texto, ""]
        if adaptado:
            partes += [NOTA_IA, ""]
        if c.id in prioritarias and c.refuerzo:
            partes += [f"> **Medida prioritaria (brecha detectada en el autodiagnóstico):** {c.refuerzo}", ""]
        f = fundamento(c, ctx)
        if f:
            partes += [f"*Fundamento: {f}.*", ""]

    partes += _anexo_dimensiones(plantilla, ctx, prioritarias, numero)
    partes += _anexo_plan(plantilla, ctx, numero)
    partes += [
        "---",
        "",
        f"*Documento generado con ComplianceAI (Therion Labs) · plantillas {VERSION_PLANTILLAS}"
        + (f" · evaluación {ctx.evaluacion_id}" if ctx.evaluacion_id else "") + ".*",
        "",
    ]
    texto = "\n".join(partes)
    return completar_identidad(texto, identidad, hoy)


def _anexo_dimensiones(plantilla: Plantilla, ctx: ContextoBorrador, prioritarias: set[str],
                       numero: dict[str, int]) -> list[str]:
    """Criterio 2: el documento queda alineado con las dimensiones del modelo de madurez."""
    puntajes = {d.nombre: d for d in ctx.dimensiones}
    filas = []
    for dim in DIMENSIONES:
        clausulas = [c for c in plantilla.clausulas if c.dimension == dim]
        if not clausulas:
            continue
        d = puntajes.get(dim)
        abiertas = [b for b in ctx.brechas if b.dimension == dim]
        secciones = ", ".join(str(numero[c.id]) for c in clausulas)
        refuerzo = [str(numero[c.id]) for c in clausulas if c.id in prioritarias]
        filas.append(
            f"| {dim} | {_puntaje(d.puntaje if d else None)} | "
            f"{ETIQUETA_MADUREZ.get(d.nivel, '—') if d and d.nivel else '—'} | {len(abiertas)} | {secciones}"
            + (f" (prioritarias: {', '.join(refuerzo)})" if refuerzo else "") + " |"
        )
    if not filas:
        return []
    salida = [
        "## Anexo A. Alineación con el autodiagnóstico",
        "",
        "Este documento cubre las siguientes dimensiones del modelo de madurez de gobernanza de IA. Las "
        "secciones prioritarias son las que tratan brechas abiertas de tu evaluación.",
        "",
    ]
    if ctx.puntaje_general is not None:
        salida += [f"Puntaje global de la evaluación: **{_puntaje(ctx.puntaje_general)}** "
                   f"({ETIQUETA_MADUREZ.get(ctx.nivel_general or '', '—')}).", ""]
    return salida + [
        "| Dimensión | Puntaje | Nivel de madurez | Brechas abiertas | Secciones del documento |",
        "|---|---|---|---|---|",
        *filas,
        "",
    ]


def _anexo_plan(plantilla: Plantilla, ctx: ContextoBorrador, numero: dict[str, int]) -> list[str]:
    brechas = ctx.brechas_de(plantilla)
    if not brechas:
        return ["## Anexo B. Plan de implementación", "",
                "Tu evaluación no tiene brechas abiertas en los temas de este documento. Mantén la evidencia de "
                "cumplimiento actualizada y revisa el documento en cada reevaluación.", ""]
    salida = ["## Anexo B. Plan de implementación", "",
              "Brechas abiertas de tu evaluación que este documento ayuda a cerrar, de la más urgente a la menos "
              "urgente. Asigna un responsable y un plazo a cada una.", "",
              "| # | Severidad | Estado | Qué falta | Acción recomendada | Secciones | Responsable y plazo |",
              "|---|---|---|---|---|---|---|"]
    for i, b in enumerate(brechas[:MAX_PLAN], start=1):
        secciones = ", ".join(str(numero[c.id]) for c in plantilla.clausulas if b.control in c.controles)
        salida.append(
            f"| {i} | {b.severidad} | {ETIQUETA_ESTADO.get(b.estado, b.estado)} | {_celda(b.obligacion)} | "
            f"{_celda(b.recomendacion or 'Ver la sección indicada')} | {secciones} | [COMPLETAR] |"
        )
    if len(brechas) > MAX_PLAN:
        salida += ["", f"*Y {len(brechas) - MAX_PLAN} brechas más en el panel de brechas de ComplianceAI.*"]
    return salida + [""]


def sin_codigos_internos(texto: str) -> bool:
    return CODIGO_INTERNO.search(texto or "") is None


def pendientes(texto: str) -> list[str]:
    """Marcadores [COMPLETAR: ...] que quedan, sin repetir y en orden de aparición."""
    return list(dict.fromkeys(m.group(0) for m in MARCADOR_PENDIENTE.finditer(texto or "")))
