from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    # OBSOLETO: lo reemplaza SANITIZER_ENABLED (con el sanitizador activo el NER es
    # siempre obligatorio). Se mantiene para no romper archivos .env existentes.
    REQUIERE_NER: bool = False
    # Qué hacer si la EVIDENCIA parece contener prompt injection:
    #   "bloquear" -> no se envía al LLM; la respuesta queda en requiere_revision
    #   "marcar"   -> se envía (anonimizada y delimitada), se registra el evento y,
    #                 si el LLM no está seguro, queda en requiere_revision (sin fallback al usuario)
    MODO_SEGURIDAD_EVIDENCIA: Literal["bloquear", "marcar"] = "bloquear"

    # ------------------------------------------------ Capa de Políticas e IA
    APP_ENV: Literal["development", "test", "production"] = "development"
    # Proveedor del LLM (cambiarlo no toca la lógica de negocio)
    LLM_PROVIDER: Literal["groq"] = "groq"
    LLM_TIMEOUT_S: float = 60.0
    LLM_MAX_REINTENTOS: int = 2
    LLM_MAX_TOKENS_SALIDA: int = 1500
    MAX_CHARS_JUSTIFICACION_LLM: int = 4000
    # Precio del modelo en USD por millón de tokens, para estimar costo en las
    # métricas. Tómalos de la página de precios del proveedor para LLM_MODEL.
    LLM_PRECIO_ENTRADA_USD_1M: float = 0.0
    LLM_PRECIO_SALIDA_USD_1M: float = 0.0
    # true  -> el motor NER anonimiza todo antes del LLM (obligatorio en producción)
    # false -> SOLO DEBUG: el texto va en claro al LLM. Prohibido si APP_ENV=production.
    SANITIZER_ENABLED: bool = True
    # Clave Fernet para cifrar el mapa de entidades guardado en BD. Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENTITY_MAP_KEY: str | None = None

    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def _validar_capa_ia(self):
        if self.APP_ENV == "production" and not self.SANITIZER_ENABLED:
            raise ValueError(
                "SANITIZER_ENABLED=false está prohibido con APP_ENV=production "
                "(enviaría datos personales en claro al LLM)."
            )
        if self.APP_ENV == "production" and not self.ENTITY_MAP_KEY:
            raise ValueError("ENTITY_MAP_KEY es obligatoria con APP_ENV=production.")
        # En desarrollo la falta de clave se detecta al crear el gateway (worker),
        # para no bloquear alembic ni la API, que no la necesitan.
        return self

settings = Settings()
