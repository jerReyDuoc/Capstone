"""
Adaptador Groq de LLMProviderPort. Solo transporte: no conoce prompts ni negocio.

Para agregar otro proveedor (OpenAI, Azure, Ollama...): crear un adaptador con la
misma interfaz y registrarlo en app/infrastructure/llm/factory.py.
"""
import asyncio
import time

from langchain_groq import ChatGroq

from app.domain.ports.llm_provider_port import (
    LLMProviderError,
    LLMProviderPort,
    LLMRequest,
    LLMResponse,
    TipoErrorLLM,
)

# Excepciones del SDK de Groq / LangChain -> tipo de error de negocio (por nombre de
# clase para no acoplarse a la versión del SDK).
_MAPA_ERRORES = {
    "APITimeoutError": TipoErrorLLM.TIMEOUT,
    "TimeoutError": TipoErrorLLM.TIMEOUT,
    "RateLimitError": TipoErrorLLM.RATE_LIMIT,
    "AuthenticationError": TipoErrorLLM.AUTENTICACION,
    "PermissionDeniedError": TipoErrorLLM.AUTENTICACION,
    "APIConnectionError": TipoErrorLLM.CONEXION,
    "InternalServerError": TipoErrorLLM.PROVEEDOR,
    "APIStatusError": TipoErrorLLM.PROVEEDOR,
    "BadRequestError": TipoErrorLLM.PROVEEDOR,
    "ValidationError": TipoErrorLLM.SALIDA_INVALIDA,
    "OutputParserException": TipoErrorLLM.SALIDA_INVALIDA,
}


def _tipo_error(e: Exception) -> TipoErrorLLM:
    for cls in type(e).__mro__:
        if cls.__name__ in _MAPA_ERRORES:
            return _MAPA_ERRORES[cls.__name__]
    return TipoErrorLLM.DESCONOCIDO


class GroqProvider(LLMProviderPort):
    nombre = "groq"

    def __init__(self, api_key: str, modelo_por_defecto: str, max_reintentos: int = 2):
        self._api_key = api_key
        self.modelo_por_defecto = modelo_por_defecto
        # El SDK reintenta 429/5xx con backoff exponencial; acotado para no
        # multiplicar costos.
        self._max_reintentos = max_reintentos

    def _cliente(self, req: LLMRequest) -> ChatGroq:
        return ChatGroq(
            model=req.modelo or self.modelo_por_defecto,
            api_key=self._api_key,
            temperature=req.temperatura,
            max_tokens=req.max_tokens_salida,
            timeout=req.timeout_s,
            max_retries=self._max_reintentos,
        )

    async def generar(self, req: LLMRequest) -> LLMResponse:
        modelo = req.modelo or self.modelo_por_defecto
        llm = self._cliente(req).with_structured_output(req.schema, include_raw=True)
        inicio = time.perf_counter()
        try:
            # Tope duro por si los reintentos internos se alargan
            salida = await asyncio.wait_for(
                llm.ainvoke([("system", req.system), ("human", req.user)]),
                timeout=req.timeout_s * (self._max_reintentos + 1) + 5,
            )
        except Exception as e:
            raise LLMProviderError(_tipo_error(e), f"{type(e).__name__}", _ms(inicio)) from e

        latencia = _ms(inicio)
        raw, parsed = salida.get("raw"), salida.get("parsed")
        if parsed is None or salida.get("parsing_error") is not None:
            error = salida.get("parsing_error")
            raise LLMProviderError(
                TipoErrorLLM.SALIDA_INVALIDA,
                f"La salida no cumple el schema ({type(error).__name__ if error else 'vacía'})",
                latencia,
            )

        tin, tout = _uso_tokens(raw)
        meta = getattr(raw, "response_metadata", None) or {}
        return LLMResponse(
            data=parsed,
            proveedor=self.nombre,
            modelo=meta.get("model_name") or modelo,
            tokens_entrada=tin,
            tokens_salida=tout,
            latencia_ms=latencia,
        )


def _uso_tokens(raw) -> tuple[int | None, int | None]:
    uso = getattr(raw, "usage_metadata", None) or {}
    if uso:
        return uso.get("input_tokens"), uso.get("output_tokens")
    tu = (getattr(raw, "response_metadata", None) or {}).get("token_usage") or {}
    return tu.get("prompt_tokens"), tu.get("completion_tokens")


def _ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 2)
