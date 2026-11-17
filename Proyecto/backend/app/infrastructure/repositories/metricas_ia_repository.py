"""Lecturas de las métricas de la capa de IA (llamadas LLM, sanitizaciones, eventos de seguridad)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.evento_seguridad import EventoSeguridad, OrigenEvento
from app.domain.models.llamada_llm import LlamadaLlm
from app.domain.models.respuesta import Respuesta
from app.domain.models.sanitizacion import Sanitizacion


class MetricasIARepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def llamadas(self, desde: datetime | None, hasta: datetime | None,
                       tarea: str | None, modelo: str | None) -> list[LlamadaLlm]:
        q = select(LlamadaLlm)
        if desde:
            q = q.where(LlamadaLlm.fecha >= desde)
        if hasta:
            q = q.where(LlamadaLlm.fecha <= hasta)
        if tarea:
            q = q.where(LlamadaLlm.tarea == tarea)
        if modelo:
            q = q.where(LlamadaLlm.modelo == modelo)
        return list((await self.session.execute(q.order_by(LlamadaLlm.fecha))).scalars().all())

    async def clasificaciones_revisadas(self, respuesta_ids: set[int]) -> dict[int, str]:
        return {
            r.id: r.clasificacion_revisada
            for r in (await self.session.execute(
                select(Respuesta).where(
                    Respuesta.id.in_(respuesta_ids), Respuesta.clasificacion_revisada.is_not(None)
                )
            )).scalars().all()
        }

    async def sanitizaciones(self, desde: datetime | None, hasta: datetime | None) -> list[Sanitizacion]:
        qs = select(Sanitizacion)
        if desde:
            qs = qs.where(Sanitizacion.fecha >= desde)
        if hasta:
            qs = qs.where(Sanitizacion.fecha <= hasta)
        return list((await self.session.execute(qs)).scalars().all())

    async def eventos_tutor(self, desde: datetime | None, hasta: datetime | None) -> list[tuple[str, str, int]]:
        qe = select(EventoSeguridad.tipo, EventoSeguridad.origen, func.count()).where(
            EventoSeguridad.origen.in_([OrigenEvento.TUTOR.value, OrigenEvento.TUTOR_ANTECEDENTE.value]))
        if desde:
            qe = qe.where(EventoSeguridad.fecha >= desde)
        if hasta:
            qe = qe.where(EventoSeguridad.fecha <= hasta)
        filas = (await self.session.execute(qe.group_by(EventoSeguridad.tipo, EventoSeguridad.origen))).all()
        return [(t, o, n) for t, o, n in filas]

    async def alertas_salida_llm(self, desde: datetime | None, hasta: datetime | None) -> dict[str, int]:
        qv = select(EventoSeguridad.tipo, func.count()).where(
            EventoSeguridad.origen == OrigenEvento.SALIDA_LLM.value)
        if desde:
            qv = qv.where(EventoSeguridad.fecha >= desde)
        if hasta:
            qv = qv.where(EventoSeguridad.fecha <= hasta)
        return {t: n for t, n in (await self.session.execute(qv.group_by(EventoSeguridad.tipo))).all()}
