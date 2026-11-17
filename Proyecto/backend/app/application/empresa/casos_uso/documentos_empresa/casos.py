"""Caso de uso "Mis documentos" de la empresa cliente: composición de los mixins por responsabilidad."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.empresa.casos_uso.documentos_empresa.acciones_documento import AccionesDocumentoMixin
from app.application.empresa.casos_uso.documentos_empresa.acciones_evidencia import AccionesEvidenciaMixin
from app.application.empresa.casos_uso.documentos_empresa.comun import _storage_documentos, _storage_evidencias
from app.application.empresa.casos_uso.documentos_empresa.listado_documentos import ListadoDocumentosMixin


class DocumentosEmpresa(ListadoDocumentosMixin, AccionesDocumentoMixin, AccionesEvidenciaMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (empresa_con_documentos)."""

    def __init__(self, db: AsyncSession, cliente, storage_documentos=None, storage_evidencias=None):
        self.db = db
        self.repo = fabricas().documentos_empresa(db)
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.bitacora = fabricas().bitacora(db)
        self._storage_documentos = storage_documentos
        self._storage_evidencias = storage_evidencias

    @property
    def storage_documentos(self):
        if self._storage_documentos is None:
            self._storage_documentos = _storage_documentos()
        return self._storage_documentos

    @property
    def storage_evidencias(self):
        if self._storage_evidencias is None:
            self._storage_evidencias = _storage_evidencias()
        return self._storage_evidencias
