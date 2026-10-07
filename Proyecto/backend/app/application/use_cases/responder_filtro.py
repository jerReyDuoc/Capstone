from datetime import date

from app.application.filters.control_tree import get_controles_aplicables
from app.domain.models.respuesta_filtro import RespuestaFiltro
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.pregunta_filtro_repository import PreguntaFiltroRepository
from app.infrastructure.repositories.respuesta_filtro_repository import RespuestaFiltroRepository


class ResponderFiltroUseCase:
    def __init__(
        self,
        evaluacion_repo: EvaluacionRepository,
        pregunta_repo: PreguntaFiltroRepository,
        respuesta_repo: RespuestaFiltroRepository,
    ):
        self.evaluacion_repo = evaluacion_repo
        self.pregunta_repo = pregunta_repo
        self.respuesta_repo = respuesta_repo

    async def execute(self, evaluacion_id: int, respuestas: dict[str, bool]) -> dict:
        # 1. Validar que la evaluación existe
        evaluacion = await self.evaluacion_repo.get(evaluacion_id)
        if not evaluacion:
            raise ValueError(f"Evaluación {evaluacion_id} no encontrada")

        # 2. Validar que las 7 preguntas estén respondidas
        preguntas = await self.pregunta_repo.list_activas()
        codigos_requeridos = {p.codigo for p in preguntas}
        codigos_recibidos = set(respuestas.keys())

        faltantes = codigos_requeridos - codigos_recibidos
        if faltantes:
            raise ValueError(
                f"Faltan respuestas para: {', '.join(sorted(faltantes))}"
            )

        desconocidos = codigos_recibidos - codigos_requeridos
        if desconocidos:
            raise ValueError(
                f"Códigos desconocidos: {', '.join(sorted(desconocidos))}"
            )

        # 3. Si ya existían respuestas, las borramos y reescribimos
        #    (permite rehacer el filtro si el usuario se equivocó)
        await self.respuesta_repo.delete_by_evaluacion(evaluacion_id)

        # 4. Crear las nuevas respuestas
        preguntas_por_codigo = {p.codigo: p for p in preguntas}
        nuevas = [
            RespuestaFiltro(
                evaluacion_id=evaluacion_id,
                pregunta_id=preguntas_por_codigo[codigo].id_pregunta,
                respuesta=valor,
                fecha_respuesta=date.today(),
            )
            for codigo, valor in respuestas.items()
        ]
        await self.respuesta_repo.bulk_create(nuevas)

        # 5. Marcar la evaluación como filtrada
        evaluacion.filtro_completado = True
        evaluacion.fecha_filtro = date.today()
        await self.evaluacion_repo.update(evaluacion)

        # 6. Calcular controles aplicables
        controles = get_controles_aplicables(respuestas)

        return {
            "evaluacion_id": evaluacion_id,
            "filtro_completado": True,
            "controles_aplicables": len(controles),
            "codigos_controles": controles,
        }