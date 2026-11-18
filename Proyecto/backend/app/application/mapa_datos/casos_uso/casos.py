"""Caso de uso del mapa de datos (HU-34): composición de los mixins por responsabilidad."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.mapa_datos.casos_uso.edicion_mapa import EdicionMixin
from app.application.mapa_datos.casos_uso.exportacion import ExportacionMixin
from app.application.mapa_datos.casos_uso.lectura import LecturaMixin
from app.application.mapa_datos.casos_uso.plantillas_y_sugerencias import PlantillasYSugerenciasMixin
from app.application.mapa_datos.casos_uso.historial_mapa import VersionesMixin


class MapaDatosCasos(LecturaMixin, EdicionMixin, PlantillasYSugerenciasMixin, VersionesMixin, ExportacionMixin):
    """`cliente` es el ClienteConServicio de app/api/dependencias/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, limitador=None, *, confirmar: bool = True):
        """T-12: con `confirmar=False` el caso de uso deja el cambio en la transacción (flush) y quien lo
        llama confirma todo junto (p. ej. aceptar una propuesta del asistente en UN solo commit)."""
        self.db = db
        self.confirmar = confirmar
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.razon_social: str = cliente.empresa.razon_social
        self.rubro_id: int | None = cliente.empresa.rubro_id
        self.usuario_id: int = cliente.usuario.id
        self.email_usuario: str = cliente.usuario.email
        self.limitador = limitador
        self.bitacora = fabricas().bitacora(db)
        self.repo = fabricas().mapa_datos(db)
        self.ultimo_id: int | None = None   # HU-39: id del último elemento o flujo creado
