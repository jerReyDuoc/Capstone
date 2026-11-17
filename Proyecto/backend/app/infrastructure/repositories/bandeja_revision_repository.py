"""Consultas de la bandeja de revisión del Oficial de Cumplimiento (HU-22), extraídas del caso de uso (A-12)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.dominio import Dominio
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.evidencia import Evidencia
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import EstadoClasificacion, FuenteClasificacion, Respuesta
from app.domain.models.usuario_admin import UsuarioAdmin

_REQ = EstadoClasificacion.REQUIERE_REVISION.value


class BandejaRevisionRepository:
    def __init__(self, session: AsyncSession):
        self.s = session

    async def candidatas(self, evaluacion_id: int | None, dominio_id: int | None, limite: int) -> list[Any]:
        con_llm = exists().where(Evidencia.respuesta_id == Respuesta.id,
                                 or_(Evidencia.clasificacion_llm.is_not(None), Evidencia.confianza.is_not(None)))
        con_evento = exists().where(EventoSeguridad.respuesta_id == Respuesta.id)
        q = (
            select(Respuesta, MatrizControl, Dominio.nombre_dominio, Evaluacion, Empresa.razon_social)
            .outerjoin(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
            .outerjoin(Dominio, Dominio.id == MatrizControl.dominio_id)
            .outerjoin(Evaluacion, Evaluacion.id == Respuesta.evaluacion_id)
            .outerjoin(Empresa, Empresa.id == Evaluacion.empresa_id)
            .options(selectinload(Respuesta.evidencias))
            .where(or_(
                con_llm, con_evento,
                Respuesta.fuente_clasificacion.in_([FuenteClasificacion.SEGURIDAD.value,
                                                    FuenteClasificacion.REVISION.value]),
                Respuesta.estado_clasificacion_final == _REQ,
            ))
            .order_by(Respuesta.id.desc())
            .limit(limite)
        )
        if evaluacion_id:
            q = q.where(Respuesta.evaluacion_id == evaluacion_id)
        if dominio_id:
            q = q.where(MatrizControl.dominio_id == dominio_id)
        return (await self.s.execute(q)).all()

    async def conteo_eventos_por_respuesta(self, respuesta_ids: list[int]) -> dict[int, int]:
        conteo: dict[int, int] = {}
        for rid, n in (await self.s.execute(
            select(EventoSeguridad.respuesta_id, func.count())
            .where(EventoSeguridad.respuesta_id.in_(respuesta_ids)).group_by(EventoSeguridad.respuesta_id)
        )).all():
            conteo[rid] = n
        return conteo

    @staticmethod
    def _q_eventos(estado: str, evaluacion_id: int | None, origen: str | None):
        q = select(EventoSeguridad, MatrizControl.codigo_control, MatrizControl.pregunta_evaluacion).outerjoin(
            MatrizControl, MatrizControl.id_control == EventoSeguridad.matriz_control_id)
        if estado == "pendiente":
            q = q.where(EventoSeguridad.revisado.is_(False))
        elif estado == "revisada":
            q = q.where(EventoSeguridad.revisado.is_(True))
        if evaluacion_id:
            q = q.where(EventoSeguridad.evaluacion_id == evaluacion_id)
        if origen:
            q = q.where(EventoSeguridad.origen == origen)
        return q

    async def contar_eventos(self, estado: str, evaluacion_id: int | None, origen: str | None) -> int:
        q = self._q_eventos(estado, evaluacion_id, origen)
        return (await self.s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()

    async def listar_eventos(self, estado: str, evaluacion_id: int | None, origen: str | None,
                             offset: int, limite: int) -> list[Any]:
        q = self._q_eventos(estado, evaluacion_id, origen)
        return (await self.s.execute(
            q.order_by(EventoSeguridad.fecha.desc(), EventoSeguridad.id_evento.desc())
            .offset(offset).limit(limite))).all()

    async def fila_respuesta(self, respuesta_id: int) -> Any | None:
        q = (
            select(Respuesta, MatrizControl, Dominio.nombre_dominio, Evaluacion, Empresa.razon_social)
            .outerjoin(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
            .outerjoin(Dominio, Dominio.id == MatrizControl.dominio_id)
            .outerjoin(Evaluacion, Evaluacion.id == Respuesta.evaluacion_id)
            .outerjoin(Empresa, Empresa.id == Evaluacion.empresa_id)
            .options(selectinload(Respuesta.evidencias))
            .where(Respuesta.id == respuesta_id)
        )
        return (await self.s.execute(q)).first()

    async def eventos_de_respuesta(self, respuesta_id: int) -> list[EventoSeguridad]:
        return list((await self.s.execute(
            select(EventoSeguridad).where(EventoSeguridad.respuesta_id == respuesta_id)
            .order_by(EventoSeguridad.fecha.desc()))).scalars().all())

    async def correos_admin(self, ids: set[int]) -> dict[int, str]:
        return {a.id: a.email for a in (await self.s.execute(
            select(UsuarioAdmin).where(UsuarioAdmin.id.in_(ids)))).scalars().all()}

    async def respuestas_revisadas(self) -> list[Respuesta]:
        return list((await self.s.execute(
            select(Respuesta).options(selectinload(Respuesta.evidencias))
            .where(Respuesta.clasificacion_revisada.is_not(None))
        )).scalars().all())

    async def conteo_resoluciones_eventos(self) -> dict[str | None, int]:
        return dict((await self.s.execute(
            select(EventoSeguridad.resolucion, func.count()).where(EventoSeguridad.revisado.is_(True))
            .group_by(EventoSeguridad.resolucion))).all())
