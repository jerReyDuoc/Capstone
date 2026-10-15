"""
Adaptador Groq de LLMProviderPort. Solo transporte: no conoce prompts ni negocio.

Usa el SDK oficial de Groq con "Structured Outputs" (response_format json_schema)
en lugar del function calling de LangChain, que con los modelos gpt-oss producía
llamadas de herramienta inválidas (HTTP 400) de forma intermitente.

  - Modo ESTRICTO (decodificación restringida: la salida SIEMPRE cumple el schema)
    en los modelos que Groq lo admite: openai/gpt-oss-20b y openai/gpt-oss-120b.
  - Modo "best effort" en el resto (p. ej. openai/gpt-oss-safeguard-20b): puede
    fallar con HTTP 400; se reintenta una vez (LLM_REINTENTOS_SALIDA).
  - Razonamiento acotado (reasoning_effort) para que el razonamiento no consuma
    el presupuesto de tokens y deje el JSON cortado.

Para agregar otro proveedor (OpenAI, Azure, Ollama...): crear un adaptador con la
misma interfaz y registrarlo en app/infrastructure/llm/factory.py.
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from typing import Any

import groq
from pydantic import ValidationError

from app.domain.ports.llm_provider_port import (
    LLMProviderError,
    LLMProviderPort,
    LLMRequest,
    LLMResponse,
    TipoErrorLLM,
)

# Según la documentación de Groq (Structured Outputs / Reasoning).
MODELOS_SALIDA_ESTRICTA = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
MODELOS_CON_REASONING_EFFORT = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
# gpt-oss devuelve su razonamiento aparte; no lo necesitamos en la respuesta.
PREFIJO_GPT_OSS = "openai/gpt-oss"

# Códigos de error de Groq que significan "el modelo no generó una salida válida":
# son reintentables y se registran como salida_invalida, no como caída del proveedor.
_CODIGOS_SALIDA_INVALIDA = {"json_validate_failed", "tool_use_failed", "output_parse_failed"}

# Restricciones de JSON Schema que el modo estricto puede rechazar. Pydantic las
# vuelve a validar al recibir la respuesta, así que no se pierde ninguna regla.
_CLAVES_NO_ESTRICTAS = {
    "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "format", "minItems", "maxItems",
}

# Un único cliente HTTP por API key: reutiliza conexiones entre evidencias.
_CLIENTES: dict[str, groq.AsyncGroq] = {}


# ---------------------------------------------------------------- schema estricto
def esquema_estricto(schema: dict) -> tuple[dict, set[str]]:
    """
    Adapta el JSON Schema de Pydantic a las reglas del modo estricto de Groq:
    todos los campos en `required` (los opcionales pasan a admitir null),
    `additionalProperties: false` en todos los objetos y sin restricciones
    numéricas/de texto. Los diccionarios libres (p. ej. `datos_extraidos: dict`)
    no se pueden expresar en modo estricto: se envían como lista de pares
    {clave, valor} y se devuelven a dict al recibir la respuesta.

    Devuelve (schema_adaptado, nombres_de_campos_dict).
    """
    s = copy.deepcopy(schema)
    defs = s.pop("$defs", {})
    campos_dict: set[str] = set()

    def resolver(nodo: Any) -> Any:
        if isinstance(nodo, dict) and "$ref" in nodo:
            return resolver(copy.deepcopy(defs[nodo["$ref"].split("/")[-1]]))
        return nodo

    def es_dict_libre(p: dict) -> bool:
        return p.get("type") == "object" and "properties" not in p

    def anulable(p: dict) -> dict:
        if "anyOf" in p:
            if not any(o.get("type") == "null" for o in p["anyOf"]):
                p["anyOf"].append({"type": "null"})
        elif isinstance(p.get("type"), str):
            p["type"] = [p["type"], "null"]
        elif isinstance(p.get("type"), list) and "null" not in p["type"]:
            p["type"].append("null")
        if "enum" in p and None not in p["enum"]:
            p["enum"].append(None)
        return p

    def limpiar(nodo: Any, raiz: bool = False) -> Any:
        nodo = resolver(nodo)
        if isinstance(nodo, list):
            return [limpiar(n) for n in nodo]
        if not isinstance(nodo, dict):
            return nodo
        nodo = {k: limpiar(v) for k, v in nodo.items() if k not in _CLAVES_NO_ESTRICTAS}
        if nodo.get("type") == "object" and "properties" in nodo:
            requeridos = set(nodo.get("required", []))
            props = {}
            for nombre, p in nodo["properties"].items():
                if raiz and es_dict_libre(p):
                    campos_dict.add(nombre)
                    p = {
                        "type": "array",
                        "description": (p.get("description") or "") + " Lista de pares clave/valor.",
                        "items": {
                            "type": "object",
                            "properties": {"clave": {"type": "string"}, "valor": {"type": "string"}},
                            "required": ["clave", "valor"],
                            "additionalProperties": False,
                        },
                    }
                props[nombre] = p if nombre in requeridos else anulable(p)
            nodo["properties"] = props
            nodo["required"] = list(props)
            nodo["additionalProperties"] = False
        return nodo

    return limpiar(s, raiz=True), campos_dict


def _desde_estricto(datos: dict, campos_dict: set[str]) -> dict:
    """Revierte la adaptación: pares -> dict, y null en opcionales -> valor por defecto."""
    salida = {}
    for clave, valor in datos.items():
        if clave in campos_dict:
            valor = {str(p.get("clave")): p.get("valor") for p in (valor or []) if isinstance(p, dict)}
        if valor is None:
            continue  # Pydantic aplica el default del campo (None, [], {}...)
        salida[clave] = valor
    return salida


# ---------------------------------------------------------------- errores
def _detalle_http(e: groq.APIStatusError) -> tuple[str | None, str]:
    """(código de Groq, detalle seguro). Nunca incluye `failed_generation`."""
    cuerpo = e.body if isinstance(e.body, dict) else {}
    err = cuerpo.get("error", cuerpo) if isinstance(cuerpo, dict) else {}
    err = err if isinstance(err, dict) else {}
    codigo = err.get("code") or err.get("type")
    mensaje = str(err.get("message") or e.message or "")[:200]
    return codigo, f"HTTP {e.status_code}{' ' + codigo if codigo else ''}: {mensaje}"


def _traducir_error(e: Exception) -> tuple[TipoErrorLLM, str]:
    if isinstance(e, (groq.APITimeoutError, asyncio.TimeoutError)):
        return TipoErrorLLM.TIMEOUT, "Tiempo de espera agotado"
    if isinstance(e, groq.APIConnectionError):
        return TipoErrorLLM.CONEXION, "No se pudo conectar con Groq"
    if isinstance(e, groq.APIStatusError):
        codigo, detalle = _detalle_http(e)
        if isinstance(e, groq.RateLimitError):
            return TipoErrorLLM.RATE_LIMIT, detalle
        if isinstance(e, (groq.AuthenticationError, groq.PermissionDeniedError)):
            return TipoErrorLLM.AUTENTICACION, detalle
        if codigo in _CODIGOS_SALIDA_INVALIDA or "does not match the expected schema" in detalle:
            return TipoErrorLLM.SALIDA_INVALIDA, detalle
        return TipoErrorLLM.PROVEEDOR, detalle
    return TipoErrorLLM.DESCONOCIDO, type(e).__name__


# ---------------------------------------------------------------- proveedor
class GroqProvider(LLMProviderPort):
    nombre = "groq"

    def __init__(
        self,
        api_key: str,
        modelo_por_defecto: str,
        max_reintentos: int = 2,
        reasoning_effort: str = "low",
        reintentos_salida: int = 1,
        cliente: groq.AsyncGroq | None = None,
    ):
        self.modelo_por_defecto = modelo_por_defecto
        # Reintentos de red/429/5xx: los hace el SDK con backoff exponencial.
        self._max_reintentos = max_reintentos
        # Reintentos cuando el modelo genera una salida inválida (JSON cortado o
        # fuera del schema). Acotado para no multiplicar costos.
        self._reintentos_salida = max(0, reintentos_salida)
        self._reasoning_effort = reasoning_effort
        if cliente is None:
            if api_key not in _CLIENTES:
                _CLIENTES[api_key] = groq.AsyncGroq(api_key=api_key, max_retries=max_reintentos)
            cliente = _CLIENTES[api_key]
        self._cliente = cliente

    def _parametros(self, req: LLMRequest, modelo: str) -> dict:
        esquema, _ = esquema_estricto(req.schema.model_json_schema())
        params: dict[str, Any] = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "temperature": req.temperatura,
            "max_completion_tokens": req.max_tokens_salida,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": req.schema.__name__,
                    "schema": esquema,
                    "strict": modelo in MODELOS_SALIDA_ESTRICTA,
                },
            },
            "timeout": req.timeout_s,
        }
        if modelo.startswith(PREFIJO_GPT_OSS):
            params["include_reasoning"] = False
        if modelo in MODELOS_CON_REASONING_EFFORT and self._reasoning_effort:
            params["reasoning_effort"] = self._reasoning_effort
        return params

    async def generar(self, req: LLMRequest) -> LLMResponse:
        modelo = req.modelo or self.modelo_por_defecto
        inicio = time.perf_counter()
        intentos = 1 + self._reintentos_salida
        ultimo: LLMProviderError | None = None
        for _ in range(intentos):
            try:
                return await asyncio.wait_for(
                    self._una_llamada(req, modelo, inicio),
                    timeout=req.timeout_s * (self._max_reintentos + 1) + 5,
                )
            except LLMProviderError as e:
                if e.tipo != TipoErrorLLM.SALIDA_INVALIDA:
                    raise
                ultimo = e  # salida inválida: se reintenta
            except Exception as e:  # noqa: BLE001 - se traduce a un tipo de negocio
                tipo, detalle = _traducir_error(e)
                error = LLMProviderError(tipo, detalle, _ms(inicio))
                if tipo != TipoErrorLLM.SALIDA_INVALIDA:
                    raise error from e
                ultimo = error
        raise LLMProviderError(
            TipoErrorLLM.SALIDA_INVALIDA,
            f"{ultimo} (tras {intentos} intento{'s' if intentos > 1 else ''})",
            _ms(inicio),
        )

    async def _una_llamada(self, req: LLMRequest, modelo: str, inicio: float) -> LLMResponse:
        _, campos_dict = esquema_estricto(req.schema.model_json_schema())
        resp = await self._cliente.chat.completions.create(**self._parametros(req, modelo))

        choice = resp.choices[0] if resp.choices else None
        contenido = (choice.message.content if choice and choice.message else None) or ""
        if choice is not None and choice.finish_reason == "length":
            raise LLMProviderError(
                TipoErrorLLM.SALIDA_INVALIDA,
                f"Respuesta truncada: se alcanzó el máximo de {req.max_tokens_salida} tokens de salida "
                "(sube LLM_MAX_TOKENS_SALIDA)",
                _ms(inicio),
            )
        if not contenido.strip():
            raise LLMProviderError(TipoErrorLLM.SALIDA_INVALIDA, "Respuesta vacía del modelo", _ms(inicio))
        try:
            datos = json.loads(contenido)
            if not isinstance(datos, dict):
                raise ValueError("no es un objeto")
        except ValueError:
            raise LLMProviderError(TipoErrorLLM.SALIDA_INVALIDA, "La respuesta no es JSON válido", _ms(inicio))
        try:
            data = req.schema.model_validate(_desde_estricto(datos, campos_dict))
        except ValidationError as e:
            # Solo nombres de campo y tipo de error: nunca los valores.
            campos = ", ".join(f"{'.'.join(map(str, x['loc']))}:{x['type']}" for x in e.errors()[:5])
            raise LLMProviderError(
                TipoErrorLLM.SALIDA_INVALIDA, f"La salida no cumple el schema ({campos})", _ms(inicio)
            )

        uso = getattr(resp, "usage", None)
        return LLMResponse(
            data=data,
            proveedor=self.nombre,
            modelo=getattr(resp, "model", None) or modelo,
            tokens_entrada=getattr(uso, "prompt_tokens", None),
            tokens_salida=getattr(uso, "completion_tokens", None),
            latencia_ms=_ms(inicio),
        )


def _ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 2)
