"""
Pruebas del motor NER de sanitización, del cifrado del mapa y de su precisión
contra un set etiquetado (tests/data/ner_gold.jsonl).

Las pruebas de reglas usan un NLP falso (no requieren spaCy). La prueba de
precisión con el modelo real se ejecuta solo si es_core_news_md está instalado.
"""
import base64
import json
import re
from pathlib import Path

import pytest

from _capa_ia_fakes import StubNLP, sanitizer_stub
from app.application.ai.metricas import EntidadGold, evaluar_ner
from app.domain.ports.sanitizer_port import ETIQUETAS, SanitizacionError, TipoEntidad
from app.infrastructure.security import seguridad
from app.infrastructure.security.cifrado import CifradorEntidades, ClaveCifradoInvalida
from app.infrastructure.security.ner_sanitizer import NERSanitizer, dv_rut, rut_valido

GOLD = [json.loads(l) for l in (Path(__file__).parent / "data" / "ner_gold.jsonl").read_text("utf-8").splitlines() if l.strip()]
NOMBRES_GOLD = [e["valor"] for c in GOLD for e in c["entidades"] if e["tipo"] == "NOMBRE"]
CLAVE = "dGVzdC1rZXktc29sby1wYXJhLXB5dGVzdC0xMjM0NTY="


# ---------------------------------------------------------------- RUT
@pytest.mark.parametrize("cuerpo,dv", [("12345678", "5"), ("11111111", "1"), ("76123456", "0")])
def test_digito_verificador(cuerpo, dv):
    assert dv_rut(cuerpo) == dv


def test_rut_valido():
    assert rut_valido("12.345.678-5")
    assert not rut_valido("12.345.678-9")


@pytest.mark.parametrize("texto", [
    "RUT 12.345.678-5", "rut 12345678-5", "RUT 12.345.678-9",  # formato explícito: aunque el DV falle
    "123456785",                                                # sin formato pero DV válido
    "cédula: 12345678",                                         # contexto
])
def test_rut_se_anonimiza(texto):
    r = sanitizer_stub().sanitizar(texto)
    assert "[RUT_ANON]" in r.texto and not re.search(r"\d{6}", r.texto)


@pytest.mark.parametrize("texto", ["Monto aprobado $15000000.", "Folio 20240315 del acta."])
def test_montos_y_folios_no_se_confunden_con_rut(texto):
    assert sanitizer_stub().sanitizar(texto).texto == texto


# ---------------------------------------------------------------- otros tipos
@pytest.mark.parametrize("texto,etiqueta", [
    ("contacto juan.perez@empresa.cl", "[CORREO_ANON]"),
    ("contacto juan punto perez arroba empresa punto cl", "[CORREO_ANON]"),
    ("contacto j.soto [at] acme (dot) cl", "[CORREO_ANON]"),
    ("llamar al +56 9 8765 4321", "[TEL_ANON]"),
    ("llamar al 987654321", "[TEL_ANON]"),
    ("vive en Av. Providencia 1234, depto 56, Providencia", "[DIRECCION_ANON]"),
    ("vive en Pasaje Los Aromos 77", "[DIRECCION_ANON]"),
    ("firmó Juan Pérez", "[NOMBRE_ANON]"),
])
def test_cada_tipo_usa_su_etiqueta_fija(texto, etiqueta):
    assert etiqueta in sanitizer_stub().sanitizar(texto).texto

@pytest.mark.parametrize("complemento", ["oficina 501", "of. 501", "depto 56", "departamento 12B"])
def test_direccion_incluye_el_numero_del_complemento(complemento):
    r = sanitizer_stub().sanitizar(f"Av. Providencia 1234, {complemento}, Providencia.")
    assert r.texto == "[DIRECCION_ANON]." and r.entidades[0].valor.endswith("Providencia")

def test_direccion_sin_prefijo_via_ner():
    s = NERSanitizer(lambda: StubNLP(lugares=["Los Leones"]))
    assert s.sanitizar("Bodega en Los Leones 456.").texto == "Bodega en [DIRECCION_ANON]."


def test_dato_codificado_con_pii():
    b64 = base64.b64encode("mi rut es 12.345.678-5".encode()).decode()
    assert sanitizer_stub().sanitizar(f"ver {b64}").texto == "ver [DATO_CODIFICADO_ANON]"


def test_nombres_en_mayusculas_y_siglas_protegidas():
    s = NERSanitizer(lambda: StubNLP(nombres=["María González"]))
    r = s.sanitizar("Aprobado por MARÍA GONZÁLEZ y revisado por el DPO y SAP.")
    assert "MARÍA" not in r.texto and "DPO" in r.texto and "SAP" in r.texto


# ---------------------------------------------------------------- reglas de negocio
def test_r5_etiquetas_consistentes_sin_numerar():
    texto = "RUT 12.345.678-5, otra vez 12.345.678-5 y otro 11.111.111-1; Juan Pérez y María González."
    r = sanitizer_stub().sanitizar(texto)
    assert r.texto.count("[RUT_ANON]") == 3 and r.texto.count("[NOMBRE_ANON]") == 2
    assert not re.search(r"\[[A-Z_]+_\d+\]", r.texto)
    assert set(re.findall(r"\[[A-Z_]+\]", r.texto)) <= ETIQUETAS


def test_mapa_de_entidades_con_offsets():
    texto = "Firmó Juan Pérez, RUT 12.345.678-5."
    r = sanitizer_stub().sanitizar(texto)
    norm = seguridad.normalizar(texto)
    assert [(e.tipo, e.valor) for e in r.entidades] == [
        (TipoEntidad.NOMBRE, "Juan Pérez"), (TipoEntidad.RUT, "12.345.678-5")]
    for e in r.entidades:
        assert norm[e.inicio:e.fin] == e.valor
    assert r.conteo_por_tipo() == {"NOMBRE": 1, "RUT": 1}


def test_recorte_no_deja_pii_a_medias():
    # El RUT empieza antes del límite y termina después: debe quedar la etiqueta completa
    texto = "x" * 95 + " 12.345.678-5 resto del documento"
    r = sanitizer_stub().sanitizar(texto, max_chars=100)
    assert r.texto.endswith("[RUT_ANON]") and r.truncado
    assert "12" not in r.texto


@pytest.mark.parametrize("loader", [
    lambda: (_ for _ in ()).throw(OSError("modelo no instalado")),
    lambda: None,
])
def test_r3_fail_closed_si_el_motor_no_carga(loader):
    with pytest.raises(SanitizacionError):
        NERSanitizer(loader).sanitizar("Juan Pérez, RUT 12.345.678-5")


def test_r3_fail_closed_si_el_nlp_explota():
    class Explota(StubNLP):
        def __call__(self, t):
            raise MemoryError()
    with pytest.raises(SanitizacionError) as exc:
        NERSanitizer(lambda: Explota()).sanitizar("Juan Pérez, RUT 12.345.678-5")
    assert "12.345" not in str(exc.value)  # el error no filtra el texto


# ---------------------------------------------------------------- cifrado
def test_cifrado_ida_y_vuelta_y_huella():
    c = CifradorEntidades(CLAVE)
    datos = [{"tipo": "RUT", "valor": "12.345.678-5"}]
    token = c.cifrar_json(datos)
    assert "12.345" not in token and c.descifrar_json(token) == datos
    assert c.huella("12.345.678-5") == c.huella("12345678-5")  # normaliza formato
    assert c.huella("12.345.678-5") != c.huella("11.111.111-1")


def test_clave_invalida():
    with pytest.raises(ClaveCifradoInvalida):
        CifradorEntidades("no-es-una-clave")
    with pytest.raises(ClaveCifradoInvalida):
        CifradorEntidades("")


# ---------------------------------------------------------------- precisión (gold set)
def _evaluar(sanitizer):
    casos = []
    for caso in GOLD:
        norm = seguridad.normalizar(caso["texto"])
        gold = []
        for e in caso["entidades"]:
            i = norm.find(seguridad.normalizar(e["valor"]))
            assert i >= 0, e
            gold.append(EntidadGold(e["tipo"], i, i + len(e["valor"])))
        pred = [EntidadGold(e.tipo.value, e.inicio, e.fin) for e in sanitizer.sanitizar(caso["texto"]).entidades]
        casos.append((gold, pred))
    return evaluar_ner(casos)


def test_precision_reglas_con_nlp_simulado():
    """Con el NLP simulado (nombres conocidos) mide la parte de reglas del motor."""
    reporte = _evaluar(NERSanitizer(lambda: StubNLP(NOMBRES_GOLD, ["Los Leones"])))
    print("\nReporte NER (NLP simulado):", json.dumps(reporte, indent=2, ensure_ascii=False))
    assert reporte["cobertura_pii"] == 1.0
    assert reporte["micro"]["precision"] >= 0.95


def test_precision_con_spacy_real():
    """Precisión real del motor. Umbral de cobertura alto: una entidad no cubierta es una fuga."""
    pytest.importorskip("spacy")
    try:
        from app.infrastructure.security.ner_sanitizer import cargar_spacy
        cargar_spacy()
    except OSError:
        pytest.skip("modelo es_core_news_md no instalado")
    reporte = _evaluar(NERSanitizer())
    print("\nReporte NER (spaCy):", json.dumps(reporte, indent=2, ensure_ascii=False))
    assert reporte["cobertura_pii"] >= 0.9
