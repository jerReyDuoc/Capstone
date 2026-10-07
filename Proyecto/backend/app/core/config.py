from typing import Literal
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    REDIS_URL: str
    GROQ_API_KEY: str
    LLM_MODEL: str = "openai/gpt-oss-safeguard-20b"
    UMBRAL_CONFIANZA: float = 0.8
    STORAGE_DIR: str = "./storage"
    # Caracteres de la evidencia que se analizan y se envían al LLM
    MAX_CHARS_EVIDENCIA_LLM: int = 8000
    # True = falla (fail-closed) si spaCy/es_core_news_md no están instalados
    REQUIERE_NER: bool = False
    # Qué hacer si la EVIDENCIA parece contener prompt injection:
    #   "bloquear" -> no se envía al LLM; la respuesta queda en requiere_revision
    #   "marcar"   -> se envía (anonimizada y delimitada), se registra el evento y,
    #                 si el LLM no está seguro, queda en requiere_revision (sin fallback al usuario)
    MODO_SEGURIDAD_EVIDENCIA: Literal["bloquear", "marcar"] = "bloquear"

    class Config:
        env_file = ".env"

settings = Settings()