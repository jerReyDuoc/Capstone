"""
PRUEBA EN EL SISTEMA REAL: API uvicorn + worker ARQ + PostgreSQL + Redis + Groq + spaCy.

A diferencia de test_e2e_capa_ia.py (todo en proceso), aquí NO se simula nada:
las peticiones van por HTTP al servidor real, el worker real toma el job desde
Redis, llama a Groq de verdad y todo queda escrito en PostgreSQL. La prueba
observa el sistema desde fuera (API + consultas a la BD), como lo haría un auditor.

Se SALTA si no defines LIVE_BASE_URL, así no afecta `pytest tests`.

Preparación (4 terminales, desde Proyecto/backend con el venv activado):
  1) docker compose up -d                       (PostgreSQL + Redis)
     alembic upgrade head                       (tablas llamadas_llm y sanitizaciones)
  2) uvicorn app.main:app --port 8000
  3) arq app.worker.tasks.WorkerSettings        (debe arrancar sin error: carga spaCy)
  4) PowerShell:  $env:LIVE_BASE_URL="http://127.0.0.1:8000"
                  pytest tests/test_live_capa_ia.py -v -s
     cmd:         set LIVE_BASE_URL=http://127.0.0.1:8000 && pytest tests/test_live_capa_ia.py -v -s

El .env de backend/ debe tener GROQ_API_KEY válida, SANITIZER_ENABLED=true y
ENTITY_MAP_KEY. La prueba lee DATABASE_URL y ENTITY_MAP_KEY desde ese .env (o desde
LIVE_DATABASE_URL / LIVE_ENTITY_MAP_KEY si los defines).

Datos: usa una evaluación dedicada (LIVE_EVALUACION_ID, por defecto 9101). Al INICIO
borra lo que haya quedado de corridas anteriores de esa evaluación; al final deja
los datos en la BD para que puedas revisarlos (LIVE_LIMPIAR_AL_FINAL=1 los borra).
Costo: 1 llamada a Groq por corrida.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BASE_URL = (os.getenv("LIVE_BASE_URL") or "").rstrip("/")
if not BASE_URL:
    pytest.skip("Prueba en vivo: define LIVE_BASE_URL (p. ej. http://127.0.0.1:8000)", allow_module_level=True)

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.infrastructure.security.cifrado import CifradorEntidades  # noqa: E402
from test_e2e_capa_ia import ACTA, INYECCION, JUSTIFICACION, PII, PII_VARIANTES, paso  # noqa: E402

EVAL_ID = int(os.getenv("LIVE_EVALUACION_ID", "9101"))
TIMEOUT_S = float(os.getenv("LIVE_TIMEOUT_S", "120"))
LIMPIAR_AL_FINAL = os.getenv("LIVE_LIMPIAR_AL_FINAL") == "1"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ESTADOS_FINALES = {"validated", "rejected", "error"}


# ---------------------------------------------------------------- configuración real
def _desde_env_file(clave: str) -> str | None:
    """Lee backend/.env (el mismo que usan la API y el worker). No se usa os.environ
    porque conftest.py define valores de prueba para DATABASE_URL y ENTITY_MAP_KEY."""
    archivo = BACKEND_DIR / ".env"
    if not archivo.exists():
        return None
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea.startswith(f"{clave}="):
            return linea.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _config(clave: str) -> str:
    valor = os.getenv(f"LIVE_{clave}") or _desde_env_file(clave)
    if not valor:
        pytest.fail(f"Falta {clave}: defínelo en backend/.env o como LIVE_{clave}.", pytrace=False)
    return valor


# ---------------------------------------------------------------- BD
_FILTRO_EVAL = (
    '"Evaluacion_id" = :e OR "Respuestas_id_respuesta" IN '
    '(SELECT id_respuesta FROM respuestas WHERE "Evaluacion_id" = :e)'
)
_SQL_LIMPIAR = [  # orden respetando claves foráneas
    f"DELETE FROM sanitizaciones WHERE {_FILTRO_EVAL}",
    f"DELETE FROM llamadas_llm WHERE {_FILTRO_EVAL}",
    f"DELETE FROM eventos_seguridad WHERE {_FILTRO_EVAL}",
    'DELETE FROM evidencias WHERE "Respuestas_id_respuesta" IN '
    '(SELECT id_respuesta FROM respuestas WHERE "Evaluacion_id" = :e)',
    'DELETE FROM resumen WHERE "Evaluacion_id" = :e',
    'DELETE FROM respuestas WHERE "Evaluacion_id" = :e',
    'DELETE FROM respuestas_filtro WHERE "Evaluacion_id" = :e',
]


class BD:
    def __init__(self, url: str):
        self.engine = create_async_engine(url, pool_pre_ping=True)

    async def filas(self, sql: str, **params) -> list[dict]:
        async with self.engine.connect() as c:
            return [dict(r._mapping) for r in (await c.execute(text(sql), params)).all()]

    async def preparar(self):
        async with self.engine.begin() as c:
            for tabla in ("llamadas_llm", "sanitizaciones"):
                if (await c.execute(text("SELECT to_regclass(:t)"), {"t": tabla})).scalar() is None:
                    pytest.fail(f"No existe la tabla {tabla}: ejecuta 'alembic upgrade head'.", pytrace=False)
            if not (await c.execute(text("SELECT count(*) FROM matriz_controles"))).scalar():
                pytest.fail("matriz_controles está vacía: ejecuta 'alembic upgrade head'.", pytrace=False)
            await c.execute(text(
                "INSERT INTO evaluacion (id, fecha_inicio, estado_progreso, filtro_completado) "
                "VALUES (:e, CURRENT_DATE, 'en_progreso', false) ON CONFLICT (id) DO NOTHING"), {"e": EVAL_ID})
        await self.limpiar()

    async def limpiar(self):
        async with self.engine.begin() as c:
            rutas = (await c.execute(text(
                'SELECT storage_path FROM evidencias WHERE "Respuestas_id_respuesta" IN '
                '(SELECT id_respuesta FROM respuestas WHERE "Evaluacion_id" = :e)'), {"e": EVAL_ID})).scalars().all()
            for sql in _SQL_LIMPIAR:
                await c.execute(text(sql), {"e": EVAL_ID})
        for ruta in rutas:  # archivos subidos en corridas anteriores
            p = Path(ruta) if Path(ruta).is_absolute() else BACKEND_DIR / ruta
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------- API
class API:
    def __init__(self, client: httpx.AsyncClient):
        self.c = client

    async def verificar(self):
        try:
            r = await self.c.get("/health")
            assert r.status_code == 200
        except Exception as e:  # noqa: BLE001
            pytest.fail(f"La API no responde en {BASE_URL}/health ({e}). "
                        "Levántala con: uvicorn app.main:app --port 8000", pytrace=False)

    async def responder(self, control_id: int, justificacion: str, estado: str = "cumplido") -> int:
        r = await self.c.post("/api/respuestas/", json={
            "evaluacion_id": EVAL_ID, "matriz_control_id": control_id,
            "estado_clasificacion": estado, "justificacion": justificacion,
        })
        assert r.status_code == 201, r.text
        return r.json()["id_respuesta"]

    async def subir(self, respuesta_id: int, contenido: bytes, nombre: str) -> int:
        r = await self.c.post(f"/api/respuestas/{respuesta_id}/evidencias",
                              files={"file": (nombre, contenido, "text/plain")})
        assert r.status_code == 202, r.text
        return r.json()["id_evidencia"]

    async def esperar_worker(self, evidencia_id: int) -> dict:
        """Espera a que el worker real procese el job (polling a la API)."""
        inicio, estado = time.monotonic(), None
        while time.monotonic() - inicio < TIMEOUT_S:
            ev = (await self.c.get(f"/api/evidencias/{evidencia_id}")).json()
            if ev["estado_validacion"] != estado:
                estado = ev["estado_validacion"]
                print(f"    [{time.monotonic() - inicio:5.1f}s] evidencia {evidencia_id}: {estado}")
            if estado in ESTADOS_FINALES:
                return ev
            await asyncio.sleep(0.5)
        pista = ("sigue 'pending': ¿está corriendo 'arq app.worker.tasks.WorkerSettings'? "
                 "¿apunta al mismo REDIS_URL que la API?" if estado == "pending"
                 else "quedó en 'processing': revisa el log del worker (puede haberse caído).")
        pytest.fail(f"El worker no terminó en {TIMEOUT_S:.0f}s: la evidencia {pista}", pytrace=False)


# =====================================================================
def test_live_sistema_real_con_capa_de_politicas_e_ia():
    asyncio.run(_live())


async def _live():
    bd = BD(_config("DATABASE_URL"))
    cifrador = CifradorEntidades(_config("ENTITY_MAP_KEY"))
    t0 = (datetime.now(timezone.utc) - timedelta(seconds=2)).replace(tzinfo=None)

    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            api = API(client)
            await api.verificar()
            await bd.preparar()
            # HU-01: solo se responden controles aplicables según el filtro F1–F7
            r = await client.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json={"respuestas": [
                {"codigo": f"F{i}", "respuesta": True} for i in range(1, 8)]})
            assert r.status_code == 200, r.text
            controles = [r["id_control"] for r in await bd.filas(
                "SELECT id_control FROM matriz_controles ORDER BY id_control LIMIT 3")]
            print(f"\n{'=' * 70}\nPRUEBA EN VIVO  |  API {BASE_URL}  |  evaluación {EVAL_ID}\n{'=' * 70}")

            # ------------------------------------------------ 1. evidencia con datos personales
            r1 = await api.responder(controles[0], JUSTIFICACION)
            ev1_id = await api.subir(r1, ACTA, "acta_designacion_dpo.txt")
            paso("1. Acta con PII subida por la API; esperando al worker",
                 respuesta=r1, evidencia=ev1_id)
            ev1 = await api.esperar_worker(ev1_id)

            if ev1["estado_validacion"] == "error":
                errores = ev1["errores_validacion"]
                pistas = {
                    "[sanitizacion]": "el worker no pudo cargar spaCy/es_core_news_md (o falló el NER)",
                    "[auditoria]": "el worker no pudo guardar el mapa (¿ENTITY_MAP_KEY en el .env del worker?)",
                    "[autenticacion]": "GROQ_API_KEY inválida",
                    "[rate_limit]": "Groq limitó la cuenta; reintenta en un minuto",
                }
                pista = next((v for k, v in pistas.items() if errores and errores[0].startswith(k)), "")
                pytest.fail(f"La evidencia terminó en error: {errores}. {pista}", pytrace=False)

            paso("   resultado de la validación",
                 estado=ev1["estado_validacion"], clasificacion_llm=ev1["clasificacion_llm"],
                 confianza=ev1["confianza"], justificacion_llm=(ev1["justificacion_llm"] or "")[:300])

            # R1 observable desde fuera: el LLM solo pudo repetir PII si la hubiera recibido
            salida_llm = json.dumps(
                [ev1["justificacion_llm"], ev1["datos_extraidos"], ev1["errores_validacion"]], ensure_ascii=False)
            fugas = [v for v in list(PII.values()) + PII_VARIANTES if v in salida_llm]
            assert not fugas, f"El LLM devolvió datos personales que no debería haber visto: {fugas}"

            # R2: mapa de entidades en PostgreSQL, cifrado
            sans = await bd.filas(
                'SELECT campo, traza_id, motor, total_entidades, conteo_por_tipo, entidades, mapa_cifrado '
                'FROM sanitizaciones WHERE "Evidencias_id_evidencia" = :ev ORDER BY campo', ev=ev1_id)
            assert {s["campo"] for s in sans} == {"evidencia", "justificacion"}, sans
            san_ev = next(s for s in sans if s["campo"] == "evidencia")
            conteo = _json(san_ev["conteo_por_tipo"])
            en_claro = json.dumps(_json(san_ev["entidades"]), ensure_ascii=False) + (san_ev["mapa_cifrado"] or "")
            assert not any(v in en_claro for v in PII.values()), "Hay PII en claro en la tabla sanitizaciones"
            mapa = cifrador.descifrar_json(san_ev["mapa_cifrado"])
            valores = {e["valor"] for e in mapa}
            no_detectados = [k for k in ("rut", "correo", "telefono", "nombre_encargado", "nombre_presidenta")
                             if not any(PII[k] in v for v in valores)]
            assert not no_detectados, f"El motor NER real no detectó: {no_detectados}"
            assert any("1234, oficina 501" in v for v in valores), "La dirección no incluyó el número de oficina"
            assert "spacy" in san_ev["motor"]
            paso("   sanitizaciones (PostgreSQL)", motor=san_ev["motor"], por_tipo=conteo,
                 mapa_descifrado=[(e["tipo"], e["valor"]) for e in mapa])

            # R4/métrica: la llamada real a Groq quedó registrada
            llamadas = await bd.filas(
                'SELECT * FROM llamadas_llm WHERE "Evidencias_id_evidencia" = :ev', ev=ev1_id)
            assert len(llamadas) == 1, llamadas
            m = llamadas[0]
            assert m["exito"] is True and m["tipo_error"] is None
            assert m["sanitizado"] is True, "El worker corre con SANITIZER_ENABLED=false"
            assert m["traza_id"] == san_ev["traza_id"]
            assert m["entidades_anonimizadas"] == sum(s["total_entidades"] for s in sans)
            assert m["tokens_entrada"] and m["tokens_salida"]
            assert m["clasificacion"] == ev1["clasificacion_llm"]
            paso("   llamadas_llm (PostgreSQL)", proveedor=m["proveedor"], modelo=m["modelo"],
                 prompt=m["prompt_version"], tokens=f"{m['tokens_entrada']} in / {m['tokens_salida']} out",
                 latencia_ms=m["latencia_ms"], costo_usd=m["costo_estimado_usd"], traza=m["traza_id"])

            # Decisión del backend coherente con la confianza del LLM
            resp1 = (await client.get(f"/api/respuestas/{r1}")).json()
            esperado = "llm" if ev1["estado_validacion"] == "validated" else "usuario"
            assert resp1["fuente_clasificacion"] == esperado, resp1
            paso("   decisión del backend", estado_final=resp1["estado_clasificacion_final"],
                 fuente=resp1["fuente_clasificacion"])

            # ------------------------------------------------ 2. prompt injection
            r2 = await api.responder(controles[1], "Contamos con una política de gobernanza aprobada.")
            ev2_id = await api.subir(r2, INYECCION, "politica_gobernanza.txt")
            paso("2. Evidencia con prompt injection; esperando al worker", evidencia=ev2_id)
            ev2 = await api.esperar_worker(ev2_id)
            resp2 = (await client.get(f"/api/respuestas/{r2}")).json()
            eventos = await bd.filas(
                'SELECT id_evento, origen, extracto FROM eventos_seguridad WHERE "Evidencias_id_evidencia" = :ev',
                ev=ev2_id)
            assert ev2["estado_validacion"] == "rejected"
            assert resp2["estado_clasificacion_final"] == "requiere_revision"
            assert len(eventos) == 1 and eventos[0]["origen"] == "evidencia"
            assert await bd.filas('SELECT 1 FROM llamadas_llm WHERE "Evidencias_id_evidencia" = :ev', ev=ev2_id) == []
            paso("   bloqueada antes de la capa de IA", estado=ev2["estado_validacion"],
                 respuesta=resp2["estado_clasificacion_final"], evento=eventos[0]["id_evento"],
                 llamadas_al_llm=0)

            # ------------------------------------------------ 3. revisión humana
            r = await client.patch(f"/api/respuestas/{r1}/revision",
                                   json={"clasificacion_revisada": "parcialmente_cumplido"})
            assert r.status_code == 200, r.text
            fila = (await bd.filas('SELECT clasificacion_revisada, fuente_clasificacion FROM respuestas '
                                   'WHERE id_respuesta = :r', r=r1))[0]
            assert fila == {"clasificacion_revisada": "parcialmente_cumplido", "fuente_clasificacion": "revision"}
            paso("3. Revisión del Oficial de Cumplimiento guardada", **fila)

            # "parcialmente_cumplido" (21 caracteres) debe caber en la BD real:
            # SQLite no valida el largo de VARCHAR, PostgreSQL sí (migración d8b3e6f2a914).
            r3 = await api.responder(controles[2], "Avance parcial del inventario de modelos.",
                                     estado="parcialmente_cumplido")
            fila3 = (await bd.filas('SELECT estado_clasificacion FROM respuestas WHERE id_respuesta = :r', r=r3))[0]
            assert fila3["estado_clasificacion"] == "parcialmente_cumplido"

            # ------------------------------------------------ 4. métricas
            met = (await client.get("/api/ia/metricas", params={"desde": t0.isoformat()})).json()
            op, prec, san = met["operacion_modelo"], met["precision_modelo"], met["sanitizacion"]
            assert op["total_llamadas"] >= 1 and op["exitosas"] >= 1
            assert op["llamadas_sin_sanitizar"] == 0
            assert prec["n_revisadas"] >= 1
            assert san["textos_sanitizados"] >= 2
            paso("4. GET /api/ia/metricas (desde el inicio de la prueba)",
                 llamadas=op["total_llamadas"], tasa_error=op["tasa_error"],
                 latencia_p50=op["latencia_ms"]["p50"], tokens=op["tokens"],
                 costo_usd=op["costo_estimado_usd"],
                 precision=f"n={prec['n_revisadas']} accuracy={prec['accuracy']}",
                 entidades=san["entidades_por_tipo"])

            print(f"\n{'=' * 70}\nOK. Revisa los datos en PostgreSQL, por ejemplo:\n"
                  f'  SELECT * FROM llamadas_llm WHERE "Evaluacion_id" = {EVAL_ID};\n'
                  f'  SELECT campo, conteo_por_tipo, entidades FROM sanitizaciones WHERE "Evaluacion_id" = {EVAL_ID};\n'
                  f"{'=' * 70}")
    finally:
        if LIMPIAR_AL_FINAL:
            await bd.limpiar()
        await bd.engine.dispose()


def _json(valor):
    return json.loads(valor) if isinstance(valor, str) else valor
