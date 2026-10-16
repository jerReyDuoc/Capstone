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
os.environ.setdefault("APP_ENV", "test")
# Clave Fernet SOLO para pruebas (no usar en ningún .env real)
os.environ.setdefault("ENTITY_MAP_KEY", "dGVzdC1rZXktc29sby1wYXJhLXB5dGVzdC0xMjM0NTY=")

# Las pruebas de API en proceso suben archivos: que no ensucien ./storage
import tempfile  # noqa: E402

os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="qa_storage_"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # para importar _api_harness


def pytest_configure(config):
    config.addinivalue_line("markers", "latencia: pruebas de tiempo de respuesta de la API REST")


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def bd_live():
    """
    Solo en modo live con LATENCIA_PREPARAR_BD=1: crea las evaluaciones de prueba
    y limpia sus datos al inicio y al final de la sesión. En otro caso no hace nada.
    """
    import asyncio
    import _api_harness as h

    if not h.PREPARAR_BD:
        yield
        return
    asyncio.run(h.preparar_bd())
    yield
    if not h.CONSERVAR_DATOS:
        asyncio.run(h.limpiar_bd())


@pytest.fixture(autouse=True)
def _catalogo_controles_limpio():
    """HU-01: el catálogo de controles se cachea en memoria; cada prueba en proceso
    crea su propia BD SQLite, así que se invalida antes y después de cada test."""
    from app.infrastructure.cache import catalogo_controles

    catalogo_controles.invalidar()
    yield
    catalogo_controles.invalidar()
