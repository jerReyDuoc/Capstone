"""HU-40 · Consultas de la revisión interna del registro (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.bitacora_auditoria import BitacoraAuditoria
from app.domain.models.empresa import Empresa
from app.domain.models.rat_modelo import RatActividad, RatActividadVersion
from app.domain.models.rat_informe import RatInforme
from app.domain.models.rat_revision import (ABIERTA, EN_CURSO, REVISADA, RatObservacion, RatPaqueteEvidencia,
                                            RatRevision, ConfiguracionRevisionRat)
from app.domain.models.usuario_definitivo import UsuarioDefinitivo


class RevisionInternaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---- empresa / usuario
    async def bloquear_empresa(self, empresa_id: int) -> None:
        await self.session.execute(select(Empresa.id).where(Empresa.id == empresa_id).with_for_update())

    async def empresa(self, empresa_id: int) -> Any | None:
        return await self.session.get(Empresa, empresa_id)

    async def usuario_definitivo(self, empresa_id: int) -> Any | None:
        return (await self.session.execute(select(UsuarioDefinitivo).where(
            UsuarioDefinitivo.empresa_id == empresa_id))).scalar_one_or_none()

    # ---- revisiones
    async def revision_en_curso(self, empresa_id: int, *, bloquear: bool = False) -> Any | None:
        q = select(RatRevision).where(RatRevision.empresa_id == empresa_id, RatRevision.estado == EN_CURSO)
        if bloquear:
            q = q.with_for_update()
        return (await self.session.execute(q)).scalar_one_or_none()

    async def revision(self, revision_id: int) -> Any | None:
        return await self.session.get(RatRevision, revision_id)

    async def revisiones_revisadas(self, empresa_id: int, limite: int) -> list:
        return list((await self.session.execute(
            select(RatRevision).where(RatRevision.empresa_id == empresa_id, RatRevision.estado == REVISADA)
            .order_by(RatRevision.fecha_revision.desc(), RatRevision.id.desc()).limit(limite))).scalars().all())

    async def ultima_revisada(self, empresa_id: int) -> Any | None:
        return (await self.session.execute(select(RatRevision).where(
            RatRevision.empresa_id == empresa_id, RatRevision.estado == REVISADA)
            .order_by(RatRevision.fecha_revision.desc()).limit(1))).scalar_one_or_none()

    async def numero_revision_en_curso(self, empresa_id: int) -> int | None:
        return (await self.session.execute(select(RatRevision.numero).where(
            RatRevision.empresa_id == empresa_id, RatRevision.estado == EN_CURSO))).scalar_one_or_none()

    async def revisada_de_version(self, empresa_id: int, version: int) -> Any | None:
        return (await self.session.execute(select(RatRevision).where(
            RatRevision.empresa_id == empresa_id, RatRevision.estado == REVISADA,
            RatRevision.version_rat == version).order_by(RatRevision.id.desc()).limit(1))).scalar_one_or_none()

    async def revisada_anterior(self, empresa_id: int, numero: int) -> Any | None:
        return (await self.session.execute(select(RatRevision).where(
            RatRevision.empresa_id == empresa_id, RatRevision.estado == REVISADA,
            RatRevision.numero < numero).order_by(RatRevision.numero.desc()).limit(1))).scalar_one_or_none()

    async def max_numero_revision(self, empresa_id: int) -> int:
        return (await self.session.execute(select(func.max(RatRevision.numero)).where(
            RatRevision.empresa_id == empresa_id))).scalar() or 0

    async def ultimas_revisiones_por_empresa(self) -> dict[int, datetime]:
        return dict((await self.session.execute(
            select(RatRevision.empresa_id, func.max(RatRevision.fecha_revision))
            .where(RatRevision.estado == REVISADA).group_by(RatRevision.empresa_id))).all())

    # ---- observaciones
    async def observaciones(self, empresa_id: int, revision_id: int | None = None) -> list:
        q = select(RatObservacion).where(RatObservacion.empresa_id == empresa_id)
        if revision_id is not None:
            q = q.where(RatObservacion.revision_id == revision_id)
        return list((await self.session.execute(q.order_by(RatObservacion.numero))).scalars().all())

    async def observaciones_abiertas(self, empresa_id: int) -> int:
        return (await self.session.execute(select(func.count()).select_from(RatObservacion).where(
            RatObservacion.empresa_id == empresa_id, RatObservacion.estado == ABIERTA))).scalar() or 0

    async def observacion_bloqueada(self, observacion_id: int, empresa_id: int) -> Any | None:
        return (await self.session.execute(select(RatObservacion).where(
            RatObservacion.id == observacion_id, RatObservacion.empresa_id == empresa_id).with_for_update())
        ).scalar_one_or_none()

    async def max_numero_observacion(self, empresa_id: int) -> int:
        return (await self.session.execute(select(func.max(RatObservacion.numero)).where(
            RatObservacion.empresa_id == empresa_id))).scalar() or 0

    # ---- configuración / vigencias
    async def config(self, empresa_id: int) -> Any | None:
        return await self.session.get(ConfiguracionRevisionRat, empresa_id)

    async def primera_vigencia(self, empresa_id: int) -> datetime | None:
        return (await self.session.execute(select(func.min(RatActividadVersion.fecha)).where(
            RatActividadVersion.empresa_id == empresa_id))).scalar()

    async def primeras_vigencias_por_empresa(self) -> dict[int, datetime]:
        return dict((await self.session.execute(
            select(RatActividadVersion.empresa_id, func.min(RatActividadVersion.fecha))
            .group_by(RatActividadVersion.empresa_id))).all())

    # ---- informes del registro
    async def ultimo_informe(self, empresa_id: int) -> Any | None:
        return (await self.session.execute(select(RatInforme).where(RatInforme.empresa_id == empresa_id)
                                           .order_by(RatInforme.id.desc()).limit(1))).scalar_one_or_none()

    async def informe(self, informe_id: int) -> Any | None:
        return await self.session.get(RatInforme, informe_id)

    async def informes_recientes(self, empresa_id: int, limite: int) -> list:
        return list((await self.session.execute(select(RatInforme).where(RatInforme.empresa_id == empresa_id)
                                                .order_by(RatInforme.id.desc()).limit(limite))).scalars().all())

    async def informe_de_version(self, empresa_id: int, version: int) -> Any | None:
        return (await self.session.execute(select(RatInforme).where(
            RatInforme.empresa_id == empresa_id, RatInforme.version_rat == version)
            .order_by(RatInforme.id.desc()).limit(1))).scalar_one_or_none()

    async def ultimo_informe_con_huella(self, empresa_id: int, huella: str) -> Any | None:
        return (await self.session.execute(select(RatInforme).where(
            RatInforme.empresa_id == empresa_id, RatInforme.huella == huella)
            .order_by(RatInforme.id.desc()).limit(1))).scalar_one_or_none()

    async def informes_con_huella(self, empresa_id: int, huella: str) -> list:
        return list((await self.session.execute(select(RatInforme).where(
            RatInforme.empresa_id == empresa_id, RatInforme.huella == huella)
            .order_by(RatInforme.id))).scalars())

    # ---- actividades
    async def versiones_de_actividades(self, empresa_id: int, actividad_ids: list[int]) -> dict[tuple[int, int], Any]:
        return {(v.actividad_id, v.numero): v for v in (await self.session.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id.in_(actividad_ids),
                                              RatActividadVersion.empresa_id == empresa_id))).scalars()}

    async def nombres_de_actividades(self, empresa_id: int) -> dict[int, str]:
        return dict((await self.session.execute(select(RatActividad.id, RatActividad.nombre).where(
            RatActividad.empresa_id == empresa_id))).all())

    # ---- bitácora y paquetes de evidencia
    async def historial_auditoria(self, *, actor_rol: str, actor_id: int | None, empresa_id: int,
                                  prefijos: tuple[str, ...], hasta: datetime | None, limite: int) -> list:
        cond_cliente = (BitacoraAuditoria.actor_rol == actor_rol) & (BitacoraAuditoria.actor_id == actor_id) \
            & or_(*[BitacoraAuditoria.accion.like(f"{p}%") for p in prefijos])
        cond_sistema = (BitacoraAuditoria.entidad == "rat_revision_config") & \
            (BitacoraAuditoria.entidad_id == empresa_id)
        q = select(BitacoraAuditoria).where(or_(cond_cliente, cond_sistema))
        if hasta is not None:
            q = q.where(BitacoraAuditoria.fecha <= hasta)
        return list((await self.session.execute(q.order_by(BitacoraAuditoria.id.desc()).limit(limite))).scalars().all())

    async def paquetes_desde(self, empresa_id: int, desde: datetime) -> int:
        return (await self.session.execute(select(func.count()).select_from(RatPaqueteEvidencia).where(
            RatPaqueteEvidencia.empresa_id == empresa_id, RatPaqueteEvidencia.fecha >= desde))).scalar() or 0

    async def paquete_por_sha256(self, sha256: str, empresa_id: int) -> Any | None:
        return (await self.session.execute(select(RatPaqueteEvidencia).where(
            RatPaqueteEvidencia.sha256 == sha256, RatPaqueteEvidencia.empresa_id == empresa_id))).scalar_one_or_none()

    async def paquete(self, paquete_id: int) -> Any | None:
        return await self.session.get(RatPaqueteEvidencia, paquete_id)

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)
