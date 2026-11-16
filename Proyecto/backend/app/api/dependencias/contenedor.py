"""
Dependencias concretas para las rutas (A-40): único punto de la capa API que obtiene
objetos de infraestructura/composición. Delega en `app.bootstrap` en cada llamada, así
los tests pueden sustituir piezas parcheando ese módulo.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app import bootstrap
from app.domain.ports.file_storage_port import ClaveNoConfiguradaError  # noqa: F401  (re-export)

# Mismo objeto que usan los tests en `app.dependency_overrides[obtener_limitador]`.
from app.infrastructure.cache.limitador import obtener_limitador  # noqa: F401


def obtener_storage_evidencias():
    """Storage cifrado de evidencias. Lanza ClaveNoConfiguradaError si falta ENTITY_MAP_KEY."""
    return bootstrap.crear_storage_evidencias()


def obtener_storage_documentos():
    return bootstrap.crear_storage_documentos()


def obtener_anonimizador():
    return bootstrap.crear_anonimizador()


def crear_anonimizador():
    return bootstrap.crear_anonimizador()


def crear_storage_evidencias():
    return bootstrap.crear_storage_evidencias()


def crear_agente(sesion_auditoria: AsyncSession):
    """Carga langgraph: importar este módulo no lo arrastra, solo llamar a esta función."""
    return bootstrap.crear_agente(sesion_auditoria)
