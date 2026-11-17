"""Repositorio de la contratación (HU-27/30/31): solicitudes, empresas cliente y contratos."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contrato.vigencia import EstadoContrato
from app.domain.errores import ConflictoIntegridadError
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.domain.models.usuario_definitivo import UsuarioDefinitivo


class ContratacionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @asynccontextmanager
    async def traducir_integridad(self) -> AsyncIterator[None]:
        try:
            yield
        except IntegrityError as e:
            raise ConflictoIntegridadError(str(e)) from e

    # ------------------------------------------------------------ solicitudes (HU-31)
    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def existe_solicitud_de_evaluacion(self, evaluacion_id: int) -> bool:
        return await self.session.scalar(select(SolicitudContratacion.id).where(
            SolicitudContratacion.evaluacion_id == evaluacion_id)) is not None

    def agregar_solicitud(self, solicitud: SolicitudContratacion) -> None:
        self.session.add(solicitud)

    async def conteo_solicitudes_por_estado(self) -> list[tuple[str, int]]:
        filas = (await self.session.execute(
            select(SolicitudContratacion.estado, func.count()).group_by(SolicitudContratacion.estado))).all()
        return [(estado, n) for estado, n in filas]

    async def listar_solicitudes(self, estado: str | None, page: int, size: int
                                 ) -> tuple[list[SolicitudContratacion], int]:
        filtros = []
        if estado:
            filtros.append(SolicitudContratacion.estado == estado)
        total = (await self.session.execute(
            select(func.count()).select_from(SolicitudContratacion).where(*filtros))).scalar_one()
        filas = (await self.session.execute(
            select(SolicitudContratacion).where(*filtros)
            .order_by(SolicitudContratacion.id.desc()).offset((page - 1) * size).limit(size)
        )).scalars().all()
        return list(filas), total

    async def obtener_solicitud(self, solicitud_id: int) -> SolicitudContratacion | None:
        return await self.session.get(SolicitudContratacion, solicitud_id)

    async def puntaje_medio_evaluacion(self, evaluacion_id: int) -> Any | None:
        return await self.session.scalar(
            select(func.avg(Resumen.puntaje_obtenido)).where(Resumen.evaluacion_id == evaluacion_id))

    # ------------------------------------------------------------ empresa cliente (HU-27)
    async def obtener_rubro(self, rubro_id: int) -> Rubro | None:
        return await self.session.get(Rubro, rubro_id)

    async def existe_empresa_con_rut(self, rut: str) -> bool:
        return await self.session.scalar(select(Empresa.id).where(Empresa.rut == rut)) is not None

    async def existe_usuario_con_email(self, email: str) -> bool:
        return await self.session.scalar(select(UsuarioDefinitivo.id).where(
            func.lower(UsuarioDefinitivo.email) == email)) is not None

    def agregar_empresa(self, empresa: Empresa) -> None:
        self.session.add(empresa)

    def agregar_usuario_definitivo(self, usuario: UsuarioDefinitivo) -> None:
        self.session.add(usuario)

    async def obtener_empresa(self, empresa_id: int) -> Empresa | None:
        return await self.session.get(Empresa, empresa_id)

    async def usuario_de_empresa(self, empresa_id: int) -> UsuarioDefinitivo | None:
        return await self.session.scalar(select(UsuarioDefinitivo).where(UsuarioDefinitivo.empresa_id == empresa_id))

    async def listar_empresas(self, page: int, size: int
                              ) -> tuple[list[tuple[Empresa, UsuarioDefinitivo | None, int | None]], int]:
        total = (await self.session.execute(select(func.count()).select_from(Empresa))).scalar_one()
        n_evals = (
            select(func.count()).select_from(Evaluacion).where(Evaluacion.empresa_id == Empresa.id)
            .correlate(Empresa).scalar_subquery()
        )
        filas = (await self.session.execute(
            select(Empresa, UsuarioDefinitivo, n_evals)
            .outerjoin(UsuarioDefinitivo, UsuarioDefinitivo.empresa_id == Empresa.id)
            .order_by(Empresa.id.desc()).offset((page - 1) * size).limit(size)
        )).all()
        return [(e, u, n) for e, u, n in filas], total

    async def evaluaciones_de_empresa(self, empresa_id: int) -> list[Evaluacion]:
        filas = (await self.session.execute(
            select(Evaluacion).where(Evaluacion.empresa_id == empresa_id).order_by(Evaluacion.id)
        )).scalars().all()
        return list(filas)

    # ------------------------------------------------------------ contrato (HU-30)
    async def obtener_empresa_para_actualizar(self, empresa_id: int) -> Empresa | None:
        return (await self.session.execute(
            select(Empresa).where(Empresa.id == empresa_id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()

    async def empresas_con_termino_vencido(self, hoy: date) -> list[Empresa]:
        filas = (await self.session.execute(
            select(Empresa).where(
                (Empresa.fecha_termino_contrato < hoy) | (Empresa.estado_contrato == EstadoContrato.TERMINADO.value)
            )
        )).scalars().all()
        return list(filas)
