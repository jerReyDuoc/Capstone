"""HU-22: revisión humana (Oficial de Cumplimiento) de la clasificación de una respuesta."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.seguridad.huella import huella
from app.application.evaluacion.casos_uso.generar_resumen import GenerarResumenUseCase
from app.domain.auditoria.acciones import Accion
from app.domain.auth.actor import Actor
from app.domain.models.respuesta import DecisionRevision, EstadoClasificacion, FuenteClasificacion, Respuesta
from app.domain.ports.repositorios import RespuestaRepositoryPort

logger = logging.getLogger(__name__)


class RespuestaNoEncontradaError(Exception):
    """La respuesta a revisar no existe."""


@dataclass(frozen=True)
class ResultadoRevision:
    respuesta: Respuesta
    decision: str
    comentario: str
    puntajes_recalculados: bool


def _ultima_clasificacion_llm(respuesta) -> str | None:
    """Clasificación que propuso el LLM en la evidencia procesada más reciente (o None)."""
    con_llm = [e for e in (respuesta.evidencias or []) if e.clasificacion_llm]
    if not con_llm:
        return None
    con_llm.sort(key=lambda e: (e.fecha_procesada or date.min, e.id_evidencia))
    return con_llm[-1].clasificacion_llm


class RevisarRespuestaUseCase:
    def __init__(self, db: AsyncSession, repo: RespuestaRepositoryPort):
        self.db = db
        self.repo = repo
        self.bitacora = fabricas().bitacora(db)

    async def revisar(self, respuesta_id: int, clasificacion_revisada: str, comentario: str, admin: Actor,
                      anonimizar: Callable[[str], Awaitable[str]]) -> ResultadoRevision:
        """`comentario` ya viene validado en largo; `anonimizar` lo deja sin PII (fail-closed)."""
        respuesta = await self.repo.get(respuesta_id)
        if not respuesta:
            raise RespuestaNoEncontradaError()
        comentario = await anonimizar(comentario)

        anterior = respuesta.estado_clasificacion_final or respuesta.estado_clasificacion
        decision = (DecisionRevision.CONFIRMADA if clasificacion_revisada == anterior
                    else DecisionRevision.CORREGIDA).value
        clasificacion_llm = _ultima_clasificacion_llm(respuesta)

        # HU-09: la revisión cambia la clasificación final: queda en el audit_log (misma transacción).
        # HU-22: con la decisión, lo que había declarado el usuario y propuesto el LLM (la verdad de
        # referencia) y solo la huella HMAC y el largo del comentario: el log nunca guarda texto libre.
        self.bitacora.registrar(
            accion=Accion.RESPUESTA_REVISADA, entidad="respuestas", entidad_id=respuesta.id, actor=admin,
            detalle={"evaluacion_id": respuesta.evaluacion_id,
                     "estado_final_anterior": respuesta.estado_clasificacion_final,
                     "fuente_anterior": respuesta.fuente_clasificacion,
                     "estado_final_nuevo": clasificacion_revisada,
                     "decision": decision,
                     "estado_declarado": respuesta.estado_clasificacion,
                     "clasificacion_llm": clasificacion_llm,
                     "revision_previa": respuesta.clasificacion_revisada,
                     "comentario_huella": huella(comentario),
                     "comentario_largo": len(comentario)},
        )
        respuesta.clasificacion_revisada = clasificacion_revisada
        respuesta.fecha_revision = date.today()
        respuesta.estado_clasificacion_final = clasificacion_revisada
        respuesta.fuente_clasificacion = FuenteClasificacion.REVISION.value
        respuesta.comentario_revision = comentario
        respuesta.decision_revision = decision
        respuesta.revisor_admin_id = admin.id
        # HU-02: la brecha sigue al estado vigente (se asigna en no_cumplido y se quita
        # en cualquier otro), también cuando la revisión corrige una decisión del LLM.
        control = None
        if clasificacion_revisada == EstadoClasificacion.NO_CUMPLIDO.value:
            control = await self.repo.get_control(respuesta.matriz_controles_id_control)
        respuesta.sincronizar_brecha(control)
        await self.repo.update(respuesta)  # DEUDA: update() hace commit interno

        # HU-22: una corrección sobre una evaluación ya cerrada cambia su puntaje (como HU-17)
        puntajes_recalculados = False
        if decision == DecisionRevision.CORREGIDA.value and respuesta.evaluacion_id:
            evaluacion = await fabricas().informes(self.db).evaluacion(respuesta.evaluacion_id)
            if evaluacion is not None and evaluacion.esta_cerrada:
                try:
                    await GenerarResumenUseCase(self.db).execute(respuesta.evaluacion_id)
                    puntajes_recalculados = True
                except Exception:  # noqa: BLE001 - la revisión ya quedó; el resumen se puede regenerar
                    await self.db.rollback()
                    logger.exception("[HU-22] no se pudo recalcular el resumen de la evaluación %s",
                                     respuesta.evaluacion_id)
        return ResultadoRevision(respuesta, decision, comentario, puntajes_recalculados)
