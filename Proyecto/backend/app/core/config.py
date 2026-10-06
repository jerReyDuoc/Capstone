from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    REDIS_URL: str
    GROQ_API_KEY: str
    LLM_MODEL: str = "openai/gpt-oss-safeguard-20b"
    UMBRAL_CONFIANZA: float = 0.8
    STORAGE_DIR: str = "./storage"

    class Config:
        env_file = ".env"

settings = Settings()