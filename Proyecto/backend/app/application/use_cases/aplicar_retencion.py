"""
T-06 — Plazos de conservación (Ley 21.719, principio de proporcionalidad).

Los datos personales se conservan solo mientras sirven a su finalidad. Vencido cada
plazo (config RETENCION_*; vacío = regla desactivada) se aplica:

  R1  Titulares      usuario_temporal con el acceso vencido hace más de
                     RETENCION_DATOS_TITULAR_DIAS y sin anonimizar -> MISMA anonimización
                     que una supresión ARCOP aprobada (AnonimizacionRepository): correo,
                     clave, justificaciones, evidencias (y sus archivos), huellas y
                     extractos. Se conservan puntajes y clasificaciones (benchmark).
                     Se omite al titular que tenga una solicitud ARCOP abierta: primero
                     hay que atender su derecho.
  R2  ARCOP          solicitudes cerradas hace más de RETENCION_ARCOP_CERRADAS_DIAS ->
                     descripción, respuesta y comentarios del historial pasan a
                     "[anonimizado]". Quedan tipo, estados, fechas y el historial como
                     prueba de que el derecho se atendió. Deja un evento
                     'anonimizacion' (actor 'sistema') en el historial.
  R3  Seguridad      eventos de seguridad REVISADOS con más de
                     RETENCION_EVENTOS_SEGURIDAD_DIAS -> extracto NULL (se conserva el
                     hash para agrupar intentos repetidos).
  R4  Tutor IA       HU-15: conversaciones con el Agente IA Tutor sin mensajes hace más de
                     TUTOR_RETENCION_DIAS (30 por defecto, decisión del PO del 28-oct) ->
                     se BORRAN con sus mensajes. Las métricas de llamadas_llm (sin texto) y
                     la bitácora se conservan.

Cada titular se procesa en su propia transacción (o todo o nada por titular) y los
archivos se borran después del commit. El resultado y los logs llevan solo conteos.

Lo ejecuta el worker una vez al día (app/worker/tasks.py) y se puede correr a mano en
modo simulación con scripts/retencion_datos.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP,
    EventoSolicitud,
    EventoSolicitudARCOP,
    SolicitudARCOP,
)
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.repositories.anonimizacion_repository import (
    TEXTO_ANONIMIZADO,
    AnonimizacionRepository,
)

logger = logging.getLogger(__name__)

ACTOR_SISTEMA = "sistema"


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class ResultadoRetencion:
    simulacion: bool
    titulares: int = 0
    titulares_omitidos_por_arcop_abierta: int = 0
    solicitudes_arcop: int = 0
    eventos_seguridad: int = 0
    conversaciones_tutor: int = 0
    archivos_borrados: int = 0
    reglas_desactivadas: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return dict(self.__dict__)


class AplicarRetencionUseCase:
    def __init__(self, session: AsyncSession, storage=None, hoy: date | None = None,
                 plazos: dict[str, int | None] | None = None):
        self.s = session
        self.storage = storage
        self.hoy = hoy or date.today()
        self.plazos = plazos if plazos is not None else {
            "titulares": settings.RETENCION_DATOS_TITULAR_DIAS,
            "arcop": settings.RETENCION_ARCOP_CERRADAS_DIAS,
            "eventos": settings.RETENCION_EVENTOS_SEGURIDAD_DIAS,
            "tutor": settings.TUTOR_RETENCION_DIAS,
        }

    def _limite(self, regla: str) -> date | None:
        dias = self.plazos.get(regla)
        return None if dias is None else self.hoy - timedelta(days=dias)

    async def execute(self, aplicar: bool = True) -> ResultadoRetencion:
        r = ResultadoRetencion(simulacion=not aplicar)
        for regla, metodo in (("titulares", self._titulares), ("arcop", self._arcop),
                              ("eventos", self._eventos), ("tutor", self._tutor)):
            if regla == "tutor" and regla not in self.plazos:
                continue  # R4 es de HU-15: quien pasa sus propios plazos sin ella no la usa
            limite = self._limite(regla)
            if limite is None:
                r.reglas_desactivadas.append(regla)
                continue
            await metodo(limite, aplicar, r)
        logger.info("T-06 retención %s: %s", "simulada" if not aplicar else "aplicada", r.como_dict())
        return r

    # ------------------------------------------------------------------ R1
    async def _titulares(self, limite: date, aplicar: bool, r: ResultadoRetencion) -> None:
        finales = list(EstadoSolicitudARCOP.finales())
        evals_del_usuario = select(Evaluacion.id).where(Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
        arcop_abierta = exists().where(
            SolicitudARCOP.estado.not_in(finales),
            or_(SolicitudARCOP.usuario_temporal_id == UsuarioTemporal.id,
                SolicitudARCOP.evaluacion_id.in_(evals_del_usuario)),
        )
        vencidos = (UsuarioTemporal.fecha_anonimizacion.is_(None),
                    UsuarioTemporal.fecha_expiracion.is_not(None),
                    UsuarioTemporal.fecha_expiracion < limite)

        r.titulares_omitidos_por_arcop_abierta += (await self.s.execute(
            select(func.count()).select_from(UsuarioTemporal).where(*vencidos, arcop_abierta)
        )).scalar_one()
        ids = (await self.s.execute(
            select(UsuarioTemporal.id).where(*vencidos, ~arcop_abierta).order_by(UsuarioTemporal.id)
        )).scalars().all()
        if not aplicar:
            r.titulares += len(ids)
            return

        repo = AnonimizacionRepository(self.s)
        for usuario_id in ids:
            ahora = _ahora()
            publicas = (await self.s.execute(
                select(Evaluacion.id).where(Evaluacion.usuario_temporal_id == usuario_id,
                                            Evaluacion.origen == ORIGEN_PUBLICA)
            )).scalars().all()
            rutas: list[str] = []
            try:
                if publicas:
                    for evaluacion_id in publicas:
                        _, rr = await repo.anonimizar_encuestado(evaluacion_id, ahora)
                        rutas += rr
                else:
                    _, rutas = await repo.anonimizar_titular(usuario_id, ahora)
                # Queda marcado aunque no tuviera evaluaciones: no se vuelve a procesar
                await self.s.execute(update(UsuarioTemporal)
                                     .where(UsuarioTemporal.id == usuario_id,
                                            UsuarioTemporal.fecha_anonimizacion.is_(None))
                                     .values(email=None, fecha_anonimizacion=ahora)
                                     .execution_options(synchronize_session=False))
                await self.s.commit()
            except Exception as e:  # noqa: BLE001 — un titular fallido no detiene al resto
                await self.s.rollback()
                logger.error("T-06 retención: no se pudo anonimizar un titular (%s)", type(e).__name__)
                continue
            r.titulares += 1
            r.archivos_borrados += await self._borrar(rutas)

    async def _borrar(self, rutas: list[str]) -> int:
        if not self.storage:
            return 0
        borrados = 0
        for ruta in rutas:
            try:
                await self.storage.delete(ruta)
                borrados += 1
            except Exception as e:  # noqa: BLE001
                logger.error("T-06 retención: no se pudo borrar un archivo (%s)", type(e).__name__)
        return borrados

    # ------------------------------------------------------------------ R2
    async def _arcop(self, limite: date, aplicar: bool, r: ResultadoRetencion) -> None:
        ya_anonimizada = exists().where(
            EventoSolicitud.solicitud_id == SolicitudARCOP.id,
            EventoSolicitud.tipo_evento == EventoSolicitudARCOP.ANONIMIZACION.value,
            EventoSolicitud.actor_rol == ACTOR_SISTEMA,
        )
        filas = (await self.s.execute(
            select(SolicitudARCOP.id, SolicitudARCOP.estado).where(
                SolicitudARCOP.fecha_cierre.is_not(None),
                SolicitudARCOP.fecha_cierre < datetime.combine(limite, datetime.min.time()),
                ~ya_anonimizada,
            ).order_by(SolicitudARCOP.id)
        )).all()
        r.solicitudes_arcop += len(filas)
        if not aplicar or not filas:
            return
        ids = [f.id for f in filas]
        ahora = _ahora()
        await self.s.execute(update(EventoSolicitud)
                             .where(EventoSolicitud.solicitud_id.in_(ids), EventoSolicitud.comentario.is_not(None))
                             .values(comentario=TEXTO_ANONIMIZADO)
                             .execution_options(synchronize_session=False))
        await self.s.execute(update(SolicitudARCOP)
                             .where(SolicitudARCOP.id.in_(ids))
                             .values(descripcion=TEXTO_ANONIMIZADO, fecha_actualizacion=ahora)
                             .execution_options(synchronize_session=False))
        # Una respuesta NULL (p. ej. solicitud cancelada) se deja NULL
        await self.s.execute(update(SolicitudARCOP)
                             .where(SolicitudARCOP.id.in_(ids), SolicitudARCOP.respuesta.is_not(None))
                             .values(respuesta=TEXTO_ANONIMIZADO)
                             .execution_options(synchronize_session=False))
        for f in filas:
            self.s.add(EventoSolicitud(
                solicitud_id=f.id, fecha=ahora,
                tipo_evento=EventoSolicitudARCOP.ANONIMIZACION.value,
                estado_anterior=f.estado, estado_nuevo=f.estado,
                actor_rol=ACTOR_SISTEMA, actor_id=None,
                comentario=None,
            ))
        await self.s.commit()

    # ------------------------------------------------------------------ R3
    async def _eventos(self, limite: date, aplicar: bool, r: ResultadoRetencion) -> None:
        cond = (EventoSeguridad.revisado.is_(True), EventoSeguridad.extracto.is_not(None),
                EventoSeguridad.fecha < datetime.combine(limite, datetime.min.time()))
        if not aplicar:
            r.eventos_seguridad += (await self.s.execute(
                select(func.count()).select_from(EventoSeguridad).where(*cond))).scalar_one()
            return
        res = await self.s.execute(update(EventoSeguridad).where(*cond).values(extracto=None)
                                   .execution_options(synchronize_session=False))
        r.eventos_seguridad += res.rowcount or 0
        await self.s.commit()

    # ------------------------------------------------------------------ R4 (HU-15)
    async def _tutor(self, limite: date, aplicar: bool, r: ResultadoRetencion) -> None:
        from app.infrastructure.repositories.tutor_repository import TutorRepository

        repo = TutorRepository(self.s)
        ids = await repo.inactivas_desde(datetime.combine(limite, datetime.min.time()))
        if not aplicar:
            r.conversaciones_tutor += len(ids)
            return
        if not ids:
            return
        r.conversaciones_tutor += await repo.eliminar_ids(ids)
        await self.s.commit()
