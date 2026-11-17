"""
HU-40 · Revisión interna del registro (modo de auditoría interna del cliente).

Como Usuario Definitivo (cliente), en su función de auditoría interna, quiero revisar el mapa, el RAT y los
informes en un modo de auditoría interna y dejar constancia de esa revisión, para verificar que el registro
es fiel y está al día antes de presentarlo, certificarlo o informarlo al directorio.

  C1  El MISMO usuario definitivo entra al modo de revisión (sin rol ni cuenta adicional) y recorre la lista de
      verificación por actividad y por elemento del mapa (app/domain/rat/revision.py).
  C2  Deja observaciones por actividad, elemento o flujo (o del registro en general) y las cierra al corregir.
      Con observaciones abiertas la versión no se puede marcar revisada.
  C3  Marca la versión del RAT como revisada con fecha y nombre: la marca aparece en el informe del registro
      (InformeRatCasos.armar busca la revisión con la misma huella) y queda en el audit_log.
  C4  Ve las diferencias entre versiones y exporta un paquete de evidencia (informe, historial, lista de
      verificación y observaciones) verificable con hash, como el ZIP del Auditor Externo (HU-09).
  C5  Recordatorio de revisión periódica con plazo configurable (12 meses por defecto): aviso en la página y
      correo diario del worker (enviar_recordatorios) cuando vence o está por vencer.

La revisión lee el registro como lo afirmaría el informe (la versión vigente de cada actividad) y el mapa de
datos actual. Cada elemento revisado guarda su huella: si cambia después, su verificación queda
desactualizada. Solo con contrato vigente. Cada acción queda en el audit_log en la misma transacción.
"""
from app.application.rat.casos_uso.revision_interna.casos import RevisionInternaCasos
from app.application.rat.casos_uso.revision_interna.comun import (
    CLAVE_REGISTRO, LARGO_CIERRE, LARGO_CONCLUSION, LARGO_OBSERVACION, MAX_HISTORIAL_AUDITORIA, Contexto,
    RevisionError, catalogo_criterios, observacion_vista,
)
from app.application.rat.casos_uso.revision_interna.periodicidad import enviar_recordatorios, resumen_periodicidad

__all__ = [
    "CLAVE_REGISTRO", "LARGO_CIERRE", "LARGO_CONCLUSION", "LARGO_OBSERVACION", "MAX_HISTORIAL_AUDITORIA", "Contexto",
    "RevisionError", "RevisionInternaCasos", "catalogo_criterios", "enviar_recordatorios", "observacion_vista",
    "resumen_periodicidad",
]
