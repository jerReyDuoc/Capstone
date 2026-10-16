from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import raiseload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.respuesta import Respuesta
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.catalogo_brechas import CatalogoBrechas


class RespuestaDuplicadaError(Exception):
    """Ya existe una respuesta para ese (evaluación, control): la insertó otra
    petición concurrente entre la búsqueda y el INSERT."""


class RespuestaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, respuesta: Respuesta) -> Respuesta:
        self.session.add(respuesta)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            # Solo la restricción única se traduce; cualquier otra violación
            # (p.ej. una FK) sigue siendo un error.
            if "uq_respuesta_evaluacion_control" in str(e.orig) or "UNIQUE constraint failed" in str(e.orig):
                raise RespuestaDuplicadaError() from e
            raise
        await self.session.refresh(respuesta)
        return respuesta

    async def get(self, respuesta_id: int) -> Respuesta | None:
        result = await self.session.execute(
            select(Respuesta)
            .options(selectinload(Respuesta.evidencias))
            .where(Respuesta.id == respuesta_id)
        )
        return result.scalar_one_or_none()

    async def get_by_evaluacion_control(self, evaluacion_id: int, control_id: int) -> Respuesta | None:
        result = await self.session.execute(
            select(Respuesta).where(
                Respuesta.evaluacion_id == evaluacion_id,
                Respuesta.matriz_controles_id_control == control_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_estado_por_evaluacion(self, evaluacion_id: int) -> list:
        """(id_respuesta, id_control, estado declarado, estado final) de cada respuesta.
        Solo columnas: sirve para el progreso sin cargar texto ni evidencias."""
        result = await self.session.execute(
            select(
                Respuesta.id,
                Respuesta.matriz_controles_id_control,
                Respuesta.estado_clasificacion,
                Respuesta.estado_clasificacion_final,
            ).where(Respuesta.evaluacion_id == evaluacion_id)
        )
        return list(result.all())

    async def update(self, respuesta: Respuesta) -> Respuesta:
        await self.session.commit()
        await self.session.refresh(respuesta)
        return respuesta

    async def get_control(self, control_id: int) -> MatrizControl | None:
        # Solo las columnas del control: sus relaciones (dominio, brecha y la ruta
        # formativa de ésta) son lazy="selectin" y costaban 3 consultas más en cada
        # respuesta. Nadie las usa aquí; si alguien las pide, falla explícitamente.
        result = await self.session.execute(
            select(MatrizControl)
            .options(raiseload(MatrizControl.dominio), raiseload(MatrizControl.brecha))
            .where(MatrizControl.id_control == control_id)
        )
        return result.scalar_one_or_none()

    async def get_brecha(self, brecha_id: int) -> CatalogoBrechas | None:
        result = await self.session.execute(
            select(CatalogoBrechas).where(CatalogoBrechas.id_brecha == brecha_id)
        )
        return result.scalar_one_or_none()
