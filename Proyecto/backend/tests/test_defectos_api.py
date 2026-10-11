"""
QA - Regresión de los defectos de contrato de la API encontrados en las pruebas
de latencia (ya corregidos). Si alguno vuelve a fallar, el defecto regresó:
  - /benchmark tapado por /{evaluacion_id}       -> orden de routers en main.py
  - /comparativa con NameError                     -> imports en reportes.py
  - listado de respuestas con 500 (id_respuesta)   -> alias en RespuestaResumenResponse

    pytest tests/test_defectos_api.py -v -rxX
"""
import asyncio

import pytest

pytest.importorskip("httpx")

from _api_harness import EVAL_ID, MODO, body_filtro, cliente_api  # noqa: E402

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite")


def _correr(fn):
    async def _run():
        async with cliente_api() as c:
            return await fn(c)
    return asyncio.run(_run())


def test_benchmark_es_alcanzable():
    async def f(c):
        return await c.get("/api/evaluaciones/benchmark")
    assert _correr(f).status_code == 200


def test_comparativa_no_falla_con_500():
    async def f(c):
        return await c.get(f"/api/evaluaciones/{EVAL_ID}/comparativa")
    assert _correr(f).status_code != 500


def test_listado_de_respuestas_con_datos():
    async def f(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=body_filtro(True))
        ctrl = (await c.get(f"/api/evaluaciones/{EVAL_ID}/controles-aplicables")).json()[0]
        await c.post("/api/respuestas/", json={
            "evaluacion_id": EVAL_ID, "matriz_control_id": ctrl["id_control"],
            "estado_clasificacion": "no_aplica", "justificacion": "",
        })
        return await c.get(f"/api/evaluaciones/{EVAL_ID}/respuestas")
    r = _correr(f)
    assert r.status_code == 200 and r.json()["total"] >= 1


def test_variante_na_por_api_se_rechaza_con_400():
    """Borde N/A en la API: solo 'no_aplica' es válido; 'N/A' debe dar 400 (no 500)."""
    async def f(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=body_filtro(True))
        ctrl = (await c.get(f"/api/evaluaciones/{EVAL_ID}/controles-aplicables")).json()[0]
        return await c.post("/api/respuestas/", json={
            "evaluacion_id": EVAL_ID, "matriz_control_id": ctrl["id_control"],
            "estado_clasificacion": "N/A", "justificacion": "",
        })
    assert _correr(f).status_code == 400


def test_subir_evidencia_vacia_por_api_da_400():
    """Borde falta de evidencia en la API: archivo de 0 bytes => 400."""
    async def f(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=body_filtro(True))
        ctrl = (await c.get(f"/api/evaluaciones/{EVAL_ID}/controles-aplicables")).json()[0]
        r = await c.post("/api/respuestas/", json={
            "evaluacion_id": EVAL_ID, "matriz_control_id": ctrl["id_control"],
            "estado_clasificacion": "cumplido", "justificacion": "Política aprobada por el directorio.",
        })
        rid = r.json()["id_respuesta"]
        return await c.post(f"/api/respuestas/{rid}/evidencias",
                            files={"file": ("vacia.txt", b"", "text/plain")})
    assert _correr(f).status_code == 400
