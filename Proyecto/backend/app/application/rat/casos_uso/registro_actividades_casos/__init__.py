"""
HU-35 · Registro de Actividades de Tratamiento (RAT) del cliente.

Como Usuario Definitivo (cliente), quiero llevar el Registro de Actividades de Tratamiento (RAT) de
mi empresa dentro de la plataforma, para cumplir la caracterización de actividades de tratamiento
que exigen la Ley 21.719 y su reglamento.

  C1  Cada actividad registra los 11 campos mínimos del reglamento, las medidas de seguridad y el
      rol de la empresa (app/domain/rat/catalogo.py: CAMPOS).
  C2  Sistemas, bases, terceros y flujos se ELIGEN DEL MAPA (HU-34) y no se ingresan dos veces
      (app/domain/rat/analisis_rat.py: derivados). Un cambio en el mapa devuelve a revisión las
      actividades afectadas, en la MISMA transacción del cambio (marcar_afectadas_por_mapa, que
      llama MapaDatosCasos._guardar).
  C3  Completitud por actividad y global; una actividad no queda vigente con campos vacíos.
  C4  Estados borrador → en revisión → vigente → archivada (app/domain/rat/estados.py). Al quedar
      vigente se guarda una versión inmutable (rat_actividad_version, con trigger) y cada cambio
      queda en el audit_log (HU-09) en la misma transacción. Solo con contrato vigente.

Concurrencia: toda edición manda la `revision` de la actividad que vio el usuario. Si cambió (otra
pestaña o un cambio en el mapa), responde 409 ACTIVIDAD_DESACTUALIZADA y nada se pisa.
"""
from app.application.rat.casos_uso.registro_actividades_casos.afectadas_por_mapa import marcar_afectadas_por_mapa
from app.application.rat.casos_uso.registro_actividades_casos.casos import RegistroActividadesCasos
from app.application.rat.casos_uso.registro_actividades_casos.comun import (
    MAX_ACTIVIDADES, MAX_MOTIVOS, RatError, _ahora, _elemento, _evaluar, _flujo, _iso, logger,
)

__all__ = [
    "MAX_ACTIVIDADES", "MAX_MOTIVOS", "RatError", "RegistroActividadesCasos", "_ahora", "_elemento", "_evaluar",
    "_flujo", "_iso", "logger", "marcar_afectadas_por_mapa",
]
