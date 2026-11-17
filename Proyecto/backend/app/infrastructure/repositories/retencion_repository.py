"""Consultas de la retención de datos: usuarios temporales (HU-25), ARCOP, eventos de seguridad (T-06)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errores import ConflictoIntegridadError
from app.domain.models.configuracion_retencion import (
    FUENTE_ENTORNO,
    ID_UNICO,
    ConfiguracionRetencion as Conf,
)
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP,
    EventoSolicitud,
    EventoSolicitudARCOP,
    SolicitudARCOP,
)
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.domain.ports.repositorios_empresa import ConfiguracionRetencionLeida
from app.domain.privacidad.anonimizacion import TEXTO_ANONIMIZADO


class RetencionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def contar_usuarios_sin_vencimiento(self) -> int:
        n = (await self.session.execute(
            select(func.count()).select_from(UsuarioTemporal)
            .where(UsuarioTemporal.fecha_anonimizacion.is_(None), UsuarioTemporal.fecha_expiracion.is_(None))
        )).scalar_one()
        return int(n)

    # ------------------------------------------------------------------ configuración (HU-25)
    async def existe_configuracion(self) -> bool:
        return await self.session.scalar(select(Conf.id).where(Conf.id == ID_UNICO)) is not None

    async def crear_configuracion_inicial(self) -> None:
        self.session.add(Conf(id=ID_UNICO, fuente_plazo=FUENTE_ENTORNO, plazo_titular_dias=None))
        try:
            await self.session.flush()
        except IntegrityError as e:  # otra sesión la creó al mismo tiempo
            raise ConflictoIntegridadError(str(e)) from e

    async def leer_configuracion(self) -> ConfiguracionRetencionLeida:
        fila = (await self.session.execute(
            select(Conf.fuente_plazo, Conf.plazo_titular_dias, Conf.fecha_actualizacion, Conf.ejecucion_desde)
            .where(Conf.id == ID_UNICO)
        )).one()
        return ConfiguracionRetencionLeida(fila.fuente_plazo, fila.plazo_titular_dias,
                                           fila.fecha_actualizacion, fila.ejecucion_desde)

    async def actualizar_configuracion(self, fuente_plazo: str, plazo_titular_dias: int | None,
                                       ahora: datetime) -> None:
        await self.session.execute(
            update(Conf).where(Conf.id == ID_UNICO)
            .values(fuente_plazo=fuente_plazo, plazo_titular_dias=plazo_titular_dias, fecha_actualizacion=ahora)
            .execution_options(synchronize_session=False))

    async def tomar_bloqueo(self, marca: datetime, abandonada: datetime) -> bool:
        res = await self.session.execute(
            update(Conf).where(Conf.id == ID_UNICO,
                               or_(Conf.ejecucion_desde.is_(None), Conf.ejecucion_desde < abandonada))
            .values(ejecucion_desde=marca).execution_options(synchronize_session=False)
        )
        return (res.rowcount or 0) == 1

    async def liberar_bloqueo(self, marca: datetime) -> None:
        await self.session.execute(
            update(Conf).where(Conf.id == ID_UNICO, Conf.ejecucion_desde == marca)
            .values(ejecucion_desde=None).execution_options(synchronize_session=False))

    # ------------------------------------------------------------------ R1 titulares
    @staticmethod
    def _filtros_titulares(limite: date):
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
        return vencidos, arcop_abierta

    async def contar_titulares_vencidos_con_arcop_abierta(self, limite: date) -> int:
        vencidos, arcop_abierta = self._filtros_titulares(limite)
        return (await self.session.execute(
            select(func.count()).select_from(UsuarioTemporal).where(*vencidos, arcop_abierta)
        )).scalar_one()

    async def ids_titulares_vencidos_sin_arcop_abierta(self, limite: date) -> list[int]:
        vencidos, arcop_abierta = self._filtros_titulares(limite)
        return list((await self.session.execute(
            select(UsuarioTemporal.id).where(*vencidos, ~arcop_abierta).order_by(UsuarioTemporal.id)
        )).scalars().all())

    async def ids_evaluaciones_publicas(self, usuario_id: int) -> list[int]:
        return list((await self.session.execute(
            select(Evaluacion.id).where(Evaluacion.usuario_temporal_id == usuario_id,
                                        Evaluacion.origen == ORIGEN_PUBLICA)
        )).scalars().all())

    async def marcar_titular_anonimizado(self, usuario_id: int, ahora: datetime) -> None:
        await self.session.execute(update(UsuarioTemporal)
                                   .where(UsuarioTemporal.id == usuario_id,
                                          UsuarioTemporal.fecha_anonimizacion.is_(None))
                                   .values(email=None, fecha_anonimizacion=ahora)
                                   .execution_options(synchronize_session=False))

    # ------------------------------------------------------------------ R2 solicitudes ARCOP
    async def solicitudes_arcop_cerradas_sin_anonimizar(self, limite: datetime,
                                                        actor_sistema: str) -> list[tuple[int, str]]:
        ya_anonimizada = exists().where(
            EventoSolicitud.solicitud_id == SolicitudARCOP.id,
            EventoSolicitud.tipo_evento == EventoSolicitudARCOP.ANONIMIZACION.value,
            EventoSolicitud.actor_rol == actor_sistema,
        )
        filas = (await self.session.execute(
            select(SolicitudARCOP.id, SolicitudARCOP.estado).where(
                SolicitudARCOP.fecha_cierre.is_not(None),
                SolicitudARCOP.fecha_cierre < limite,
                ~ya_anonimizada,
            ).order_by(SolicitudARCOP.id)
        )).all()
        return [(f.id, f.estado) for f in filas]

    async def anonimizar_textos_solicitudes_arcop(self, ids: list[int], ahora: datetime) -> None:
        s = self.session
        await s.execute(update(EventoSolicitud)
                        .where(EventoSolicitud.solicitud_id.in_(ids), EventoSolicitud.comentario.is_not(None))
                        .values(comentario=TEXTO_ANONIMIZADO)
                        .execution_options(synchronize_session=False))
        await s.execute(update(SolicitudARCOP)
                        .where(SolicitudARCOP.id.in_(ids))
                        .values(descripcion=TEXTO_ANONIMIZADO, fecha_actualizacion=ahora)
                        .execution_options(synchronize_session=False))
        # Una respuesta NULL (p. ej. solicitud cancelada) se deja NULL
        await s.execute(update(SolicitudARCOP)
                        .where(SolicitudARCOP.id.in_(ids), SolicitudARCOP.respuesta.is_not(None))
                        .values(respuesta=TEXTO_ANONIMIZADO)
                        .execution_options(synchronize_session=False))

    def agregar_evento_anonimizacion(self, solicitud_id: int, estado: str, ahora: datetime,
                                     actor_sistema: str) -> None:
        self.session.add(EventoSolicitud(
            solicitud_id=solicitud_id, fecha=ahora,
            tipo_evento=EventoSolicitudARCOP.ANONIMIZACION.value,
            estado_anterior=estado, estado_nuevo=estado,
            actor_rol=actor_sistema, actor_id=None,
            comentario=None,
        ))

    # ------------------------------------------------------------------ R3 eventos de seguridad
    @staticmethod
    def _cond_eventos(limite: datetime):
        return (EventoSeguridad.revisado.is_(True), EventoSeguridad.extracto.is_not(None),
                EventoSeguridad.fecha < limite)

    async def contar_eventos_seguridad_revisados(self, limite: datetime) -> int:
        return (await self.session.execute(
            select(func.count()).select_from(EventoSeguridad).where(*self._cond_eventos(limite)))).scalar_one()

    async def ids_eventos_seguridad_revisados(self, limite: datetime) -> list[int]:
        return list((await self.session.execute(
            select(EventoSeguridad.id_evento).where(*self._cond_eventos(limite))
            .order_by(EventoSeguridad.id_evento))).scalars().all())

    async def borrar_extracto_eventos(self, ids: list[int]) -> int:
        res = await self.session.execute(
            update(EventoSeguridad).where(EventoSeguridad.id_evento.in_(ids)).values(extracto=None)
            .execution_options(synchronize_session=False))
        return res.rowcount or 0
