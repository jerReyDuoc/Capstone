"""
QA - HU-21: informe del autodiagnóstico en PDF para el directorio o un auditor.

  Criterio 1  El PDF se genera con los datos de la API (no del navegador)
  Criterio 2  Aviso legal en la primera página y en el pie (HU-04), los 5 puntajes (HU-03),
              las brechas (HU-11) y las rutas (HU-12)
  Criterio 3  Fecha, código de evaluación y versión de la matriz

Ejecutar desde Proyecto/backend/:
    pytest tests/test_hu21_informe_pdf.py -v

Las pruebas de lógica y de PDF no necesitan BD (el texto del PDF se lee con pypdf). Las de
API corren en proceso (SQLite en memoria, ver _api_harness.py) y se omiten en modo live.
"""
import asyncio
import io
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.application.informes.analisis import ComparativaDominio, DominioResultado, FiltrosBrechas, parsear_filtros
from app.application.informes.ficha import (
    AVISO_INFORME,
    DIMENSIONES_OFICIALES,
    SIN_APLICABLES,
    cinco_puntajes,
    codigo_evaluacion,
    digito_verificador,
    huella_legible,
    huella_matriz,
    leer_codigo,
    version_matriz,
)
from dataclasses import replace

from test_hu12_plan_formativo import CATALOGO, DOMINIOS, RESPUESTAS as _RESPUESTAS_HU12


def _sin_codigo(b):
    # En los datos de HU-12 la descripción de la brecha repite su código ("Comportamiento ERR-…");
    # en la semilla real es una frase. Aquí se usa una frase para probar que el PDF no los muestra.
    return replace(b, comportamiento=f"Descripción de la brecha {b.id}") if b else None


RESPUESTAS = [replace(r, brecha_respuesta=_sin_codigo(r.brecha_respuesta), brecha_control=_sin_codigo(r.brecha_control),
                      control_obligacion=f"Obligación de la pregunta {r.id}")
              for r in _RESPUESTAS_HU12]


def _datos(**cambios):
    """Lo mismo que entrega carga.cargar_evaluacion (DatosEvaluacion), sin BD."""
    base = dict(
        evaluacion_id=123, fecha_inicio=date(2026, 10, 30), estado="completada", rubro="Retail",
        puntaje_general=55.5, controles_evaluados=6, en_revision=0, dominios=DOMINIOS,
        respuestas=RESPUESTAS, rutas=CATALOGO,
        comparativa=[ComparativaDominio(d.nombre, d.puntaje, None, 0, 75.0) for d in DOMINIOS],
        email_registrado=None, fecha_completado=datetime(2026, 11, 2, 15, 30),
        version_matriz="2026.1+3fa9c2d1", version_matriz_actual=None,
        aviso_aceptado_version="2026-10-v1", aviso_aceptado_fecha=datetime(2026, 10, 30, 12, 0),
        dimensiones_catalogo=tuple(sorted(d.nombre for d in DOMINIOS)),
    )
    base.update(cambios)
    return SimpleNamespace(**base)


def _informe(datos=None, generado=datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc), filtros=None):
    from app.application.informes.informe import construir_informe

    return construir_informe(datos or _datos(), filtros or FiltrosBrechas(), generado)


def _paginas(pdf: bytes) -> list[str]:
    pypdf = pytest.importorskip("pypdf")
    lector = pypdf.PdfReader(io.BytesIO(pdf))
    # pypdf corta las líneas largas: se normalizan los espacios para buscar frases
    return [re.sub(r"\s+", " ", pag.extract_text() or "") for pag in lector.pages]


def _pdf(informe) -> bytes:
    pytest.importorskip("reportlab")
    from app.application.informes.pdf_informe import generar_pdf

    return generar_pdf(informe)


# =====================================================================
# Criterio 3 · Código de evaluación, fecha y versión de la matriz
# =====================================================================
@pytest.mark.parametrize("numero,dv", [(11111111, "1"), (12345678, "5"), (1, "9"), (0, "0"), (6, "K")])
def test_digito_verificador_es_el_modulo_11_del_rut(numero, dv):
    assert digito_verificador(numero) == dv


def test_codigo_de_evaluacion_con_anio_numero_y_digito():
    codigo = codigo_evaluacion(123, 2026)
    assert re.fullmatch(r"CIA-2026-000123-[0-9K]", codigo)
    assert leer_codigo(codigo) == (2026, 123)
    assert leer_codigo(codigo.lower()) == (2026, 123)


@pytest.mark.parametrize("malo", ["", "CIA-2026-000123", "XYZ-2026-000123-1", "CIA-26-000123-1", "CIA-2026-123-1"])
def test_codigo_mal_formado_no_se_acepta(malo):
    assert leer_codigo(malo) is None


def test_codigo_mal_transcrito_se_detecta_por_el_digito():
    codigo = codigo_evaluacion(123, 2026)
    otro_dv = "0" if codigo[-1] != "0" else "1"
    assert leer_codigo(codigo[:-1] + otro_dv) is None
    # un dígito cambiado en el número también
    assert leer_codigo(codigo.replace("000123", "000132")) is None


def test_huella_de_la_matriz_no_depende_del_orden_y_cambia_con_el_contenido():
    filas = [(1, "DAT-001", 1, "¿Hay registro?", "Siempre", "Alta", "Art. 14", 1),
             (2, "GOB-001", 2, "¿Hay política?", "Siempre", "Media", "Art. 3", None)]
    h = huella_matriz(filas)
    assert h == huella_matriz(list(reversed(filas))) and len(h) == 64
    cambiada = [filas[0][:5] + ("Baja",) + filas[0][6:], filas[1]]
    assert huella_matriz(cambiada) != h
    assert version_matriz("2026.1", h) == f"2026.1+{h[:8]}"


def test_la_ficha_trae_codigo_fechas_y_version_de_la_matriz_registrada():
    f = _informe().ficha
    assert f.codigo == codigo_evaluacion(123, 2026)
    assert f.fecha_evaluacion == date(2026, 10, 30) and f.fecha_completado == datetime(2026, 11, 2, 15, 30)
    assert f.version_matriz == "2026.1+3fa9c2d1" and f.version_matriz_registrada is True


def test_evaluacion_antigua_usa_la_version_vigente_y_lo_avisa():
    f = _informe(_datos(version_matriz=None, version_matriz_actual="2026.1+aaaabbbb")).ficha
    assert f.version_matriz == "2026.1+aaaabbbb" and f.version_matriz_registrada is False
    pag1 = _paginas(_pdf(_informe(_datos(version_matriz=None, version_matriz_actual="2026.1+aaaabbbb"))))[0]
    assert "anterior al registro de versión" in pag1


def test_portada_del_pdf_lleva_fecha_codigo_y_version():
    informe = _informe()
    pag1 = _paginas(_pdf(informe))[0]
    assert informe.ficha.codigo in pag1
    assert "Versión de la matriz" in pag1 and "2026.1+3fa9c2d1" in pag1
    assert "Fecha de la evaluación" in pag1 and "02-11-2026" in pag1   # 15:30 UTC = 12:30 en Chile
    assert "Emitido el" in pag1


# =====================================================================
# Criterio 2 · Aviso legal (HU-04), 5 puntajes (HU-03), brechas (HU-11), rutas (HU-12)
# =====================================================================
def test_aviso_legal_completo_en_la_primera_pagina():
    pag1 = _paginas(_pdf(_informe()))[0]
    assert "Aviso legal" in pag1
    assert "no certifica el cumplimiento de la Ley N.º 21.719" in pag1   # HU-04 C3
    assert "no constituye asesoría legal" in pag1
    assert "responsabilidad de la organización" in pag1
    assert "versión 2026-10-v1" in pag1   # lo que aceptó el encuestado antes de responder


def test_aviso_legal_y_pagina_x_de_y_en_el_pie_de_todas_las_paginas():
    paginas = _paginas(_pdf(_informe()))
    assert len(paginas) >= 2
    for i, texto in enumerate(paginas, start=1):
        assert AVISO_INFORME.pie in texto, f"falta el aviso en el pie de la página {i}"
        assert f"Página {i} de {len(paginas)}" in texto
        assert _informe().ficha.codigo in texto


def test_siempre_cinco_puntajes_en_el_orden_de_hu03():
    p = cinco_puntajes(55.5, 6, DOMINIOS)
    assert [x.nombre for x in p] == ["Global", *DIMENSIONES_OFICIALES]
    assert p[0].es_global and p[0].puntaje == 55.5


def test_dimension_sin_preguntas_aplicables_se_informa_y_no_desaparece():
    sin_riesgos = [d for d in DOMINIOS if d.nombre != "Gestión de Riesgos"]
    p = {x.nombre: x for x in cinco_puntajes(50, 5, sin_riesgos, ["Gestión de Riesgos"])}
    assert len(p) == 5
    assert p["Gestión de Riesgos"].puntaje is None and p["Gestión de Riesgos"].nivel == SIN_APLICABLES


def test_las_dimensiones_salen_del_catalogo_de_la_bd():
    # Una instalación con otro catálogo (como _api_harness.py) no recibe dimensiones inventadas
    catalogo = ["Datos", "Gobernanza", "Riesgos", "Seguridad"]
    dominios = [DominioResultado(1, "Datos", 50.0, "en_desarrollo", 6),
                DominioResultado(2, "Gobernanza", 40.0, "en_desarrollo", 5)]
    p = cinco_puntajes(45, 11, dominios, catalogo)
    assert [x.nombre for x in p] == ["Global", "Datos", "Gobernanza", "Riesgos", "Seguridad"]
    assert p[3].puntaje is None and p[3].nivel == SIN_APLICABLES


def test_dimension_extra_de_la_bd_no_se_pierde():
    extra = [*DOMINIOS, DominioResultado(9, "Ciberseguridad", 40.0, "en_desarrollo", 3)]
    nombres = [x.nombre for x in cinco_puntajes(50, 9, extra)]
    assert nombres[:5] == ["Global", *DIMENSIONES_OFICIALES] and nombres[-1] == "Ciberseguridad"


def test_pdf_trae_los_5_puntajes_las_brechas_y_las_rutas():
    paginas = _paginas(_pdf(_informe()))
    pag1, todo = paginas[0], " ".join(paginas)
    assert "Puntajes de madurez" in pag1 and "Puntaje global" in pag1
    for dim in DIMENSIONES_OFICIALES:
        assert dim in pag1
    assert "55,5" in pag1 and "62,5" in pag1
    assert "Brechas priorizadas" in todo
    assert "Plan formativo recomendado" in todo
    assert "Protección de Datos - Inicial" in todo   # una ruta del plan


def test_el_pdf_no_muestra_codigos_internos():
    todo = " ".join(_paginas(_pdf(_informe())))
    assert not re.search(r"\b(ERR-)?[A-Z]{3}-\d{3}\b", todo), "el informe del cliente no lleva códigos internos"


def test_portada_resume_el_listado_completo_aunque_se_filtre():
    filtrado = _informe(filtros=parsear_filtros("Crítica", None, None, None))
    completo = _informe()
    assert len(filtrado.brechas) < len(completo.brechas)
    assert filtrado.brechas_total == completo.brechas_total
    assert filtrado.ficha.huella == completo.ficha.huella


# =====================================================================
# Huella de los resultados (verificación del auditor)
# =====================================================================
def test_huella_estable_entre_descargas_y_sensible_a_los_resultados():
    a = _informe(generado=datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)).ficha.huella
    b = _informe(generado=datetime(2026, 12, 24, 9, 0, tzinfo=timezone.utc)).ficha.huella
    assert a == b
    otros = [DominioResultado(d.dominio_id, d.nombre, (d.puntaje or 0) + 1, d.nivel_madurez) for d in DOMINIOS]
    assert _informe(_datos(dominios=otros)).ficha.huella != a
    assert re.fullmatch(r"[0-9A-F]{4}( [0-9A-F]{4}){3}", huella_legible(a))


def test_la_huella_del_pdf_es_la_de_la_ficha():
    from app.application.informes.informe import ficha_a_dict

    informe = _informe()
    ficha = ficha_a_dict(informe)
    assert ficha["huella_corta"] in " ".join(_paginas(_pdf(informe)))
    assert ficha["codigo"] == informe.ficha.codigo


def test_ficha_json_tiene_lo_que_muestra_la_pagina_sin_codigos_internos():
    from app.application.informes.informe import ficha_a_dict

    f = ficha_a_dict(_informe())
    assert {"codigo", "fecha_evaluacion", "fecha_completado", "version_matriz", "version_matriz_registrada",
            "aviso_legal", "puntajes", "brechas", "rutas", "huella", "huella_corta", "archivo"} <= set(f)
    assert len(f["puntajes"]) == 5 and f["puntajes"][0]["global"] is True
    assert f["aviso_legal"]["pie"] == AVISO_INFORME.pie and f["aviso_legal"]["parrafos"]
    assert f["brechas"]["total"] == 4 and len(f["brechas"]["principales"]) == 3
    assert f["rutas"]["modulos"] > 0 and f["rutas"]["horas"] > 0
    assert not re.search(r"\b(ERR-)?[A-Z]{3}-\d{3}\b", str(f))


# =====================================================================
# API (en proceso) · Criterio 1: el PDF sale de los datos guardados en la BD
# =====================================================================
try:
    import httpx  # noqa: F401
    import aiosqlite  # noqa: F401
    _HAY_API = True
except ImportError:
    _HAY_API = False

api = pytest.mark.skipif(not _HAY_API, reason="requiere httpx y aiosqlite (pip install -r requirements.txt)")


def _correr(escenario):
    from _api_harness import EVAL_ID, MODO, TODOS_LOS_CONTROLES, cliente_api
    if MODO == "live":
        pytest.skip("cambian el estado de la evaluación; solo en proceso")

    async def _main():
        async with cliente_api() as c:
            await escenario(c, EVAL_ID, TODOS_LOS_CONTROLES)
    asyncio.run(_main())


@api
def test_api_ficha_404_sin_resultados():
    async def esc(c, eval_id, todos):
        r = await c.get(f"/api/evaluaciones/{eval_id}/informe/ficha")
        assert r.status_code == 404 and r.json()["detail"]["codigo"] == "SIN_RESULTADOS"
    _correr(esc)


@api
def test_api_completar_registra_la_version_de_la_matriz_y_el_pdf_la_imprime():
    pytest.importorskip("reportlab")
    from test_hu12_plan_formativo import _completar

    async def esc(c, eval_id, todos):
        await _completar(c, eval_id, todos)
        r = await c.get(f"/api/evaluaciones/{eval_id}/informe/ficha")
        assert r.status_code == 200, r.text
        ficha = r.json()
        assert r.headers["cache-control"] == "no-store"
        assert leer_codigo(ficha["codigo"]) is not None and leer_codigo(ficha["codigo"])[1] == eval_id
        assert ficha["version_matriz_registrada"] is True
        assert re.fullmatch(r".+\+[0-9a-f]{8}", ficha["version_matriz"])
        assert len(ficha["puntajes"]) == 5

        pdf = await c.get(f"/api/evaluaciones/{eval_id}/informe/pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        paginas = _paginas(pdf.content)
        assert ficha["codigo"] in paginas[0] and ficha["version_matriz"] in paginas[0]
        assert ficha["huella_corta"] in " ".join(paginas)
        assert all(AVISO_INFORME.pie in p for p in paginas)
    _correr(esc)
