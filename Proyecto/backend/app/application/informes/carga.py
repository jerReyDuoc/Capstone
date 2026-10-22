"""
Lee de la BD todo lo que necesitan los informes y lo entrega como las dataclasses de
analisis.py (la lógica no toca la BD).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.informes.analisis import (
    BrechaCatalogo,
    ComparativaDominio,
    DominioResultado,
    RespuestaFila,
    RutaCatalogo,
)
from app.core.config import settings
from app.domain.models.benchmark import Benchmark
from app.domain.models.catalogo_brechas import CatalogoBrechas
from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.usuario_temporal import UsuarioTemporal


class SinResultadosError(Exception):
    """La evaluación no existe o todavía no tiene resumen (no se ha completado)."""


@dataclass(frozen=True)
class DatosEvaluacion:
    evaluacion_id: int
    fecha_inicio: date | None
    estado: str | None
    rubro: str | None
    puntaje_general: float
    controles_evaluados: int
    en_revision: int
    dominios: list[DominioResultado]
    respuestas: list[RespuestaFila]
    rutas: list[RutaCatalogo]
    comparativa: list[ComparativaDominio]
    email_registrado: str | None


def _ruta(r: RutaFormativa | None, dominios: dict[int, str]) -> RutaCatalogo | None:
    if r is None:
        return None
    return RutaCatalogo(
        id=r.id, nombre=r.nombre or f"Ruta {r.id}",
        dominio=dominios.get(r.dominio_id) if r.dominio_id else None,
        nivel=r.nivel, objetivo=r.objetivo,
        objetivos_especificos=r.lista_objetivos, contenidos=r.lista_contenidos,
        horas=r.horas, modalidad=r.modalidad, publico_objetivo=r.publico_objetivo,
    )


def _brecha(b: CatalogoBrechas | None, rutas: dict[int, RutaCatalogo]) -> BrechaCatalogo | None:
    if b is None:
        return None
    return BrechaCatalogo(
        id=b.id_brecha, codigo=b.codigo_brecha, categoria=b.categoria,
        comportamiento=b.comportamiento_detectado, criticidad=b.criticidad, accion=b.accion_sistema,
        ruta=rutas.get(b.ruta_formativa_id) if b.ruta_formativa_id else None,
    )


async def cargar_evaluacion(db: AsyncSession, evaluacion_id: int) -> DatosEvaluacion:
    evaluacion = await db.get(Evaluacion, evaluacion_id)
    if evaluacion is None:
        raise SinResultadosError("Evaluación no encontrada")

    filas_resumen = (await db.execute(
        select(Resumen, Dominio).join(Dominio, Resumen.dominio_id == Dominio.id)
        .where(Resumen.evaluacion_id == evaluacion_id)
    )).all()
    if not filas_resumen:
        raise SinResultadosError("La evaluación todavía no tiene resultados: complétala primero.")

    nombres_dominio = {d.id: d.nombre_dominio or f"Dominio {d.id}"
                       for d in (await db.execute(select(Dominio))).scalars().all()}

    dominios = [
        DominioResultado(dominio_id=d.id, nombre=d.nombre_dominio or f"Dominio {d.id}",
                         puntaje=r.puntaje_obtenido, nivel_madurez=r.nivel_madurez,
                         controles=r.total_controles_evaluados)
        for r, d in filas_resumen
    ]
    total = sum(d.controles or 0 for d in dominios)
    puntaje_general = (
        round(sum((d.puntaje or 0) * (d.controles or 0) for d in dominios) / total, 2) if total else 0.0
    )

    rutas_orm = (await db.execute(select(RutaFormativa).order_by(RutaFormativa.id))).scalars().all()
    rutas = {r.id: _ruta(r, nombres_dominio) for r in rutas_orm}
    brechas = {
        b.id_brecha: _brecha(b, rutas)
        for b in (await db.execute(select(CatalogoBrechas))).scalars().all()
    }
    controles = {
        c.id_control: c
        for c in (await db.execute(
            select(MatrizControl).options(selectinload(MatrizControl.dominio))
        )).scalars().all()
    }

    respuestas_orm = (await db.execute(
        select(Respuesta).where(Respuesta.evaluacion_id == evaluacion_id).order_by(Respuesta.id)
    )).scalars().all()
    respuestas: list[RespuestaFila] = []
    en_revision = 0
    for r in respuestas_orm:
        estado = r.estado_clasificacion_final or r.estado_clasificacion
        if estado == "requiere_revision":
            en_revision += 1
        c = controles.get(r.matriz_controles_id_control) if r.matriz_controles_id_control else None
        respuestas.append(RespuestaFila(
            id=r.id, estado=estado,
            control_id=c.id_control if c else None,
            control_codigo=c.codigo_control if c else None,
            control_obligacion=c.obligacion if c else None,
            control_criticidad=c.criticidad if c else None,
            control_recomendacion=c.recomendacion if c else None,
            control_dominio=(c.dominio.nombre_dominio if c and c.dominio else None),
            brecha_respuesta=brechas.get(r.catalogo_brechas_id_brecha) if r.catalogo_brechas_id_brecha else None,
            brecha_control=brechas.get(c.catalogo_brechas_id_brecha) if c and c.catalogo_brechas_id_brecha else None,
        ))

    usuario = await db.get(UsuarioTemporal, evaluacion.usuario_temporal_id) if evaluacion.usuario_temporal_id else None
    rubro = await db.get(Rubro, usuario.rubro_id) if usuario and usuario.rubro_id else None
    bench = {}
    if usuario and usuario.rubro_id:
        bench = {b.dominio_id: b for b in (await db.execute(
            select(Benchmark).where(Benchmark.rubro_id == usuario.rubro_id)
        )).scalars().all()}
    comparativa = [
        ComparativaDominio(
            dominio=d.nombre, tu_puntaje=d.puntaje,
            promedio_industria=(bench[d.dominio_id].promedio_puntaje
                                if d.dominio_id in bench and referencia_suficiente(bench[d.dominio_id]) else None),
            muestras=(bench[d.dominio_id].total_evaluaciones or 0) if d.dominio_id in bench else 0,
            meta=settings.META_CUMPLIMIENTO_PUNTAJE,
        )
        for d in dominios
    ]

    return DatosEvaluacion(
        evaluacion_id=evaluacion_id, fecha_inicio=evaluacion.fecha_inicio, estado=evaluacion.estado_progreso,
        rubro=rubro.nombre_rubro if rubro else None,
        puntaje_general=puntaje_general, controles_evaluados=total, en_revision=en_revision,
        dominios=sorted(dominios, key=lambda d: d.nombre), respuestas=respuestas,
        rutas=[r for r in rutas.values() if r is not None],
        comparativa=sorted(comparativa, key=lambda c: c.dominio),
        email_registrado=usuario.email if usuario else None,
    )


def referencia_suficiente(bm: Benchmark | None) -> bool:
    """El promedio del rubro solo se muestra con suficientes evaluaciones (incluye la propia)."""
    return bm is not None and (bm.total_evaluaciones or 0) >= settings.COMPARATIVA_MIN_MUESTRAS
