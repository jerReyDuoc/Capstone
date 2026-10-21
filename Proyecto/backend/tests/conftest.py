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


def _spacy_disponible() -> bool:
    try:
        from app.infrastructure.security.ner_sanitizer import cargar_spacy
        cargar_spacy()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(autouse=True, scope="session")
def _motor_ner_para_la_api():
    """
    HU-06: la API anonimiza la justificación y el nombre del archivo ANTES de guardarlos
    y, si el motor NER no carga, responde 503 (fail-closed). En Docker spaCy está
    instalado y se usa el motor real. Si no lo está (p. ej. un entorno de revisión sin
    PyPI), las pruebas de API en proceso usan el mismo motor con un NLP simulado
    (reglas de RUT, correo, teléfono, direcciones y datos codificados intactas), como
    ya hacía test_e2e_capa_ia.py. Las pruebas que necesitan spaCy real siguen
    omitiéndose por su cuenta. Alcance de sesión: también cubre los fixtures de módulo
    (p. ej. la medición de test_latencia_api.py).
    """
    if _spacy_disponible():
        yield
        return
    import app.infrastructure.llm.factory as factory
    from app.infrastructure.security.ner_sanitizer import NERSanitizer
    from _capa_ia_fakes import StubNLP

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(factory, "NERSanitizer", lambda: NERSanitizer(lambda: StubNLP()))
        yield


@pytest.fixture(autouse=True)
def _catalogo_controles_limpio():
    """HU-01: el catálogo de controles se cachea en memoria; cada prueba en proceso
    crea su propia BD SQLite, así que se invalida antes y después de cada test."""
    from app.infrastructure.cache import catalogo_controles

    catalogo_controles.invalidar()
    yield
    catalogo_controles.invalidar()


@pytest.fixture(autouse=True)
def _limitador_en_memoria(monkeypatch):
    """
    HU-19: los límites contra abuso usan Redis. En las pruebas en proceso se usa un
    limitador en memoria NUEVO en cada prueba: no se toca el Redis real (en Docker el
    .env dice APP_ENV=development) y los contadores no se acumulan entre pruebas.
    """
    from app.infrastructure.cache import limitador

    monkeypatch.setattr(limitador, "_limitador", limitador.LimitadorMemoria())

