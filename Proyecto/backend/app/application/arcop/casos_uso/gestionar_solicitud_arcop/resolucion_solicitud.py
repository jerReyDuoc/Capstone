"""Resolución de solicitudes (incluye la anonimización de una supresión aprobada) y borrado de archivos."""
from app.domain.auth.actor import Actor, Rol
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    EventoSolicitudARCOP as Evento,
    SolicitudARCOP,
    TipoSolicitudARCOP,
    transicion_permitida,
)
from app.domain.models.sesion_modelo import MotivoCierre
from app.application.cuentas.casos_uso.sesiones import cerrar_todas
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.comun import (
    MAX_RESPUESTA, MIN_RESPUESTA, OperacionNoPermitidaError, RESULTADOS_RESOLUCION, TransicionInvalidaError,
    _ahora, _texto, logger,
)


class ResolucionSolicitudMixin:
    async def resolver(self, actor: Actor, solicitud_id: int, resultado: str,
                       respuesta: str) -> SolicitudARCOP:
        if not actor.es_admin:
            raise OperacionNoPermitidaError("Solo admin_therion puede resolver solicitudes.")
        if resultado not in RESULTADOS_RESOLUCION:
            raise ValueError(f"Resultado inválido. Debe ser uno de: {', '.join(sorted(RESULTADOS_RESOLUCION))}")
        texto = _texto(respuesta, "respuesta", MIN_RESPUESTA, MAX_RESPUESTA, obligatorio=True)
        solicitud = await self._obtener_visible(actor, solicitud_id, para_actualizar=True)
        if not transicion_permitida(solicitud.estado, resultado):
            raise TransicionInvalidaError(solicitud.estado, resultado)
        solicitud.respuesta = texto

        eventos_extra, rutas, auditoria_extra = (), [], None
        if resultado == Estado.RESUELTA.value and solicitud.tipo == TipoSolicitudARCOP.SUPRESION.value:
            if self.anonimizacion_repo is None:
                raise RuntimeError("Falta el repositorio de anonimización para resolver una supresión.")
            # Mismo commit que la resolución: si algo falla, no queda nada a medias
            if solicitud.usuario_temporal_id is not None:
                conteo, rutas = await self.anonimizacion_repo.anonimizar_titular(
                    solicitud.usuario_temporal_id, _ahora()
                )
            elif solicitud.usuario_definitivo_id is not None:  # HU-30
                ahora = _ahora()
                conteo, rutas = await self.anonimizacion_repo.anonimizar_usuario_definitivo(
                    solicitud.usuario_definitivo_id, ahora
                )
                # El cierre de sesiones es un caso de uso, no del repositorio; misma sesión/transacción.
                # `sesiones` conserva su posición (tras enlaces_recuperacion) para no alterar la bitácora.
                sesiones = await cerrar_todas(
                    self.anonimizacion_repo.session, Rol.CLIENTE.value,
                    solicitud.usuario_definitivo_id, MotivoCierre.SUPRESION_ARCOP, ahora,
                )
                reordenado = {}
                for k, v in conteo.items():
                    reordenado[k] = v
                    if k == "enlaces_recuperacion":
                        reordenado["sesiones"] = sesiones
                conteo = reordenado
            else:
                conteo, rutas = await self.anonimizacion_repo.anonimizar_encuestado(
                    solicitud.evaluacion_id, _ahora()
                )
            resumen = ", ".join(f"{k}={v}" for k, v in conteo.items())
            # HU-09: qué se suprimió (conteos por tabla) queda en el audit_log
            auditoria_extra = {"suprimido": {str(k): int(v or 0) for k, v in conteo.items()}}
            eventos_extra = (self._evento(
                actor, Evento.ANONIMIZACION, resultado, resultado,
                f"Datos del titular anonimizados ({resumen}).",
            ),)

        resuelta = await self._transicionar(
            actor, solicitud, resultado, Evento.RESOLUCION, None, eventos_extra, auditoria_extra
        )
        await self._borrar_archivos(solicitud_id, rutas)
        return resuelta

    async def _borrar_archivos(self, solicitud_id: int, rutas: list[str]) -> None:
        """Tras el commit: si un archivo no se puede borrar se registra para revisarlo a mano."""
        if not rutas:
            return
        fallidos = 0
        for ruta in rutas:
            try:
                await self.storage.delete(ruta)
            except Exception:  # noqa: BLE001
                fallidos += 1
        if fallidos:
            logger.error(
                "Supresión ARCOP %s: no se pudieron borrar %s de %s archivos de evidencia",
                solicitud_id, fallidos, len(rutas),
            )
