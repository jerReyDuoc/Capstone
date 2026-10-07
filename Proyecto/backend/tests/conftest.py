"""
Variables mínimas para poder importar app.core.config sin un .env real.
Los tests NO se conectan a PostgreSQL, Redis ni Groq: usan repositorios falsos.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5433/test")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://test:test@127.0.0.1:5433/test")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379")
os.environ.setdefault("GROQ_API_KEY", "gsk_test")
