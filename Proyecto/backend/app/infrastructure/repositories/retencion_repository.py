"""Consultas de la retención de datos: usuarios temporales (HU-25), ARCOP, eventos de seguridad (T-06)."""
from __future__ import annotations

import secrets
from datetime import date, datetime

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errores import ConflictoIntegridadError
from app.domain.models.configuracion_retencion import (
    FUENTE_ENTORNO,
    ID_UNICO,
    ConfiguracionRetencion as Conf,
)
from app.domain.models.documento_empresa import DocumentoEmpresa
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.evidencia import Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.models.sanitizacion import Sanitizacion
from app.domain.models.tutor_conversaciones import ConversacionTutor, MensajeTutor
from app.domain.models.usuario_definitivo import UsuarioDefinitivo
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP,
    EventoSolicitud,
    EventoSolicitudARCOP,
    SolicitudARCOP,
)
from app.domain.models.solicitud_contratacion import EstadoSolicitudContratacion as EstadoContratacion, SolicitudContratacion
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.domain.ports.repositorios_empresa import ConfiguracionRetencionLeida
from app.domain.privacidad.anonimizacion import TEXTO_ANONIMIZADO


# T-11: un código de seguimiento retirado empieza así (20 caracteres en total, como la columna)
PREFIJO_SEGUIMIENTO_RETIRADO = "RET-"


def codigo_retirado() -> str:
    return PREFIJO_SEGUIMIENTO_RETIRADO + secrets.token_hex(8)


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

    # ------------------------------------------------------------------ T-11 R5 contrataciones descartadas
    async def ids_contrataciones_descartadas(self, limite: datetime) -> list[int]:
        """Solicitudes descartadas antes de `limite` (la fecha del descarte es fecha_actualizacion)."""
        fecha = func.coalesce(SolicitudContratacion.fecha_actualizacion, SolicitudContratacion.fecha_creacion)
        return list((await self.session.execute(
            select(SolicitudContratacion.id).where(
                SolicitudContratacion.estado == EstadoContratacion.DESCARTADA.value, fecha < limite,
            ).order_by(SolicitudContratacion.id))).scalars().all())

    async def borrar_contrataciones(self, ids: list[int]) -> int:
        if not ids:
            return 0
        r = await self.session.execute(delete(SolicitudContratacion).where(SolicitudContratacion.id.in_(ids))
                                       .execution_options(synchronize_session=False))
        return int(r.rowcount or 0)

    # ------------------------------------------------------------------ T-11 R6 seguimiento ARCOP
    async def ids_seguimiento_arcop_vencido(self, limite: datetime) -> list[int]:
        """Solicitudes cerradas antes de `limite` cuyo código de seguimiento aún sirve."""
        return list((await self.session.execute(
            select(SolicitudARCOP.id).where(
                SolicitudARCOP.fecha_cierre.is_not(None), SolicitudARCOP.fecha_cierre < limite,
                ~SolicitudARCOP.codigo_seguimiento.startswith(PREFIJO_SEGUIMIENTO_RETIRADO),
            ).order_by(SolicitudARCOP.id))).scalars().all())

    async def retirar_seguimiento_arcop(self, ids: list[int], ahora: datetime) -> None:
        """El código deja de servir (uno aleatorio, que nadie conoce) y el historial pierde al actor."""
        s = self.session
        for solicitud_id in ids:
            await s.execute(update(SolicitudARCOP).where(SolicitudARCOP.id == solicitud_id)
                            .values(codigo_seguimiento=codigo_retirado(), fecha_actualizacion=ahora)
                            .execution_options(synchronize_session=False))
        await s.execute(update(EventoSolicitud)
                        .where(EventoSolicitud.solicitud_id.in_(ids), EventoSolicitud.actor_id.is_not(None))
                        .values(actor_id=None)
                        .execution_options(synchronize_session=False))

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

    # ------------------------------------------------------------------ T-17 R7 empresas con la gracia vencida
    async def empresas_pendientes_de_borrado(self, ids: list[int]) -> tuple[list[int], int]:
        """
        De las empresas con la gracia vencida: (las que aún hay que procesar y no tienen una solicitud
        ARCOP abierta, cuántas se omiten por tenerla). Las ya procesadas (datos_eliminados_en) no cuentan.
        """
        if not ids:
            return [], 0
        pendientes = list((await self.session.execute(
            select(Empresa.id).where(Empresa.id.in_(ids), Empresa.datos_eliminados_en.is_(None))
            .order_by(Empresa.id))).scalars().all())
        libres, omitidas = [], 0
        for empresa_id in pendientes:
            if await self._empresa_con_arcop_abierta(empresa_id):
                omitidas += 1
            else:
                libres.append(empresa_id)
        return libres, omitidas

    async def _empresa_con_arcop_abierta(self, empresa_id: int) -> bool:
        """Abierta = no final, de un usuario de la empresa, de una de sus evaluaciones o de su titular de origen."""
        evals = select(Evaluacion.id).where(Evaluacion.empresa_id == empresa_id)
        titulares = select(Evaluacion.usuario_temporal_id).where(Evaluacion.empresa_id == empresa_id)
        usuarios = select(UsuarioDefinitivo.id).where(UsuarioDefinitivo.empresa_id == empresa_id)
        return bool((await self.session.execute(
            select(func.count()).select_from(SolicitudARCOP).where(
                SolicitudARCOP.estado.not_in(list(EstadoSolicitudARCOP.finales())),
                or_(SolicitudARCOP.usuario_definitivo_id.in_(usuarios),
                    SolicitudARCOP.evaluacion_id.in_(evals),
                    SolicitudARCOP.usuario_temporal_id.in_(titulares))))).scalar_one())

    async def ids_usuarios_definitivos_de_empresa(self, empresa_id: int) -> list[int]:
        return list((await self.session.execute(
            select(UsuarioDefinitivo.id).where(UsuarioDefinitivo.empresa_id == empresa_id)
            .order_by(UsuarioDefinitivo.id))).scalars().all())

    async def borrar_documentos_empresa(self, empresa_id: int) -> tuple[int, list[str]]:
        """Borra las filas de documento_empresa; devuelve (cantidad, rutas de archivo a borrar tras el commit)."""
        rutas = [r for r in (await self.session.execute(
            select(DocumentoEmpresa.storage_path).where(DocumentoEmpresa.empresa_id == empresa_id)
        )).scalars().all() if r]
        res = await self.session.execute(delete(DocumentoEmpresa).where(DocumentoEmpresa.empresa_id == empresa_id)
                                         .execution_options(synchronize_session=False))
        return int(res.rowcount or 0), rutas

    async def eliminar_evidencias_empresa(self, empresa_id: int, ahora: datetime) -> tuple[int, list[str]]:
        """
        Como "eliminar" en Mis documentos (HU-29): se pierde el archivo, lo extraído y los textos; la fila
        conserva clasificación, estados y puntajes para que el historial de madurez siga explicable.
        """
        resps = select(Respuesta.id).where(Respuesta.evaluacion_id.in_(
            select(Evaluacion.id).where(Evaluacion.empresa_id == empresa_id)))
        propias = Evidencia.respuesta_id.in_(resps)
        rutas = [r for r in (await self.session.execute(
            select(Evidencia.storage_path).where(propias))).scalars().all() if r]
        await self.session.execute(
            update(Sanitizacion).where(Sanitizacion.evidencia_id.in_(select(Evidencia.id_evidencia).where(propias)))
            .values(mapa_cifrado=None, entidades=None).execution_options(synchronize_session=False))
        res = await self.session.execute(
            update(Evidencia).where(propias, Evidencia.fecha_eliminacion.is_(None))
            .values(nombre_archivo=TEXTO_ANONIMIZADO, storage_path="", datos_extraidos=None, justificacion_llm=None,
                    errores_validacion=None, justificacion_remediacion=None, fecha_eliminacion=ahora)
            .execution_options(synchronize_session=False))
        return int(res.rowcount or 0), rutas

    async def borrar_conversaciones_tutor_empresa(self, empresa_id: int) -> int:
        ids = select(ConversacionTutor.id).where(ConversacionTutor.empresa_id == empresa_id)
        await self.session.execute(delete(MensajeTutor).where(MensajeTutor.conversacion_id.in_(ids))
                                   .execution_options(synchronize_session=False))
        res = await self.session.execute(delete(ConversacionTutor).where(ConversacionTutor.empresa_id == empresa_id)
                                         .execution_options(synchronize_session=False))
        return int(res.rowcount or 0)

    async def marcar_empresa_datos_eliminados(self, empresa_id: int, ahora: datetime) -> None:
        await self.session.execute(update(Empresa).where(Empresa.id == empresa_id)
                                   .values(datos_eliminados_en=ahora).execution_options(synchronize_session=False))
