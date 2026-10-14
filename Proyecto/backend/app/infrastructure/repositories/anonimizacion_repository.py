"""
Anonimización de los datos personales de un titular (supresión ARCOP aprobada).

NO hace commit: el caso de uso la ejecuta dentro de la MISMA transacción que la
resolución de la solicitud, así o se aplica todo o nada.

Qué se borra / qué se conserva (decisión del equipo, ver CAMBIOS_ARCOP.md):
  usuario_temporal      email y validacion_invitacion -> NULL; fecha_anonimizacion = ahora.
                        Se conserva Rubro_id (benchmark por rubro).
  respuestas            justificacion_usuario -> NULL. Se conservan clasificaciones.
  evidencias            nombre, ruta, hash, datos extraídos, justificación del LLM y
                        errores -> vacíos. Los ARCHIVOS se borran del disco después
                        del commit. Se conservan estado, clasificación y confianza.
  sanitizaciones        mapa_cifrado y entidades (huellas HMAC) -> NULL.
                        Se conservan conteos por tipo.
  eventos_seguridad     extracto y hash del texto -> vacíos.
  solicitudes_arcop     descripción del titular -> "[anonimizado]"; comentarios que
                        escribió el titular en el historial -> NULL. Se conservan
                        tipo, estados, fechas y la respuesta del admin (prueba de
                        que el derecho se atendió).
  Sin cambios           respuestas_filtro, resumen, llamadas_llm (sin texto personal).
"""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.evidencia import Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.models.sanitizacion import Sanitizacion
from app.domain.models.solicitud_arcop import EventoSolicitud, SolicitudARCOP
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.core.autenticacion import Rol

TEXTO_ANONIMIZADO = "[anonimizado]"


class AnonimizacionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def anonimizar_titular(self, usuario_id: int, ahora: datetime) -> tuple[dict, list[str]]:
        """Devuelve (conteo de filas por tabla, rutas de archivos a borrar tras el commit)."""
        s = self.session
        evals = select(Evaluacion.id).where(Evaluacion.usuario_temporal_id == usuario_id)
        resps = select(Respuesta.id).where(Respuesta.evaluacion_id.in_(evals))
        evids = select(Evidencia.id_evidencia).where(Evidencia.respuesta_id.in_(resps))
        sols = select(SolicitudARCOP.id).where(SolicitudARCOP.usuario_temporal_id == usuario_id)

        rutas = [
            r for r in (await s.execute(
                select(Evidencia.storage_path).where(Evidencia.respuesta_id.in_(resps))
            )).scalars().all() if r
        ]

        conteo = {}

        async def _upd(nombre, stmt):
            conteo[nombre] = (await s.execute(stmt.execution_options(synchronize_session=False))).rowcount or 0

        await _upd("usuario_temporal", update(UsuarioTemporal)
                   .where(UsuarioTemporal.id == usuario_id)
                   .values(email=None, validacion_invitacion=None, fecha_anonimizacion=ahora))
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
        await _upd("solicitudes_arcop", update(SolicitudARCOP)
                   .where(SolicitudARCOP.usuario_temporal_id == usuario_id)
                   .values(descripcion=TEXTO_ANONIMIZADO))
        await _upd("comentarios_titular", update(EventoSolicitud)
                   .where(EventoSolicitud.solicitud_id.in_(sols),
                          EventoSolicitud.actor_rol == Rol.REFERENTE.value,
                          EventoSolicitud.comentario.is_not(None))
                   .values(comentario=None))
        conteo["archivos"] = len(rutas)
        return conteo, rutas
