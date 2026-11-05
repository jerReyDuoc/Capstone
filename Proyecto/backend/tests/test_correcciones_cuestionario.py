"""
Correcciones 05-11 · Cuestionario:
  - la justificación es opcional en todos los estados (JUSTIFICACION_OBLIGATORIA=false, el
    valor por defecto de la app);
  - para completar, cada pregunta "cumplido" necesita evidencia
    (EVIDENCIA_OBLIGATORIA_CUMPLIDO=true, el valor por defecto de la app).
conftest.py fuerza los valores antiguos para las demás suites; aquí se activan los nuevos.
"""
import pytest

pytest.importorskip("httpx")

from app.application.filters.control_tree import CONTROLES_BASE  # noqa: E402
from app.application.use_cases.create_respuesta import validar_justificacion  # noqa: E402
from app.core.config import Settings, settings  # noqa: E402
from test_hu02_matriz_estados import (  # noqa: E402
    CUMP, EVAL_ID, PARC, REV, SOLO_BASE, _body, _correr, _procesar_con_llm, _subir, solo_en_proceso,
)


def test_valores_por_defecto_de_la_app():
    campos = Settings.model_fields
    assert campos["JUSTIFICACION_OBLIGATORIA"].default is False
    assert campos["EVIDENCIA_OBLIGATORIA_CUMPLIDO"].default is True


def test_justificacion_opcional_en_todos_los_estados(monkeypatch):
    monkeypatch.setattr(settings, "JUSTIFICACION_OBLIGATORIA", False)
    for estado in (CUMP, PARC, REV, "no_cumplido", "no_aplica"):
        validar_justificacion(estado, "")      # no lanza


@solo_en_proceso
def test_api_acepta_parcial_sin_justificacion(monkeypatch):
    monkeypatch.setattr(settings, "JUSTIFICACION_OBLIGATORIA", False)

    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)
        r = await c.post("/api/respuestas/", json=_body("GOB-001", PARC, ""))
        assert r.status_code in (200, 201), r.text
    _correr(esc)


@solo_en_proceso
def test_completar_exige_evidencia_en_cumplido(monkeypatch):
    monkeypatch.setattr(settings, "EVIDENCIA_OBLIGATORIA_CUMPLIDO", True)

    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)
        ids = {}
        for codigo in CONTROLES_BASE:
            ids[codigo] = (await c.post("/api/respuestas/", json=_body(codigo, CUMP))).json()["id_respuesta"]
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "CUMPLIDO_SIN_EVIDENCIA"
        for codigo, rid in ids.items():
            await _procesar_con_llm(await _subir(c, rid), CUMP, confianza=0.95)
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 200, r.text
    _correr(esc)
