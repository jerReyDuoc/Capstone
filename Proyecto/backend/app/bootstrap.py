"""
Raíz de composición (A-21/A-40): único lugar que conecta casos de uso con infraestructura.
Ensambla la capa de IA a partir de la configuración (proveedor concreto: LLM_PROVIDER)
y registra las fábricas que consumen los casos de uso (app/application/fabricas.py).
Cada punto de entrada (API, worker, CLI, scripts, tests) llama a `configurar()`.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.agente import AgenteIA
from app.application.ai.anonimizador import AnonimizadorPII
from app.application.ai.validador_evidencias import ValidadorEvidenciasGateway
from app.application.ai.gateway import GatewayIA, PreciosModelo
from app.application.ai.politicas import crear_politicas
from app.application import fabricas as _fabricas
from app.core.config import settings
from app.domain.ports.almacenamiento_port import ClaveNoConfiguradaError
from app.infrastructure.archivos.extractor_texto import ExtractorTexto
from app.infrastructure.correo.smtp import CorreoSmtp
from app.infrastructure.documentos.adaptador_documentos import GeneradorDocumentos
from app.infrastructure.llm.proveedores import crear_proveedor
from app.infrastructure.cache.cache_matriz import CacheMatriz
from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository
from app.infrastructure.repositories.cuentas_repository import (
    AuditoresRepository,
    CuentasRepository,
    TokensCuentaRepository,
)
from app.infrastructure.repositories.exportacion_datos_repository import ExportacionDatosRepository
from app.infrastructure.repositories.retencion_repository import RetencionRepository
from app.infrastructure.repositories.sesion_repository import SesionRepository
from app.infrastructure.repositories.asistente_rat_repository import AsistenteRatRepository
from app.infrastructure.repositories.cumplimiento_rat_repository import CumplimientoRatRepository
from app.infrastructure.repositories.informe_rat_repository import InformeRatRepository
from app.infrastructure.repositories.benchmark_repository import BenchmarkRepository
from app.infrastructure.repositories.bitacora_repository import BitacoraRepository
from app.infrastructure.repositories.informe_repository import InformeRepository
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.integridad_bitacora import IntegridadBitacora
from app.infrastructure.repositories.matriz_repository import MatrizRepository
from app.infrastructure.repositories.metricas_ia_repository import MetricasIARepository
from app.infrastructure.repositories.recalculo_benchmark_repository import RecalculoBenchmarkRepository
from app.infrastructure.repositories.pregunta_filtro_repository import PreguntaFiltroRepository
from app.infrastructure.repositories.respuesta_filtro_repository import RespuestaFiltroRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.repositories.registro_actividades_repository import RegistroActividadesRepository
from app.infrastructure.repositories.revision_interna_repository import RevisionInternaRepository
from app.infrastructure.repositories.solicitud_contratacion_repository import SolicitudContratacionRepository
from app.infrastructure.repositories.contratacion_repository import ContratacionRepository
from app.infrastructure.repositories.documentos_empresa_repository import DocumentosEmpresaRepository
from app.infrastructure.repositories.formacion_empresa_repository import FormacionEmpresaRepository
from app.infrastructure.repositories.historial_empresa_repository import HistorialEmpresaRepository
from app.infrastructure.repositories.tutor_repository import TutorRepository
from app.infrastructure.repositories.mapa_datos_repository import MapaDatosRepository
from app.infrastructure.repositories.informe_ropa_repository import InformeRopaRepository
from app.infrastructure.repositories.plataforma_repository import PlataformaRepository
from app.infrastructure.repositories.borradores_repository import BorradoresRepository
from app.infrastructure.repositories.evaluacion_consultas_repository import EvaluacionConsultasRepository
from app.infrastructure.repositories.bandeja_revision_repository import BandejaRevisionRepository
from app.infrastructure.repositories.registro_ia_repository import RegistroIARepository
from app.infrastructure.security.cripto.contrasenas_y_tokens import CredencialesPBKDF2
from app.infrastructure.security.cripto.cifrado import CifradorDatos, CifradorEntidades
from app.infrastructure.security.pii.sanitizador_ner import SanitizadorNer
from app.infrastructure.storage.archivo_cifrado_almacenamiento import ArchivoCifradoAlmacenamiento
from app.infrastructure.storage.almacenamiento_local import AlmacenamientoLocal


def crear_gateway(sesion_auditoria: AsyncSession) -> GatewayIA:
    """`sesion_auditoria` debe ser una sesión dedicada a métricas/auditoría."""
    cifrador = None
    if settings.SANITIZER_ENABLED:
        if not settings.ENTITY_MAP_KEY:
            raise RuntimeError(
                "SANITIZER_ENABLED=true requiere ENTITY_MAP_KEY para cifrar el mapa de entidades. "
                "Genera una con: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        cifrador = CifradorEntidades(settings.ENTITY_MAP_KEY)

    return GatewayIA(
        provider=crear_proveedor(),
        sanitizer=SanitizadorNer(),
        registro=RegistroIARepository(
            sesion_auditoria, cifrador, guardar_mapa=settings.GUARDAR_MAPA_ENTIDADES_CIFRADO
        ),
        politicas=crear_politicas(
            max_chars_evidencia=settings.MAX_CHARS_EVIDENCIA_LLM,
            max_chars_justificacion=settings.MAX_CHARS_JUSTIFICACION_LLM,
            max_tokens_salida=settings.LLM_MAX_TOKENS_SALIDA,
            timeout_s=settings.LLM_TIMEOUT_S,
            # HU-15: tarea tutor
            max_chars_mensaje_tutor=settings.TUTOR_MAX_CHARS_MENSAJE,
            max_tokens_tutor=settings.TUTOR_MAX_TOKENS_SALIDA,
            timeout_tutor_s=settings.TUTOR_TIMEOUT_S,
            modelo_tutor=settings.TUTOR_MODELO,
            temperatura_tutor=settings.TUTOR_TEMPERATURA,
            # HU-16: tarea redactar_borrador
            max_chars_instrucciones_borrador=settings.BORRADORES_MAX_CHARS_INSTRUCCIONES,
            max_tokens_borrador=settings.BORRADOR_MAX_TOKENS_SALIDA,
            timeout_borrador_s=settings.BORRADOR_TIMEOUT_S,
            modelo_borrador=settings.BORRADOR_MODELO,
            temperatura_borrador=settings.BORRADOR_TEMPERATURA,
            # HU-39: tarea asistente_rat
            max_chars_respuesta_asistente=settings.ASISTENTE_MAX_CHARS_RESPUESTA,
            max_chars_documento_asistente=settings.ASISTENTE_MAX_CHARS_DOCUMENTO_LLM,
            max_tokens_asistente=settings.ASISTENTE_MAX_TOKENS_SALIDA,
            timeout_asistente_s=settings.ASISTENTE_TIMEOUT_S,
            modelo_asistente=settings.ASISTENTE_MODELO,
            temperatura_asistente=settings.ASISTENTE_TEMPERATURA,
        ),
        sanitizer_enabled=settings.SANITIZER_ENABLED,
        precios=PreciosModelo(settings.LLM_PRECIO_ENTRADA_USD_1M, settings.LLM_PRECIO_SALIDA_USD_1M),
    )


def crear_agente(sesion_auditoria: AsyncSession) -> AgenteIA:
    """HU-15: agente de LangGraph con sus skills (validar_evidencia, tutor y, HU-16, borrador)."""
    from app.infrastructure.security.prompt_injection.filtro_agente import FiltroAgente
    from app.infrastructure.security.prompt_injection.guardia_prompt import ReglasGuardiaPrompt
    guard = ReglasGuardiaPrompt()
    return AgenteIA(crear_gateway(sesion_auditoria), guard=guard, filtro=FiltroAgente(guard))  # HU-18


def crear_validador_evidencias(sesion_auditoria: AsyncSession) -> ValidadorEvidenciasGateway:
    agente = crear_agente(sesion_auditoria)
    return ValidadorEvidenciasGateway(agente.gateway, agente)


# ---------------------------------------------------------------- HU-06
def crear_anonimizador() -> AnonimizadorPII:
    """Mismo motor NER que el gateway, para anonimizar lo que se PERSISTE."""
    if not settings.SANITIZER_ENABLED:
        return AnonimizadorPII(None, habilitado=False)  # solo depuración (R6)
    return AnonimizadorPII(SanitizadorNer())


def crear_storage_evidencias() -> ArchivoCifradoAlmacenamiento:
    """Storage de evidencias: archivos cifrados en reposo hasta que el worker los anonimiza."""
    if not settings.ENTITY_MAP_KEY:
        raise ClaveNoConfiguradaError(
            "ENTITY_MAP_KEY no configurada: las evidencias se guardan cifradas (HU-06). "
            "Genera una con: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return ArchivoCifradoAlmacenamiento(AlmacenamientoLocal(), CifradorDatos(settings.ENTITY_MAP_KEY, "evidencias"))


def crear_storage_documentos() -> ArchivoCifradoAlmacenamiento:
    """HU-29: documentos generados de la empresa (informes PDF, borradores), cifrados en reposo."""
    if not settings.ENTITY_MAP_KEY:
        raise ClaveNoConfiguradaError(
            "ENTITY_MAP_KEY no configurada: los documentos de la empresa se guardan cifrados (HU-29)."
        )
    return ArchivoCifradoAlmacenamiento(AlmacenamientoLocal(), CifradorDatos(settings.ENTITY_MAP_KEY, "documentos"))


def configurar() -> None:
    """Registra las fábricas concretas. Idempotente."""
    _fabricas.configurar(_fabricas.Fabricas(
        bitacora=BitacoraRepository,
        storage_documentos=crear_storage_documentos,
        storage_evidencias=crear_storage_evidencias,
        credenciales=CredencialesPBKDF2(),
        integridad_bitacora=IntegridadBitacora(),
        cache_matriz=CacheMatriz(),
        evaluaciones=EvaluacionRepository,
        respuestas=RespuestaRepository,
        evidencias=EvidenciaRepository,
        tutor=TutorRepository,
        preguntas_filtro=PreguntaFiltroRepository,
        respuestas_filtro=RespuestaFiltroRepository,
        matriz=MatrizRepository,
        metricas_ia=MetricasIARepository,
        recalculo_benchmark=RecalculoBenchmarkRepository,
        anonimizacion=AnonimizacionRepository,
        informes=InformeRepository,
        benchmark=BenchmarkRepository,
        revision_interna=RevisionInternaRepository,
        asistente_rat=AsistenteRatRepository,
        registro_actividades=RegistroActividadesRepository,
        informe_rat=InformeRatRepository,
        cumplimiento_rat=CumplimientoRatRepository,
        solicitudes_contratacion=SolicitudContratacionRepository,
        contratacion=ContratacionRepository,
        documentos_empresa=DocumentosEmpresaRepository,
        formacion_empresa=FormacionEmpresaRepository,
        historial_empresa=HistorialEmpresaRepository,
        remediacion=EvaluacionConsultasRepository,
        bandeja_revision=BandejaRevisionRepository,
        migracion_evaluaciones=EvaluacionConsultasRepository,
        cierre_evaluacion=EvaluacionConsultasRepository,
        limites_encuesta=EvaluacionConsultasRepository,
        encuesta_publica=EvaluacionConsultasRepository,
        mapa_datos=MapaDatosRepository,
        informe_ropa=InformeRopaRepository,
        plataforma=PlataformaRepository,
        borradores=BorradoresRepository,
        retencion=RetencionRepository,
        sesiones=SesionRepository,
        cuentas=CuentasRepository,
        tokens_cuenta=TokensCuentaRepository,
        auditores=AuditoresRepository,
        exportacion_datos=ExportacionDatosRepository,
        documentos=GeneradorDocumentos(),
        correo=CorreoSmtp(),
        extractor_texto=ExtractorTexto(),
    ))
