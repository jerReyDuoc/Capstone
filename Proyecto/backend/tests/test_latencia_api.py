"""
QA - Prueba de LATENCIA de la API REST: peticiones CRUD del diagnóstico < 500 ms.

Ejecutar desde Proyecto/backend/:

  # 1) En proceso (sin Docker): app real + SQLite en memoria + ARQ falso
  pytest tests/test_latencia_api.py -v -s

  # 2) LIVE contra PostgreSQL (prueba de ACEPTACIÓN del requisito)
  #    docker compose up -d ; alembic upgrade head
  #    uvicorn app.main:app --port 8000 --log-level warning   (otra terminal)
  LATENCIA_BASE_URL=http://127.0.0.1:8000 pytest tests/test_latencia_api.py -v -s

  En live el arnés verifica /health, crea las evaluaciones 9001 y 9002 si no
  existen y borra sus datos antes y después (ver tests/_api_harness.py).

Variables opcionales:
  LATENCIA_UMBRAL_MS       umbral en ms (defecto 500)
  LATENCIA_N               peticiones medidas por endpoint (defecto 30)
  LATENCIA_WARMUP          peticiones de calentamiento no medidas (defecto 3)
  LATENCIA_CONCURRENCIA    peticiones simultáneas por endpoint, solo live (defecto 1)
  LATENCIA_ESTRICTO=1      exige que el MÁXIMO esté bajo el umbral (defecto: p95)
  LATENCIA_UPLOAD=0/1      incluir subida de evidencias (defecto 1 en proceso, 0 live).
                           En live solo encola el job en Redis: si el worker ARQ NO
                           está corriendo, no se llama al LLM.
  LATENCIA_REPORTE=ruta    archivo .md con el reporte (defecto en live:
                           reporte_latencia_live.md)
  LATENCIA_EVALUACION_ID / LATENCIA_EVALUACION_NA_ID   (defecto live 9001 / 9002)
  LATENCIA_PREPARAR_BD=0   no tocar la BD (las evaluaciones deben existir)
  LATENCIA_CONSERVAR_DATOS=1  no borrar los datos de prueba al terminar

Criterio: para cada endpoint, todas las respuestas tienen el código HTTP
esperado y el p95 (o el máximo, en modo estricto) es < umbral.
"""
import asyncio
import math
import os
import platform
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import pytest

pytest.importorskip("httpx")

from _api_harness import (  # noqa: E402
    BASE_URL_LIVE, EVAL_ID, EVAL_NA_ID, MODO, body_filtro, cliente_api,
)

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite (o usar LATENCIA_BASE_URL)")

pytestmark = pytest.mark.latencia

UMBRAL_MS = float(os.getenv("LATENCIA_UMBRAL_MS", "500"))
N = int(os.getenv("LATENCIA_N", "30"))
WARMUP = int(os.getenv("LATENCIA_WARMUP", "3"))
ESTRICTO = os.getenv("LATENCIA_ESTRICTO") == "1"
# En proceso la BD SQLite comparte una sola conexión: no se mide concurrencia.
CONCURRENCIA = max(1, int(os.getenv("LATENCIA_CONCURRENCIA", "1"))) if MODO == "live" else 1
INCLUIR_UPLOAD = os.getenv("LATENCIA_UPLOAD", "1" if MODO == "en_proceso" else "0") == "1"
REPORTE = os.getenv("LATENCIA_REPORTE") or ("reporte_latencia_live.md" if MODO == "live" else None)

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
    # False = reescribe la MISMA evaluación (filtro, cerrar): en paralelo chocaría
    # consigo misma, algo que no hacen usuarios reales; se mide secuencial.
    concurrente: bool = True
    # Otros códigos HTTP correctos. HU-01: POST /api/respuestas es un upsert y
    # responde 200 cuando el control ya estaba respondido (la medición recorre los
    # controles más de una vez).
    otros_validos: tuple = ()

    def valido(self, codigo: int) -> bool:
        return codigo == self.esperado or codigo in self.otros_validos


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

    @property
    def media(self):
        return statistics.mean(self.tiempos_ms)


def _guardar_respuesta(r, ctx):
    if r.status_code in (200, 201):
        ctx["respuestas"].append(r.json()["id_respuesta"])


def _guardar_evidencia(r, ctx):
    if r.status_code == 202:
        ctx["evidencias"].append(r.json()["id_evidencia"])


def _control(i, ctx):
    ids = ctx["controles"]
    return ids[i % len(ids)]


def _respuesta_id(i, ctx):
    return ctx["respuestas"][i % len(ctx["respuestas"])]


OPERACIONES = [
    Op("POST filtro (crear/rehacer)", "C", "POST", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/filtro", 200,
       lambda i, c: {"json": body_filtro(True)}, concurrente=False),
    Op("GET filtro", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/filtro", 200),
    Op("GET controles aplicables", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/controles-aplicables", 200),
    Op("POST respuesta", "C", "POST", lambda i, c: "/api/respuestas/", 201,
       lambda i, c: {"json": {"evaluacion_id": EVAL_ID, "matriz_control_id": _control(i, c),
                              "estado_clasificacion": "cumplido", "justificacion": JUSTIFICACION}},
       _guardar_respuesta, otros_validos=(200,)),
    Op("GET respuesta", "R", "GET", lambda i, c: f"/api/respuestas/{_respuesta_id(i, c)}", 200),
    Op("GET respuestas de evaluación (paginado)", "R", "GET",
       lambda i, c: f"/api/evaluaciones/{EVAL_ID}/respuestas?page=1&size=50", 200),
    Op("GET evaluación", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}", 200),
    # HU-01: progreso del cuestionario (respondidos / aplicables) para reanudar
    Op("GET progreso del cuestionario", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/progreso", 200),
]
if INCLUIR_UPLOAD:
    OPERACIONES += [
        Op("POST evidencia (upload)", "C", "POST",
           lambda i, c: f"/api/respuestas/{_respuesta_id(i, c)}/evidencias", 202,
           lambda i, c: {"files": {"file": (f"evidencia_{i}.txt", EVIDENCIA, "text/plain")}},
           _guardar_evidencia),
        Op("GET evidencia", "R", "GET", lambda i, c: f"/api/evidencias/{c['evidencias'][i % len(c['evidencias'])]}", 200),
    ]
OPERACIONES += [
    Op("POST cerrar (recalcular resumen)", "U", "POST", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/cerrar", 200,
       concurrente=False),
    Op("GET resumen", "R", "GET", lambda i, c: f"/api/evaluaciones/{EVAL_ID}/resumen", 200),
    # --- Borde: evaluación con 100 % N/A ---------------------------------
    Op("POST cerrar con 100% N/A", "U", "POST", lambda i, c: f"/api/evaluaciones/{EVAL_NA_ID}/cerrar", 200,
       concurrente=False),
    # Sin controles evaluables no se crean filas Resumen => la API responde 404.
    Op("GET resumen con 100% N/A (404 esperado)", "R", "GET",
       lambda i, c: f"/api/evaluaciones/{EVAL_NA_ID}/resumen", 404),
]

# Operaciones con un defecto conocido sin corregir: {nombre: motivo}. Se marcan xfail.
DEFECTOS_CONOCIDOS: dict[str, str] = {}

ARRANQUE_FRIO_MS: list[float] = []


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


async def _una(c, op, i, ctx):
    t0 = time.perf_counter()
    r = await c.request(op.metodo, op.ruta(i, ctx), **op.kwargs(i, ctx))
    ms = (time.perf_counter() - t0) * 1000
    if op.al_responder:
        op.al_responder(r, ctx)
    return ms, r.status_code


async def _medir_op(c, op, ctx) -> Medicion:
    med = Medicion()
    k = CONCURRENCIA if op.concurrente else 1
    # Calentamiento con la MISMA concurrencia que la medición: así las conexiones
    # nuevas (cliente HTTP y pool de BD del servidor) no se cuentan como latencia.
    w = WARMUP * k
    for inicio in range(0, w, k):
        await asyncio.gather(*(_una(c, op, j, ctx) for j in range(inicio, min(inicio + k, w))))
    i = w
    while i < w + N:                              # medición en lotes concurrentes
        lote = range(i, min(i + k, w + N))
        for ms, codigo in await asyncio.gather(*(_una(c, op, j, ctx) for j in lote)):
            med.tiempos_ms.append(ms)
            med.codigos.append(codigo)
        i += len(lote)
    return med


async def _medir_todo() -> dict[str, Medicion]:
    resultados: dict[str, Medicion] = {}
    async with cliente_api() as c:
        ctx = {"respuestas": [], "evidencias": [], "controles": []}

        # Preparación (no medida)
        r = await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=body_filtro(True))
        assert r.status_code == 200, f"No se pudo preparar el filtro de la evaluación {EVAL_ID}: {r.text}"
        controles = (await c.get(f"/api/evaluaciones/{EVAL_ID}/controles-aplicables")).json()
        ctx["controles"] = [x["id_control"] for x in controles]
        assert ctx["controles"], "No hay controles aplicables: ¿faltan las semillas/migraciones?"
        ctx["n_controles_na"] = await _preparar_evaluacion_na(c)

        # Arranque en frío: el primer lote concurrente abre conexiones nuevas
        # (HTTP y pool de PostgreSQL del servidor). Se mide aparte, solo informativo.
        if CONCURRENCIA > 1:
            for ronda in range(2):
                t0 = time.perf_counter()
                await asyncio.gather(*(c.get(f"/api/evaluaciones/{EVAL_ID}") for _ in range(CONCURRENCIA)))
                if ronda == 0:
                    ARRANQUE_FRIO_MS.append((time.perf_counter() - t0) * 1000)

        for op in OPERACIONES:
            resultados[op.nombre] = await _medir_op(c, op, ctx)

    _reportar(resultados)
    return resultados


def _cumple(op: Op, m: Medicion) -> bool:
    valor = m.maximo if ESTRICTO else m.p(.95)
    return all(op.valido(x) for x in m.codigos) and valor < UMBRAL_MS


def _reportar(res: dict[str, Medicion]):
    criterio = "máximo" if ESTRICTO else "p95"
    destino = BASE_URL_LIVE if MODO == "live" else "en proceso (SQLite en memoria)"
    ops = {op.nombre: op for op in OPERACIONES}
    total_ok = sum(_cumple(ops[n], m) for n, m in res.items())

    lineas = [
        "# Reporte de latencia - API REST diagnóstico",
        "",
        f"- **Fecha:** {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- **Modo:** {MODO} — {destino}",
        f"- **Requisito:** {criterio} < {UMBRAL_MS:.0f} ms por endpoint",
        f"- **Muestras:** {N} medidas por endpoint + {WARMUP} lote(s) de calentamiento "
        f"con la misma concurrencia; concurrencia {CONCURRENCIA} (filtro y cerrar, secuenciales)",
        f"- **Subida de evidencias incluida:** {'sí' if INCLUIR_UPLOAD else 'no'}",
        f"- **Cliente:** Python {platform.python_version()} en {platform.system()} {platform.release()}",
        f"- **Resultado:** {total_ok}/{len(res)} endpoints cumplen",
        *([f"- **Arranque en frío (informativo, no evaluado):** primer lote de {CONCURRENCIA} "
           f"peticiones simultáneas tras abrir conexiones = {ARRANQUE_FRIO_MS[0]:.0f} ms"]
          if ARRANQUE_FRIO_MS else []),
        "",
        "| CRUD | Endpoint | Conc. | p50 (ms) | p95 (ms) | máx (ms) | media (ms) | HTTP | Cumple |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for nombre, m in res.items():
        op = ops[nombre]
        codigos = ",".join(sorted({str(x) for x in m.codigos}))
        lineas.append(
            f"| {op.crud} | {nombre} | {CONCURRENCIA if op.concurrente else 1} | {m.p(.5):.1f} | {m.p(.95):.1f} | {m.maximo:.1f} | "
            f"{m.media:.1f} | {codigos} | {'✅' if _cumple(op, m) else '❌'} |"
        )
    texto = "\n".join(lineas) + "\n"
    print("\n" + texto)
    if REPORTE:
        with open(REPORTE, "w", encoding="utf-8") as f:
            f.write(texto)
        print(f"Reporte guardado en: {os.path.abspath(REPORTE)}")


@pytest.fixture(scope="module")
def mediciones(bd_live):
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
    incorrectos = [x for x in m.codigos if not op.valido(x)]
    assert not incorrectos, f"{op.nombre}: esperaba HTTP {op.esperado}, recibió {sorted(set(incorrectos))}"

    valor = m.maximo if ESTRICTO else m.p(.95)
    etiqueta = "máx" if ESTRICTO else "p95"
    assert valor < UMBRAL_MS, (
        f"{op.nombre}: {etiqueta}={valor:.1f} ms >= {UMBRAL_MS:.0f} ms "
        f"(p50={m.p(.5):.1f}, máx={m.maximo:.1f}, "
        f"concurrencia={CONCURRENCIA if op.concurrente else 1})"
    )
