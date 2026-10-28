"""
QA - HU-26: registrar el avance de los módulos formativos completados.

  C1  Con contrato vigente (HU-30) cada módulo del plan formativo (HU-12) se recorre:
      contenidos, material de apoyo (placeholders) y una actividad de verificación al final.
  C2  El avance queda en la empresa (iniciados, completados y % por dimensión y nivel) y se
      ve en el panel de formación.
  C3  Al completar un módulo se registra la fecha y se descarga una constancia. Las brechas
      asociadas muestran que la formación está hecha, pero el puntaje solo cambia con nueva
      evidencia (HU-17).

Parte 1: lógica pura (app/application/formacion/logica.py y la constancia PDF); corre en
cualquier entorno. Parte 2: API en proceso (SQLite), reutiliza la preparación de
test_hu27_empresa_cliente.py; necesita FastAPI, SQLAlchemy y aiosqlite (Docker).
"""
import asyncio
import random
from datetime import datetime

import pytest

from app.application.formacion.logica import (
    COMPLETADO,
    EN_CURSO,
    NO_INICIADO,
    AvanceModulo,
    Pregunta,
    codigo_constancia,
    corregir,
    lecciones_de_ruta,
    preguntas_publicas,
    resumir_avance,
)
from app.application.informes.analisis import (
    BrechaCubierta,
    DimensionPlan,
    ModuloPlan,
    PlanFormativo,
    RutaCatalogo,
)


# ===================================================================== datos de prueba
def _ruta(i, dominio="Protección de Datos", nivel="Inicial", horas=4, contenidos=("A", "B", "C", "D")):
    return RutaCatalogo(id=i, nombre=f"{dominio} - {nivel}", dominio=dominio, nivel=nivel, horas=horas,
                        contenidos=tuple(contenidos), objetivo="Objetivo del módulo")


def _plan() -> PlanFormativo:
    r1, r2, r3 = _ruta(1), _ruta(2, nivel="Intermedio", horas=8), _ruta(3, "Gobernanza de IA", "Inicial", 3)
    b1 = BrechaCubierta("BR-1", "PDP-001", "Protección de Datos", "Crítica", "no_cumplido", 1, respuesta_id=11)
    b2 = BrechaCubierta("BR-2", "PDP-002", "Protección de Datos", "Media", "parcialmente_cumplido", 3, respuesta_id=12)
    b3 = BrechaCubierta("BR-3", "GOB-001", "Gobernanza de IA", "Alta", "no_cumplido", 2, respuesta_id=13)
    pdp = DimensionPlan(1, "Protección de Datos", 40.0, "en_desarrollo", "Inicial", "obj", 2, [
        ModuloPlan(r1, "Inicial", "brechas", "Crítica", [b1]),
        ModuloPlan(r2, "Intermedio", "brechas", "Media", [b2]),
    ])
    gob = DimensionPlan(2, "Gobernanza de IA", 60.0, "gestionado", "Intermedio", "obj", 1, [
        ModuloPlan(r3, "Inicial", "brechas", "Alta", [b3]),
    ])
    return PlanFormativo([gob, pdp], brechas_total=3, brechas_mapeadas=3, brechas_sin_ruta=[])


PREGUNTAS = [
    Pregunta(id=10, orden=1, enunciado="¿P1?", opciones=("a", "b", "c", "d"), correcta=1, explicacion="porque b"),
    Pregunta(id=11, orden=2, enunciado="¿P2?", opciones=("a", "b", "c"), correcta=0, explicacion="porque a"),
    Pregunta(id=12, orden=3, enunciado="¿P3?", opciones=("a", "b"), correcta=1, explicacion="porque b"),
]


# ===================================================================== C1: lecciones y actividad
def test_lecciones_salen_de_la_bd_o_de_los_contenidos_como_placeholder():
    ruta = _ruta(1, horas=4)
    derivadas = lecciones_de_ruta(ruta, [])
    assert [l.orden for l in derivadas] == [1, 2, 3, 4]
    assert [l.titulo for l in derivadas] == ["A", "B", "C", "D"]
    assert all(l.material and l.contenido for l in derivadas)      # material de apoyo (placeholders)
    assert derivadas[0].duracion_min == 60                          # 4 h repartidas en 4 lecciones
    from app.application.formacion.logica import Leccion
    propias = [Leccion(orden=2, titulo="Dos"), Leccion(orden=1, titulo="Uno")]
    assert [l.titulo for l in lecciones_de_ruta(ruta, propias)] == ["Uno", "Dos"]
    assert lecciones_de_ruta(_ruta(9, contenidos=()), []) == []


def test_la_actividad_publica_no_revela_la_respuesta_y_baraja_estable_por_empresa():
    pub = preguntas_publicas(PREGUNTAS, empresa_id=7)
    texto = str(pub)
    assert "correcta" not in texto and "explicacion" not in texto
    assert [p["id"] for p in pub] == [10, 11, 12]
    assert sorted(o["id"] for o in pub[0]["opciones"]) == [0, 1, 2, 3]
    assert pub == preguntas_publicas(PREGUNTAS, empresa_id=7)     # mismo orden en cada visita
    ordenes = {tuple(o["id"] for o in preguntas_publicas(PREGUNTAS, empresa_id=e)[0]["opciones"]) for e in range(30)}
    assert len(ordenes) > 1                                          # cambia entre empresas


def test_corregir_aprueba_con_el_umbral_y_solo_explica_al_aprobar():
    mal = corregir(PREGUNTAS, {10: 0, 11: 1}, umbral=70)
    assert (mal.correctas, mal.total, mal.puntaje, mal.aprobado) == (0, 3, 0.0, False)
    assert mal.sin_responder == [12]
    assert all("explicacion" not in d for d in mal.detalle)
    casi = corregir(PREGUNTAS, {10: 1, 11: 0, 12: 0}, umbral=70)
    assert (casi.puntaje, casi.aprobado) == (66.7, False)
    bien = corregir(PREGUNTAS, {10: 1, 11: 0, 12: 1}, umbral=70)
    assert (bien.puntaje, bien.aprobado) == (100.0, True)
    assert [d["explicacion"] for d in bien.detalle] == ["porque b", "porque a", "porque b"]
    with pytest.raises(ValueError):
        corregir([], {}, umbral=70)


def test_codigo_de_constancia_sin_caracteres_ambiguos():
    codigos = {codigo_constancia(random.Random(i)) for i in range(200)}
    assert len(codigos) == 200
    for c in codigos:
        assert len(c) == 12 and c.startswith("CF-") and c[7] == "-"
        assert not set(c[3:].replace("-", "")) & set("01OI")


# ===================================================================== C2 y C3: avance
def test_avance_por_modulo_dimension_y_nivel():
    ahora = datetime(2026, 10, 27, 15, 0)
    avances = {
        1: AvanceModulo(1, COMPLETADO, frozenset({1, 2, 3, 4}), intentos=2, mejor_puntaje=100.0,
                        fecha_inicio=ahora, fecha_completado=ahora, codigo_constancia="CF-AAAA-BBBB"),
        3: AvanceModulo(3, EN_CURSO, frozenset({1, 9})),           # la 9 no existe: no cuenta
    }
    a = resumir_avance(_plan(), avances, {1: 4, 2: 4, 3: 4})
    r = a["resumen"]
    assert (r["modulos_total"], r["completados"], r["en_curso"], r["iniciados"]) == (3, 1, 1, 2)
    assert r["porcentaje"] == 33.3
    assert (r["horas_total"], r["horas_completadas"]) == (15, 4)

    por_dim = {d["dominio"]: d for d in a["por_dimension"]}
    assert (por_dim["Protección de Datos"]["completados"], por_dim["Protección de Datos"]["porcentaje"]) == (1, 50.0)
    assert (por_dim["Gobernanza de IA"]["en_curso"], por_dim["Gobernanza de IA"]["porcentaje"]) == (1, 0.0)
    assert [n["nivel"] for n in a["por_nivel"]] == ["Inicial", "Intermedio"]   # orden de aprendizaje
    assert {n["nivel"]: n["porcentaje"] for n in a["por_nivel"]} == {"Inicial": 50.0, "Intermedio": 0.0}

    mod = {m["ruta_id"]: m for m in a["modulos"]}
    assert mod[1]["estado"] == COMPLETADO and mod[1]["porcentaje_lecciones"] == 100.0
    assert mod[1]["fecha_completado"] == "2026-10-27T15:00:00" and mod[1]["codigo_constancia"] == "CF-AAAA-BBBB"
    assert (mod[3]["estado"], mod[3]["lecciones_vistas"], mod[3]["porcentaje_lecciones"]) == (EN_CURSO, 1, 25.0)
    assert mod[2]["estado"] == NO_INICIADO and mod[2]["intentos"] == 0


def test_brechas_del_modulo_completado_muestran_formacion_hecha():
    a = resumir_avance(_plan(), {1: AvanceModulo(1, COMPLETADO)}, {1: 4, 2: 4, 3: 4})
    brechas = {b["codigo"]: b for b in a["brechas"]}
    assert brechas["BR-1"]["formacion_completada"] is True and brechas["BR-1"]["respuesta_id"] == 11
    assert brechas["BR-2"]["formacion_completada"] is False
    assert [b["codigo"] for b in a["brechas"]] == ["BR-1", "BR-3", "BR-2"]          # por prioridad
    assert (a["resumen"]["brechas_con_formacion"], a["resumen"]["porcentaje_brechas_con_formacion"]) == (1, 33.3)
    # el avance no trae ni toca puntajes de madurez: eso es HU-17
    assert "puntaje" not in a["resumen"]


def test_cerrar_una_brecha_no_baja_el_avance():
    """Si la evidencia cierra la brecha (HU-17), el módulo sale del plan pero sigue contando."""
    plan = _plan()
    plan.dimensiones[1].modulos.pop(0)                    # BR-1 se cerró: su módulo ya no está en el plan
    avances = {1: AvanceModulo(1, COMPLETADO)}
    a = resumir_avance(plan, avances, {1: 4, 2: 4, 3: 4}, rutas_fuera_del_plan=[_ruta(1), _ruta(2)])
    mod = {m["ruta_id"]: m for m in a["modulos"]}
    assert mod[1]["en_plan"] is False and mod[1]["estado"] == COMPLETADO and mod[1]["motivo"] == "historial"
    assert a["resumen"]["completados"] == 1 and a["resumen"]["modulos_total"] == 3
    assert a["modulos"][-1]["ruta_id"] == 1                # el historial va al final


def test_constancia_pdf_de_una_pagina_con_el_codigo():
    pytest.importorskip("reportlab")
    pypdf = pytest.importorskip("pypdf")
    import io
    from app.application.formacion.constancia_pdf import DatosConstancia, fecha_larga, generar_constancia, nombre_constancia

    d = DatosConstancia(
        razon_social="ACME Servicios SpA", rut="76086428-5", participante="Gabriela Rojas",
        modulo="Protección de Datos - Inicial", dominio="Protección de Datos", nivel="Inicial", horas=4,
        modalidad="E-learning autoguiado", objetivo="Reconocer qué es un dato personal.",
        fecha_completado=datetime(2026, 10, 27, 18, 30), puntaje=100.0, codigo="CF-AB2C-D3EF",
    )
    pdf = generar_constancia(d)
    assert pdf.startswith(b"%PDF")
    lector = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(lector.pages) == 1
    texto = lector.pages[0].extract_text()
    for esperado in ("Constancia de formación", "ACME Servicios SpA", "CF-AB2C-D3EF", "27 de octubre de 2026",
                     "No modifica el puntaje"):
        assert esperado in texto.replace("\n", " ")
    assert nombre_constancia(d) == "constancia_CF-AB2C-D3EF.pdf"
    assert fecha_larga(datetime(2026, 1, 1, 2, 0)) == "31 de diciembre de 2025"     # UTC -> hora de Chile


# ===================================================================== API (en proceso)
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
        pytest.skip("HU-26: solo en proceso")
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


async def _sembrar_curso(hu27, ruta_id=1):
    """La ruta 1 del arnés no trae contenido: se le dan dos lecciones y dos preguntas."""
    async def f(s):
        from app.domain.models import LeccionFormativa, PreguntaVerificacion, RutaFormativa
        ruta = await s.get(RutaFormativa, ruta_id)
        ruta.horas, ruta.nivel = 4, "Inicial"
        s.add_all([
            LeccionFormativa(ruta_formativa_id=ruta_id, orden=1, titulo="Qué es un dato personal",
                             contenido="Párrafo 1\nPárrafo 2", material_apoyo=[{"tipo": "guia", "titulo": "Guía"}]),
            LeccionFormativa(ruta_formativa_id=ruta_id, orden=2, titulo="Minimización", contenido="Texto"),
            PreguntaVerificacion(ruta_formativa_id=ruta_id, orden=1, enunciado="¿Uno?", opciones=["a", "b", "c"],
                                 correcta=2, explicacion="c"),
            PreguntaVerificacion(ruta_formativa_id=ruta_id, orden=2, enunciado="¿Dos?", opciones=["a", "b"],
                                 correcta=0, explicacion="a"),
        ])
        await s.commit()
    await hu27._bd(f)


async def _cliente(hu27, c) -> dict:
    x = await hu27._empresa_creada(c)
    h = await hu27._activar_y_entrar(c)
    await _sembrar_curso(hu27)
    return {**x, "hc": h}


async def _ids_preguntas(c, h) -> dict:
    r = await c.get("/api/formacion/modulos/1", headers=h)
    assert r.status_code == 200, r.text
    return {p["enunciado"]: p["id"] for p in r.json()["actividad"]["preguntas"]}


@api
def test_api_recorrido_completo_avance_constancia_y_puntaje_intacto(hu27):
    async def esc(c):
        x = await _cliente(hu27, c)
        h, ev = x["hc"], x["ev"]
        resumen_antes = (await c.get(f"/api/evaluaciones/{ev}/resumen", headers=h)).json()

        # C2: el panel de formación muestra el plan sin avance
        r = await c.get("/api/formacion/avance", headers=h)
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["evaluacion_id"] == ev and a["resumen"]["completados"] == 0
        modulo = next(m for m in a["modulos"] if m["ruta_id"] == 1)
        assert modulo["estado"] == "no_iniciado" and modulo["lecciones_total"] == 2
        assert a["brechas"] and not any(b["formacion_completada"] for b in a["brechas"])
        assert all(b["respuesta_id"] for b in a["brechas"])

        # C1: el módulo se recorre; la actividad no trae la respuesta correcta
        r = await c.get("/api/formacion/modulos/1", headers=h)
        d = r.json()
        assert [l["titulo"] for l in d["lecciones"]] == ["Qué es un dato personal", "Minimización"]
        assert d["lecciones"][0]["material_apoyo"] and d["lecciones"][0]["contenido"] == ["Párrafo 1", "Párrafo 2"]
        assert "correcta" not in r.text and d["actividad"]["disponible"] is False
        ids = await _ids_preguntas(c, h)

        r = await c.post("/api/formacion/modulos/1/verificacion", headers=h,
                         json={"respuestas": {ids["¿Uno?"]: 2, ids["¿Dos?"]: 0}})
        assert r.status_code == 409 and hu27._codigo(r) == "LECCIONES_PENDIENTES"

        r = await c.post("/api/formacion/modulos/1/lecciones/1/vista", headers=h, json={})
        assert r.status_code == 200 and r.json()["estado"] == "en_curso" and r.json()["porcentaje_lecciones"] == 50.0
        assert (await c.post("/api/formacion/modulos/1/lecciones/1/vista", headers=h)).json()["lecciones_vistas"] == [1]
        assert (await c.post("/api/formacion/modulos/1/lecciones/9/vista", headers=h)).status_code == 404
        await c.post("/api/formacion/modulos/1/lecciones/2/vista", headers=h)

        # Respuesta inválida (opción fuera de rango o pregunta ajena) -> 422, sin gastar intento
        r = await c.post("/api/formacion/modulos/1/verificacion", headers=h, json={"respuestas": {ids["¿Uno?"]: 7}})
        assert r.status_code == 422
        # Reprobada: queda en curso y sin constancia
        r = await c.post("/api/formacion/modulos/1/verificacion", headers=h,
                         json={"respuestas": {ids["¿Uno?"]: 0, ids["¿Dos?"]: 0}})
        assert r.status_code == 200, r.text
        assert (r.json()["aprobado"], r.json()["puntaje"]) == (False, 50.0)
        assert all("explicacion" not in x for x in r.json()["detalle"])
        assert (await c.get("/api/formacion/modulos/1/constancia", headers=h)).status_code == 404

        # C3: aprobada -> completado con fecha y código de constancia
        r = await c.post("/api/formacion/modulos/1/verificacion", headers=h,
                         json={"respuestas": {ids["¿Uno?"]: 2, ids["¿Dos?"]: 0}})
        res = r.json()
        assert res["aprobado"] is True and res["puntaje"] == 100.0
        assert res["avance"]["estado"] == "completado" and res["avance"]["fecha_completado"]
        assert res["avance"]["codigo_constancia"].startswith("CF-") and res["avance"]["intentos"] == 2

        r = await c.get("/api/formacion/modulos/1/constancia", headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
        assert res["avance"]["codigo_constancia"] in r.headers["content-disposition"]
        r = await c.post("/api/formacion/modulos/1/verificacion", headers=h, json={"respuestas": {}})
        assert r.status_code == 409 and hu27._codigo(r) == "MODULO_COMPLETADO"

        a = (await c.get("/api/formacion/avance", headers=h)).json()
        assert a["resumen"]["completados"] == 1
        assert all(b["formacion_completada"] for b in a["brechas"] if b["ruta_id"] == 1)
        assert a["resumen"]["brechas_con_formacion"] == len([b for b in a["brechas"] if b["ruta_id"] == 1])

        # ...pero el puntaje NO cambió: solo cambia con evidencia nueva (HU-17)
        assert (await c.get(f"/api/evaluaciones/{ev}/resumen", headers=h)).json() == resumen_antes

        # Bitácora (HU-09)
        acciones = [f["accion"] for f in (await c.get("/api/admin/bitacora?size=200", headers=hu27.admin())).json()["items"]]
        for accion in ("formacion.modulo_iniciado", "formacion.verificacion_intento",
                       "formacion.modulo_completado", "formacion.constancia_descargada"):
            assert accion in acciones

        # El admin ve el mismo avance desde el panel interno; el cliente no puede usar esa ruta
        r = await c.get(f"/api/admin/empresas/{x['empresa_id']}/formacion", headers=hu27.admin())
        assert r.status_code == 200 and r.json()["resumen"]["completados"] == 1
        assert (await c.get(f"/api/admin/empresas/{x['empresa_id']}/formacion", headers=h)).status_code == 403
        assert (await c.get("/api/admin/empresas/999/formacion", headers=hu27.admin())).status_code == 404
    _correr(esc)


@api
def test_api_solo_el_cliente_con_servicio_activo(hu27, monkeypatch):
    async def esc(c):
        x = await _cliente(hu27, c)
        assert (await c.get("/api/formacion/avance")).status_code == 401
        r = await c.get("/api/formacion/avance", headers=hu27.admin())
        assert r.status_code == 403 and hu27._codigo(r) == "NO_AUTORIZADO"
        otro = await c.post("/api/encuesta-publica/iniciar", json={
            "rubro_id": 1, "aviso_legal": {"version": hu27.settings.AVISO_LEGAL_VERSION, "aceptado": True},
            "captcha_token": "t"})
        h_enc = hu27._bearer(otro.json()["access_token"])
        assert (await c.get("/api/formacion/modulos/1", headers=h_enc)).status_code == 403

        # HU-30: si el servicio deja de estar habilitado, el recorrido se corta con 403
        import app.core.servicio_pagado as sp
        monkeypatch.setattr(sp, "servicio_habilitado", lambda empresa, hoy=None: False)
        r = await c.get("/api/formacion/avance", headers=x["hc"])
        assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE"
    _correr(esc)


@api
def test_api_modulo_fuera_del_plan_y_limite_de_intentos(hu27, monkeypatch):
    async def esc(c):
        x = await _cliente(hu27, c)
        h = x["hc"]
        assert (await c.get("/api/formacion/modulos/999", headers=h)).status_code == 404
        r = await c.get("/api/formacion/avance?evaluacion_id=987654", headers=h)
        assert r.status_code == 404
        for orden in (1, 2):
            await c.post(f"/api/formacion/modulos/1/lecciones/{orden}/vista", headers=h)
        monkeypatch.setattr(hu27.settings, "FORMACION_INTENTOS_DIA", 1)
        ids = await _ids_preguntas(c, h)
        r = await c.post("/api/formacion/modulos/1/verificacion", headers=h, json={"respuestas": {ids["¿Uno?"]: 0}})
        assert r.status_code == 200 and r.json()["intentos_restantes_hoy"] == 0
        r = await c.post("/api/formacion/modulos/1/verificacion", headers=h, json={"respuestas": {ids["¿Uno?"]: 2}})
        assert r.status_code == 429 and hu27._codigo(r) == "LIMITE_INTENTOS" and "Retry-After" in r.headers
    _correr(esc)
