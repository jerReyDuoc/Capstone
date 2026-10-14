# Imagen única del backend: la usan los servicios migrate, api y worker
# (cambia solo el comando). Incluye spaCy + es_core_news_md, así el worker
# arranca con el motor NER listo.

# ---------------------------------------------------------------- etapa 1: wheels
# Compila aquí cualquier dependencia que no traiga wheel para Python 3.13, para
# que la imagen final no necesite compiladores.
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------------------------------------------------------------- etapa 2: runtime
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STORAGE_DIR=/data/storage

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels \
    && python -c "import spacy; spacy.load('es_core_news_md')"

WORKDIR /app
COPY . .

# Usuario sin privilegios. /data/storage es el volumen compartido entre la API
# (guarda las evidencias) y el worker (las lee).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/storage \
    && chown -R app:app /data /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
