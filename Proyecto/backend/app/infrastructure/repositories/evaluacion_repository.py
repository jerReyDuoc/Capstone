from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.filters.control_tree import get_controles_aplicables
from app.domain.models.evaluacion import ESTADOS_CERRADOS, Evaluacion
from app.domain.models.pregunta_filtro import PreguntaFiltro
from app.domain.models.respuesta_filtro import RespuestaFiltro


@dataclass(frozen=True)
class ContextoEvaluacion:
    """
    Lo mínimo que el cuestionario necesita saber de una evaluación para decidir
    qué preguntas mostrar y si acepta respuestas. Se obtiene en UNA consulta.
    """
    id: int
    estado_progreso: str | None
    filtro_completado: bool
    respuestas_filtro: dict[str, bool] = field(default_factory=dict)

    @property
    def cerrada(self) -> bool:
        return self.estado_progreso in ESTADOS_CERRADOS

    @property
    def codigos_aplicables(self) -> list[str]:
        """Códigos de control que aplican según el filtro F1–F7 (orden alfabético)."""
        if not self.filtro_completado:
            return []
        return get_controles_aplicables(self.respuestas_filtro)


class EvaluacionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, evaluacion_id: int) -> Evaluacion | None:
        result = await self.session.execute(
            select(Evaluacion).where(Evaluacion.id == evaluacion_id)
        )
        return result.scalar_one_or_none()

    async def get_contexto(self, evaluacion_id: int) -> ContextoEvaluacion | None:
        """
        Evaluación + respuestas del filtro en una sola ida a la BD (LEFT JOIN y solo
        columnas: sin cargar entidades ORM ni relaciones lazy="selectin").
        Devuelve None si la evaluación no existe.
        """
        result = await self.session.execute(
            select(
                Evaluacion.id,
                Evaluacion.estado_progreso,
                Evaluacion.filtro_completado,
                PreguntaFiltro.codigo,
                RespuestaFiltro.respuesta,
            )
            .select_from(Evaluacion)
            .outerjoin(RespuestaFiltro, RespuestaFiltro.evaluacion_id == Evaluacion.id)
            .outerjoin(PreguntaFiltro, PreguntaFiltro.id_pregunta == RespuestaFiltro.pregunta_id)
            .where(Evaluacion.id == evaluacion_id)
        )
        filas = result.all()
        if not filas:
            return None
        primera = filas[0]
        return ContextoEvaluacion(
            id=primera.id,
            estado_progreso=primera.estado_progreso,
            filtro_completado=bool(primera.filtro_completado),
            respuestas_filtro={
                f.codigo: bool(f.respuesta) for f in filas if f.codigo is not None
            },
        )

    async def update(self, evaluacion) -> "Evaluacion":
        await self.session.commit()
        await self.session.refresh(evaluacion)
        return evaluacion
