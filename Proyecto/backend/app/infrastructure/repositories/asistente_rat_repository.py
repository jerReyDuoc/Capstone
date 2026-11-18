"""HU-39 · Consultas del asistente de IA del mapa de datos y el RAT (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.asistente import AsistenteDocumento, AsistenteMensaje, AsistentePropuesta, AsistenteSesion
from app.domain.models.mapa_datos_tablas import MapaDatos, MapaElemento, MapaFlujo
from app.domain.models.rat_modelo import RatActividad


class AsistenteRatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---- sesiones
    async def sesion(self, sesion_id: int, empresa_id: int, *, bloquear: bool = False) -> Any | None:
        q = select(AsistenteSesion).where(AsistenteSesion.id == sesion_id, AsistenteSesion.empresa_id == empresa_id)
        if bloquear:
            # populate_existing: si la sesión ya estaba cargada, se relee lo que hay en la BD al bloquearla
            q = q.with_for_update().execution_options(populate_existing=True)
        return (await self.session.execute(q)).scalar_one_or_none()

    async def sesion_activa(self, empresa_id: int) -> Any | None:
        return (await self.session.execute(
            select(AsistenteSesion).where(AsistenteSesion.empresa_id == empresa_id,
                                          AsistenteSesion.estado == "activa")
            .order_by(AsistenteSesion.id.desc()).limit(1))).scalar_one_or_none()

    # ---- propuestas
    async def propuesta(self, propuesta_id: int, empresa_id: int, *, bloquear: bool = False) -> Any | None:
        q = select(AsistentePropuesta).where(AsistentePropuesta.id == propuesta_id,
                                             AsistentePropuesta.empresa_id == empresa_id)
        if bloquear:
            q = q.with_for_update()
        return (await self.session.execute(q)).scalar_one_or_none()

    async def propuestas_recientes(self, empresa_id: int, limite: int) -> list:
        return list((await self.session.execute(
            select(AsistentePropuesta).where(AsistentePropuesta.empresa_id == empresa_id)
            .order_by(AsistentePropuesta.id.desc()).limit(limite))).scalars().all())

    async def propuesta_por_clave(self, empresa_id: int, clave: str) -> Any | None:
        return (await self.session.execute(select(AsistentePropuesta).where(
            AsistentePropuesta.empresa_id == empresa_id, AsistentePropuesta.clave == clave))).scalar_one_or_none()

    async def entidad_de_propuesta(self, tipo: str, propuesta_id: int, empresa_id: int) -> int | None:
        """T-12: id del elemento, flujo o actividad que ya creó esta propuesta (reintento), o None."""
        if tipo in ("elemento", "flujo"):
            modelo = MapaElemento if tipo == "elemento" else MapaFlujo
            q = (select(modelo.id).join(MapaDatos, MapaDatos.id == modelo.mapa_id)
                 .where(modelo.propuesta_ia_id == propuesta_id, MapaDatos.empresa_id == empresa_id))
        else:
            q = select(RatActividad.id).where(RatActividad.propuesta_ia_id == propuesta_id,
                                              RatActividad.empresa_id == empresa_id)
        return (await self.session.execute(q.order_by(q.selected_columns[0]).limit(1))).scalar_one_or_none()

    async def claves_de_propuestas(self, empresa_id: int) -> list[str]:
        return list((await self.session.execute(
            select(AsistentePropuesta.clave).where(AsistentePropuesta.empresa_id == empresa_id))).scalars().all())

    async def contar_pendientes(self, empresa_id: int) -> int:
        return (await self.session.execute(select(func.count()).select_from(AsistentePropuesta).where(
            AsistentePropuesta.empresa_id == empresa_id, AsistentePropuesta.estado == "sugerida"))).scalar() or 0

    # ---- mensajes y documentos
    async def mensajes_recientes(self, sesion_id: int, limite: int) -> list:
        """Del más nuevo al más antiguo."""
        return list((await self.session.execute(
            select(AsistenteMensaje).where(AsistenteMensaje.sesion_id == sesion_id)
            .order_by(AsistenteMensaje.id.desc()).limit(limite))).scalars().all())

    async def mensajes_usuario_no_bloqueados(self, sesion_id: int, limite: int) -> list:
        """Del más nuevo al más antiguo."""
        return list((await self.session.execute(
            select(AsistenteMensaje).where(AsistenteMensaje.sesion_id == sesion_id, AsistenteMensaje.rol == "usuario",
                                           AsistenteMensaje.bloqueado.is_(False))
            .order_by(AsistenteMensaje.id.desc()).limit(limite))).scalars().all())

    async def documentos_recientes(self, empresa_id: int, limite: int) -> list:
        return list((await self.session.execute(
            select(AsistenteDocumento).where(AsistenteDocumento.empresa_id == empresa_id)
            .order_by(AsistenteDocumento.id.desc()).limit(limite))).scalars().all())

    # ---- RAT
    async def actividades(self, empresa_id: int) -> list:
        return list((await self.session.execute(
            select(RatActividad).where(RatActividad.empresa_id == empresa_id).order_by(RatActividad.nombre)
        )).scalars().all())

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)
