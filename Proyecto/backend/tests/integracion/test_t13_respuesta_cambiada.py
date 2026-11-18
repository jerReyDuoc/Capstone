"""
T-13 · No sobrescribir una respuesta que el usuario cambió mientras se revisaba su evidencia.

flujo_validacion_evidencia.py guarda el estado y la justificación de la respuesta ANTES de llamar al LLM y,
después, relee la respuesta con bloqueo. Si cambió, la clasificación del LLM no se aplica: la evidencia queda
con el aviso "Tu respuesta cambió mientras revisábamos el documento; vuelve a subirlo" y el descarte queda
en el audit log. Sin cambios, todo funciona igual que antes.

Mismo arnés que HU-02 (FastAPI + SQLite en memoria, LLM simulado).
"""
import asyncio

import pytest

pytest.importorskip("httpx")

import app.domain.models  # noqa: E402,F401
from apoyo.api_harness import EVAL_ID, MODO, cliente_api  # noqa: E402
from app.domain.evidencias.validacion_evidencia import ValidacionEvidencia  # noqa: E402

from test_hu02_matriz_estados import JUST, SOLO_BASE, _body, _filas, _sesion, _subir  # noqa: E402

solo_en_proceso = pytest.mark.skipif(MODO == "live", reason="usa la BD SQLite en memoria del arnés")
CUMP, PARC, NOC = "cumplido", "parcialmente_cumplido", "no_cumplido"
AVISO = "Tu respuesta cambió mientras revisábamos el documento; vuelve a subirlo."


def _correr(escenario):
    async def _main():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_main())


async def _procesar(evidencia_id: int, respuesta_id: int, clasificacion: str, cambio: tuple[str, str] | None):
    """Lo que hace el worker. Si `cambio` viene, el usuario guarda (estado, justificación) MIENTRAS el LLM piensa."""
    from sqlalchemy import text

    from app.application.evidencias.casos_uso.procesar_evidencia import ProcesarEvidenciaUseCase
    from app.bootstrap import crear_storage_evidencias
    from app.domain.auditoria.acciones import Accion
    from app.infrastructure.repositories.bitacora_repository import BitacoraRepository
    from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
    from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
    from app.infrastructure.security.prompt_injection.guardia_prompt import ReglasGuardiaPrompt

    class LLM:
        async def validate(self, contenido, control, respuesta, brecha=None, justificacion=None, contexto=None):
            if cambio is not None:   # el usuario cambia su respuesta en otra pestaña
                gen = await _sesion()
                otra = await gen.__anext__()
                try:
                    await otra.execute(text(
                        "UPDATE respuestas SET estado_clasificacion = :e, estado_clasificacion_final = :e, "
                        "justificacion_usuario = :j WHERE id_respuesta = :r"), {"e": cambio[0], "j": cambio[1],
                                                                                "r": respuesta_id})
                    await otra.commit()
                finally:
                    await gen.aclose()
            return ValidacionEvidencia(clasificacion=clasificacion, confianza=0.95, justificacion="decisión simulada",
                                       respalda_clasificacion_usuario=False, evidencia_suficiente=True)

    gen = await _sesion()
    s = await gen.__anext__()
    try:
        def auditar_descarte(evidencia, respuesta, detalle):   # lo mismo que inyecta el worker
            BitacoraRepository(s).registrar(
                accion=Accion.EVIDENCIA_CLASIFICACION_DESCARTADA, entidad="evidencias",
                entidad_id=evidencia.id_evidencia, actor_rol="sistema", resultado="rechazado",
                detalle={"respuesta_id": respuesta.id, "evaluacion_id": respuesta.evaluacion_id, **detalle})

        await ProcesarEvidenciaUseCase(EvidenciaRepository(s), RespuestaRepository(s), crear_storage_evidencias(),
                                     LLM(), guard=ReglasGuardiaPrompt(),
                                     auditar_descarte=auditar_descarte).execute(evidencia_id)
    finally:
        await gen.aclose()


@solo_en_proceso
def test_si_el_usuario_cambia_no_cumplido_por_cumplido_se_conserva_su_eleccion():
    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)
        rid = (await c.post("/api/respuestas/", json=_body("GOB-001", PARC))).json()["id_respuesta"]
        evidencia_id = await _subir(c, rid)
        nueva = "Ahora sí: la política está aprobada por el directorio y publicada."
        # El LLM diría "no cumplido", pero mientras revisa el usuario cambia su respuesta a "cumplido"
        await _procesar(evidencia_id, rid, NOC, cambio=(CUMP, nueva))

        d = (await c.get(f"/api/respuestas/{rid}")).json()
        assert d["estado_clasificacion"] == CUMP                       # la elección del usuario se conserva
        assert d["estado_clasificacion_final"] == CUMP                 # el LLM no la sobrescribió
        ev = d["evidencias"][0]
        assert ev["estado_validacion"] == "rejected" and ev["clasificacion_llm"] is None
        assert AVISO in ev["errores_validacion"]
        filas = await _filas("SELECT accion, entidad_id, resultado FROM audit_log WHERE accion = :a",
                             a="evidencia.clasificacion_descartada")
        assert len(filas) == 1 and filas[0][1] == evidencia_id and filas[0][2] == "rechazado"
    _correr(esc)


@solo_en_proceso
def test_si_solo_cambia_la_justificacion_tambien_se_descarta():
    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)
        rid = (await c.post("/api/respuestas/", json=_body("GOB-001", PARC))).json()["id_respuesta"]
        evidencia_id = await _subir(c, rid)
        await _procesar(evidencia_id, rid, NOC, cambio=(PARC, JUST + " Agregamos un anexo."))
        d = (await c.get(f"/api/respuestas/{rid}")).json()
        assert d["estado_clasificacion_final"] == PARC
        assert AVISO in d["evidencias"][0]["errores_validacion"]
    _correr(esc)


@solo_en_proceso
def test_sin_cambios_la_validacion_funciona_igual_que_hoy():
    async def esc(c):
        await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)
        rid = (await c.post("/api/respuestas/", json=_body("GOB-001", PARC))).json()["id_respuesta"]
        evidencia_id = await _subir(c, rid)
        await _procesar(evidencia_id, rid, NOC, cambio=None)

        d = (await c.get(f"/api/respuestas/{rid}")).json()
        ev = d["evidencias"][0]
        assert ev["clasificacion_llm"] == NOC and AVISO not in (ev["errores_validacion"] or [])
        assert ev["estado_validacion"] in ("validated", "rejected")
        assert d["estado_clasificacion"] == PARC
        assert await _filas("SELECT id FROM audit_log WHERE accion = :a", a="evidencia.clasificacion_descartada") == []
    _correr(esc)

