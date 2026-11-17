"""Caso de uso de la revisión interna del registro (HU-40): composición de los mixins por responsabilidad."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.rat.casos_uso.generar_informe import InformeRatCasos
from app.application.rat.casos_uso.revision_interna.entregables import EntregablesMixin
from app.application.rat.casos_uso.revision_interna.lectura import LecturaMixin
from app.application.rat.casos_uso.revision_interna.revision import RevisionMixin


class RevisionInternaCasos(LecturaMixin, RevisionMixin, EntregablesMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, limitador=None, storage=None):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.razon_social: str = cliente.empresa.razon_social
        self.rut: str | None = getattr(cliente.empresa, "rut", None)
        self.usuario_id: int = cliente.usuario.id
        self.nombre_usuario: str = getattr(cliente.usuario, "nombre", "") or ""
        self.email_usuario: str = cliente.usuario.email
        self.limitador = limitador
        self.bitacora = fabricas().bitacora(db)
        self.repo = fabricas().revision_interna(db)
        self.informes = InformeRatCasos(db, cliente, limitador, storage)
