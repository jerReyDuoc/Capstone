"""Selección del proveedor LLM concreto a partir de la configuración (LLM_PROVIDER)."""
from app.core.config import settings
from app.domain.ports.llm_provider_port import LLMProviderPort


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
    if settings.LLM_PROVIDER == "ollama":  # HU-07: modelo local
        from app.infrastructure.llm.ollama_provider import OllamaProvider
        return OllamaProvider(
            url=settings.OLLAMA_URL,
            modelo_por_defecto=settings.LLM_MODEL,
            reintentos_salida=settings.LLM_REINTENTOS_SALIDA,
        )
    raise ValueError(f"LLM_PROVIDER no soportado: {settings.LLM_PROVIDER}")
