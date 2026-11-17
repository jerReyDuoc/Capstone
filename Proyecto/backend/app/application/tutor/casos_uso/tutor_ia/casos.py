"""Caso de uso del Agente IA Tutor (HU-15): composición de los mixins."""
from __future__ import annotations

from app.application.ai.agente import AgenteIA
from app.application.ai.anonimizador import AnonimizadorPII
from app.application.fabricas import fabricas
from app.application.tutor.casos_uso.tutor_ia.bloqueo_tutor import BloqueoMixin
from app.application.tutor.casos_uso.tutor_ia.conversaciones_tutor import ConversacionesMixin
from app.application.tutor.casos_uso.tutor_ia.envio_mensaje_tutor import EnvioMixin
from app.application.tutor.casos_uso.tutor_ia.lectura import LecturaMixin
from app.domain.ports.limitador_port import Limitador


class TutorIA(LecturaMixin, ConversacionesMixin, EnvioMixin, BloqueoMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db, cliente, agente: AgenteIA | None, anonimizador: AnonimizadorPII | None,
                 limitador: Limitador | None, registrar_evento=None):
        self.db = db
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.usuario = cliente.usuario
        self.agente = agente
        self.anonimizador = anonimizador
        self.limitador = limitador
        self.registrar_evento = registrar_evento
        self.repo = fabricas().tutor(db)
        self.bitacora = fabricas().bitacora(db)
