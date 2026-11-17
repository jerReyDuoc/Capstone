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
from app.domain.ports.almacenamiento_port import AlmacenamientoPort
from app.domain.ports.integridad_bitacora_port import IntegridadBitacoraPort
from app.domain.ports.repositorios_administracion import (
    MatrizRepositoryPort,
    MetricasIARepositoryPort,
    RecalculoBenchmarkRepositoryPort,
)
from app.domain.ports.repositorios_arcop import ExportacionDatosRepositoryPort
from app.domain.ports.repositorios_cuentas import (
    AuditoresRepositoryPort,
    CuentasRepositoryPort,
    SesionRepositoryPort,
    TokensCuentaRepositoryPort,
)
from app.domain.ports.repositorios_empresa import RetencionRepositoryPort
from app.domain.ports.repositorios_admin import SolicitudContratacionRepositoryPort
from app.domain.ports.repositorios_evaluacion import (
    BandejaRevisionRepositoryPort,
    CierreEvaluacionRepositoryPort,
    EncuestaPublicaRepositoryPort,
    LimitesEncuestaRepositoryPort,
    MigracionEvaluacionRepositoryPort,
    RemediacionRepositoryPort,
)
from app.domain.ports.repositorios_contratacion import ContratacionRepositoryPort
from app.domain.ports.repositorios_documentos import (
    BorradoresRepositoryPort,
    InformeRopaRepositoryPort,
    MapaDatosRepositoryPort,
    PlataformaRepositoryPort,
)
from app.domain.ports.repositorios_empresa_casos import (
    DocumentosEmpresaRepositoryPort,
    FormacionEmpresaRepositoryPort,
    HistorialEmpresaRepositoryPort,
)
from app.domain.ports.repositorios_rat import (
    AsistenteRatRepositoryPort,
    CumplimientoRatRepositoryPort,
    InformeRatRepositoryPort,
    RegistroActividadesRepositoryPort,
    RevisionInternaRepositoryPort,
)
from app.domain.ports.repositorios import (
    AnonimizacionRepositoryPort,
    BenchmarkRepositoryPort,
    EvaluacionRepositoryPort,
    EvidenciaRepositoryPort,
    InformeRepositoryPort,
    PreguntaFiltroRepositoryPort,
    RespuestaFiltroRepositoryPort,
    RespuestaRepositoryPort,
    TutorRepositoryPort,
)


@dataclass(frozen=True)
class Fabricas:
    bitacora: Callable[[AsyncSession], BitacoraPort]
    storage_documentos: Callable[[], AlmacenamientoPort]
    storage_evidencias: Callable[[], AlmacenamientoPort]
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
    metricas_ia: Callable[[AsyncSession], MetricasIARepositoryPort]
    recalculo_benchmark: Callable[[AsyncSession], RecalculoBenchmarkRepositoryPort]
    anonimizacion: Callable[[AsyncSession], AnonimizacionRepositoryPort]
    informes: Callable[[AsyncSession], InformeRepositoryPort]
    benchmark: Callable[[AsyncSession], BenchmarkRepositoryPort]
    revision_interna: Callable[[AsyncSession], RevisionInternaRepositoryPort]
    asistente_rat: Callable[[AsyncSession], AsistenteRatRepositoryPort]
    registro_actividades: Callable[[AsyncSession], RegistroActividadesRepositoryPort]
    informe_rat: Callable[[AsyncSession], InformeRatRepositoryPort]
    cumplimiento_rat: Callable[[AsyncSession], CumplimientoRatRepositoryPort]
    solicitudes_contratacion: Callable[[AsyncSession], SolicitudContratacionRepositoryPort]
    contratacion: Callable[[AsyncSession], ContratacionRepositoryPort]
    documentos_empresa: Callable[[AsyncSession], DocumentosEmpresaRepositoryPort]
    formacion_empresa: Callable[[AsyncSession], FormacionEmpresaRepositoryPort]
    historial_empresa: Callable[[AsyncSession], HistorialEmpresaRepositoryPort]
    remediacion: Callable[[AsyncSession], RemediacionRepositoryPort]
    bandeja_revision: Callable[[AsyncSession], BandejaRevisionRepositoryPort]
    migracion_evaluaciones: Callable[[AsyncSession], MigracionEvaluacionRepositoryPort]
    cierre_evaluacion: Callable[[AsyncSession], CierreEvaluacionRepositoryPort]
    limites_encuesta: Callable[[AsyncSession], LimitesEncuestaRepositoryPort]
    encuesta_publica: Callable[[AsyncSession], EncuestaPublicaRepositoryPort]
    mapa_datos: Callable[[AsyncSession], MapaDatosRepositoryPort]
    informe_ropa: Callable[[AsyncSession], InformeRopaRepositoryPort]
    plataforma: Callable[[AsyncSession], PlataformaRepositoryPort]
    borradores: Callable[[AsyncSession], BorradoresRepositoryPort]
    retencion: Callable[[AsyncSession], RetencionRepositoryPort]
    sesiones: Callable[[AsyncSession], SesionRepositoryPort]
    cuentas: Callable[[AsyncSession], CuentasRepositoryPort]
    tokens_cuenta: Callable[[AsyncSession], TokensCuentaRepositoryPort]
    auditores: Callable[[AsyncSession], AuditoresRepositoryPort]
    exportacion_datos: Callable[[AsyncSession], ExportacionDatosRepositoryPort]
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
