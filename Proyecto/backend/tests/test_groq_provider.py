"""
Pruebas del adaptador GroqProvider con el SDK real de Groq y un servidor HTTP
simulado (httpx.MockTransport): se verifica exactamente qué se envía a Groq y
cómo se interpreta cada respuesta, sin red ni API key.
"""
import asyncio
import json

import pytest

groq = pytest.importorskip("groq")
import httpx  # noqa: E402

from app.application.schemas.evidence_validation import EvidenceValidation  # noqa: E402
from app.domain.ports.llm_provider_port import LLMProviderError, LLMRequest, TipoErrorLLM  # noqa: E402
from app.infrastructure.llm.groq_provider import GroqProvider, esquema_estricto  # noqa: E402

SALIDA_OK = {
    "clasificacion": "parcialmente_cumplido",
    "confianza": 0.86,
    "justificacion": "El acta designa al encargado pero no documenta bases de licitud.",
    "respalda_clasificacion_usuario": False,
    "divergencia_explicada": "Falta el registro de bases de licitud.",
    "evidencia_suficiente": True,
    "datos_extraidos": [{"clave": "documento", "valor": "acta de directorio"}],
    "errores": None,
}


def _completion(contenido, finish="stop", modelo="openai/gpt-oss-20b"):
    return {
        "id": "chatcmpl-x", "object": "chat.completion", "created": 1, "model": modelo,
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": contenido}}],
        "usage": {"prompt_tokens": 1500, "completion_tokens": 320, "total_tokens": 1820},
    }


def _error(status, code, message="error simulado"):
    return status, {"error": {"message": message, "type": "invalid_request_error", "code": code,
                              "failed_generation": "TEXTO QUE NO DEBE APARECER"}}


class GroqFalso:
    """Responde en orden la lista de respuestas y guarda cada request."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        status, cuerpo = self.respuestas.pop(0)
        return httpx.Response(status, json=cuerpo)


def _proveedor(servidor, modelo="openai/gpt-oss-20b", reintentos_salida=1):
    cliente = groq.AsyncGroq(api_key="gsk_test", max_retries=0,
                             http_client=httpx.AsyncClient(transport=httpx.MockTransport(servidor)))
    return GroqProvider(api_key="gsk_test", modelo_por_defecto=modelo, max_reintentos=0,
                        reasoning_effort="low", reintentos_salida=reintentos_salida, cliente=cliente)


def _req(max_tokens=4096):
    return LLMRequest(system="reglas", user="evidencia [RUT_ANON]", schema=EvidenceValidation,
                      max_tokens_salida=max_tokens, timeout_s=10)


def _generar(prov, req=None):
    return asyncio.run(prov.generar(req or _req()))


# ---------------------------------------------------------------- schema estricto
def test_esquema_estricto_cumple_reglas_de_groq():
    esquema, campos_dict = esquema_estricto(EvidenceValidation.model_json_schema())
    assert campos_dict == {"datos_extraidos"}

    def revisar(nodo):
        if isinstance(nodo, dict):
            if nodo.get("type") == "object" or "properties" in nodo:
                assert nodo["additionalProperties"] is False
                assert set(nodo["required"]) == set(nodo["properties"])
            for clave in ("minimum", "maximum", "default"):
                assert clave not in nodo
            for v in nodo.values():
                revisar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                revisar(v)

    revisar(esquema)
    props = esquema["properties"]
    assert props["datos_extraidos"]["type"] == ["array", "null"]
    assert "null" in props["errores"]["type"]                       # opcional -> admite null
    assert props["clasificacion"]["enum"] == ["cumplido", "parcialmente_cumplido", "no_cumplido"]


# ---------------------------------------------------------------- request
def test_request_gpt_oss_20b_usa_salida_estricta_y_razonamiento_bajo():
    servidor = GroqFalso((200, _completion(json.dumps(SALIDA_OK))))
    _generar(_proveedor(servidor))
    body = servidor.requests[0]
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["reasoning_effort"] == "low" and body["include_reasoning"] is False
    assert body["max_completion_tokens"] == 4096 and body["temperature"] == 0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert "tools" not in body and "tool_choice" not in body       # ya no usa function calling


def test_request_safeguard_usa_best_effort_sin_reasoning_effort():
    servidor = GroqFalso((200, _completion(json.dumps(SALIDA_OK), modelo="openai/gpt-oss-safeguard-20b")))
    _generar(_proveedor(servidor, modelo="openai/gpt-oss-safeguard-20b"))
    body = servidor.requests[0]
    assert body["response_format"]["json_schema"]["strict"] is False
    assert "reasoning_effort" not in body


# ---------------------------------------------------------------- respuesta
def test_respuesta_valida_se_convierte_al_schema_de_negocio():
    r = _generar(_proveedor(GroqFalso((200, _completion(json.dumps(SALIDA_OK))))))
    assert isinstance(r.data, EvidenceValidation)
    assert r.data.clasificacion == "parcialmente_cumplido"
    assert r.data.datos_extraidos == {"documento": "acta de directorio"}   # pares -> dict
    assert r.data.errores == []                                           # null -> default
    assert (r.tokens_entrada, r.tokens_salida, r.proveedor) == (1500, 320, "groq")


def test_json_cortado_por_max_tokens_reintenta_y_luego_explica_la_causa():
    cortado = (200, _completion('{"clasificacion": "cump', finish="length"))
    servidor = GroqFalso(cortado, cortado)
    with pytest.raises(LLMProviderError) as exc:
        _generar(_proveedor(servidor), _req(max_tokens=1500))
    assert exc.value.tipo == TipoErrorLLM.SALIDA_INVALIDA
    assert "1500" in str(exc.value) and "LLM_MAX_TOKENS_SALIDA" in str(exc.value)
    assert len(servidor.requests) == 2                                  # 1 reintento


def test_400_json_validate_failed_se_reintenta_y_recupera():
    servidor = GroqFalso(_error(400, "json_validate_failed"), (200, _completion(json.dumps(SALIDA_OK))))
    r = _generar(_proveedor(servidor))
    assert r.data.clasificacion == "parcialmente_cumplido" and len(servidor.requests) == 2


def test_400_tool_use_failed_persistente_es_salida_invalida_con_detalle_seguro():
    servidor = GroqFalso(_error(400, "tool_use_failed"), _error(400, "tool_use_failed"))
    with pytest.raises(LLMProviderError) as exc:
        _generar(_proveedor(servidor))
    assert exc.value.tipo == TipoErrorLLM.SALIDA_INVALIDA
    assert "HTTP 400 tool_use_failed" in str(exc.value)
    assert "TEXTO QUE NO DEBE APARECER" not in str(exc.value)          # no filtra failed_generation


@pytest.mark.parametrize("status,code,tipo", [
    (404, "model_not_found", TipoErrorLLM.PROVEEDOR),
    (400, "model_decommissioned", TipoErrorLLM.PROVEEDOR),
    (413, "request_too_large", TipoErrorLLM.PROVEEDOR),
    (503, "service_unavailable", TipoErrorLLM.PROVEEDOR),
    (429, "rate_limit_exceeded", TipoErrorLLM.RATE_LIMIT),
    (401, "invalid_api_key", TipoErrorLLM.AUTENTICACION),
])
def test_errores_http_se_clasifican_sin_reintentar_y_con_codigo(status, code, tipo):
    servidor = GroqFalso(_error(status, code))
    with pytest.raises(LLMProviderError) as exc:
        _generar(_proveedor(servidor))
    assert exc.value.tipo == tipo
    assert f"HTTP {status} {code}" in str(exc.value)
    assert len(servidor.requests) == 1


def test_valor_fuera_de_rango_es_salida_invalida_sin_exponer_el_valor():
    malo = dict(SALIDA_OK, confianza=1.7, justificacion="VALOR-SECRETO")
    servidor = GroqFalso((200, _completion(json.dumps(malo))), (200, _completion(json.dumps(malo))))
    with pytest.raises(LLMProviderError) as exc:
        _generar(_proveedor(servidor))
    assert exc.value.tipo == TipoErrorLLM.SALIDA_INVALIDA
    assert "confianza" in str(exc.value) and "1.7" not in str(exc.value)


def test_sin_reintentos_de_salida_falla_al_primer_intento():
    servidor = GroqFalso(_error(400, "json_validate_failed"))
    with pytest.raises(LLMProviderError):
        _generar(_proveedor(servidor, reintentos_salida=0))
    assert len(servidor.requests) == 1
