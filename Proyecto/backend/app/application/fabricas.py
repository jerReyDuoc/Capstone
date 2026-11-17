"""
Registro de fábricas que llena la raíz de composición (app/bootstrap.py).

Los casos de uso piden aquí sus dependencias concretas sin importar infraestructura.
Para agregar una dependencia: añade un campo a `Fabricas` y llénalo en bootstrap.configurar().
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.generador_documentos_port import GeneradorDocumentosPort
from app.domain.ports.bitacora_port import BitacoraPort
from app.domain.ports.cache_matriz_port import CacheMatrizPort
from app.domain.ports.correo_port import CorreoPort
from app.domain.ports.credenciales_port import CredencialesPort
from app.domain.ports.extractor_texto_port import ExtractorTextoPort
from app.domain.ports.almacenamiento_port import FileStoragePort
from app.domain.ports.integridad_bitacora_port import IntegridadBitacoraPort
from app.domain.ports.repositorios_rat import (
    AsistenteRatRepositoryPort,
    RegistroActividadesRepositoryPort,
    RevisionInternaRepositoryPort,
)
from app.domain.ports.repositorios import (
    AnonimizacionRepositoryPort,
    BenchmarkRepositoryPort,
    EvaluacionRepositoryPort,
    EvidenciaRepositoryPort,
    InformeRepositoryPort,
    MatrizRepositoryPort,
    PreguntaFiltroRepositoryPort,
    RespuestaFiltroRepositoryPort,
    RespuestaRepositoryPort,
    TutorRepositoryPort,
)


@dataclass(frozen=True)
class Fabricas:
    bitacora: Callable[[AsyncSession], BitacoraPort]
    storage_documentos: Callable[[], FileStoragePort]
    storage_evidencias: Callable[[], FileStoragePort]
    credenciales: CredencialesPort
    integridad_bitacora: IntegridadBitacoraPort
    cache_matriz: CacheMatrizPort
    evaluaciones: Callable[[AsyncSession], EvaluacionRepositoryPort]
    respuestas: Callable[[AsyncSession], RespuestaRepositoryPort]
    evidencias: Callable[[AsyncSession], EvidenciaRepositoryPort]
    tutor: Callable[[AsyncSession], TutorRepositoryPort]
    preguntas_filtro: Callable[[AsyncSession], PreguntaFiltroRepositoryPort]
    respuestas_filtro: Callable[[AsyncSession], RespuestaFiltroRepositoryPort]
    matriz: Callable[[AsyncSession], MatrizRepositoryPort]
    anonimizacion: Callable[[AsyncSession], AnonimizacionRepositoryPort]
    informes: Callable[[AsyncSession], InformeRepositoryPort]
    benchmark: Callable[[AsyncSession], BenchmarkRepositoryPort]
    revision_interna: Callable[[AsyncSession], RevisionInternaRepositoryPort]
    asistente_rat: Callable[[AsyncSession], AsistenteRatRepositoryPort]
    registro_actividades: Callable[[AsyncSession], RegistroActividadesRepositoryPort]
    documentos: GeneradorDocumentosPort
    correo: CorreoPort
    extractor_texto: ExtractorTextoPort


_actual: Fabricas | None = None


def configurar(f: Fabricas) -> None:
    global _actual
    _actual = f


def fabricas() -> Fabricas:
    if _actual is None:
        raise RuntimeError("Raíz de composición no configurada: llama a app.bootstrap.configurar()")
    return _actual
