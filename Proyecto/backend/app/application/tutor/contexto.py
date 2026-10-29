"""
HU-15 · Contexto AISLADO del Agente IA Tutor.

Criterio 1 ("carga aislada del contexto de brechas no-conformes de la empresa"):

  - La empresa sale SIEMPRE del token (ClienteConServicio), nunca de un parámetro.
  - Se usa la evaluación MÁS RECIENTE con resultados de esa empresa
    (evaluacion_de_la_empresa(None), la misma regla del panel de formación).
  - Entran las brechas no conformes: no_cumplido y parcialmente_cumplido (decisión del PO,
    28-oct: el tutor ayuda a subir no_cumplido -> parcialmente -> cumplido desde cualquier
    estado). Se leen en cada mensaje: si una evidencia de remediación (HU-17) mejora un
    control, el tutor lo ve en el mensaje siguiente.
  - Datos CONFIABLES del catálogo y del control: código, dimensión, descripción, severidad,
    estado, acción recomendada, módulo formativo y (v1.1) la obligación, la pregunta, la
    evidencia esperada y la fuente normativa real (framework y artículo) del control.
  - v1.1 (prueba del equipo, 28-oct): ANTECEDENTES de la propia empresa para las brechas en
    foco: su justificación y el resultado de su última evidencia. Sin esto el tutor no podía
    responder "¿qué tengo implementado?" ni "¿por qué me rechazaron la evidencia?". Son
    textos NO CONFIABLES (ya anonimizados al guardarse, HU-06) y además pasan otra vez por
    el NER del gateway antes del LLM, entre delimitadores.
  - NO van la razón social, el RUT ni datos de contacto de la empresa.

Este módulo es lógica de aplicación: el LLM no lo llama ni toca la BD; el caso de uso arma
el contexto y lo entrega al agente como dato de solo lectura.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes.analisis import (
    ESTADOS_BRECHA,
    Brecha,
    construir_brechas,
    construir_plan,
    nivel_madurez,
    nivel_por_puntaje,
)
from app.application.informes.carga import DatosEvaluacion, SinResultadosError, cargar_evaluacion
from app.application.schemas.tutor import NivelTutor


class ContextoTutorError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje = status, codigo, mensaje


@dataclass(frozen=True)
class DetalleControl:
    """Datos del control de la matriz (catálogo de Therion Labs: confiables)."""
    obligacion: str | None = None
    pregunta: str | None = None
    evidencia_esperada: str | None = None
    framework: str | None = None
    articulo: str | None = None
    recomendacion: str | None = None

    @property
    def fuente(self) -> str | None:
        partes = [p.strip() for p in (self.framework, self.articulo) if p and p.strip()]
        return " · ".join(partes) or None


@dataclass(frozen=True)
class AntecedenteBrecha:
    """Lo que la EMPRESA dijo o subió para el control (no confiable; anonimizado al guardarse)."""
    justificacion: str | None = None
    evidencia_estado: str | None = None          # pending | validated | rejected | ...
    evidencia_clasificacion: str | None = None   # la clasificación que propuso el LLM
    evidencia_motivo: str | None = None          # por qué (justificación del LLM / errores)
    evidencia_remediacion: bool = False

    @property
    def vacio(self) -> bool:
        return not (self.justificacion or self.evidencia_estado)


@dataclass(frozen=True)
class BrechaTutor:
    ref: str                     # identificador único en la evaluación (código del control)
    codigo: str                  # código de la brecha del catálogo (puede repetirse entre controles)
    control_codigo: str | None
    dominio: str
    descripcion: str
    severidad: str
    estado: str
    accion: str | None
    prioridad: int
    respuesta_id: int
    ruta_id: int | None = None
    ruta_nombre: str | None = None
    ruta_nivel: str | None = None
    formacion_completada: bool = False
    control: DetalleControl = field(default_factory=DetalleControl)
    antecedente: AntecedenteBrecha = field(default_factory=AntecedenteBrecha)

    def como_dict(self) -> dict:
        return {
            "ref": self.ref, "codigo": self.codigo, "control_codigo": self.control_codigo,
            "dominio": self.dominio, "descripcion": self.descripcion, "severidad": self.severidad,
            "estado": self.estado, "accion": self.accion, "prioridad": self.prioridad,
            "respuesta_id": self.respuesta_id, "ruta_id": self.ruta_id, "ruta_nombre": self.ruta_nombre,
            "ruta_nivel": self.ruta_nivel, "formacion_completada": self.formacion_completada,
            "fuente_normativa": self.control.fuente,
        }


@dataclass(frozen=True)
class DominioTutor:
    nombre: str
    puntaje: float | None
    nivel: str | None


@dataclass(frozen=True)
class FocoRuta:
    """Módulo formativo desde el que se abrió el tutor (fija el nivel por defecto)."""
    id: int
    nombre: str
    dominio: str | None
    nivel: str | None
    objetivo: str | None
    contenidos: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextoTutor:
    evaluacion_id: int
    fecha_evaluacion: str | None
    puntaje_general: float | None
    nivel_madurez: str | None
    dominios: tuple[DominioTutor, ...]
    brechas: tuple[BrechaTutor, ...]
    foco: FocoRuta | None = None
    brechas_omitidas: int = 0          # por sobre el máximo que entra al prompt
    rutas_del_plan: frozenset[int] = field(default_factory=frozenset)

    @property
    def referencias_validas(self) -> frozenset[str]:
        """Lo que el tutor puede citar en brechas_referenciadas."""
        return frozenset(b.ref for b in self.brechas) | frozenset(b.codigo for b in self.brechas)

    def normalizar_referencias(self, refs: list[str]) -> list[str]:
        """Deja solo referencias del contexto, como `ref` únicas y en el orden en que vinieron."""
        por_ref = {b.ref: b.ref for b in self.brechas}
        por_codigo: dict[str, str] = {}
        for b in self.brechas:
            por_codigo.setdefault(b.codigo, b.ref)
        salida: list[str] = []
        for r in refs:
            r = (r or "").strip().strip("[]").strip()
            ref = por_ref.get(r) or por_codigo.get(r)
            if ref and ref not in salida:
                salida.append(ref)
        return salida

    def por_ref(self) -> dict[str, BrechaTutor]:
        return {b.ref: b for b in self.brechas}

    def referencias_normativas(self, refs: list[str]) -> list[str]:
        """v1.1: la fuente REAL (framework · artículo) de los controles citados, sin repetir."""
        tabla = self.por_ref()
        salida: list[str] = []
        for r in refs:
            fuente = tabla[r].control.fuente if r in tabla else None
            if fuente and fuente not in salida:
                salida.append(fuente)
        return salida

    @property
    def articulos_validos(self) -> frozenset[str]:
        """Números de artículo/cláusula que aparecen en las fuentes del contexto."""
        numeros: set[str] = set()
        for b in self.brechas:
            numeros.update(re.findall(r"\d+(?:\.\d+)*", b.control.articulo or ""))
        return frozenset(numeros)

    def brechas_nombradas(self, textos: list[str] | None = None) -> list[str]:
        """Brechas que se nombran en los textos (sin importar mayúsculas: "gob-003"), en orden de aparición."""
        texto = " ".join(t for t in (textos or []) if t).upper()
        encontradas: list[tuple[int, str]] = []
        for b in self.brechas:
            claves = {b.ref.upper(), (b.control_codigo or "").upper(), b.codigo.upper()} - {""}
            posiciones = [m.start() for c in claves
                          for m in re.finditer(rf"(?<![A-Z0-9-]){re.escape(c)}(?![0-9])", texto)]
            if posiciones:
                encontradas.append((min(posiciones), b.ref))
        return list(dict.fromkeys(r for _, r in sorted(encontradas)))

    def brechas_en_foco(self, textos: list[str] | None = None, maximo: int = 3) -> list[str]:
        """
        Brechas de las que se está hablando: las nombradas en los textos o, si no se nombra
        ninguna, las `maximo` más prioritarias. Solo de estas va el detalle al prompt.
        """
        refs = self.brechas_nombradas(textos) or [b.ref for b in sorted(self.brechas, key=lambda x: x.prioridad)]
        return refs[:maximo]

    def nivel_sugerido(self) -> NivelTutor:
        """
        Nivel por defecto ("la ruta por defecto", decisión del PO del 28-oct):
          1. el nivel del módulo desde el que se abrió el tutor;
          2. si no, el del módulo de la brecha más prioritaria;
          3. si no, el que corresponde al puntaje general (misma regla del plan formativo).
        """
        if self.foco and NivelTutor.normalizar(self.foco.nivel):
            return NivelTutor.normalizar(self.foco.nivel)
        for b in sorted(self.brechas, key=lambda x: x.prioridad):
            if NivelTutor.normalizar(b.ruta_nivel):
                return NivelTutor.normalizar(b.ruta_nivel)
        return NivelTutor.normalizar(nivel_por_puntaje(self.puntaje_general)) or NivelTutor.INICIAL

    def huella(self) -> str:
        """Identifica qué brechas (y en qué estado) vio el tutor. Para auditoría, sin PII."""
        base = {"ev": self.evaluacion_id, "b": sorted((b.ref, b.estado) for b in self.brechas)}
        return hashlib.sha256(json.dumps(base, ensure_ascii=False).encode()).hexdigest()[:32]

    def resumen(self) -> dict:
        por_estado: dict[str, int] = {}
        por_severidad: dict[str, int] = {}
        for b in self.brechas:
            por_estado[b.estado] = por_estado.get(b.estado, 0) + 1
            por_severidad[b.severidad] = por_severidad.get(b.severidad, 0) + 1
        return {
            "evaluacion_id": self.evaluacion_id,
            "fecha_evaluacion": self.fecha_evaluacion,
            "puntaje_general": self.puntaje_general,
            "nivel_madurez": self.nivel_madurez,
            "nivel_sugerido": self.nivel_sugerido().value,
            "brechas_total": len(self.brechas) + self.brechas_omitidas,
            "brechas_por_estado": por_estado,
            "brechas_por_severidad": por_severidad,
            "brechas": [b.como_dict() for b in self.brechas],
            "foco": None if self.foco is None else {
                "ruta_id": self.foco.id, "nombre": self.foco.nombre, "nivel": self.foco.nivel},
        }


# ------------------------------------------------------------------ construcción (pura)
def construir_contexto(
    datos: DatosEvaluacion,
    rutas_completadas: set[int] | frozenset[int] = frozenset(),
    foco_ruta_id: int | None = None,
    max_brechas: int = 40,
    detalles: dict[int, tuple[DetalleControl, AntecedenteBrecha]] | None = None,
) -> ContextoTutor:
    detalles = detalles or {}
    puntajes = {d.nombre: d.puntaje for d in datos.dominios if d.puntaje is not None}
    brechas: list[Brecha] = [b for b in construir_brechas(datos.respuestas, puntajes)
                             if b.estado in ESTADOS_BRECHA]
    plan = construir_plan(brechas, datos.dominios, datos.rutas)
    rutas_plan = {m.ruta.id: m.ruta for d in plan.dimensiones for m in d.modulos}

    foco = None
    if foco_ruta_id is not None:
        ruta = rutas_plan.get(foco_ruta_id)
        if ruta is None:
            raise ContextoTutorError(404, "RUTA_NO_ENCONTRADA",
                                     "Ese módulo no está en el plan formativo de tu empresa.")
        foco = FocoRuta(id=ruta.id, nombre=ruta.nombre, dominio=ruta.dominio_efectivo,
                        nivel=ruta.nivel_efectivo, objetivo=ruta.objetivo, contenidos=tuple(ruta.contenidos))

    vistos: set[str] = set()
    tutor: list[BrechaTutor] = []
    for b in brechas:  # ya vienen por prioridad (1 = más urgente)
        ref = b.control_codigo or b.codigo
        if ref in vistos:
            ref = f"{ref}#{b.respuesta_id}"
        vistos.add(ref)
        tutor.append(BrechaTutor(
            ref=ref, codigo=b.codigo, control_codigo=b.control_codigo, dominio=b.dominio,
            descripcion=b.descripcion, severidad=b.severidad, estado=b.estado, accion=b.accion,
            prioridad=b.prioridad, respuesta_id=b.respuesta_id,
            ruta_id=b.ruta.id if b.ruta else None,
            ruta_nombre=b.ruta.nombre if b.ruta else None,
            ruta_nivel=b.ruta.nivel_efectivo if b.ruta else None,
            formacion_completada=bool(b.ruta and b.ruta.id in rutas_completadas),
            control=detalles.get(b.respuesta_id, (DetalleControl(), AntecedenteBrecha()))[0],
            antecedente=detalles.get(b.respuesta_id, (DetalleControl(), AntecedenteBrecha()))[1],
        ))

    omitidas = max(0, len(tutor) - max_brechas)
    return ContextoTutor(
        evaluacion_id=datos.evaluacion_id,
        fecha_evaluacion=datos.fecha_inicio.isoformat() if datos.fecha_inicio else None,
        puntaje_general=datos.puntaje_general,
        nivel_madurez=nivel_madurez(datos.puntaje_general),
        dominios=tuple(DominioTutor(d.nombre, d.puntaje, nivel_madurez(d.puntaje) if d.puntaje is not None else None)
                       for d in datos.dominios),
        brechas=tuple(tutor[:max_brechas]),
        foco=foco,
        brechas_omitidas=omitidas,
        rutas_del_plan=frozenset(rutas_plan),
    )


# ------------------------------------------------------------------ carga desde la BD
async def cargar_contexto_tutor(db: AsyncSession, empresa_id: int, foco_ruta_id: int | None = None,
                                max_brechas: int = 40) -> ContextoTutor:
    """Contexto de la evaluación más reciente con resultados de la empresa (y solo de ella)."""
    from app.application.use_cases.formacion_empresa import FormacionError, evaluacion_de_la_empresa
    from app.domain.models.formacion import AvanceFormativo, EstadoAvance

    try:
        evaluacion_id = await evaluacion_de_la_empresa(db, empresa_id, None)
    except FormacionError as e:
        raise ContextoTutorError(e.status, e.codigo, e.mensaje)
    try:
        datos = await cargar_evaluacion(db, evaluacion_id)
    except SinResultadosError as e:
        raise ContextoTutorError(404, "SIN_RESULTADOS", str(e))
    completadas = set((await db.execute(
        select(AvanceFormativo.ruta_formativa_id).where(
            AvanceFormativo.empresa_id == empresa_id,
            AvanceFormativo.estado == EstadoAvance.COMPLETADO.value,
        )
    )).scalars().all())
    previo = construir_contexto(datos, completadas, foco_ruta_id, max_brechas)
    detalles = await _detalles(db, [b.respuesta_id for b in previo.brechas])
    return construir_contexto(datos, completadas, foco_ruta_id, max_brechas, detalles)


MAX_ANTECEDENTE = 500


def _corto(texto: str | None, maximo: int = MAX_ANTECEDENTE) -> str | None:
    t = " ".join((texto or "").split())
    if not t:
        return None
    return t if len(t) <= maximo else t[:maximo - 1].rstrip() + "…"


async def _detalles(db: AsyncSession, respuesta_ids: list[int]) -> dict[int, tuple[DetalleControl, AntecedenteBrecha]]:
    """Control de la matriz y antecedentes de la empresa de cada brecha (solo de SUS respuestas)."""
    from app.domain.models.evidencia import Evidencia
    from app.domain.models.matriz_control import MatrizControl
    from app.domain.models.respuesta import Respuesta

    if not respuesta_ids:
        return {}
    filas = (await db.execute(
        select(Respuesta.id, Respuesta.justificacion_usuario, MatrizControl)
        .outerjoin(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
        .where(Respuesta.id.in_(respuesta_ids))
    )).all()
    ultimas: dict[int, Evidencia] = {}
    for ev in (await db.execute(
        select(Evidencia).where(Evidencia.respuesta_id.in_(respuesta_ids)).order_by(Evidencia.id_evidencia)
    )).scalars().all():
        ultimas[ev.respuesta_id] = ev  # la última gana
    salida = {}
    for rid, justificacion, mc in filas:
        ev = ultimas.get(rid)
        motivo = None
        if ev is not None:
            errores = "; ".join(str(e) for e in (ev.errores_validacion or [])[:3])
            motivo = _corto(" ".join(x for x in (ev.justificacion_llm, errores) if x), 400)
        salida[rid] = (
            DetalleControl(
                obligacion=getattr(mc, "obligacion", None), pregunta=getattr(mc, "pregunta_evaluacion", None),
                evidencia_esperada=_corto(getattr(mc, "evidencia_esperada", None), 600),
                framework=getattr(mc, "framework_fuente", None), articulo=getattr(mc, "articulo_referencia", None),
                recomendacion=_corto(getattr(mc, "recomendacion", None), 400),
            ),
            AntecedenteBrecha(
                justificacion=_corto(justificacion),
                evidencia_estado=ev.estado_validacion if ev else None,
                evidencia_clasificacion=ev.clasificacion_llm if ev else None,
                evidencia_motivo=motivo,
                evidencia_remediacion=bool(ev and getattr(ev, "origen", None) == "remediacion"),
            ),
        )
    return salida
