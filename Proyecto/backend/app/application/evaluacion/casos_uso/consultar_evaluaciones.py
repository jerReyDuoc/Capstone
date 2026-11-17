"""Consultas de evaluaciones y respuestas, y marcado de prueba (HU-19/HU-20/HU-27). A-41."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auditoria.acciones import Accion
from app.domain.auth.actor import Actor, Rol
from app.domain.models.evaluacion import Evaluacion
from app.domain.ports.bitacora_port import BitacoraPort
from app.domain.ports.repositorios_consultas import (
    ALCANCE_EMPRESA,
    ALCANCE_EVALUACION,
    ALCANCE_NADA,
    ALCANCE_REFERENTE,
    ALCANCE_SIN_PUBLICAS,
    ALCANCE_TODO,
    AlcanceEvaluaciones,
    ConsultaEvaluacionesPort,
)


class EvaluacionNoEncontradaError(Exception):
    """La evaluación no existe (la ruta responde 404)."""

    def __init__(self, mensaje: str = "Evaluación no encontrada"):
        super().__init__(mensaje)


@dataclass
class Pagina:
    items: list[Any]
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        return (self.total + self.size - 1) // self.size if self.size > 0 else 0


class ConsultarEvaluacionesUseCase:
    def __init__(self, repo: ConsultaEvaluacionesPort, session: AsyncSession, bitacora: BitacoraPort):
        self.repo = repo
        self.session = session
        self.bitacora = bitacora

    async def _alcance(self, actor: Actor | None) -> AlcanceEvaluaciones:
        # HU-19/HU-20: las de la encuesta pública solo las lista un admin; un encuestado ve solo
        # la suya y un referente solo las de su invitación. Sin token solo se llega con
        # EXIGIR_TOKEN_EVALUACIONES=false (dev).
        if actor is None:
            return AlcanceEvaluaciones(ALCANCE_SIN_PUBLICAS)
        if actor.es_encuestado:
            return AlcanceEvaluaciones(ALCANCE_EVALUACION, actor.id)
        if actor.rol == Rol.REFERENTE.value:
            return AlcanceEvaluaciones(ALCANCE_REFERENTE, actor.id)
        if actor.es_cliente:
            # HU-27: solo las evaluaciones de su empresa (migradas y, HU-29, sus reevaluaciones)
            return AlcanceEvaluaciones(ALCANCE_EMPRESA, await self.repo.empresa_del_usuario_definitivo(actor.id))
        if actor.es_admin:
            return AlcanceEvaluaciones(ALCANCE_TODO)
        return AlcanceEvaluaciones(ALCANCE_NADA)

    async def listar(self, actor: Actor | None, page: int, size: int,
                     estado_progreso: str | None = None) -> Pagina:
        alcance = await self._alcance(actor)
        items, total = await self.repo.listar_evaluaciones(
            alcance=alcance, estado_progreso=estado_progreso, offset=(page - 1) * size, limit=size,
        )
        return Pagina(items, total, page, size)

    async def detalle(self, evaluacion_id: int) -> Evaluacion:
        evaluacion = await self.repo.obtener_evaluacion(evaluacion_id)
        if not evaluacion:
            raise EvaluacionNoEncontradaError()
        return evaluacion

    async def listar_respuestas(self, evaluacion_id: int, page: int, size: int,
                                estado_final: str | None = None, fuente: str | None = None) -> Pagina:
        if not await self.repo.existe_evaluacion(evaluacion_id):
            raise EvaluacionNoEncontradaError()
        items, total = await self.repo.listar_respuestas(
            evaluacion_id, estado_final=estado_final, fuente=fuente, offset=(page - 1) * size, limit=size,
        )
        return Pagina(items, total, page, size)

    async def marcar_prueba(self, evaluacion_id: int, es_prueba: bool, actor: Actor) -> Evaluacion:
        """HU-19 criterio 4: marca o desmarca una evaluación de prueba (fuera del benchmark)."""
        evaluacion = await self.repo.obtener_evaluacion(evaluacion_id)
        if evaluacion is None:
            raise EvaluacionNoEncontradaError()
        anterior = bool(evaluacion.es_prueba)
        evaluacion.es_prueba = es_prueba
        if anterior != bool(es_prueba):
            # HU-09: modificación de datos en la misma transacción
            self.bitacora.registrar(
                accion=Accion.EVALUACION_PRUEBA, entidad="evaluacion", entidad_id=evaluacion.id, actor=actor,
                detalle={"es_prueba_anterior": anterior, "es_prueba": bool(es_prueba)},
            )
        await self.session.commit()
        return evaluacion
