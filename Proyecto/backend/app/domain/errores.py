"""Errores del dominio que los repositorios traducen desde la tecnología de persistencia."""
from __future__ import annotations


class ConflictoIntegridadError(Exception):
    """Una restricción de integridad (unicidad, clave foránea) se violó al escribir: carrera entre peticiones."""
