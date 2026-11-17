"""Casos de uso del Registro de Actividades de Tratamiento (HU-35): composición de los mixins."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.rat.casos_uso.registro_actividades_casos.edicion_actividad import EdicionMixin
from app.application.rat.casos_uso.registro_actividades_casos.estados_actividad import EstadosMixin
from app.application.rat.casos_uso.registro_actividades_casos.lectura import LecturaMixin
from app.application.fabricas import fabricas


class RegistroActividadesCasos(LecturaMixin, EdicionMixin, EstadosMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.usuario_id: int = cliente.usuario.id
        self.bitacora = fabricas().bitacora(db)
        self.repo = fabricas().registro_actividades(db)
