"""
QA - Completar (cerrar definitivamente) una evaluación y bloquear evidencias en
evaluaciones cerradas.

  POST /api/evaluaciones/{id}/completar
    * exige filtro completo, todos los controles aplicables respondidos y ninguna
      evidencia pendiente/en proceso;
    * genera el resumen y marca estado_progreso = 'completada' en una transacción;
    * después: no se responde, no se rehace el filtro, no se suben evidencias y no
      se puede completar de nuevo.

Ejecutar desde Proyecto/backend/:
    pytest tests/test_completar_evaluacion.py -v

En proceso (app real + SQLite en memoria, ver _api_harness.py). En modo live
(LATENCIA_BASE_URL) se omiten: cambian el estado de la evaluación.
"""
import asyncio

import pytest

pytest.importorskip("httpx")

from _api_harness import EVAL_ID, EVAL_NA_ID, MODO, TODOS_LOS_CONTROLES, body_filtro, cliente_api  # noqa: E402
from app.application.filters.control_tree import CONTROLES_BASE  # noqa: E402

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

pytestmark = pytest.mark.skipif(MODO == "live", reason="cambian el estado de la evaluación; solo en proceso")

ID = {codigo: i + 1 for i, codigo in enumerate(TODOS_LOS_CONTROLES)}
SOLO_BASE = {"respuestas": [{"codigo": f"F{i}", "respuesta": i == 1} for i in range(1, 8)]}
F1_NO = {"respuestas": [{"codigo": f"F{i}", "respuesta": False} for i in range(1, 8)]}
JUST = "Contamos con una política de IA aprobada por el directorio."
EVIDENCIA = b"Politica de uso responsable de IA v2. Aprobada por el directorio."


def _correr(escenario):
    async def _main():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_main())


async def _sql(sql, **params):
    from sqlalchemy import text
    from app.core.database import get_db
    from app.main import app
    gen = app.dependency_overrides[get_db]()
    s = await gen.__anext__()
    try:
        r = await s.execute(text(sql), params)
        await s.commit()
        return r
    finally:
        await gen.aclose()


async def _responder(c, codigo, estado="cumplido", justificacion=JUST, evaluacion=EVAL_ID):
    r = await c.post("/api/respuestas/", json={
        "evaluacion_id": evaluacion, "matriz_control_id": ID[codigo],
        "estado_clasificacion": estado, "justificacion": justificacion})
    assert r.status_code in (200, 201), r.text
    return r.json()["id_respuesta"]


async def _responder_base(c, estado="cumplido"):
    """Filtro solo base (22 controles) y todos respondidos."""
    assert (await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)).status_code == 200
    return {codigo: await _responder(c, codigo, estado) for codigo in CONTROLES_BASE}


def _codigo(r):
    return r.json()["detail"]["codigo"]


# =====================================================================
# Condiciones para completar
# =====================================================================
def test_inexistente_404_y_filtro_pendiente_409():
    async def esc(c):
        r = await c.post("/api/evaluaciones/987654/completar")
        assert r.status_code == 404 and _codigo(r) == "EVALUACION_NO_ENCONTRADA"
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 409 and _codigo(r) == "FILTRO_PENDIENTE"
    _correr(esc)


def test_cuestionario_incompleto_409_y_la_evaluacion_sigue_abierta():
    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)
        for codigo in CONTROLES_BASE[:20]:
            await _responder(c, codigo)
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 409 and _codigo(r) == "CUESTIONARIO_INCOMPLETO"
        assert "Faltan 2 de 22" in r.json()["detail"]["mensaje"]
        assert CONTROLES_BASE[20] in r.json()["detail"]["mensaje"]
        ev = (await c.get(f"/api/evaluaciones/{EVAL_ID}")).json()
        assert ev["estado_progreso"] == "en_progreso"
        assert (await c.get(f"/api/evaluaciones/{EVAL_ID}/resumen")).status_code == 404  # no se generó
    _correr(esc)


def test_respuestas_de_controles_fuera_de_alcance_no_cuentan_como_avance():
    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=body_filtro(True))
        await _responder(c, "SEG-001")                  # aplica solo con F4
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)
        for codigo in CONTROLES_BASE[:-1]:
            await _responder(c, codigo)
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 409 and "Faltan 1 de 22" in r.json()["detail"]["mensaje"]
    _correr(esc)


def test_evidencia_en_validacion_impide_completar_hasta_que_termina():
    async def esc(c):
        ids = await _responder_base(c)
        r = await c.post(f"/api/respuestas/{ids['GOB-001']}/evidencias",
                         files={"file": ("politica.txt", EVIDENCIA, "text/plain")})
        assert r.status_code == 202, r.text
        evidencia_id = r.json()["id_evidencia"]

        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 409 and _codigo(r) == "EVIDENCIAS_EN_PROCESO"
        await _sql("UPDATE evidencias SET estado_validacion='processing' WHERE id_evidencia=:i", i=evidencia_id)
        assert (await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")).status_code == 409

        # El worker terminó (validada o con error): ya se puede completar
        await _sql("UPDATE evidencias SET estado_validacion='validated' WHERE id_evidencia=:i", i=evidencia_id)
        assert (await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")).status_code == 200
    _correr(esc)


# =====================================================================
# Completar y lo que queda bloqueado después
# =====================================================================
def test_completar_genera_resumen_marca_completada_y_bloquea_todo():
    async def esc(c):
        ids = await _responder_base(c)
        await _responder(c, "GOB-001", "no_cumplido", "No hay política.")      # 21/22 => 95,45 %

        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["estado_progreso"] == "completada"
        assert (cuerpo["total_controles_evaluados"], cuerpo["controles_aplicables"]) == (22, 22)
        assert cuerpo["puntaje_general"] == round(21 / 22 * 100, 2)

        assert (await c.get(f"/api/evaluaciones/{EVAL_ID}")).json()["estado_progreso"] == "completada"
        resumen = (await c.get(f"/api/evaluaciones/{EVAL_ID}/resumen")).json()
        assert resumen["puntaje_general"] == cuerpo["puntaje_general"]
        p = (await c.get(f"/api/evaluaciones/{EVAL_ID}/progreso")).json()
        assert p["etapa"] == "cerrada" and p["cerrada"] is True

        # Después de completar
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/completar")
        assert r.status_code == 409 and _codigo(r) == "EVALUACION_CERRADA"
        r = await c.post("/api/respuestas/", json={
            "evaluacion_id": EVAL_ID, "matriz_control_id": ID["GOB-001"],
            "estado_clasificacion": "cumplido", "justificacion": JUST})
        assert r.status_code == 409 and _codigo(r) == "EVALUACION_CERRADA"
        r = await c.put(f"/api/respuestas/{ids['DAT-001']}",
                        json={"estado_clasificacion": "no_aplica", "justificacion": ""})
        assert r.status_code == 409
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=body_filtro(True))
        assert r.status_code == 400 and "cerrada" in r.json()["detail"]
        r = await c.post(f"/api/respuestas/{ids['DAT-001']}/evidencias",
                         files={"file": ("tarde.txt", EVIDENCIA, "text/plain")})
        assert r.status_code == 409 and _codigo(r) == "EVALUACION_CERRADA"
        assert "no admite evidencias" in r.json()["detail"]["mensaje"]
        n = (await _sql('SELECT count(*) FROM evidencias e JOIN respuestas r ON r.id_respuesta = '
                        'e."Respuestas_id_respuesta" WHERE r."Evaluacion_id" = :e', e=EVAL_ID)).scalar()
        assert n == 0
    _correr(esc)


def test_evidencia_rechazada_en_evaluacion_cerrada_por_otro_estado():
    """El bloqueo de evidencias también vale para estado_progreso = 'cerrada'."""
    async def esc(c):
        ids = await _responder_base(c)
        await _sql("UPDATE evaluacion SET estado_progreso='cerrada' WHERE id=:e", e=EVAL_ID)
        r = await c.post(f"/api/respuestas/{ids['GOB-002']}/evidencias",
                         files={"file": ("x.txt", EVIDENCIA, "text/plain")})
        assert r.status_code == 409 and _codigo(r) == "EVALUACION_CERRADA"
    _correr(esc)


def test_evidencia_en_evaluacion_abierta_sigue_funcionando():
    async def esc(c):
        ids = await _responder_base(c)
        r = await c.post(f"/api/respuestas/{ids['GOB-002']}/evidencias",
                         files={"file": ("ok.txt", EVIDENCIA, "text/plain")})
        assert r.status_code == 202, r.text
    _correr(esc)


def test_con_f1_no_se_completa_sin_controles():
    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_NA_ID}/filtro", json=F1_NO)
        r = await c.post(f"/api/evaluaciones/{EVAL_NA_ID}/completar")
        assert r.status_code == 200, r.text
        assert (r.json()["controles_aplicables"], r.json()["total_controles_evaluados"]) == (0, 0)
        assert (await c.get(f"/api/evaluaciones/{EVAL_NA_ID}")).json()["estado_progreso"] == "completada"
    _correr(esc)


def test_cerrar_sigue_siendo_vista_previa_sin_cambiar_el_estado():
    async def esc(c):
        await _responder_base(c)
        assert (await c.post(f"/api/evaluaciones/{EVAL_ID}/cerrar")).status_code == 200
        assert (await c.get(f"/api/evaluaciones/{EVAL_ID}")).json()["estado_progreso"] == "en_progreso"
        assert (await c.post("/api/respuestas/", json={
            "evaluacion_id": EVAL_ID, "matriz_control_id": ID["GOB-001"],
            "estado_clasificacion": "no_aplica", "justificacion": ""})).status_code == 200
    _correr(esc)
