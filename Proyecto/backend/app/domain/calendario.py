"""
Calendario de días hábiles (lógica PURA: sin config, sin BD, sin reloj).

Día hábil = lunes a viernes que no sea feriado. Los feriados llegan como parámetro
(`feriados`: año -> fechas); la capa que sí puede leer la configuración
(app/core/feriados.py -> settings.FERIADOS_CL) los inyecta. Este módulo no importa app/core.

Si un año que el rango recorre NO tiene feriados cargados, se emite UNA advertencia por año
(logging.warning + warnings.warn) y se cuentan solo los fines de semana: nunca se lanza error.
"""
from __future__ import annotations

import logging
import warnings
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

Feriados = Mapping[int, Iterable[date]]

_AVISADOS: set[int] = set()   # años ya advertidos (una vez por año y proceso)


def _avisar_anio_sin_feriados(anio: int) -> None:
    if anio in _AVISADOS:
        return
    _AVISADOS.add(anio)
    msg = (f"No hay feriados cargados para {anio}: los días hábiles de ese año solo excluyen "
           "fines de semana. Cargar el calendario en app/core/feriados.py.")
    log.warning(msg)
    warnings.warn(msg, RuntimeWarning, stacklevel=3)


def es_dia_habil(dia: date, feriados: Feriados | None = None) -> bool:
    if dia.weekday() >= 5:
        return False
    if feriados is None or dia.year not in feriados:
        _avisar_anio_sin_feriados(dia.year)
        return True
    return dia not in set(feriados[dia.year])


def sumar_dias_habiles(desde, dias: int | None, feriados: Feriados | None = None):
    """
    `desde` (date o datetime) + `dias` días hábiles. El día de partida no cuenta; si cae en
    fin de semana o feriado, se cuenta desde el siguiente día. None o 0 devuelve `desde`.
    Conserva el tipo (y la hora) de `desde`.
    """
    fecha, restantes = desde, int(dias or 0)
    while restantes > 0:
        fecha += timedelta(days=1)
        d = fecha.date() if isinstance(fecha, datetime) else fecha
        if es_dia_habil(d, feriados):
            restantes -= 1
    return fecha
