"""
QA - HU-29: historial de evaluaciones, reevaluación desde la cuenta y "Mis documentos".

  C1  "Mis evaluaciones" con todas las evaluaciones de la empresa, incluidas las migradas:
      fecha, estado, puntaje global y nivel, con la evolución global y por dimensión.
  C2  Una evaluación nueva iniciada desde la cuenta pertenece a la empresa, sin usuario
      temporal. Para el benchmark solo cuenta la evaluación más reciente de cada empresa.
  C3  "Mis documentos" con informes PDF, borradores (HU-16), evidencias y constancias
      (HU-26), con descarga y eliminación. Cada eliminación queda en el audit log.

Parte 1: lógica pura (app/application/informes/historial.py); corre sin BD ni FastAPI.
Parte 2: API en proceso (SQLite), reutiliza la preparación de test_hu27_empresa_cliente.py;
necesita FastAPI, SQLAlchemy y aiosqlite (Docker).

Ejecutar desde Proyecto/backend/:
    pytest tests/test_hu29_historial_documentos.py -v
"""
import asyncio
from datetime import date, datetime

import pytest

from app.application.informes.historial import (
    DimensionFila as D,
    EvaluacionFila as E,
    construir_historial,
    evaluaciones_para_benchmark,
    mediana,
    puntaje_global,
)


# ===================================================================== parte 1: lógica pura
def _ev(id_, estado="completada", origen="publica", dims=((1, "Datos", 40.0, 4), (2, "Gobernanza", 60.0, 6)),
        inicio=date(2026, 10, 1), completado=None, migracion=None):
    return E(id=id_, origen=origen, estado=estado, fecha_inicio=inicio, fecha_completado=completado,
             fecha_migracion=migracion, dimensiones=tuple(D(*d) for d in dims))


def test_puntaje_global_ponderado_por_controles_como_el_resumen():
    assert puntaje_global([D(1, "A", 40.0, 4), D(2, "B", 60.0, 6)]) == 52.0
    assert puntaje_global([D(1, "A", 40.0, 0), D(2, "B", 60.0, None)]) == 50.0   # sin controles: promedio simple
    assert puntaje_global([]) is None


def test_historial_con_migrada_y_reevaluaciones():
    migrada = _ev(10, migracion=datetime(2026, 10, 5, 12))
    reev = _ev(15, origen="empresa", dims=((1, "Datos", 70.0, 4), (2, "Gobernanza", 80.0, 6)),
               inicio=date(2026, 10, 20), completado=datetime(2026, 10, 22, 9, 30))
    en_curso = _ev(18, estado="en_progreso", origen="empresa", dims=((1, "Datos", 99.0, 4),),
                   inicio=date(2026, 10, 28))
    h = construir_historial([reev, en_curso, migrada])   # el orden de entrada no importa

    # Tabla: de la más reciente a la más antigua, todas (también la migrada y la en curso)
    assert [e["id"] for e in h["evaluaciones"]] == [18, 15, 10]
    abierta, nueva, vieja = h["evaluaciones"]
    assert (vieja["tipo"], vieja["fecha"], vieja["puntaje_global"]) == ("migrada", "2026-10-01", 52.0)
    assert vieja["nivel"] == {"codigo": "gestionado", "etiqueta": "Gestionado"} and vieja["variacion"] is None
    assert (nueva["tipo"], nueva["fecha"], nueva["puntaje_global"]) == ("reevaluacion", "2026-10-22", 76.0)
    assert nueva["nivel"]["codigo"] == "optimizado" and nueva["variacion"] == 24.0 and nueva["vigente"] is True
    assert [d["dominio"] for d in nueva["dimensiones"]] == ["Datos", "Gobernanza"]
    # La en curso aparece, pero su vista previa no se informa como puntaje ni entra al gráfico
    assert abierta["completada"] is False and abierta["puntaje_global"] is None and abierta["nivel"] is None
    assert abierta["dimensiones"] == [] and abierta["vigente"] is False

    g = h["evolucion"]["global"]
    assert [(p["evaluacion_id"], p["puntaje"]) for p in g] == [(10, 52.0), (15, 76.0)]
    dims = {s["dominio"]: [p["puntaje"] for p in s["puntos"]] for s in h["evolucion"]["dimensiones"]}
    assert dims == {"Datos": [40.0, 70.0], "Gobernanza": [60.0, 80.0]}

    r = h["resumen"]
    assert (r["total"], r["completadas"], r["evaluacion_vigente_id"], r["evaluacion_en_curso_id"]) == (3, 2, 15, 18)
    assert (r["puntaje_actual"], r["variacion_total"], r["nivel_actual"]["codigo"]) == (76.0, 24.0, "optimizado")


def test_dimension_que_no_aplica_queda_como_punto_vacio():
    a = _ev(1, dims=((1, "Datos", 40.0, 4), (2, "Gobernanza", 60.0, 6)))
    b = _ev(2, dims=((1, "Datos", 50.0, 4),))
    dims = {s["dominio"]: [p["puntaje"] for p in s["puntos"]]
            for s in construir_historial([a, b])["evolucion"]["dimensiones"]}
    assert dims == {"Datos": [40.0, 50.0], "Gobernanza": [60.0, None]}


def test_historial_vacio():
    h = construir_historial([])
    assert h["evaluaciones"] == [] and h["evolucion"] == {"global": [], "dimensiones": []}
    assert h["resumen"]["evaluacion_vigente_id"] is None and h["resumen"]["variacion_total"] is None


def test_benchmark_cuenta_solo_la_mas_reciente_de_cada_empresa():
    # (evaluación, empresa): 1 y 2 son encuestados anónimos; la empresa 7 tiene 3, 5 y 9
    filas = [(1, None), (2, None), (3, 7), (9, 7), (5, 7), (4, 8)]
    assert evaluaciones_para_benchmark(filas) == {1, 2, 9, 4}
    assert evaluaciones_para_benchmark([]) == set()


def test_mediana():
    assert mediana([3, 1, 2]) == 2 and mediana([4, 1, 3, 2]) == 2.5 and mediana([]) is None


def test_constantes_iguales_a_las_del_modelo():
    """historial.py no importa SQLAlchemy: sus constantes deben coincidir con las del modelo."""
    pytest.importorskip("sqlalchemy")
    from app.application.informes import historial
    from app.domain.models import evaluacion

    assert historial.ESTADOS_CERRADOS == evaluacion.ESTADOS_CERRADOS
    assert historial.ORIGEN_EMPRESA == evaluacion.ORIGEN_EMPRESA


# ===================================================================== parte 2: API
def _hay_api() -> bool:
    try:
        import aiosqlite  # noqa: F401
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
        return True
    except ImportError:
        return False


api = pytest.mark.skipif(not _hay_api(), reason="Pruebas de API: requieren FastAPI, SQLAlchemy y aiosqlite (Docker)")


@pytest.fixture
def hu27(monkeypatch, tmp_path):
    if not _hay_api():
        pytest.skip("sin FastAPI/SQLAlchemy")
    import test_hu27_empresa_cliente as m
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("HU-29: solo en proceso")
    from app.core.config import settings
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", m.SECRETO)
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ACTIVACION_URL_BASE", "http://localhost:3000/activar")
    monkeypatch.setattr(settings, "BENCHMARK_AL_COMPLETAR", True)
    monkeypatch.setattr(settings, "DOCUMENTOS_ARCHIVAR_AL_COMPLETAR", True)
    limitador = LimitadorMemoria()
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield m
    app.dependency_overrides.pop(obtener_limitador, None)


def _correr(escenario):
    from _api_harness import cliente_api

    async def _main():
        async with cliente_api(rol=None) as c:
            await escenario(c)
    asyncio.run(_main())


async def _cliente(hu27, c) -> dict:
    x = await hu27._empresa_creada(c)
    return {**x, "hc": await hu27._activar_y_entrar(c)}


async def _responder_reevaluacion(hu27, c, h, ev: int, estado: str = "cumplido") -> dict:
    """Responde la reevaluación con la sesión del CLIENTE (mismas rutas del cuestionario)."""
    from app.application.filters.control_tree import CONTROLES_BASE

    r = await c.post(f"/api/evaluaciones/{ev}/filtro", json=hu27.SOLO_BASE, headers=h)
    assert r.status_code == 200, r.text
    for codigo in CONTROLES_BASE:
        r = await c.post("/api/respuestas/", headers=h, json={
            "evaluacion_id": ev, "matriz_control_id": hu27.ID_CONTROL[codigo],
            "estado_clasificacion": estado, "justificacion": hu27.JUST})
        assert r.status_code in (200, 201), r.text
    r = await c.post(f"/api/evaluaciones/{ev}/completar", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def _acciones(c, hu27) -> list[dict]:
    return (await c.get("/api/admin/bitacora?size=200", headers=hu27.admin())).json()["items"]


@api
def test_api_historial_reevaluacion_y_benchmark(hu27):
    async def esc(c):
        from sqlalchemy import select

        x = await _cliente(hu27, c)
        h, migrada, eid = x["hc"], x["ev"], x["empresa_id"]

        # C1: la migrada aparece con fecha, estado, puntaje global y nivel
        r = await c.get("/api/cliente/evaluaciones", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert [e["id"] for e in d["evaluaciones"]] == [migrada]
        e = d["evaluaciones"][0]
        assert e["tipo"] == "migrada" and e["completada"] and e["fecha"] and e["vigente"]
        resumen = (await c.get(f"/api/evaluaciones/{migrada}/resumen", headers=h)).json()
        assert e["puntaje_global"] == resumen["puntaje_general"]
        assert e["nivel"]["codigo"] == resumen["nivel_madurez_general"]
        assert len(d["evolucion"]["global"]) == 1 and d["evolucion"]["dimensiones"]
        assert d["puede_reevaluar"] is True

        # C2: la reevaluación pertenece a la empresa y no crea usuario temporal
        async def temporales(s):
            from app.domain.models import UsuarioTemporal
            return len((await s.execute(select(UsuarioTemporal.id))).all())
        antes = await hu27._bd(temporales)
        r = await c.post("/api/cliente/evaluaciones", headers=h)
        assert r.status_code == 201, r.text
        nueva = r.json()["evaluacion_id"]
        assert r.json()["origen"] == "empresa" and r.json()["empresa_id"] == eid
        assert await hu27._bd(temporales) == antes

        async def fila(s):
            from app.domain.models import Evaluacion
            return await s.get(Evaluacion, nueva)
        ev = await hu27._bd(fila)
        assert ev.usuario_temporal_id is None and ev.empresa_id == eid and ev.clave_acceso_hash is None

        # Una sola en curso: la segunda vez se ofrece retomar la misma
        r = await c.post("/api/cliente/evaluaciones", headers=h)
        assert r.status_code == 409 and hu27._codigo(r) == "EVALUACION_EN_CURSO"
        assert r.json()["detail"]["evaluacion_id"] == nueva
        d = (await c.get("/api/cliente/evaluaciones", headers=h)).json()
        assert d["puede_reevaluar"] is False and d["resumen"]["evaluacion_en_curso_id"] == nueva

        # Sin token no se toca nunca (aunque EXIGIR_TOKEN_EVALUACIONES=false)
        assert (await c.get(f"/api/evaluaciones/{nueva}/progreso")).status_code == 401

        # El cliente la responde con su sesión y la completa: mejor puntaje que la migrada
        fin = await _responder_reevaluacion(hu27, c, h, nueva)
        assert fin["estado_progreso"] == "completada" and fin["documento_id"]

        d = (await c.get("/api/cliente/evaluaciones", headers=h)).json()
        assert [e["id"] for e in d["evaluaciones"]] == [nueva, migrada]
        nueva_e = d["evaluaciones"][0]
        assert nueva_e["tipo"] == "reevaluacion" and nueva_e["vigente"] and nueva_e["fecha_completado"]
        assert nueva_e["puntaje_global"] == 100.0 and nueva_e["variacion"] > 0
        assert [p["evaluacion_id"] for p in d["evolucion"]["global"]] == [migrada, nueva]
        assert d["resumen"]["evaluacion_vigente_id"] == nueva and d["puede_reevaluar"] is True

        # El rubro de la comparativa sale de la empresa (no hay usuario temporal)
        r = await c.get(f"/api/evaluaciones/{nueva}/comparativa", headers=h)
        assert r.status_code == 200 and r.json()["rubro_id"] == 1

        # C2: en el benchmark solo cuenta la más reciente de la empresa
        async def bench(s):
            from app.domain.models.benchmark import Benchmark
            return (await s.execute(select(Benchmark))).scalars().all()
        filas = await hu27._bd(bench)
        assert filas and all(b.total_evaluaciones == 1 for b in filas)
        assert all(b.promedio_puntaje == 100.0 for b in filas)

        # Formación y tutor usan la evaluación completada más reciente
        async def base_formacion(s):
            from app.application.use_cases.formacion_empresa import evaluacion_de_la_empresa
            return await evaluacion_de_la_empresa(s, eid, None)
        assert await hu27._bd(base_formacion) == nueva

        acciones = [f["accion"] for f in await _acciones(c, hu27)]
        assert "evaluacion.reevaluacion_iniciada" in acciones
        assert "evaluacion.completada_empresa" in acciones and "documento.generado" in acciones
    _correr(esc)


@api
def test_api_sin_contrato_vigente_ve_el_historial_pero_no_reevalua(hu27):
    async def esc(c):
        x = await _cliente(hu27, c)
        h, adm = x["hc"], hu27.admin()
        r = await c.post(f"/api/admin/empresas/{x['empresa_id']}/contrato/suspension",
                         json={"motivo": "no_pago"}, headers=adm)
        assert r.status_code == 200, r.text
        r = await c.get("/api/cliente/evaluaciones", headers=h)
        assert r.status_code == 200 and r.json()["puede_reevaluar"] is False
        r = await c.post("/api/cliente/evaluaciones", headers=h)
        assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE"
        # Suspendido: los documentos siguen disponibles (HU-30)
        assert (await c.get("/api/cliente/documentos", headers=h)).status_code == 200

        # Solo el cliente: 401 sin token, 403 con otro rol
        for ruta in ("/api/cliente/evaluaciones", "/api/cliente/documentos"):
            assert (await c.get(ruta)).status_code == 401
            assert (await c.get(ruta, headers=adm)).status_code == 403
    _correr(esc)


@api
def test_api_mis_documentos_descarga_y_eliminacion_auditada(hu27):
    async def esc(c):
        from app.domain.models import AvanceFormativo, Evidencia

        x = await _cliente(hu27, c)
        h, ev, eid = x["hc"], x["ev"], x["empresa_id"]

        # Una constancia de un módulo completado (HU-26)
        async def constancia(s):
            s.add(AvanceFormativo(empresa_id=eid, ruta_formativa_id=1, evaluacion_id=ev, estado="completado",
                                  intentos=1, mejor_puntaje=100.0, fecha_inicio=datetime(2026, 10, 1),
                                  fecha_ultima_actividad=datetime(2026, 10, 2),
                                  fecha_completado=datetime(2026, 10, 2), codigo_constancia="CF-ABCD-EFGH"))
            await s.commit()
        await hu27._bd(constancia)

        r = await c.get("/api/cliente/documentos", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["informes"] == [] and d["borradores"] == []
        assert len(d["evidencias"]) == 1 and d["evidencias"][0]["evaluacion_id"] == ev
        assert [k["codigo"] for k in d["constancias"]] == ["CF-ABCD-EFGH"]
        evid = d["evidencias"][0]["id"]

        # Informe PDF archivado desde "Mis evaluaciones"
        r = await c.post("/api/cliente/documentos/informes", json={"evaluacion_id": ev}, headers=h)
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["tipo"] == "informe_pdf" and doc["nombre"].endswith(".pdf")
        r = await c.get(f"/api/cliente/documentos/{doc['id']}/descarga", headers=h)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        assert r.headers["content-type"] == "application/pdf"
        assert f'filename="{doc["nombre"]}"' in r.headers["content-disposition"]
        # Un informe de una evaluación ajena o inexistente: 404
        r = await c.post("/api/cliente/documentos/informes", json={"evaluacion_id": 1}, headers=h)
        assert r.status_code == 404

        # Evidencia: se descarga (en esta prueba el worker no corrió: es el original descifrado)
        r = await c.get(f"/api/cliente/documentos/evidencias/{evid}/descarga", headers=h)
        assert r.status_code == 200 and b"Politica de IA" in r.content
        assert r.headers["content-type"].startswith("text/plain")

        resumen_antes = (await c.get(f"/api/evaluaciones/{ev}/resumen", headers=h)).json()

        # Eliminar: informe, evidencia y constancia
        assert (await c.delete(f"/api/cliente/documentos/{doc['id']}", headers=h)).status_code == 204
        assert (await c.get(f"/api/cliente/documentos/{doc['id']}/descarga", headers=h)).status_code == 404
        assert (await c.delete(f"/api/cliente/documentos/{doc['id']}", headers=h)).status_code == 404

        assert (await c.delete(f"/api/cliente/documentos/evidencias/{evid}", headers=h)).status_code == 204
        assert (await c.get(f"/api/cliente/documentos/evidencias/{evid}/descarga", headers=h)).status_code == 404

        async def evidencia(s):
            return await s.get(Evidencia, evid)
        fila = await hu27._bd(evidencia)
        assert fila.fecha_eliminacion and fila.storage_path == "" and fila.estado_validacion == "validated"
        # Borrar un archivo no cambia ningún puntaje
        assert (await c.get(f"/api/evaluaciones/{ev}/resumen", headers=h)).json() == resumen_antes

        assert (await c.delete("/api/cliente/documentos/constancias/1", headers=h)).status_code == 204
        r = await c.get("/api/formacion/modulos/1/constancia", headers=h)
        assert r.status_code == 404 and hu27._codigo(r) == "CONSTANCIA_ELIMINADA"

        d = (await c.get("/api/cliente/documentos", headers=h)).json()
        assert d["informes"] == [] and d["evidencias"] == [] and d["constancias"] == []

        # C3: cada eliminación (y cada descarga) queda en la bitácora, sin datos personales
        filas = await _acciones(c, hu27)
        eliminados = [f for f in filas if f["accion"] == "documento.eliminado"]
        assert {f["detalle"]["tipo"] for f in eliminados} == {"informe_pdf", "evidencia", "constancia"}
        assert all(f["actor_rol"] == "cliente" for f in eliminados)
        assert len([f for f in filas if f["accion"] == "documento.descargado"]) == 2
        assert "@" not in str(filas) and "Politica" not in str(filas)
    _correr(esc)


@api
def test_api_limite_de_informes_y_evaluacion_no_completada(hu27, monkeypatch):
    async def esc(c):
        from app.core.config import settings

        x = await _cliente(hu27, c)
        h, ev = x["hc"], x["ev"]
        monkeypatch.setattr(settings, "DOCUMENTOS_INFORMES_POR_EVALUACION", 1)
        assert (await c.post("/api/cliente/documentos/informes", json={"evaluacion_id": ev}, headers=h)).status_code == 201
        r = await c.post("/api/cliente/documentos/informes", json={"evaluacion_id": ev}, headers=h)
        assert r.status_code == 409 and hu27._codigo(r) == "LIMITE_INFORMES"

        nueva = (await c.post("/api/cliente/evaluaciones", headers=h)).json()["evaluacion_id"]
        r = await c.post("/api/cliente/documentos/informes", json={"evaluacion_id": nueva}, headers=h)
        assert r.status_code == 409 and hu27._codigo(r) == "EVALUACION_NO_COMPLETADA"
    _correr(esc)
