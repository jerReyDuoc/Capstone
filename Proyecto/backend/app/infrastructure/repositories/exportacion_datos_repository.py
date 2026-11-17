"""Lecturas de los datos personales de un titular para la exportación ARCOP (HU-32)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dominio import Dominio
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import Evidencia
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.respuesta_filtro import RespuestaFiltro
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_arcop import SolicitudARCOP
from app.domain.models.usuario_definitivo import UsuarioDefinitivo
from app.domain.models.usuario_temporal import UsuarioTemporal


class ExportacionDatosRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def solicitudes_del_titular(self, solicitud: SolicitudARCOP) -> list[SolicitudARCOP]:
        if solicitud.usuario_definitivo_id is not None:
            filtro = SolicitudARCOP.usuario_definitivo_id == solicitud.usuario_definitivo_id
        elif solicitud.evaluacion_id is not None:
            filtro = SolicitudARCOP.evaluacion_id == solicitud.evaluacion_id
        else:
            filtro = SolicitudARCOP.usuario_temporal_id == solicitud.usuario_temporal_id
        return list((await self.session.execute(
            select(SolicitudARCOP).where(filtro).order_by(SolicitudARCOP.id))).scalars().all())

    async def nombre_rubro(self, rubro_id: int) -> str | None:
        rubro = await self.session.get(Rubro, rubro_id)
        return rubro.nombre_rubro if rubro else None

    async def usuario_definitivo(self, usuario_id: int) -> UsuarioDefinitivo | None:
        return await self.session.get(UsuarioDefinitivo, usuario_id)

    async def empresa(self, empresa_id: int) -> Empresa | None:
        return await self.session.get(Empresa, empresa_id)

    async def usuario_temporal(self, usuario_id: int) -> UsuarioTemporal | None:
        return await self.session.get(UsuarioTemporal, usuario_id)

    async def evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def evaluaciones_de_usuario_temporal(self, usuario_id: int) -> list[Evaluacion]:
        return list((await self.session.execute(
            select(Evaluacion).where(Evaluacion.usuario_temporal_id == usuario_id).order_by(Evaluacion.id)
        )).scalars().all())

    async def respuestas_filtro(self, evaluacion_id: int) -> list[RespuestaFiltro]:
        return list((await self.session.execute(
            select(RespuestaFiltro).where(RespuestaFiltro.evaluacion_id == evaluacion_id)
            .order_by(RespuestaFiltro.id_respuesta_filtro)
        )).scalars().all())

    async def respuestas_con_control(self, evaluacion_id: int) -> list[tuple[Respuesta, MatrizControl | None]]:
        filas = (await self.session.execute(
            select(Respuesta, MatrizControl)
            .outerjoin(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
            .where(Respuesta.evaluacion_id == evaluacion_id)
            .order_by(Respuesta.id)
        )).all()
        return [(r, c) for r, c in filas]

    async def evidencias_de_respuestas(self, respuesta_ids: list[int]) -> list[Evidencia]:
        return list((await self.session.execute(
            select(Evidencia).where(Evidencia.respuesta_id.in_(respuesta_ids)).order_by(Evidencia.id_evidencia)
        )).scalars().all())

    async def resumen_con_dominio(self, evaluacion_id: int) -> list[tuple[Resumen, Dominio | None]]:
        filas = (await self.session.execute(
            select(Resumen, Dominio)
            .outerjoin(Dominio, Dominio.id == Resumen.dominio_id)
            .where(Resumen.evaluacion_id == evaluacion_id)
            .order_by(Resumen.id_resumen)
        )).all()
        return [(x, d) for x, d in filas]
