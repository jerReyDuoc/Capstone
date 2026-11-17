"""Consultas del ciclo de la evaluación extraídas de los casos de uso (A-12): remediación,
migración, cierre/resumen, límites y alta de la encuesta pública. La sesión es la unidad de
trabajo del caso de uso (commit/rollback/flush los decide él)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import ORIGEN_REMEDIACION, ORIGENES_REMEDIACION, EstadoValidacion, Evidencia
from app.domain.models.formacion_recorrido import AvanceFormativo, EstadoAvance
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.matriz_version import ESTADO_PUBLICADA, MatrizVersion
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_arcop import EstadoSolicitudARCOP, SolicitudARCOP
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.domain.models.usuario_temporal import UsuarioTemporal

_SIN_TERMINAR = (EstadoValidacion.PENDING.value, EstadoValidacion.PROCESSING.value)


class EvaluacionConsultasRepository:
    """Implementa RemediacionRepositoryPort, MigracionEvaluacionRepositoryPort,
    CierreEvaluacionRepositoryPort, LimitesEncuestaRepositoryPort y EncuestaPublicaRepositoryPort."""

    def __init__(self, session: AsyncSession):
        self.db = session

    # ------------------------------------------------------------ remediación (HU-17)
    async def filas_resumen(self, evaluacion_id: int) -> list[Any]:
        return (await self.db.execute(
            select(Resumen.puntaje_obtenido, Resumen.total_controles_evaluados)
            .where(Resumen.evaluacion_id == evaluacion_id)
        )).all()

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.db.get(Evaluacion, evaluacion_id)

    async def obtener_respuesta(self, respuesta_id: int) -> Respuesta | None:
        return await self.db.get(Respuesta, respuesta_id)

    async def obtener_evidencia(self, evidencia_id: int) -> Evidencia | None:
        return await self.db.get(Evidencia, evidencia_id)

    async def controles_por_ids(self, ids: list[int]) -> dict[int, MatrizControl]:
        return {
            c.id_control: c for c in (await self.db.execute(
                select(MatrizControl).where(MatrizControl.id_control.in_(ids))
            )).scalars().all()
        }

    async def rutas_completadas(self, empresa_id: int) -> set[int]:
        return set((await self.db.execute(
            select(AvanceFormativo.ruta_formativa_id).where(
                AvanceFormativo.empresa_id == empresa_id, AvanceFormativo.estado == EstadoAvance.COMPLETADO.value)
        )).scalars().all())

    async def evidencias_remediacion(self, respuesta_ids: list[int]) -> list[Evidencia]:
        return list((await self.db.execute(
            select(Evidencia).where(Evidencia.respuesta_id.in_(respuesta_ids),
                                    Evidencia.origen.in_(ORIGENES_REMEDIACION))   # HU-38: también el registro
            .order_by(Evidencia.id_evidencia)
        )).scalars().all())

    async def mejoras(self, evaluacion_id: int) -> list[Any]:
        return (await self.db.execute(
            select(Evidencia.fecha_procesada, Evidencia.puntaje_previo, Evidencia.puntaje_resultante,
                   Evidencia.respuesta_id, Evidencia.estado_previo, Evidencia.estado_resultante)
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .where(Respuesta.evaluacion_id == evaluacion_id, Evidencia.origen.in_(ORIGENES_REMEDIACION),
                   Evidencia.puntaje_resultante.is_not(None), Evidencia.puntaje_previo.is_not(None),
                   Evidencia.puntaje_resultante > Evidencia.puntaje_previo)
            .order_by(Evidencia.id_evidencia)
        )).all()

    async def contar_en_proceso(self, respuesta_id: int) -> int:
        return (await self.db.execute(
            select(func.count(Evidencia.id_evidencia)).where(
                Evidencia.respuesta_id == respuesta_id, Evidencia.origen == ORIGEN_REMEDIACION,
                Evidencia.estado_validacion.in_(_SIN_TERMINAR))
        )).scalar() or 0

    def agregar_evidencia(self, evidencia: Evidencia) -> None:
        self.db.add(evidencia)

    # ------------------------------------------------------------ migración (HU-27)
    async def bloquear_solicitud(self, solicitud_id: int) -> SolicitudContratacion | None:
        return await self.db.scalar(
            select(SolicitudContratacion).where(SolicitudContratacion.id == solicitud_id).with_for_update()
        )

    async def bloquear_evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return (await self.db.execute(
            select(Evaluacion).where(Evaluacion.id == evaluacion_id).with_for_update()
        )).scalar_one_or_none()

    async def bloquear_usuario_temporal(self, usuario_id: int) -> UsuarioTemporal | None:
        return await self.db.scalar(
            select(UsuarioTemporal).where(UsuarioTemporal.id == usuario_id).with_for_update()
        )

    async def contar_contenido(self, evaluacion_id: int) -> tuple[int, int, int]:
        respuestas = (await self.db.execute(
            select(func.count()).select_from(Respuesta).where(Respuesta.evaluacion_id == evaluacion_id)
        )).scalar_one()
        evidencias = (await self.db.execute(
            select(func.count()).select_from(Evidencia).join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .where(Respuesta.evaluacion_id == evaluacion_id)
        )).scalar_one()
        dimensiones = (await self.db.execute(
            select(func.count()).select_from(Resumen).where(Resumen.evaluacion_id == evaluacion_id)
        )).scalar_one()
        return respuestas, evidencias, dimensiones

    async def hay_arcop_abierta(self, evaluacion_id: int, usuario_temporal_id: int | None) -> bool:
        condicion = SolicitudARCOP.evaluacion_id == evaluacion_id
        if usuario_temporal_id is not None:
            condicion = or_(condicion, SolicitudARCOP.usuario_temporal_id == usuario_temporal_id)
        return (await self.db.scalar(
            select(SolicitudARCOP.id)
            .where(condicion, SolicitudARCOP.estado.not_in(list(EstadoSolicitudARCOP.finales())))
            .limit(1)
        )) is not None

    # ------------------------------------------------------------ cierre y resumen
    async def contar_evidencias_sin_terminar(self, evaluacion_id: int) -> int:
        return (await self.db.execute(
            select(func.count(Evidencia.id_evidencia))
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .where(
                Respuesta.evaluacion_id == evaluacion_id,
                Evidencia.estado_validacion.in_(_SIN_TERMINAR),
            )
        )).scalar() or 0

    async def respuestas_con_evidencia(self, respuesta_ids: list[int]) -> set[int]:
        return set((await self.db.execute(
            select(Evidencia.respuesta_id).where(Evidencia.respuesta_id.in_(respuesta_ids)).distinct()
        )).scalars().all())

    async def version_matriz_publicada(self) -> tuple[int, str] | None:
        vigente = (await self.db.execute(
            select(MatrizVersion.id, MatrizVersion.version_texto).where(MatrizVersion.estado == ESTADO_PUBLICADA)
        )).first()
        return None if vigente is None else (vigente[0], vigente[1])

    async def respuestas_con_control(self, evaluacion_id: int) -> list[Any]:
        result = await self.db.execute(
            select(Respuesta, MatrizControl)
            .join(MatrizControl, Respuesta.matriz_controles_id_control == MatrizControl.id_control)
            .where(Respuesta.evaluacion_id == evaluacion_id)
            .order_by(Respuesta.id)
        )
        return result.all()

    async def eliminar_resumenes(self, evaluacion_id: int) -> None:
        existing = await self.db.execute(
            select(Resumen).where(Resumen.evaluacion_id == evaluacion_id)
        )
        for r in existing.scalars().all():
            await self.db.delete(r)
        await self.db.flush()

    def agregar_resumen(self, resumen: Resumen) -> None:
        self.db.add(resumen)

    # ------------------------------------------------------------ límites de la encuesta pública
    async def origen_de_evaluacion(self, evaluacion_id: int) -> str | None:
        return await self.db.scalar(select(Evaluacion.origen).where(Evaluacion.id == evaluacion_id))

    async def contar_evidencias(self, evaluacion_id: int) -> int:
        return int(await self.db.scalar(
            select(func.count(Evidencia.id_evidencia))
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .where(Respuesta.evaluacion_id == evaluacion_id)
        ) or 0)

    async def evaluacion_de_respuesta(self, respuesta_id: int) -> int | None:
        return await self.db.scalar(select(Respuesta.evaluacion_id).where(Respuesta.id == respuesta_id))

    # ------------------------------------------------------------ alta de la encuesta pública
    async def existe_rubro(self, rubro_id: int) -> bool:
        return await self.db.get(Rubro, rubro_id) is not None

    def agregar_usuario_temporal(self, usuario: UsuarioTemporal) -> None:
        self.db.add(usuario)

    def agregar_evaluacion(self, evaluacion: Evaluacion) -> None:
        self.db.add(evaluacion)
