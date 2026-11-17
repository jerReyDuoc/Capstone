"""
HU-22 · Bandeja de revisión del Oficial de Cumplimiento.

  C1  Listado filtrable de pendientes: clasificaciones que el LLM o la capa de seguridad
      tocaron (divergencias, baja confianza, bloqueos, controles sin resolver) y eventos de
      seguridad sin resolver.
  C2  Confirmar o corregir: PATCH /api/respuestas/{id}/revision (con comentario) y
      PATCH /api/seguridad/eventos/{id}/revision (ataque confirmado o falso positivo).
  C3  Cada revisión queda en el audit_log (HU-09); el historial de una respuesta se lee de ahí.

Motivos por los que una respuesta entra a la bandeja (una puede tener varios):

  seguridad         la capa anti prompt-injection bloqueó su justificación o una evidencia
  divergencia       el LLM propuso una clasificación distinta de la que declaró el usuario
  sin_resolver      sigue en 'requiere_revision' (nadie la ha cerrado)
  baja_confianza    el LLM respondió con confianza < UMBRAL_CONFIANZA (no se aplicó)
  resuelta_por_llm  el usuario no supo clasificarla (declaró 'requiere_revision') y la cerró el LLM
  concordante       el LLM respaldó al usuario con confianza suficiente. No es urgente: solo se
                    lista al pedirla (filtro motivo=concordante) para muestrear la verdad de
                    referencia también donde el modelo "acertó".

Una respuesta está PENDIENTE si nunca se revisó o si, después de revisada, otra evidencia
volvió a cambiar su clasificación (la fuente dejó de ser 'revision').

La verdad de referencia (resumen) compara la última clasificación del LLM de cada respuesta
revisada con la clasificación del oficial, con la misma función que /api/ia/metricas.

Escala: el piloto tiene pocas evaluaciones; se cargan como máximo MAX_CANDIDATAS respuestas
candidatas y se filtra y pagina en memoria (los motivos se calculan con sus evidencias).
"""
from app.application.evaluacion.casos_uso.bandeja_revision.casos import BandejaRevision
from app.application.evaluacion.casos_uso.bandeja_revision.comun import (
    BAJA_CONFIANZA, CONCORDANTE, DIVERGENCIA, ESTADOS_REVISION, MAX_CANDIDATAS, MOTIVOS, MOTIVOS_PRIORITARIOS,
    ORDENES, RESUELTA_POR_LLM, SEGURIDAD, SIN_RESOLVER, rango_criticidad,
)
from app.application.evaluacion.casos_uso.bandeja_revision.modelos_bandeja import FiltrosBandeja
from app.application.evaluacion.casos_uso.bandeja_revision.reglas_motivos import (
    EvidenciaLlm, calcular_motivos, clave_prioridad, es_prioritaria, esta_pendiente, ultima_del_llm,
)

__all__ = [
    "BAJA_CONFIANZA", "BandejaRevision", "CONCORDANTE", "DIVERGENCIA", "ESTADOS_REVISION", "EvidenciaLlm",
    "FiltrosBandeja", "MAX_CANDIDATAS", "MOTIVOS", "MOTIVOS_PRIORITARIOS", "ORDENES", "RESUELTA_POR_LLM",
    "SEGURIDAD", "SIN_RESOLVER", "calcular_motivos", "clave_prioridad", "es_prioritaria", "esta_pendiente",
    "rango_criticidad", "ultima_del_llm",
]
