"""
Ciclo de vida de las solicitudes de derechos ARCOP.

Reglas de negocio (el backend decide, nunca el cliente):
  - Titular = invitado (rol referente) o encuestado anónimo de la encuesta pública
    (rol encuestado). Solo el titular crea, cancela y aporta información a SUS solicitudes.
  - Solo admin_therion cambia estados intermedios y registra la resolución.
  - Un titular nunca ve solicitudes ajenas: se responde "no encontrada" (no se
    revela que el id existe).
  - Toda transición se valida contra TRANSICIONES_ARCOP y deja un evento en el
    historial en la misma transacción.
  - Una SUPRESIÓN aprobada (resuelta) anonimiza los datos del titular en la misma
    transacción que la resolución (ver AnonimizacionRepository).
  - Cada solicitud tiene un código de seguimiento único (ARC-XXXX-XXXX).
  - Plazos (Ley 21.719): respuesta en 30 días corridos, prorrogable UNA vez por 30 días
    más con motivo; el bloqueo temporal se responde en 2 días hábiles (configurables).
"""
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.casos import GestionarSolicitudARCOPUseCase
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.comun import (
    ESTADOS_GESTION, MAX_COMENTARIO, MAX_DESCRIPCION, MAX_RESPUESTA, MIN_DESCRIPCION, MIN_RESPUESTA,
    OperacionNoPermitidaError, RESULTADOS_RESOLUCION, SolicitudNoEncontradaError, TransicionInvalidaError,
    _sumar_dias, _sumar_dias_habiles, normalizar_codigo, nuevo_codigo_seguimiento, plazo_por_vencer, plazo_vencido,
    ventana_por_vencer,
)

__all__ = [
    "ESTADOS_GESTION", "GestionarSolicitudARCOPUseCase", "MAX_COMENTARIO", "MAX_DESCRIPCION", "MAX_RESPUESTA",
    "MIN_DESCRIPCION", "MIN_RESPUESTA", "OperacionNoPermitidaError", "RESULTADOS_RESOLUCION",
    "SolicitudNoEncontradaError", "TransicionInvalidaError", "_sumar_dias", "_sumar_dias_habiles",
    "normalizar_codigo", "nuevo_codigo_seguimiento", "plazo_por_vencer", "plazo_vencido", "ventana_por_vencer",
]
