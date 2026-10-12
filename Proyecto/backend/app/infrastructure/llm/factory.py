"""
Ensamblado de la capa de IA a partir de la configuración.
Es el ÚNICO lugar que sabe qué proveedor concreto se usa (LLM_PROVIDER).
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.evidence_validator import GatewayEvidenceValidator
from app.application.ai.gateway import AIGateway, PreciosModelo
from app.application.ai.politicas import crear_politicas
from app.core.config import settings
from app.domain.ports.llm_provider_port import LLMProviderPort
from app.infrastructure.repositories.registro_ia_repository import RegistroIARepository
from app.infrastructure.security.cifrado import CifradorEntidades
from app.infrastructure.security.ner_sanitizer import NERSanitizer


def crear_proveedor() -> LLMProviderPort:
    if settings.LLM_PROVIDER == "groq":
        from app.infrastructure.llm.groq_provider import GroqProvider
        return GroqProvider(
            api_key=settings.GROQ_API_KEY,
            modelo_por_defecto=settings.LLM_MODEL,
            max_reintentos=settings.LLM_MAX_REINTENTOS,
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
        registro=RegistroIARepository(sesion_auditoria, cifrador),
        politicas=crear_politicas(
            max_chars_evidencia=settings.MAX_CHARS_EVIDENCIA_LLM,
            max_chars_justificacion=settings.MAX_CHARS_JUSTIFICACION_LLM,
            max_tokens_salida=settings.LLM_MAX_TOKENS_SALIDA,
            timeout_s=settings.LLM_TIMEOUT_S,
        ),
        sanitizer_enabled=settings.SANITIZER_ENABLED,
        precios=PreciosModelo(settings.LLM_PRECIO_ENTRADA_USD_1M, settings.LLM_PRECIO_SALIDA_USD_1M),
    )


def crear_validador_evidencias(sesion_auditoria: AsyncSession) -> GatewayEvidenceValidator:
    return GatewayEvidenceValidator(crear_gateway(sesion_auditoria))
