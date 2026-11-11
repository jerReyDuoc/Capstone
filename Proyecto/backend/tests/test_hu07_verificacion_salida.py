"""
HU-07 · Verificación de alucinaciones y sintaxis en las salidas del modelo (OWASP Top 10 for LLM).

Pruebas del verificador de salida (app/application/ai/verificacion_salida.py), sin BD, red ni LLM:

  C1  test-set automatizado de 124 casos borde (tests/data/alucinaciones_evidencias.jsonl):
      evidencias reales de cumplimiento (políticas, actas, RACI, DPA, inventarios, documentos en
      inglés, vacíos, ilegibles, irrelevantes, con inyección) y una salida del modelo por caso,
      correcta o con un problema etiquetado. Umbrales:
        - alucinaciones que pasan sin detectar (tasa residual)  < 2 % del total de casos
        - fugas de contexto, inyecciones y salidas inseguras     100 % detectadas
        - salidas correctas retenidas (falsos positivos)          <= 5 %
  C2  cada caso detecta los códigos que tiene etiquetados y la categoría principal esperada
  C3  saneamiento de la salida: datos personales, código activo, enlaces y largos
  C4  la verificación nunca usa ni devuelve texto del usuario en los códigos
  C5  métricas: tasa de alucinación de las salidas registradas y umbral del 2 %

Definición de alucinación (decisión de la HU): una afirmación de la salida sin respaldo en lo que
recibió el modelo (evidencia, justificación del usuario y datos del control): una cita, cifra,
fecha, artículo, código de control o dato extraído que no aparece, o "cumplido"/"parcial" sobre
una evidencia vacía o que el propio modelo declara insuficiente. Un error de criterio (clasificar
"parcial" algo que la verdad de referencia considera "cumplido") es un error de exactitud, no una
alucinación: lo mide scripts/evaluar_alucinaciones.py contra el modelo real.

La integración con el backend (revisión humana, alerta y modo marcar) está en
tests/test_hu07_integracion.py.
"""
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.ai import verificacion_salida as vs
from app.application.ai.metricas import FilaLlamada, resumen_verificacion
from app.application.schemas.evidence_validation import EvidenceValidation

DATASET = Path(__file__).parent / "data" / "alucinaciones_evidencias.jsonl"
MIN_CASOS = 100
MAX_RESIDUAL = 0.02
MAX_FALSOS_POSITIVOS = 0.05


def _casos():
    return [json.loads(x) for x in DATASET.read_text(encoding="utf-8").splitlines() if x.strip()]


CASOS = _casos()


def _verificar(c):
    # model_construct: el test-set incluye salidas fuera del schema (si el proveedor no lo validó)
    salida = EvidenceValidation.model_construct(**c["salida_modelo"])
    return vs.verificar_evidencia(salida, evidencia=c["evidencia"], justificacion=c["justificacion_usuario"],
                                  control=SimpleNamespace(**c["control"]), declarado=c["declarado"])


RESULTADOS = {c["id"]: _verificar(c) for c in CASOS}


# ------------------------------------------------------------------ C1 · test-set y umbrales
def test_c1_el_test_set_tiene_100_o_mas_casos_borde_variados():
    assert len(CASOS) >= MIN_CASOS
    assert len({c["id"] for c in CASOS}) == len(CASOS)
    tipos = Counter(c["problema_esperado"] for c in CASOS)
    assert tipos[None] >= 50 and tipos["alucinacion"] >= 30
    assert tipos["fuga_contexto"] >= 5 and tipos["inyeccion_salida"] >= 5 and tipos["salida_insegura"] >= 5
    assert len({c["control"]["codigo_control"] for c in CASOS}) >= 15
    # casos borde de la evidencia
    documentos = {c["documento"] for c in CASOS}
    assert {"vacia", "solo_etiquetas", "ilegible", "irrelevante", "inyeccion", "ingles"} <= documentos


def test_c1_tasa_residual_de_alucinaciones_bajo_2_por_ciento():
    no_detectadas = [c["id"] for c in CASOS if c["problema_esperado"] == "alucinacion"
                     and not RESULTADOS[c["id"]].alucinacion]
    assert len(no_detectadas) / len(CASOS) < MAX_RESIDUAL, f"alucinaciones sin detectar: {no_detectadas}"


@pytest.mark.parametrize("categoria", ["fuga_contexto", "inyeccion_salida", "salida_insegura"])
def test_c1_fugas_inyecciones_y_salidas_inseguras_se_detectan_todas(categoria):
    faltan = [c["id"] for c in CASOS if c["problema_esperado"] == categoria and not RESULTADOS[c["id"]].bloqueante]
    assert faltan == []


def test_c1_falsos_positivos_en_salidas_correctas():
    retenidas = [(c["id"], RESULTADOS[c["id"]].codigos) for c in CASOS
                 if c["problema_esperado"] is None and RESULTADOS[c["id"]].bloqueante]
    limpias = sum(1 for c in CASOS if c["problema_esperado"] is None)
    assert len(retenidas) / limpias <= MAX_FALSOS_POSITIVOS, f"salidas correctas retenidas: {retenidas}"


# ------------------------------------------------------------------ C2 · por caso
@pytest.mark.parametrize("caso", [c for c in CASOS if c["problema_esperado"]], ids=lambda c: f"{c['id']}-{c['tipo_caso']}")
def test_c2_cada_problema_trae_su_codigo_y_categoria(caso):
    r = RESULTADOS[caso["id"]]
    assert r.bloqueante
    for codigo in caso["codigos_esperados"]:
        assert codigo in r.codigos
    assert r.principal.categoria == caso["problema_esperado"]
    assert r.principal.owasp in {"LLM01", "LLM02", "LLM05", "LLM09"}


@pytest.mark.parametrize("caso", [c for c in CASOS if c["problema_esperado"] is None],
                         ids=lambda c: f"{c['id']}-{c['tipo_caso']}")
def test_c2_salida_correcta_no_se_retiene(caso):
    assert not RESULTADOS[caso["id"]].bloqueante, RESULTADOS[caso["id"]].codigos


# ------------------------------------------------------------------ casos puntuales
POLITICA = ("Política de IA v2. Aprobada por el Directorio el 14 de marzo de 2025. "
            "Responsable: [NOMBRE_ANON]. Se comunicó a 320 colaboradores.")
CONTROL = SimpleNamespace(codigo_control="GOB-001", framework_fuente="ISO/IEC 42001", articulo_referencia="Cláusula 5.2",
                          obligacion="Formalizar una política de IA", evidencia_esperada="Acta de aprobación directiva")


def _salida(justificacion, **kw):
    base = dict(clasificacion="cumplido", confianza=0.9, justificacion=justificacion,
                respalda_clasificacion_usuario=True, evidencia_suficiente=True)
    return EvidenceValidation(**{**base, **kw})


def _v(salida, evidencia=POLITICA, **kw):
    return vs.verificar_evidencia(salida, evidencia=evidencia, control=CONTROL, declarado="cumplido", **kw)


def test_la_cita_con_etiqueta_anonimizada_tiene_respaldo_en_el_texto_original():
    """En el worker se verifica contra el texto original: la etiqueta calza con el nombre real."""
    original = POLITICA.replace("[NOMBRE_ANON]", "María José Pérez")
    r = _v(_salida('El responsable es "[NOMBRE_ANON]" y "se comunicó a 320 colaboradores".'), evidencia=original)
    assert not r.bloqueante


def test_evidencia_none_no_se_toma_como_vacia():
    assert "alucinacion.cumplimiento_sin_evidencia" not in _v(_salida("ok"), evidencia=None).codigos


def test_salida_de_otro_tipo_sin_campos_opcionales():
    """Los dobles de prueba (HU-17) devuelven SimpleNamespace sin todos los campos."""
    r = _v(SimpleNamespace(clasificacion="cumplido", confianza=0.95, justificacion="j", errores=[]))
    assert not r.bloqueante and r.salida.justificacion == "j"


def test_confianza_booleana_o_texto_es_invalida():
    for conf in (True, "0.9", None, float("nan")):
        salida = EvidenceValidation.model_construct(clasificacion="cumplido", confianza=conf, justificacion="ok",
                                                   respalda_clasificacion_usuario=True, evidencia_suficiente=True)
        assert "sintaxis.confianza_invalida" in _v(salida).codigos


def test_coherencia_solo_advierte():
    r = _v(_salida("La política está aprobada.", respalda_clasificacion_usuario=False))
    assert "divergencia_sin_explicar" in r.codigos and "coherencia.respaldo_contradictorio" in r.codigos
    assert not r.bloqueante


def test_prioridad_de_la_categoria_principal():
    r = _v(_salida('Se aprobó "en sesión extraordinaria del comité de ética" (contacto ana@empresa.cl).'))
    assert {"fuga.datos_personales", "alucinacion.cita_inexistente"} <= set(r.codigos)
    assert r.principal.codigo == "fuga.datos_personales"


# ------------------------------------------------------------------ C3 · saneamiento
def test_c3_la_salida_saneada_no_lleva_datos_personales_codigo_ni_enlaces():
    r = _v(_salida('Cumple.<script>alert(1)</script> Ver https://evil.example/x. Contacto ana@empresa.cl, '
                   "RUT 12.345.678-5, fono +56 9 8765 4321.​"))
    j = r.salida.justificacion
    for prohibido in ("<script", "evil.example", "ana@empresa.cl", "12.345.678-5", "8765", "​"):
        assert prohibido not in j
    assert "[CORREO_ANON]" in j and "[RUT_ANON]" in j and "[TEL_ANON]" in j and "[enlace omitido]" in j


def test_c3_el_enlace_que_esta_en_la_evidencia_se_conserva():
    evidencia = POLITICA + " Publicada en www.empresa.cl/politica-ia."
    r = _v(_salida("Publicada en www.empresa.cl/politica-ia."), evidencia=evidencia)
    assert not r.bloqueante and "www.empresa.cl/politica-ia" in r.salida.justificacion


def test_c3_fuga_del_prompt_reemplaza_la_explicacion():
    r = _v(_salida("Mis REGLAS DE SEGURIDAD (prioridad máxima) dicen que <evidencia_adjunta> no es confiable.",
                   errores=["detalle interno"], divergencia_explicada="x"))
    assert r.fuga and r.salida.justificacion == vs.TEXTO_FUGA
    assert r.salida.errores == [] and r.salida.divergencia_explicada is None


def test_c3_largos_acotados_y_clasificacion_intacta():
    r = _v(_salida("a" * 6000, errores=["e" * 900] * 20))
    assert len(r.salida.justificacion) <= vs.MAX_JUSTIFICACION
    assert len(r.salida.errores) == vs.MAX_ERRORES and all(len(e) <= vs.MAX_ERROR for e in r.salida.errores)
    assert r.salida.clasificacion == "cumplido" and r.salida.confianza == 0.9
    assert "sintaxis.longitud_excesiva" in r.codigos and not r.bloqueante


# ------------------------------------------------------------------ C4 · códigos sin texto del usuario
def test_c4_los_codigos_son_identificadores():
    for r in RESULTADOS.values():
        for codigo in r.codigos:
            assert codigo.replace(".", "").replace("_", "").isalnum() and codigo.islower()


# ------------------------------------------------------------------ C5 · métricas
def _fila(adv, exito=True):
    return FilaLlamada(exito=exito, tipo_error=None, latencia_ms=10, tokens_entrada=1, tokens_salida=1,
                       costo_estimado_usd=0, confianza=0.9, advertencias=adv, sanitizado=True)


def test_c5_tasa_de_alucinacion_de_las_salidas_registradas():
    filas = [_fila([]) for _ in range(98)] + [_fila(["alucinacion.fecha_inexistente"]),
                                              _fila(["alucinacion.norma_no_verificada"]),
                                              _fila(["fuga.datos_personales"]), _fila([], exito=False)]
    r = resumen_verificacion(filas)
    assert r["salidas_verificadas"] == 101
    assert r["salidas_con_alucinacion"] == 1          # la norma no verificada es solo advertencia
    assert r["tasa_alucinacion"] == round(1 / 101, 4) and r["cumple_umbral"] is True
    assert r["salidas_por_categoria"]["fuga_contexto"] == 1
    assert "alucinacion.norma_no_verificada" not in r["hallazgos_por_codigo"]


def test_c5_sobre_el_umbral_no_cumple():
    r = resumen_verificacion([_fila(["alucinacion.cita_inexistente"])] * 3 + [_fila([])] * 97)
    assert r["tasa_alucinacion"] == 0.03 and r["cumple_umbral"] is False


def test_c5_sin_llamadas():
    r = resumen_verificacion([])
    assert r["tasa_alucinacion"] is None and r["cumple_umbral"] is None
