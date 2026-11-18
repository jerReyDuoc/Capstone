"""
Feriados legales de Chile, por año. Los consume app/core/config.py (settings.FERIADOS_CL) y se
inyectan a la lógica pura de app/domain/calendario.py.

FUENTE: lista oficial de feriados legales (Ley 2.977, 19.668, 19.973, 20.215, 20.299, 20.663,
20.983, 21.357 y calendario publicado por el Gobierno / feriados.cl). Incluye los traslados a
lunes que corresponden a cada año.
MANTENIMIENTO: hay que cargar el calendario de CADA año nuevo antes de que empiece. Un año sin
cargar solo genera una advertencia y cuenta únicamente fines de semana (ver calendario.py).
"""
from __future__ import annotations

from datetime import date

FERIADOS_CHILE: dict[int, tuple[date, ...]] = {
    2026: (
        date(2026, 1, 1),    # Año Nuevo (irrenunciable)
        date(2026, 4, 3),    # Viernes Santo
        date(2026, 4, 4),    # Sábado Santo
        date(2026, 5, 1),    # Día del Trabajo (irrenunciable)
        date(2026, 5, 21),   # Glorias Navales
        date(2026, 6, 21),   # Pueblos Indígenas (domingo)
        date(2026, 6, 29),   # San Pedro y San Pablo (lunes)
        date(2026, 7, 16),   # Virgen del Carmen
        date(2026, 8, 15),   # Asunción de la Virgen (sábado)
        date(2026, 9, 18),   # Independencia (irrenunciable)
        date(2026, 9, 19),   # Glorias del Ejército (irrenunciable)
        date(2026, 10, 12),  # Encuentro de Dos Mundos (lunes)
        date(2026, 10, 31),  # Iglesias Evangélicas (sábado)
        date(2026, 11, 1),   # Todos los Santos (domingo)
        date(2026, 12, 8),   # Inmaculada Concepción
        date(2026, 12, 25),  # Navidad (irrenunciable)
    ),
    2027: (
        date(2027, 1, 1),    # Año Nuevo (irrenunciable)
        date(2027, 3, 26),   # Viernes Santo (Pascua 28 mar)
        date(2027, 3, 27),   # Sábado Santo
        date(2027, 5, 1),    # Día del Trabajo (sábado, irrenunciable)
        date(2027, 5, 21),   # Glorias Navales
        date(2027, 6, 21),   # Pueblos Indígenas (solsticio de invierno: 21-jun-2027 10:11 hora de Chile)
        date(2027, 6, 28),   # San Pedro y San Pablo (29 jun es martes: se traslada al lunes)
        date(2027, 7, 16),   # Virgen del Carmen
        date(2027, 8, 15),   # Asunción de la Virgen (domingo)
        # 17-sep NO es feriado en 2027: la Ley 20.215 solo lo agrega si cae lunes (18 en martes).
        date(2027, 9, 18),   # Independencia (sábado, irrenunciable)
        date(2027, 9, 19),   # Glorias del Ejército (domingo, irrenunciable)
        date(2027, 10, 11),  # Encuentro de Dos Mundos (12 oct es martes: se traslada al lunes)
        date(2027, 10, 31),  # Iglesias Evangélicas (domingo)
        date(2027, 11, 1),   # Todos los Santos (lunes)
        date(2027, 12, 8),   # Inmaculada Concepción
        date(2027, 12, 25),  # Navidad (sábado, irrenunciable)
    ),
}
