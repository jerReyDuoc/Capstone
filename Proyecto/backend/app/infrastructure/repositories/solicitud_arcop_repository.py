from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models.solicitud_arcop import EstadoSolicitudARCOP, SolicitudARCOP, EventoSolicitud
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.usuario_temporal import UsuarioTemporal


class SolicitudARCOPRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def existe_usuario(self, usuario_id: int) -> bool:
        return await self.session.get(UsuarioTemporal, usuario_id) is not None

    async def existe_usuario_definitivo(self, usuario_id: int) -> bool:
        from app.domain.models.usuario_definitivo import UsuarioDefinitivo

        return await self.session.get(UsuarioDefinitivo, usuario_id) is not None

    async def existe_evaluacion(self, evaluacion_id: int) -> bool:
        return await self.session.get(Evaluacion, evaluacion_id) is not None

    async def existe_codigo(self, codigo: str) -> bool:
        q = select(func.count()).select_from(SolicitudARCOP).where(SolicitudARCOP.codigo_seguimiento == codigo)
        return ((await self.session.execute(q)).scalar() or 0) > 0

    async def get_por_codigo(self, codigo: str) -> SolicitudARCOP | None:
        q = select(SolicitudARCOP).where(SolicitudARCOP.codigo_seguimiento == codigo)
        return (await self.session.execute(q)).scalar_one_or_none()

    async def create(self, solicitud: SolicitudARCOP, evento: EventoSolicitud) -> SolicitudARCOP:
        """Crea la solicitud y su primer evento en una sola transacción."""
        solicitud.eventos.append(evento)
        self.session.add(solicitud)
        await self.session.commit()
        return await self.get(solicitud.id)

    async def get(self, solicitud_id: int, para_actualizar: bool = False) -> SolicitudARCOP | None:
        """
        Con para_actualizar=True bloquea la fila (SELECT ... FOR UPDATE en PostgreSQL)
        para que dos cambios de estado simultáneos no se pisen.
        """
        q = (
            select(SolicitudARCOP)
            .where(SolicitudARCOP.id == solicitud_id)
            .options(selectinload(SolicitudARCOP.eventos))
            .execution_options(populate_existing=True)
        )
        if para_actualizar:
            q = q.with_for_update(of=SolicitudARCOP)
        result = await self.session.execute(q)
        return result.scalar_one_or_none()

    async def list(
        self,
        usuario_temporal_id: int | None = None,
        estado: str | None = None,
        evaluacion_id: int | None = None,
        tipo: str | None = None,
        solo_vencidas_al: datetime | None = None,
        usuario_definitivo_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[SolicitudARCOP], int]:
        q = select(SolicitudARCOP).order_by(SolicitudARCOP.id.desc())
        count_q = select(func.count()).select_from(SolicitudARCOP)
        filtros = []
        if usuario_temporal_id is not None:
            filtros.append(SolicitudARCOP.usuario_temporal_id == usuario_temporal_id)
        if evaluacion_id is not None:
            filtros.append(SolicitudARCOP.evaluacion_id == evaluacion_id)
        if usuario_definitivo_id is not None:
            filtros.append(SolicitudARCOP.usuario_definitivo_id == usuario_definitivo_id)
        if estado:
            filtros.append(SolicitudARCOP.estado == estado)
        if tipo:
            filtros.append(SolicitudARCOP.tipo == tipo)
        if solo_vencidas_al is not None:
            filtros.append(SolicitudARCOP.estado.not_in(EstadoSolicitudARCOP.finales()))
            filtros.append(or_(
                SolicitudARCOP.fecha_limite_respuesta < solo_vencidas_al,
                and_(
                    SolicitudARCOP.estado == EstadoSolicitudARCOP.PENDIENTE_INFORMACION.value,
                    SolicitudARCOP.fecha_limite_informacion < solo_vencidas_al,
                ),
            ))
        for f in filtros:
            q = q.where(f)
            count_q = count_q.where(f)

        total = (await self.session.execute(count_q)).scalar() or 0
        result = await self.session.execute(q.offset(offset).limit(limit))
        return list(result.scalars().all()), total

    async def guardar(self, solicitud: SolicitudARCOP, *eventos: EventoSolicitud) -> SolicitudARCOP:
        """Persiste el cambio de la solicitud y sus eventos en la MISMA transacción."""
        solicitud.eventos.extend(eventos)
        await self.session.commit()
        return await self.get(solicitud.id)
