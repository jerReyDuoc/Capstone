from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/mydb" # Cambiar link a real database
    REDIS_URL: str = "redis://localhost:6379" # Cambiar link a real Redis URL
    OPENAI_API_KEY: str = "" # Cambiar key a real API key
    LLM_MODEL: str = "gpt-4o" # Cambiar modelo a real modelo
    LLM_CONFIDENCE_THRESHOLD: float = 0.8 # Cambiar umbral a real umbral
    STORAGE_DIR: str = "./storage" # Cambiar directorio a real directorio

    class Config:
        env_file = ".env"

settings = Settings()