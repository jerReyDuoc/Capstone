"""
Ensamblado de la capa de IA a partir de la configuración.
Es el ÚNICO lugar que sabe qué proveedor concreto se usa (LLM_PROVIDER).
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.agente import AgenteIA
from app.application.ai.anonimizador import AnonimizadorPII
from app.application.ai.evidence_validator import GatewayEvidenceValidator
from app.application.ai.gateway import AIGateway, PreciosModelo
from app.application.ai.politicas import crear_politicas
from app.core.config import settings
from app.domain.ports.llm_provider_port import LLMProviderPort
from app.infrastructure.repositories.registro_ia_repository import RegistroIARepository
from app.infrastructure.security.cifrado import CifradorDatos, CifradorEntidades
from app.infrastructure.security.ner_sanitizer import NERSanitizer
from app.infrastructure.storage.archivo_cifrado_storage import ArchivoCifradoStorage
from app.infrastructure.storage.local_storage import LocalFileStorage


def crear_proveedor() -> LLMProviderPort:
    if settings.LLM_PROVIDER == "groq":
        from app.infrastructure.llm.groq_provider import GroqProvider
        return GroqProvider(
            api_key=settings.GROQ_API_KEY,
            modelo_por_defecto=settings.LLM_MODEL,
            max_reintentos=settings.LLM_MAX_REINTENTOS,
            reasoning_effort=settings.LLM_REASONING_EFFORT,
            reintentos_salida=settings.LLM_REINTENTOS_SALIDA,
        )
    raise ValueError(f"LLM_PROVIDER no soportado: {settings.LLM_PROVIDER}")


def crear_gateway(sesion_auditoria: AsyncSession) -> AIGateway:
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

    return AIGateway(
        provider=crear_proveedor(),
        sanitizer=NERSanitizer(),
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
        ),
        sanitizer_enabled=settings.SANITIZER_ENABLED,
        precios=PreciosModelo(settings.LLM_PRECIO_ENTRADA_USD_1M, settings.LLM_PRECIO_SALIDA_USD_1M),
    )


def crear_agente(sesion_auditoria: AsyncSession) -> AgenteIA:
    """HU-15: agente de LangGraph con sus skills (validar_evidencia, tutor)."""
    from app.infrastructure.security.prompt_guard import ReglasPromptGuard
    return AgenteIA(crear_gateway(sesion_auditoria), guard=ReglasPromptGuard())


def crear_validador_evidencias(sesion_auditoria: AsyncSession) -> GatewayEvidenceValidator:
    agente = crear_agente(sesion_auditoria)
    return GatewayEvidenceValidator(agente.gateway, agente)


# ---------------------------------------------------------------- HU-06
def crear_anonimizador() -> AnonimizadorPII:
    """Mismo motor NER que el gateway, para anonimizar lo que se PERSISTE."""
    if not settings.SANITIZER_ENABLED:
        return AnonimizadorPII(None, habilitado=False)  # solo depuración (R6)
    return AnonimizadorPII(NERSanitizer())


class ClaveNoConfiguradaError(RuntimeError):
    """Falta ENTITY_MAP_KEY: no se pueden guardar evidencias sin cifrar (fail-closed)."""


def crear_storage_evidencias() -> ArchivoCifradoStorage:
    """Storage de evidencias: archivos cifrados en reposo hasta que el worker los anonimiza."""
    if not settings.ENTITY_MAP_KEY:
        raise ClaveNoConfiguradaError(
            "ENTITY_MAP_KEY no configurada: las evidencias se guardan cifradas (HU-06). "
            "Genera una con: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return ArchivoCifradoStorage(LocalFileStorage(), CifradorDatos(settings.ENTITY_MAP_KEY, "evidencias"))
