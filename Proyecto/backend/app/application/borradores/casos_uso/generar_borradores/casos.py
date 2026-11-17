"""Caso de uso de los borradores de documentos de cumplimiento (HU-16): composición de los mixins."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.agente import AgenteIA
from app.application.ai.anonimizador import AnonimizadorPII
from app.application.fabricas import fabricas
from app.application.borradores.casos_uso.generar_borradores.adaptacion_borrador import AdaptacionMixin
from app.application.borradores.casos_uso.generar_borradores.generacion_borrador import GeneracionMixin
from app.application.borradores.casos_uso.generar_borradores.lectura import LecturaMixin
from app.application.borradores.casos_uso.generar_borradores.ciclo_borrador import RevisionMixin
from app.domain.ports.limitador_port import Limitador


class Borradores(LecturaMixin, GeneracionMixin, AdaptacionMixin, RevisionMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, agente: AgenteIA | None = None,
                 anonimizador: AnonimizadorPII | None = None, limitador: Limitador | None = None,
                 registrar_evento=None):
        self.db = db
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.usuario = cliente.usuario
        self.agente = agente
        self.anonimizador = anonimizador
        self.limitador = limitador
        self.registrar_evento = registrar_evento
        self.bitacora = fabricas().bitacora(db)
        self.repo = fabricas().borradores(db)
