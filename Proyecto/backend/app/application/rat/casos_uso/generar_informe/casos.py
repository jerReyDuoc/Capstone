"""Caso de uso del informe RAT: composición de los mixins por responsabilidad."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.rat.casos_uso.generar_informe.descarga_envio_informe import DescargaEnvioInformeMixin
from app.application.rat.casos_uso.generar_informe.emision_informe import EmisionInformeMixin
from app.application.rat.casos_uso.generar_informe.lectura_registro import LecturaRegistroMixin
from app.application.rat.casos_uso.generar_informe.verificacion_informe import VerificacionInformeMixin


class InformeRatCasos(LecturaRegistroMixin, EmisionInformeMixin, DescargaEnvioInformeMixin, VerificacionInformeMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, limitador=None, storage=None):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa = cliente.empresa
        self.empresa_id: int = cliente.empresa.id
        # Valores simples (no el objeto ORM): siguen disponibles después de un rollback
        self.razon_social: str = cliente.empresa.razon_social
        self.rut: str | None = getattr(cliente.empresa, "rut", None)
        self.rubro_id: int | None = getattr(cliente.empresa, "rubro_id", None)
        self.usuario_id: int = cliente.usuario.id
        self.email_usuario: str = cliente.usuario.email
        self.limitador = limitador
        self.bitacora = fabricas().bitacora(db)
        self.repo = fabricas().informe_rat(db)
        self._storage = storage
