from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    REDIS_URL: str
    GROQ_API_KEY: str
    # openai/gpt-oss-20b y gpt-oss-120b admiten salida ESTRICTA en Groq (el JSON siempre
    # cumple el schema). gpt-oss-safeguard-20b solo "best effort": falla más seguido.
    LLM_MODEL: str = "openai/gpt-oss-20b"
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
    # Incluye los tokens de razonamiento de gpt-oss: con muy pocos el JSON queda cortado.
    LLM_MAX_TOKENS_SALIDA: int = 4096
    # Esfuerzo de razonamiento (solo gpt-oss-20b/120b): low | medium | high
    LLM_REASONING_EFFORT: Literal["low", "medium", "high"] = "low"
    # Reintentos cuando el modelo devuelve una salida inválida (JSON cortado / fuera del schema)
    LLM_REINTENTOS_SALIDA: int = 1
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
    # ------------------------------------------------ Autenticación de la API
    # Secreto HMAC para firmar/verificar los tokens bearer (app/core/autenticacion.py).
    AUTH_SECRET: str | None = None
    AUTH_TOKEN_TTL_MIN: int = 480
    # ------------------------------------------------ Plazos de solicitudes ARCOP
    # PENDIENTES DE DEFINIR por el equipo (dependen de la Ley 21.719). Vacíos = no
    # se calcula fecha límite. Se cuentan en días CORRIDOS.
    ARCOP_PLAZO_RESPUESTA_DIAS: int | None = None
    ARCOP_PLAZO_INFORMACION_DIAS: int | None = None

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
        if self.APP_ENV == "production" and (not self.AUTH_SECRET or len(self.AUTH_SECRET) < 32):
            raise ValueError("AUTH_SECRET (mínimo 32 caracteres) es obligatorio con APP_ENV=production.")
        # En desarrollo la falta de clave se detecta al crear el gateway (worker),
        # para no bloquear alembic ni la API, que no la necesitan.
        return self

settings = Settings()
