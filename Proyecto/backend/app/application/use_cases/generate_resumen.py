from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta, EstadoClasificacion
from app.domain.models.resumen import Resumen
from app.infrastructure.repositories.respuesta_filtro_repository import RespuestaFiltroRepository
from app.application.filters.control_tree import get_controles_aplicables


# Puntajes por clasificación
PUNTAJE_CUMPLIDO = 1.0
PUNTAJE_PARCIAL = 0.5
PUNTAJE_NO_CUMPLIDO = 0.0
# Bloqueada por seguridad (posible prompt injection): cuenta como 0 y NO se excluye
# del denominador, para que inyectar texto nunca pueda subir el puntaje.
PUNTAJE_REQUIERE_REVISION = 0.0


def nivel_madurez(puntaje: float) -> str:
    """Traduce un puntaje 0-100 a un nivel cualitativo."""
    if puntaje <= 25:
        return "inicial"
    if puntaje <= 50:
        return "en_desarrollo"
    if puntaje <= 75:
        return "gestionado"
    return "optimizado"


class GenerateResumenUseCase:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, evaluacion_id: int) -> dict:
        # 1. Validar evaluación
        evaluacion = await self.session.get(Evaluacion, evaluacion_id)
        if not evaluacion:
            raise ValueError(f"Evaluación {evaluacion_id} no encontrada")

        # 2. Obtener respuestas del filtro y calcular controles aplicables
        resp_filtro_repo = RespuestaFiltroRepository(self.session)
        respuestas_filtro = await resp_filtro_repo.list_by_evaluacion(evaluacion_id)
        respuestas_filtro_dict = {
            r.pregunta.codigo: r.respuesta
            for r in respuestas_filtro
            if r.pregunta is not None
        }
        codigos_aplicables = set(get_controles_aplicables(respuestas_filtro_dict))

        # 3. Obtener todas las respuestas de la evaluación con sus controles
        result = await self.session.execute(
            select(Respuesta, MatrizControl)
            .join(MatrizControl, Respuesta.matriz_controles_id_control == MatrizControl.id_control)
            .where(Respuesta.evaluacion_id == evaluacion_id)
        )
        pares = list(result.all())

        # 4. Filtrar a los que aplican y no son "no_aplica"
        por_dominio: dict[int, list[dict]] = {}

        for respuesta, control in pares:
            if control.codigo_control not in codigos_aplicables:
                continue

            if respuesta.estado_clasificacion_final == EstadoClasificacion.NO_APLICA.value:
                continue

            if control.dominio_id is None:
                continue

            clasif = respuesta.estado_clasificacion_final or respuesta.estado_clasificacion
            if clasif == EstadoClasificacion.CUMPLIDO.value:
                puntaje = PUNTAJE_CUMPLIDO
            elif clasif == EstadoClasificacion.PARCIALMENTE_CUMPLIDO.value:
                puntaje = PUNTAJE_PARCIAL
            elif clasif == EstadoClasificacion.NO_CUMPLIDO.value:
                puntaje = PUNTAJE_NO_CUMPLIDO
            elif clasif == EstadoClasificacion.REQUIERE_REVISION.value:
                puntaje = PUNTAJE_REQUIERE_REVISION
            else:
                continue

            por_dominio.setdefault(control.dominio_id, []).append({
                "clasificacion": clasif,
                "puntaje": puntaje,
            })

        # 5. Reemplazar resúmenes previos
        existing = await self.session.execute(
            select(Resumen).where(Resumen.evaluacion_id == evaluacion_id)
        )
        for r in existing.scalars().all():
            await self.session.delete(r)
        await self.session.flush()

        # 6. Crear nuevos resúmenes por dominio
        resumenes_creados = []
        total_general_controles = 0
        total_general_puntaje = 0.0

        for dominio_id, items in por_dominio.items():
            total_evaluados = len(items)
            if total_evaluados == 0:
                continue

            suma = sum(i["puntaje"] for i in items)
            puntaje_dominio = round((suma / total_evaluados) * 100, 2)
            cumplidos = sum(1 for i in items if i["clasificacion"] == EstadoClasificacion.CUMPLIDO.value)
            parciales = sum(1 for i in items if i["clasificacion"] == EstadoClasificacion.PARCIALMENTE_CUMPLIDO.value)
            no_cumplidos = sum(1 for i in items if i["clasificacion"] == EstadoClasificacion.NO_CUMPLIDO.value)
            en_revision = sum(1 for i in items if i["clasificacion"] == EstadoClasificacion.REQUIERE_REVISION.value)

            resumen = Resumen(
                evaluacion_id=evaluacion_id,
                dominio_id=dominio_id,
                puntaje_obtenido=puntaje_dominio,
                nivel_madurez=nivel_madurez(puntaje_dominio),
                total_controles_evaluados=total_evaluados,
            )
            self.session.add(resumen)
            resumenes_creados.append({
                "dominio_id": dominio_id,
                "puntaje": puntaje_dominio,
                "nivel": nivel_madurez(puntaje_dominio),
                "total_evaluados": total_evaluados,
                "cumplidos": cumplidos,
                "parciales": parciales,
                "no_cumplidos": no_cumplidos,
                "en_revision": en_revision,
            })

            total_general_controles += total_evaluados
            total_general_puntaje += suma

        # 7. Calcular puntaje general
        puntaje_general = 0.0
        if total_general_controles > 0:
            puntaje_general = round((total_general_puntaje / total_general_controles) * 100, 2)

        await self.session.commit()

        return {
            "evaluacion_id": evaluacion_id,
            "puntaje_general": puntaje_general,
            "nivel_madurez_general": nivel_madurez(puntaje_general),
            "total_controles_evaluados": total_general_controles,
            "dominios": resumenes_creados,
        }