"""
QA - HU-12: planes de estudio recomendados según las brechas, y el informe (PDF y correo).

  Criterio 1  Mapeo automático entre brechas y catálogo formativo
  Criterio 2  Niveles asignados (Inicial, Intermedio, Avanzado) con objetivos
  Criterio 3  Panel organizado por dimensión normativa

Además: severidad igual a la del panel (frontend-next/lib/severidad.ts), comparativa con
meta y benchmark recalculado al completar, PDF descargable y envío por correo.

Ejecutar desde Proyecto/backend/:
    pytest tests/test_hu12_plan_formativo.py -v

Las pruebas de lógica pura no necesitan BD. Las de API corren en proceso (SQLite en
memoria, ver _api_harness.py) y se omiten en modo live.
"""
import asyncio

import pytest

from app.application.informes.analisis import (
    BrechaCatalogo,
    DominioResultado,
    RespuestaFila,
    RutaCatalogo,
    calcular_severidad,
    construir_brechas,
    construir_plan,
    filtrar_brechas,
    nivel_por_puntaje,
    parsear_filtros,
    plan_a_dict,
)

# --------------------------------------------------------------------- datos de prueba
RUTAS = {
    (dom, niv): RutaCatalogo(id=i, nombre=f"{dom} - {niv}", horas=4 + i,
                             objetivo=f"Objetivo {dom} {niv}", objetivos_especificos=("a", "b"))
    for i, (dom, niv) in enumerate(
        [(d, n) for d in ("Protección de Datos", "Gobernanza de IA", "Gestión de Riesgos", "Uso Responsable")
         for n in ("Inicial", "Intermedio", "Avanzado")], start=1)
}
CATALOGO = list(RUTAS.values())


def _brecha(i, codigo, dom, crit, ruta):
    return BrechaCatalogo(id=i, codigo=codigo, categoria=dom, comportamiento=f"Comportamiento {codigo}",
                          criticidad=crit, accion="Acción", ruta=ruta)


B_DAT1 = _brecha(1, "ERR-DAT-001", "Protección de Datos", "Alta", RUTAS["Protección de Datos", "Inicial"])
# Brecha de Datos cuya ruta es de OTRA dimensión (como ERR-DAT-002 en la semilla real)
B_DAT2 = _brecha(2, "ERR-DAT-002", "Protección de Datos", "Alta", RUTAS["Gestión de Riesgos", "Intermedio"])
B_GOB1 = _brecha(3, "ERR-GOB-001", "Gobernanza de IA", "Media", RUTAS["Gobernanza de IA", "Inicial"])
B_SIN = _brecha(4, "ERR-XXX-001", "Uso Responsable", "Baja", None)


def _resp(i, estado, brecha, dominio, codigo):
    # Igual que el backend: la respuesta lleva la brecha solo si es no cumplida
    return RespuestaFila(
        id=i, estado=estado, control_id=i, control_codigo=codigo, control_criticidad="Media",
        control_dominio=dominio, control_obligacion=f"Obligación {codigo}",
        brecha_respuesta=brecha if estado == "no_cumplido" else None, brecha_control=brecha,
    )


RESPUESTAS = [
    _resp(1, "no_cumplido", B_DAT1, "Protección de Datos", "DAT-001"),
    _resp(2, "parcialmente_cumplido", B_DAT2, "Protección de Datos", "DAT-002"),
    _resp(3, "no_cumplido", B_GOB1, "Gobernanza de IA", "GOB-001"),
    _resp(4, "cumplido", B_GOB1, "Gobernanza de IA", "GOB-002"),
    _resp(5, "no_cumplido", B_SIN, "Uso Responsable", "USO-001"),
    _resp(6, "no_aplica", B_DAT1, "Protección de Datos", "DAT-003"),
]
DOMINIOS = [
    DominioResultado(1, "Protección de Datos", 30.0, "en_desarrollo"),
    DominioResultado(2, "Gobernanza de IA", 62.5, "gestionado"),
    DominioResultado(3, "Gestión de Riesgos", 80.0, "optimizado"),
    DominioResultado(4, "Uso Responsable", 50.0, "en_desarrollo"),
]


def _plan():
    puntajes = {d.nombre: d.puntaje for d in DOMINIOS}
    return construir_plan(construir_brechas(RESPUESTAS, puntajes), DOMINIOS, CATALOGO)


def _dim(plan, nombre):
    return next(d for d in plan.dimensiones if d.dominio == nombre)


# =====================================================================
# Severidad y orden (paridad con el panel)
# =====================================================================
@pytest.mark.parametrize("cat,estado,ctrl,esperado", [
    ("Alta", "no_cumplido", None, "Crítica"),
    ("ALTA", "parcialmente_cumplido", None, "Alta"),
    ("Media", "no_cumplido", None, "Alta"),
    ("media", "parcialmente_cumplido", None, "Media"),
    ("Baja", "no_cumplido", None, "Media"),
    ("Baja", "parcialmente_cumplido", None, "Baja"),
    ("Crítica", "parcialmente_cumplido", None, "Crítica"),
    (None, "no_cumplido", "Alta", "Crítica"),      # sin catálogo: manda el control
    (None, "no_cumplido", None, "Sin clasificar"),
])
def test_matriz_de_severidad_igual_a_la_del_panel(cat, estado, ctrl, esperado):
    assert calcular_severidad(cat, estado, ctrl)[0] == esperado


def test_brechas_priorizadas_solo_no_cumplidas_y_parciales():
    brechas = construir_brechas(RESPUESTAS)
    # Crítica -> Alta -> Media (no cumplida antes que parcial)
    assert [b.respuesta_id for b in brechas] == [1, 3, 5, 2]
    assert brechas[0].severidad == "Crítica" and brechas[0].codigo == "ERR-DAT-001"
    # el parcial no trae brecha en la respuesta: usa código y criticidad del control
    parcial = next(b for b in brechas if b.respuesta_id == 2)
    assert parcial.codigo == "DAT-002" and parcial.severidad == "Media"
    assert [b.prioridad for b in brechas] == list(range(1, 5))


def test_filtros_mismos_que_la_url_del_panel():
    brechas = construir_brechas(RESPUESTAS)
    f = parsear_filtros("Crítica,Alta,inventada", None, None, None)
    assert f.severidades == ("Crítica", "Alta")
    assert {b.severidad for b in filtrar_brechas(brechas, f)} <= {"Crítica", "Alta"}
    assert len(filtrar_brechas(brechas, parsear_filtros(None, None, "parcialmente_cumplido", None))) == 1
    # búsqueda sin tildes; también encuentra por nombre de la ruta formativa
    assert [b.codigo for b in filtrar_brechas(brechas, parsear_filtros(None, None, None, "proteccion"))] == ["ERR-DAT-001"]
    assert len(filtrar_brechas(brechas, parsear_filtros(None, "Protección de Datos", None, None))) == 2
    assert parsear_filtros(None, None, "cualquiera", None).estado is None


# =====================================================================
# Criterio 1 · Mapeo automático brecha -> catálogo formativo
# =====================================================================
def test_cada_brecha_activa_la_ruta_que_le_asigna_el_catalogo():
    plan = _plan()
    datos = _dim(plan, "Protección de Datos")
    inicial = next(m for m in datos.modulos if m.ruta.nombre == "Protección de Datos - Inicial")
    assert inicial.motivo == "brechas" and [b.codigo for b in inicial.brechas] == ["ERR-DAT-001"]
    assert inicial.prioridad == "Crítica"


def test_parcial_sin_brecha_asignada_igual_se_mapea_por_la_del_control():
    riesgos = _dim(_plan(), "Gestión de Riesgos")
    modulo = next(m for m in riesgos.modulos if m.ruta.nombre == "Gestión de Riesgos - Intermedio")
    assert modulo.motivo == "brechas"
    assert modulo.brechas[0].codigo == "DAT-002" and modulo.brechas[0].dominio == "Protección de Datos"


def test_brechas_sin_ruta_se_informan_y_bajan_la_cobertura():
    plan = _plan()
    assert [b.codigo for b in plan.brechas_sin_ruta] == ["ERR-XXX-001"]
    assert plan.brechas_total == 4 and plan.brechas_mapeadas == 3 and plan.cobertura == 75.0


# =====================================================================
# Criterio 2 · Niveles con objetivos
# =====================================================================
@pytest.mark.parametrize("puntaje,nivel", [(0, "Inicial"), (50, "Inicial"), (50.1, "Intermedio"),
                                           (75, "Intermedio"), (75.1, "Avanzado"), (None, "Inicial")])
def test_nivel_asignado_por_puntaje_de_la_dimension(puntaje, nivel):
    assert nivel_por_puntaje(puntaje) == nivel


def test_cada_dimension_tiene_nivel_objetivo_y_la_ruta_base_de_su_nivel():
    plan = _plan()
    gob = _dim(plan, "Gobernanza de IA")
    assert gob.nivel_asignado == "Intermedio" and gob.objetivo_nivel
    base = [m for m in gob.modulos if m.motivo == "nivel"]
    assert [m.ruta.nombre for m in base] == ["Gobernanza de IA - Intermedio"]
    assert base[0].prioridad == "Complementario"
    # sin brechas y puntaje alto: igual recibe su ruta del nivel (Avanzado)
    riesgos = _dim(plan, "Gestión de Riesgos")
    assert riesgos.nivel_asignado == "Avanzado"
    assert "Gestión de Riesgos - Avanzado" in [m.ruta.nombre for m in riesgos.modulos]


def test_modulos_ordenados_inicial_intermedio_avanzado():
    for dim in _plan().dimensiones:
        pesos = [("Inicial", "Intermedio", "Avanzado").index(m.nivel) for m in dim.modulos]
        assert pesos == sorted(pesos), dim.dominio


def test_nivel_y_dimension_se_deducen_del_nombre_si_faltan_columnas():
    r = RutaCatalogo(id=99, nombre="Uso Responsable - Avanzado")
    assert r.nivel_efectivo == "Avanzado" and r.dominio_efectivo == "Uso Responsable"
    r = RutaCatalogo(id=98, nombre="Ruta base de gobernanza IA")
    assert r.nivel_efectivo is None and r.dominio_efectivo is None


# =====================================================================
# Criterio 3 · Organizado por dimensión normativa
# =====================================================================
def test_plan_agrupado_por_dimension_con_totales():
    plan = _plan()
    assert [d.dominio for d in plan.dimensiones] == sorted(d.nombre for d in DOMINIOS)
    datos = _dim(plan, "Protección de Datos")
    assert datos.brechas_dimension == 2 and datos.nivel_asignado == "Inicial"
    j = plan_a_dict(plan)
    assert j["resumen"]["modulos"] == plan.modulos and j["resumen"]["horas"] == plan.horas > 0
    assert {"dominio", "nivel_asignado", "objetivo_nivel", "modulos", "horas"} <= set(j["dimensiones"][0])
    modulo = j["dimensiones"][0]["modulos"][0]
    assert {"nivel", "motivo", "prioridad", "ruta", "brechas"} <= set(modulo)
    assert modulo["ruta"]["objetivos_especificos"] == ["a", "b"]


# =====================================================================
# PDF (sin BD)
# =====================================================================
def test_pdf_generado_es_valido_y_lleva_las_secciones():
    pytest.importorskip("reportlab")
    from datetime import datetime, timezone

    from app.application.informes.analisis import ComparativaDominio, FiltrosBrechas
    from app.application.informes.pdf_informe import DatosInforme, generar_pdf

    brechas = construir_brechas(RESPUESTAS)
    pdf = generar_pdf(DatosInforme(
        evaluacion_id=7, rubro="Retail", puntaje_general=55.5, controles_evaluados=6, en_revision=1,
        comparativa=[ComparativaDominio("Protección de Datos", 30.0, None, 1, 75.0),
                     ComparativaDominio("Gobernanza de IA", 62.5, 58.0, 5, 75.0)],
        brechas_total=len(brechas), brechas=brechas, filtros=FiltrosBrechas(), plan=_plan(),
        generado=datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc),
    ))
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF") and len(pdf) > 3000


# =====================================================================
# API (en proceso)
# =====================================================================
try:
    import httpx  # noqa: F401
    import aiosqlite  # noqa: F401
    _HAY_API = True
except ImportError:
    _HAY_API = False

api = pytest.mark.skipif(not _HAY_API, reason="requiere httpx y aiosqlite (pip install -r requirements.txt)")


def _api():
    from _api_harness import EVAL_ID, MODO, TODOS_LOS_CONTROLES, cliente_api
    if MODO == "live":
        pytest.skip("cambian el estado de la evaluación; solo en proceso")
    return EVAL_ID, TODOS_LOS_CONTROLES, cliente_api


SOLO_BASE = {"respuestas": [{"codigo": f"F{i}", "respuesta": i == 1} for i in range(1, 8)]}
JUST = "Existe una política aprobada, pero aún no se aplica en todas las áreas."


async def _completar(c, eval_id, todos):
    from app.application.filters.control_tree import CONTROLES_BASE
    ids = {codigo: i + 1 for i, codigo in enumerate(todos)}
    assert (await c.post(f"/api/evaluaciones/{eval_id}/filtro", json=SOLO_BASE)).status_code == 200
    for n, codigo in enumerate(CONTROLES_BASE):
        estado = "no_cumplido" if n % 3 == 0 else ("parcialmente_cumplido" if n % 3 == 1 else "cumplido")
        r = await c.post("/api/respuestas/", json={
            "evaluacion_id": eval_id, "matriz_control_id": ids[codigo], "estado_clasificacion": estado,
            "justificacion": JUST})
        assert r.status_code in (200, 201), r.text
    r = await c.post(f"/api/evaluaciones/{eval_id}/completar")
    assert r.status_code == 200, r.text


def _correr(escenario):
    eval_id, todos, cliente_api = _api()

    async def _main():
        async with cliente_api() as c:
            await escenario(c, eval_id, todos)
    asyncio.run(_main())


@api
def test_api_plan_formativo_404_sin_resultados_y_200_al_completar():
    async def esc(c, eval_id, todos):
        r = await c.get(f"/api/evaluaciones/{eval_id}/plan-formativo")
        assert r.status_code == 404 and r.json()["detail"]["codigo"] == "SIN_RESULTADOS"
        await _completar(c, eval_id, todos)
        r = await c.get(f"/api/evaluaciones/{eval_id}/plan-formativo")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["resumen"]["brechas_total"] > 0
        assert j["resumen"]["brechas_mapeadas"] == j["resumen"]["brechas_total"]  # semilla: todo con ruta
        assert j["dimensiones"] and all(d["nivel_asignado"] in ("Inicial", "Intermedio", "Avanzado")
                                        for d in j["dimensiones"])
    _correr(esc)


@api
def test_api_comparativa_trae_meta_y_benchmark_tras_completar(monkeypatch):
    from app.core.config import settings
    # HU-10: con k = 1 una sola empresa basta para ver el promedio del rubro (solo en pruebas)
    monkeypatch.setattr(settings, "K_ANONIMATO_MINIMO", 1)

    async def esc(c, eval_id, todos):
        await _completar(c, eval_id, todos)
        j = (await c.get(f"/api/evaluaciones/{eval_id}/comparativa")).json()
        assert j["meta_puntaje"] == settings.META_CUMPLIMIENTO_PUNTAJE
        fila = j["comparativas"][0]
        assert fila["meta"] == j["meta_puntaje"] and "diferencia_vs_meta" in fila
        # El benchmark se recalculó al completar: ya hay promedio del rubro (n = 1 permitido)
        assert fila["muestras"] >= 1 and fila["promedio_industria"] is not None
        assert j["sector"]["cohorte_suficiente"] is True and j["sector"]["promedio"] is not None
    _correr(esc)


@api
def test_api_comparativa_oculta_el_promedio_con_pocas_muestras(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "K_ANONIMATO_MINIMO", 5)

    async def esc(c, eval_id, todos):
        await _completar(c, eval_id, todos)
        fila = (await c.get(f"/api/evaluaciones/{eval_id}/comparativa")).json()["comparativas"][0]
        assert fila["promedio_industria"] is None and fila["referencia_suficiente"] is False
        # HU-10: con k < 5 tampoco se revela cuántas empresas hay
        assert fila["muestras"] is None
    _correr(esc)


@api
def test_api_informe_pdf_se_descarga_como_adjunto():
    pytest.importorskip("reportlab")

    async def esc(c, eval_id, todos):
        await _completar(c, eval_id, todos)
        r = await c.get(f"/api/evaluaciones/{eval_id}/informe/pdf", params={"severidad": "Crítica"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("attachment; filename=\"informe_evaluacion-")
        assert r.content.startswith(b"%PDF-")
    _correr(esc)


@api
def test_api_enviar_informe_por_correo_en_modo_archivo(monkeypatch, tmp_path):
    pytest.importorskip("reportlab")
    from app.core.config import settings
    monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "INFORME_CORREOS_DIA_EVALUACION", 2)

    async def esc(c, eval_id, todos):
        await _completar(c, eval_id, todos)
        url = f"/api/evaluaciones/{eval_id}/informe/enviar"
        r = await c.post(url, json={})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "EMAIL_REQUERIDO"
        r = await c.post(url, json={"email": "no-es-correo"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "EMAIL_INVALIDO"
        r = await c.post(url, json={"email": "Persona@Empresa.cl"})
        assert r.status_code == 200, r.text
        assert r.json() == {"enviado": True, "destino": "p***a@empresa.cl", "modo": "archivo"}
        eml = list((tmp_path / "correos").glob("*.eml"))
        assert len(eml) == 1
        contenido = eml[0].read_bytes()
        assert b"persona@empresa.cl" in contenido and b"application/pdf" in contenido
        assert (await c.post(url, json={"email": "persona@empresa.cl"})).status_code == 200
        r = await c.post(url, json={"email": "persona@empresa.cl"})
        assert r.status_code == 429 and r.json()["detail"]["codigo"] == "LIMITE_CORREOS"
    _correr(esc)


@api
def test_api_correo_desactivado_responde_503(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CORREO_MODO", "desactivado")

    async def esc(c, eval_id, todos):
        r = await c.post(f"/api/evaluaciones/{eval_id}/informe/enviar", json={"email": "a@b.cl"})
        assert r.status_code == 503 and r.json()["detail"]["codigo"] == "CORREO_NO_DISPONIBLE"
    _correr(esc)


@api
def test_api_catalogo_de_brechas_ahora_trae_la_ruta_formativa():
    async def esc(c, eval_id, todos):
        brechas = (await c.get("/api/brechas")).json()
        assert brechas[0]["ruta_formativa"] == {
            "id": 1, "nombre": "Ruta base de gobernanza IA", "dominio_id": None, "nivel": None,
            "objetivo": None, "horas": None, "modalidad": None, "publico_objetivo": None,
        }
    _correr(esc)
