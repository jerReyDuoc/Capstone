"""Caso de uso del asistente de IA del RAT (HU-39): composición de los mixins por responsabilidad."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.anonimizador import AnonimizadorPII
from app.application.rat.casos_uso.asistente_rat.conversacion import ConversacionMixin
from app.application.rat.casos_uso.asistente_rat.decisiones import DecisionesMixin
from app.application.rat.casos_uso.asistente_rat.documentos import DocumentosMixin
from app.application.rat.casos_uso.asistente_rat.guia import GuiaMixin
from app.application.rat.casos_uso.asistente_rat.sesion_asistente import SesionMixin
from app.application.fabricas import fabricas
from app.domain.ports.limitador_port import Limitador


class AsistenteRat(SesionMixin, ConversacionMixin, DocumentosMixin, DecisionesMixin, GuiaMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, agente=None, anonimizador: AnonimizadorPII | None = None,
                 limitador: Limitador | None = None, registrar_evento=None):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.usuario_id: int = cliente.usuario.id
        self.agente = agente
        self.anonimizador = anonimizador
        self.limitador = limitador
        self.registrar_evento = registrar_evento
        self.bitacora = fabricas().bitacora(db)
        self.repo = fabricas().asistente_rat(db)
