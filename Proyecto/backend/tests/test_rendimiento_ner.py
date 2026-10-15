"""
T-04 · Optimización del motor NER: páginas en < 2,0 s sin sacrificar precisión.

Dos grupos de pruebas:
  1. Estructurales (NLP simulado, siempre corren): verifican que las optimizaciones
     siguen activas aunque la máquina sea rápida (la 2.ª pasada no reprocesa el
     documento, el NER no bloquea el event loop, filtros de precisión).
  2. Con el modelo real (es_core_news_md; se saltan si no está instalado):
     latencia por página, pipeline mínimo, modelo compartido y precisión contra el
     corpus etiquetado. Son las que respaldan el criterio de aceptación de T-04.

Ejecutar solo estas:  pytest tests/test_rendimiento_ner.py -v -s
Benchmark detallado:  python scripts/benchmark_ner.py --paginas 100 --evidencia 8000 --perfil
"""
import asyncio
import json
import statistics
import time
from types import SimpleNamespace

import pytest

from _capa_ia_fakes import StubNLP, crear_gateway, sanitizer_stub
from _corpus_ner import CHARS_POR_PAGINA, pagina_etiquetada, paginas
from app.application.ai.metricas import EntidadGold, evaluar_ner
from app.application.ai.politicas import TareaIA
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.domain.ports.sanitizer_port import ResultadoSanitizacion, SanitizerPort
from app.infrastructure.security import seguridad
from app.infrastructure.security.ner_sanitizer import NERSanitizer

LIMITE_POR_PAGINA_S = 2.0


class NLPContador(StubNLP):
    """StubNLP que registra qué textos recibe el modelo."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.textos = []

    def __call__(self, texto):
        self.textos.append(texto)
        return super().__call__(texto)


# ============================================================ 1. estructurales
def test_siglas_sueltas_no_disparan_la_segunda_pasada():
    """Antes, cualquier palabra en mayúscula (ISO, DPO, SAP) hacía procesar el
    documento entero dos veces."""
    nlp = NLPContador()
    NERSanitizer(lambda: nlp).sanitizar("El DPO revisó la política ISO 27001 y el contrato SAP. " * 40)
    assert len(nlp.textos) == 1


def test_segunda_pasada_solo_procesa_ventanas_pequenas():
    nlp = NLPContador(nombres=["María González Rojas"])
    texto = "Texto de relleno sin datos personales. " * 150 + "Aprobó MARÍA GONZÁLEZ ROJAS el acta. " \
        + "Más relleno sin datos. " * 150
    r = NERSanitizer(lambda: nlp).sanitizar(texto)
    assert "MARÍA" not in r.texto and "[NOMBRE_ANON]" in r.texto
    assert len(nlp.textos) == 2
    assert len(nlp.textos[1]) < 300 < len(texto)  # ventana, no el documento


def test_ventanas_cercanas_se_fusionan():
    texto = "x " * 50 + "JUAN PÉREZ y MARÍA SOTO firmaron" + " y" * 50
    ventanas = NERSanitizer._ventanas_mayusculas(texto)
    assert len(ventanas) == 1
    ini, fin = ventanas[0]
    assert texto[ini:fin].count("PÉREZ") == 1 and texto[ini:fin].count("SOTO") == 1


def test_el_ner_no_bloquea_el_event_loop_del_worker():
    """El sanitizador corre en un hilo: mientras procesa, otras corrutinas avanzan."""
    class Lento(SanitizerPort):
        def sanitizar(self, texto, max_chars=None):
            time.sleep(0.3)  # simula CPU del modelo
            return ResultadoSanitizacion(texto=texto[:max_chars] if max_chars else texto)

    gw = crear_gateway(sanitizer=Lento())
    ticks = []

    async def reloj():
        for _ in range(20):
            ticks.append(time.perf_counter())
            await asyncio.sleep(0.02)

    async def main():
        tarea = asyncio.create_task(reloj())
        await asyncio.sleep(0.05)  # el reloj ya está corriendo cuando empieza el NER
        await gw.ejecutar(
            TareaIA.VALIDAR_EVIDENCIA,
            textos={"evidencia": "texto", "justificacion": "texto"},
            datos={"control": SimpleNamespace(codigo_control="C", obligacion="o", evidencia_esperada="e"),
                   "respuesta": SimpleNamespace(estado_clasificacion="cumplido", justificacion_usuario="j"),
                   "brecha": None},
            contexto=ContextoLlamada(evaluacion_id=1, respuesta_id=1, evidencia_id=1),
        )
        await tarea

    asyncio.run(main())
    # 2 campos x 0,3 s bloqueantes = 0,6 s; si bloqueara, el reloj no avanzaría en ese lapso
    huecos = [b - a for a, b in zip(ticks, ticks[1:])]
    assert max(huecos) < 0.2


@pytest.mark.parametrize("texto,no_debe", [
    ("El tratamiento se ajusta a la Ley 21.719 sobre datos.", "[DIRECCION_ANON]"),
    ("Según el artículo 14 de la Ley 19.628.", "[DIRECCION_ANON]"),
])
def test_referencias_normativas_no_son_direcciones(texto, no_debe):
    s = NERSanitizer(lambda: StubNLP(lugares=["la Ley", "artículo"]))
    assert no_debe not in s.sanitizar(texto).texto


@pytest.mark.parametrize("span,esperado", [
    ("Presidenta del Directorio", None),
    ("Asistió la Presidenta del Directorio", None),
    ("Gerente General Pedro Soto", "Pedro Soto"),
    ("Sra. Camila Rojas", "Camila Rojas"),
])
def test_cargos_se_recortan_del_nombre(span, esperado):
    s = NERSanitizer(lambda: StubNLP(nombres=[span]))
    r = s.sanitizar(f"Lo aprobó {span} en sesión.")
    valores = [e.valor for e in r.entidades]
    assert valores == ([esperado] if esperado else [])


def test_cargo_mas_nombre_marcado_como_org_se_anonimiza():
    class NLPOrg(StubNLP):
        def __call__(self, texto):
            i = texto.find("Gerente General Pedro Soto Rojas")
            ents = [SimpleNamespace(label_="ORG", start_char=i, end_char=i + 32,
                                    text="Gerente General Pedro Soto Rojas")] if i >= 0 else []
            return SimpleNamespace(ents=ents)
    r = NERSanitizer(lambda: NLPOrg()).sanitizar("Lo aprobó el Gerente General Pedro Soto Rojas.")
    assert r.texto == "Lo aprobó el Gerente General [NOMBRE_ANON]."


def test_org_sin_cargo_no_se_toca():
    class NLPOrg(StubNLP):
        def __call__(self, texto):
            return SimpleNamespace(ents=[SimpleNamespace(label_="ORG", start_char=13, end_char=25,
                                                         text="Banco Estado")])
    assert NERSanitizer(lambda: NLPOrg()).sanitizar("Contrato con Banco Estado.").entidades == []


def test_correo_con_tildes_se_anonimiza_completo():
    r = sanitizer_stub().sanitizar("Escribir a matías.díaz@empresa.cl o a sebastián.muñoz@empresa.cl.")
    assert r.texto == "Escribir a [CORREO_ANON] o a [CORREO_ANON]."


# ============================================================ 2. modelo real
@pytest.fixture(scope="module")
def nlp_real():
    pytest.importorskip("spacy")
    from app.infrastructure.security.ner_sanitizer import cargar_spacy
    try:
        return cargar_spacy()
    except OSError:
        pytest.skip("modelo es_core_news_md no instalado")


def test_pipeline_minimo_y_modelo_compartido(nlp_real):
    assert nlp_real.pipe_names == ["ner"]
    assert seguridad._NLP is nlp_real  # seguridad.py no carga una segunda copia


def test_pipeline_minimo_da_las_mismas_entidades_que_el_completo(nlp_real):
    import spacy
    completo = spacy.load("es_core_news_md", disable=["parser", "lemmatizer"])
    for t in paginas(5):
        a = [(e.start_char, e.end_char, e.label_) for e in completo(t).ents]
        b = [(e.start_char, e.end_char, e.label_) for e in nlp_real(t).ents]
        assert a == b


def test_t04_cada_pagina_en_menos_de_2_segundos(nlp_real):
    s = NERSanitizer()
    textos = paginas(20)
    s.sanitizar(textos[0])  # el modelo ya está cargado; esto descarta el primer acceso a memoria
    tiempos = []
    for t in textos:
        ini = time.perf_counter()
        s.sanitizar(t)
        tiempos.append(time.perf_counter() - ini)
    p95 = sorted(tiempos)[int(len(tiempos) * 0.95) - 1]
    print(f"\nT-04: {len(textos)} páginas de {CHARS_POR_PAGINA} caracteres: "
          f"p50={statistics.median(tiempos) * 1000:.0f} ms p95={p95 * 1000:.0f} ms max={max(tiempos) * 1000:.0f} ms")
    assert max(tiempos) < LIMITE_POR_PAGINA_S


def test_t04_evidencia_completa_8000_caracteres(nlp_real):
    """El worker sanitiza hasta MAX_CHARS_EVIDENCIA_LLM (8.000) + margen: ~3 páginas."""
    s = NERSanitizer()
    doc = pagina_etiquetada(99, chars=8500)[0]
    ini = time.perf_counter()
    s.sanitizar(doc, max_chars=8000)
    dur = time.perf_counter() - ini
    assert dur < LIMITE_POR_PAGINA_S * 8500 / CHARS_POR_PAGINA


def test_precision_y_cobertura_en_corpus_etiquetado(nlp_real):
    """La optimización no puede costar precisión: cobertura de PII = 100 % y
    precisión >= 95 % sobre 40 páginas etiquetadas."""
    s = NERSanitizer()
    casos = []
    for i in range(40):
        texto, ents = pagina_etiquetada(i)
        norm, pos, gold = seguridad.normalizar(texto), {}, []
        for tipo, valor in ents:
            v = seguridad.normalizar(valor)
            k = norm.find(v, pos.get(v, 0))
            pos[v] = k + 1
            gold.append(EntidadGold(tipo, k, k + len(v)))
        pred = [EntidadGold(e.tipo.value, e.inicio, e.fin) for e in s.sanitizar(texto).entidades]
        casos.append((gold, pred))
    reporte = evaluar_ner(casos)
    print("\nPrecisión NER (corpus T-04):", json.dumps(reporte["micro"]), "cobertura:", reporte["cobertura_pii"])
    assert reporte["cobertura_pii"] == 1.0
    assert reporte["micro"]["precision"] >= 0.95
