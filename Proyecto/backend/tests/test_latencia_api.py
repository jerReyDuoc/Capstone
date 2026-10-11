"""
QA - Prueba de LATENCIA de la API REST: peticiones CRUD del diagnóstico < 500 ms.

Ejecutar desde Proyecto/backend/:

  # 1) En proceso (sin Docker): app real + SQLite en memoria + ARQ falso
  pytest tests/test_latencia_api.py -v -s

  # 2) Live, contra el servidor real (prueba de ACEPTACIÓN del requisito)
  #    docker compose up -d ; alembic upgrade head ; uvicorn app.main:app
  #    Usar una BD de PRUEBAS: se reescribe el filtro y se agregan respuestas
  #    a las evaluaciones indicadas.
  LATENCIA_BASE_URL=http://127.0.0.1:8000 \
  LATENCIA_EVALUACION_ID=1 LATENCIA_EVALUACION_NA_ID=2 \
  pytest tests/test_latencia_api.py -v -s

Variables opcionales:
  LATENCIA_UMBRAL_MS   umbral en ms (defecto 500)
  LATENCIA_N           peticiones medidas por endpoint (defecto 30)
  LATENCIA_WARMUP      peticiones de calentamiento no medidas (defecto 3)
  LATENCIA_ESTRICTO=1  exige que TODAS las peticiones (máx.) estén bajo el umbral;
                       por defecto se exige el p95.
  LATENCIA_UPLOAD=0/1  incluir subida de evidencias (defecto 1 en proceso, 0 live,
                       porque en live encola un job real que llama al LLM).

Criterio: para cada endpoint, todas las respuestas tienen el código HTTP
esperado y el p95 (o el máximo, en modo estricto) es < umbral.
"""
import asyncio
import math
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable

import pytest

pytest.importorskip("httpx")

from _api_harness import (  # noqa: E402
    EVAL_ID, EVAL_NA_ID, MODO, body_filtro, cliente_api,
)

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite (o usar LATENCIA_BASE_URL)")

pytestmark = pytest.mark.latencia

UMBRAL_MS = float(os.getenv("LATENCIA_UMBRAL_MS", "500"))
N = int(os.getenv("LATENCIA_N", "30"))
WARMUP = int(os.getenv("LATENCIA_WARMUP", "3"))
ESTRICTO = os.getenv("LATENCIA_ESTRICTO") == "1"
INCLUIR_UPLOAD = os.getenv("LATENCIA_UPLOAD", "1" if MODO == "en_proceso" else "0") == "1"

JUSTIFICACION = "Contamos con una política de IA aprobada por el directorio en marzo de 2025."
EVIDENCIA = "Política de uso responsable de IA v2. Aprobada por el directorio. Revisión anual.".encode()


@dataclass
class Op:
    nombre: str
    crud: str
    metodo: str
    ruta: Callable[[int, dict], str]
    esperado: int
    kwargs: Callable[[int, dict], dict] = lambda i, ctx: {}
    al_responder: Callable[[object, dict], None] | None = None


@dataclass
class Medicion:
    tiempos_ms: list = field(default_factory=list)
    codigos: list = field(default_factory=list)

    def p(self, q):
        orden = sorted(self.tiempos_ms)
        return orden[max(0, math.ceil(q * len(orden)) - 1)]

    @property
    def maximo(self):
        return max(self.tiempos_ms)


def _guardar_respuesta(r, ctx):
    if r.status_code == 201:
        ctx["respuestas"].append(r.json()["id_respuesta"])


def _guardar_evidencia(r, ctx):
    if r.status_code == 202:
        ctx["evidencias"].append(r.json()["id_evidencia"])


def _control(i, ctx):
    ids = ctx["controles"]
    return ids[i % len(ids)]


OPERACIONES = [
    Op("POST filtro (crear/rehacer)", "C", "POST", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/filtro", 200,
       lambda i, c: {"json": body_filtro(True)}),
    Op("GET filtro", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/filtro", 200),
    Op("GET controles aplicables", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/controles-aplicables", 200),
    Op("POST respuesta", "C", "POST", lambda i, c: "/api/respuestas/", 201,
       lambda i, c: {"json": {"evaluacion_id": EVAL_ID, "matriz_control_id": _control(i, c),
                              "estado_clasificacion": "cumplido", "justificacion": JUSTIFICACION}},
       _guardar_respuesta),
    Op("GET respuesta", "R", "GET", lambda i, c: f"/api/respuestas/{c['respuestas'][i % len(c['respuestas'])]}", 200),
    Op("GET respuestas de evaluación (paginado)", "R", "GET",
       lambda i, c: f"/api/evaluaciones/{EVAL_ID}/respuestas?page=1&size=50", 200),
    Op("GET evaluación", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}", 200),
]
if INCLUIR_UPLOAD:
    OPERACIONES += [
        Op("POST evidencia (upload)", "C", "POST",
           lambda i, c: f"/api/respuestas/{c['respuestas'][i % len(c['respuestas'])]}/evidencias", 202,
           lambda i, c: {"files": {"file": (f"evidencia_{i}.txt", EVIDENCIA, "text/plain")}},
           _guardar_evidencia),
        Op("GET evidencia", "R", "GET", lambda i, c: f"/api/evidencias/{c['evidencias'][i % len(c['evidencias'])]}", 200),
    ]
OPERACIONES += [
    Op("POST cerrar (recalcular resumen)", "U", "POST", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/cerrar", 200),
    Op("GET resumen", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/resumen", 200),
    # --- Borde: evaluación con 100 % N/A ---------------------------------
    Op("POST cerrar con 100% N/A", "U", "POST", lambda i, c: f"/api/evaluaciones/{EVAL_NA_ID}/cerrar", 200),
    # Sin controles evaluables no se crean filas Resumen => la API responde 404.
    Op("GET resumen con 100% N/A (404 esperado)", "R", "GET",
       lambda i, c: f"/api/evaluaciones/{EVAL_NA_ID}/resumen", 404),
]

DEFECTOS_CONOCIDOS = {
    "GET respuestas de evaluación (paginado)": (
        "DEFECTO: RespuestaResumenResponse pide 'id_respuesta' pero el modelo Respuesta "
        "expone el atributo 'id' (columna id_respuesta). model_validate falla y el "
        "endpoint responde 500 en cuanto la evaluación tiene al menos una respuesta."
    ),
}


async def _preparar_evaluacion_na(c):
    """Filtro con todo SI y una respuesta 'no_aplica' para cada control aplicable."""
    r = await c.post(f"/api/evaluaciones/{EVAL_NA_ID}/filtro", json=body_filtro(True))
    assert r.status_code == 200, r.text
    controles = (await c.get(f"/api/evaluaciones/{EVAL_NA_ID}/controles-aplicables")).json()
    for ctrl in controles:
        r = await c.post("/api/respuestas/", json={
            "evaluacion_id": EVAL_NA_ID, "matriz_control_id": ctrl["id_control"],
            "estado_clasificacion": "no_aplica", "justificacion": "",
        })
        assert r.status_code == 201, r.text
    return len(controles)


async def _medir_todo() -> dict[str, Medicion]:
    resultados: dict[str, Medicion] = {}
    async with cliente_api() as c:
        ctx = {"respuestas": [], "evidencias": [], "controles": []}

        # Preparación (no medida)
        assert (await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=body_filtro(True))).status_code == 200
        controles = (await c.get(f"/api/evaluaciones/{EVAL_ID}/controles-aplicables")).json()
        ctx["controles"] = [x["id_control"] for x in controles]
        assert ctx["controles"], "No hay controles aplicables: ¿faltan las semillas/migraciones?"
        ctx["n_controles_na"] = await _preparar_evaluacion_na(c)

        for op in OPERACIONES:
            med = Medicion()
            for i in range(WARMUP + N):
                t0 = time.perf_counter()
                r = await c.request(op.metodo, op.ruta(i, ctx), **op.kwargs(i, ctx))
                ms = (time.perf_counter() - t0) * 1000
                if op.al_responder:
                    op.al_responder(r, ctx)
                if i >= WARMUP:
                    med.tiempos_ms.append(ms)
                    med.codigos.append(r.status_code)
            resultados[op.nombre] = med

    _imprimir(resultados)
    return resultados


def _imprimir(res: dict[str, Medicion]):
    filas = [f"\nLatencia API ({MODO}) - n={N}, umbral={UMBRAL_MS:.0f} ms, criterio={'máx' if ESTRICTO else 'p95'}",
             f"{'Endpoint':45} {'p50':>8} {'p95':>8} {'máx':>8} {'media':>8}  códigos"]
    for nombre, m in res.items():
        codigos = ",".join(sorted({str(x) for x in m.codigos}))
        filas.append(f"{nombre:45} {m.p(.5):8.1f} {m.p(.95):8.1f} {m.maximo:8.1f} "
                     f"{statistics.mean(m.tiempos_ms):8.1f}  {codigos}")
    texto = "\n".join(filas)
    print(texto)
    if os.getenv("LATENCIA_REPORTE"):
        with open(os.getenv("LATENCIA_REPORTE"), "w", encoding="utf-8") as f:
            f.write(texto + "\n")


@pytest.fixture(scope="module")
def mediciones():
    return asyncio.run(_medir_todo())


def _params():
    for op in OPERACIONES:
        marcas = []
        if op.nombre in DEFECTOS_CONOCIDOS:
            marcas.append(pytest.mark.xfail(strict=True, reason=DEFECTOS_CONOCIDOS[op.nombre]))
        yield pytest.param(op, id=f"{op.crud}-{op.nombre}", marks=marcas)


@pytest.mark.parametrize("op", list(_params()))
def test_endpoint_responde_bajo_umbral(mediciones, op):
    m = mediciones[op.nombre]
    incorrectos = [x for x in m.codigos if x != op.esperado]
    assert not incorrectos, f"{op.nombre}: esperaba HTTP {op.esperado}, recibió {sorted(set(incorrectos))}"

    valor = m.maximo if ESTRICTO else m.p(.95)
    etiqueta = "máx" if ESTRICTO else "p95"
    assert valor < UMBRAL_MS, (
        f"{op.nombre}: {etiqueta}={valor:.1f} ms >= {UMBRAL_MS:.0f} ms "
        f"(p50={m.p(.5):.1f}, máx={m.maximo:.1f})"
    )
