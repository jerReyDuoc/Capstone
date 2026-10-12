"""Cálculo de métricas de la capa de IA (funciones puras, sin BD)."""
import pytest

from app.application.ai.metricas import (
    EntidadGold,
    FilaLlamada,
    evaluar_ner,
    precision_clasificacion,
    resumen_operacion,
)


def _fila(exito=True, tipo_error=None, latencia=100.0, conf=0.9, tin=1000, tout=200, costo=0.001,
          adv=None, sanitizado=True):
    return FilaLlamada(exito, tipo_error, latencia, tin, tout, costo, conf, adv, sanitizado)


def test_tasa_de_error_y_errores_por_tipo():
    filas = [_fila() for _ in range(7)] + [
        _fila(False, "rate_limit"), _fila(False, "rate_limit"), _fila(False, "sanitizacion"),
    ]
    r = resumen_operacion(filas, umbral_confianza=0.8)
    assert r["total_llamadas"] == 10 and r["fallidas"] == 3
    assert r["tasa_error"] == 0.3
    assert r["errores_por_tipo"]["rate_limit"] == {"cantidad": 2, "tasa": 0.2}
    assert r["errores_por_tipo"]["sanitizacion"]["cantidad"] == 1
    assert r["tokens"] == {"entrada": 7000, "salida": 1400}
    assert r["costo_estimado_usd"] == pytest.approx(0.007)


def test_latencia_baja_confianza_y_advertencias():
    filas = [_fila(latencia=l, conf=c, adv=a) for l, c, a in
             [(100, 0.9, None), (200, 0.5, None), (300, 0.95, ["divergencia_sin_explicar"]), (400, 0.7, None)]]
    r = resumen_operacion(filas, umbral_confianza=0.8)
    assert r["latencia_ms"]["p50"] == 250.0
    assert r["tasa_baja_confianza"] == 0.5
    assert r["tasa_salida_con_advertencias"] == 0.25


def test_resumen_sin_datos():
    r = resumen_operacion([], 0.8)
    assert r["tasa_error"] is None and r["latencia_ms"]["p50"] is None


def test_precision_del_modelo_contra_revision_humana():
    pares = [  # (llm, humano)
        ("cumplido", "cumplido"), ("cumplido", "cumplido"), ("cumplido", "parcialmente_cumplido"),
        ("no_cumplido", "no_cumplido"), ("parcialmente_cumplido", "no_cumplido"),
    ]
    r = precision_clasificacion(pares)
    assert r["n_revisadas"] == 5
    assert r["accuracy"] == 0.6 and r["tasa_error_modelo"] == 0.4
    assert r["por_clase"]["cumplido"]["precision"] == pytest.approx(0.6667, abs=1e-4)
    assert r["por_clase"]["cumplido"]["recall"] == 1.0
    assert r["por_clase"]["no_cumplido"]["recall"] == 0.5
    assert r["matriz_confusion"]["valores"]["parcialmente_cumplido"]["cumplido"] == 1


def test_precision_sin_revisiones():
    r = precision_clasificacion([])
    assert r["n_revisadas"] == 0 and r["accuracy"] is None


def test_evaluacion_ner_y_cobertura():
    gold = [EntidadGold("RUT", 0, 12), EntidadGold("NOMBRE", 20, 30), EntidadGold("CORREO", 40, 60)]
    pred = [EntidadGold("RUT", 0, 12), EntidadGold("DIRECCION", 20, 30), EntidadGold("TEL", 70, 80)]
    r = evaluar_ner([(gold, pred)])
    assert r["por_tipo"]["RUT"]["precision"] == 1.0
    assert r["por_tipo"]["NOMBRE"]["recall"] == 0.0     # mal etiquetado...
    assert r["cobertura_pii"] == pytest.approx(0.6667, abs=1e-4)  # ...pero sí quedó oculto
    assert r["por_tipo"]["CORREO"]["fn"] == 1 and r["por_tipo"]["TEL"]["fp"] == 1
