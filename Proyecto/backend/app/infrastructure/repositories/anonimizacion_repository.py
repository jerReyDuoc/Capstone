from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.evidencia import Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.models.sanitizacion import Sanitizacion
from app.domain.models.solicitud_arcop import EventoSolicitud, SolicitudARCOP
from app.domain.models.solicitud_contratacion import EstadoSolicitudContratacion, SolicitudContratacion
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.core.autenticacion import Rol

TEXTO_ANONIMIZADO = "[anonimizado]"


class AnonimizacionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def anonimizar_titular(self, usuario_id: int, ahora: datetime) -> tuple[dict, list[str]]:
        """Invitado: todas sus evaluaciones y solicitudes (también las hechas como encuestado)."""
        # HU-27: las migradas a una empresa ya no son del titular temporal (pasaron al
        # contrato con la empresa); una supresión o la retención no las tocan.
        evals = select(Evaluacion.id).where(Evaluacion.usuario_temporal_id == usuario_id,
                                            Evaluacion.empresa_id.is_(None))
        filtro_sols = (SolicitudARCOP.usuario_temporal_id == usuario_id) | SolicitudARCOP.evaluacion_id.in_(evals)
        return await self._anonimizar(evals, filtro_sols, ahora, usuario_id=usuario_id)

    async def anonimizar_encuestado(self, evaluacion_id: int, ahora: datetime) -> tuple[dict, list[str]]:
        """Encuestado anónimo: su evaluación y las solicitudes hechas con su clave."""
        evals = select(Evaluacion.id).where(Evaluacion.id == evaluacion_id, Evaluacion.empresa_id.is_(None))
        filtro_sols = SolicitudARCOP.evaluacion_id == evaluacion_id
        return await self._anonimizar(evals, filtro_sols, ahora, usuario_id=None)

    async def anonimizar_usuario_definitivo(self, usuario_id: int, ahora: datetime) -> tuple[dict, list[str]]:
        """
        HU-30: supresión ARCOP del usuario de una empresa cliente (persona natural).

        Se borran SUS datos personales (nombre, correo, contraseña), se cierra la cuenta y sus
        sesiones y se revocan sus enlaces; también sus textos en las solicitudes ARCOP. NO se
        tocan la empresa (persona jurídica) ni las evaluaciones migradas a ella: son datos del
        contrato con la empresa (sus evidencias ya están anonimizadas desde HU-06) y su
        conservación la deciden la vigencia del contrato (HU-30) y la retención (HU-25).
        """
        from app.application.use_cases.sesiones import cerrar_todas
        from app.domain.models.sesion import MotivoCierre, TokenRecuperacion
        from app.domain.models.usuario_definitivo import (
            EstadoUsuarioDefinitivo, TokenActivacion, UsuarioDefinitivo,
        )

        s = self.session
        conteo = {}

        async def _upd(nombre, stmt):
            conteo[nombre] = (await s.execute(stmt.execution_options(synchronize_session=False))).rowcount or 0

        # El correo es NOT NULL y único: queda un marcador irrepetible que no es de nadie
        # (.invalid está reservado, RFC 2606) y con el que nadie puede iniciar sesión.
        await _upd("usuario_definitivo", update(UsuarioDefinitivo)
                   .where(UsuarioDefinitivo.id == usuario_id)
                   .values(nombre=TEXTO_ANONIMIZADO, email=f"suprimido-{usuario_id}@anonimizado.invalid",
                           password_hash=None, estado=EstadoUsuarioDefinitivo.BLOQUEADO.value))
        await _upd("enlaces_activacion", update(TokenActivacion)
                   .where(TokenActivacion.usuario_definitivo_id == usuario_id,
                          TokenActivacion.fecha_uso.is_(None), TokenActivacion.fecha_revocacion.is_(None))
                   .values(fecha_revocacion=ahora))
        await _upd("enlaces_recuperacion", update(TokenRecuperacion)
                   .where(TokenRecuperacion.actor_rol == Rol.CLIENTE.value, TokenRecuperacion.actor_id == usuario_id,
                          TokenRecuperacion.fecha_uso.is_(None), TokenRecuperacion.fecha_revocacion.is_(None))
                   .values(fecha_revocacion=ahora))
        conteo["sesiones"] = await cerrar_todas(s, Rol.CLIENTE.value, usuario_id, MotivoCierre.SUPRESION_ARCOP, ahora)

        sols = select(SolicitudARCOP.id).where(SolicitudARCOP.usuario_definitivo_id == usuario_id)
        await _upd("comentarios_titular", update(EventoSolicitud)
                   .where(EventoSolicitud.solicitud_id.in_(sols),
                          EventoSolicitud.actor_rol == Rol.CLIENTE.value,
                          EventoSolicitud.comentario.is_not(None))
                   .values(comentario=None))
        await _upd("solicitudes_arcop", update(SolicitudARCOP)
                   .where(SolicitudARCOP.usuario_definitivo_id == usuario_id)
                   .values(descripcion=TEXTO_ANONIMIZADO))
        conteo["archivos"] = 0
        return conteo, []

    async def _anonimizar(self, evals, filtro_sols, ahora: datetime,
                          usuario_id: int | None) -> tuple[dict, list[str]]:
        """Devuelve (conteo de filas por tabla, rutas de archivos a borrar tras el commit)."""
        s = self.session
        resps = select(Respuesta.id).where(Respuesta.evaluacion_id.in_(evals))
        evids = select(Evidencia.id_evidencia).where(Evidencia.respuesta_id.in_(resps))
        sols = select(SolicitudARCOP.id).where(filtro_sols)

        rutas = [
            r for r in (await s.execute(
                select(Evidencia.storage_path).where(Evidencia.respuesta_id.in_(resps))
            )).scalars().all() if r
        ]

        conteo = {}

        async def _upd(nombre, stmt):
            conteo[nombre] = (await s.execute(stmt.execution_options(synchronize_session=False))).rowcount or 0

        if usuario_id is not None:
            await _upd("usuario_temporal", update(UsuarioTemporal)
                       .where(UsuarioTemporal.id == usuario_id)
                       .values(email=None, validacion_invitacion=None, fecha_anonimizacion=ahora))
        else:
            # T-06 (hallazgo H1): desde HU-19 el encuestado público puede dejar un email
            # OPCIONAL en su usuario temporal anónimo. Ese usuario es solo de su evaluación
            # pública, así que la supresión también borra el email.
            # Si la evaluación no es pública no se toca a nadie y no aparece en el conteo.
            filas = (await s.execute(
                update(UsuarioTemporal)
                .where(UsuarioTemporal.id.in_(
                    select(Evaluacion.usuario_temporal_id)
                    .where(Evaluacion.id.in_(evals), Evaluacion.origen == ORIGEN_PUBLICA)
                ))
                .values(email=None, fecha_anonimizacion=ahora)
                .execution_options(synchronize_session=False)
            )).rowcount or 0
            if filas:
                conteo["usuario_temporal"] = filas
        await _upd("claves_evaluacion", update(Evaluacion)
                   .where(Evaluacion.id.in_(evals), Evaluacion.clave_acceso_hash.is_not(None))
                   .values(clave_acceso_hash=None))
        await _upd("respuestas", update(Respuesta)
                   .where(Respuesta.id.in_(resps))
                   .values(justificacion_usuario=None))
        await _upd("evidencias", update(Evidencia)
                   .where(Evidencia.id_evidencia.in_(evids))
                   .values(nombre_archivo=TEXTO_ANONIMIZADO, storage_path="", hash_archivo="",
                           datos_extraidos=None, justificacion_llm=None, errores_validacion=None))
        await _upd("sanitizaciones", update(Sanitizacion)
                   .where(
                       Sanitizacion.evaluacion_id.in_(evals)
                       | Sanitizacion.respuesta_id.in_(resps)
                       | Sanitizacion.evidencia_id.in_(evids)
                   )
                   .values(mapa_cifrado=None, entidades=None))
        await _upd("eventos_seguridad", update(EventoSeguridad)
                   .where(
                       EventoSeguridad.evaluacion_id.in_(evals)
                       | EventoSeguridad.respuesta_id.in_(resps)
                       | EventoSeguridad.evidencia_id.in_(evids)
                   )
                   .values(extracto=None, hash_texto=""))
        # Comentarios antes que solicitudes: `sols` es una subconsulta sobre solicitudes_arcop
        await _upd("comentarios_titular", update(EventoSolicitud)
                   .where(EventoSolicitud.solicitud_id.in_(sols),
                          EventoSolicitud.actor_rol.in_([Rol.REFERENTE.value, Rol.ENCUESTADO.value]),
                          EventoSolicitud.comentario.is_not(None))
                   .values(comentario=None))
        await _upd("solicitudes_arcop", update(SolicitudARCOP)
                   .where(filtro_sols)
                   .values(descripcion=TEXTO_ANONIMIZADO))
        # HU-31: suprimir los datos también retira el consentimiento de contacto comercial.
        # Las solicitudes de contratación aún no migradas pierden el contacto y se descartan
        # (sin contacto no hay a quién llamar, y sin titular no hay evaluación que migrar).
        filas = (await s.execute(
            update(SolicitudContratacion)
            .where(SolicitudContratacion.evaluacion_id.in_(evals),
                   SolicitudContratacion.estado != EstadoSolicitudContratacion.MIGRADA.value)
            .values(nombre_contacto=None, cargo_contacto=None, email_contacto=None, telefono_contacto=None,
                    estado=EstadoSolicitudContratacion.DESCARTADA.value, fecha_actualizacion=ahora)
            .execution_options(synchronize_session=False)
        )).rowcount or 0
        if filas:
            conteo["solicitudes_contratacion"] = filas
        conteo["archivos"] = len(rutas)
        return conteo, rutas
