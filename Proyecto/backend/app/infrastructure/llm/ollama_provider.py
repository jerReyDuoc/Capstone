"""
Adaptador de LLMProviderPort para un MODELO LOCAL servido con Ollama (HU-07).

Con LLM_PROVIDER=ollama el texto no sale del servidor: el modelo corre en la misma red del
backend (servicio "ollama" del docker-compose, perfil `modelo-local`). Igual que con Groq, solo
transporta: recibe el prompt ya anonimizado y el schema Pydantic, y devuelve el objeto validado.

  - Salida estructurada: la API /api/chat de Ollama acepta un JSON Schema en `format` y
    restringe la generación a ese schema. La respuesta se vuelve a validar con Pydantic.
  - Reintentos acotados (LLM_REINTENTOS_SALIDA) cuando la salida no es JSON válido o no cumple
    el schema, como en Groq; los errores de red no se reintentan aquí.
  - Errores traducidos a TipoErrorLLM: el gateway los registra igual que los de Groq (R4).

Modelos sugeridos (admiten salida estructurada en Ollama): qwen2.5:7b-instruct o llama3.1:8b.
Descargar antes con `docker compose exec ollama ollama pull <modelo>`.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.domain.ports.llm_provider_port import (
    LLMProviderError,
    LLMProviderPort,
    LLMRequest,
    LLMResponse,
    TipoErrorLLM,
)


def _ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 2)


class OllamaProvider(LLMProviderPort):
    nombre = "ollama"

    def __init__(
        self,
        url: str,
        modelo_por_defecto: str,
        reintentos_salida: int = 1,
        keep_alive: str | None = "10m",
        cliente: httpx.AsyncClient | None = None,
    ):
        self.url = url.rstrip("/")
        self.modelo_por_defecto = modelo_por_defecto
        self._reintentos_salida = max(0, reintentos_salida)
        self._keep_alive = keep_alive
        self._cliente = cliente

    def _cuerpo(self, req: LLMRequest, modelo: str) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
            "stream": False,
            "format": req.schema.model_json_schema(),
            "options": {"temperature": req.temperatura, "num_predict": req.max_tokens_salida},
        }
        if self._keep_alive:
            cuerpo["keep_alive"] = self._keep_alive
        return cuerpo

    async def generar(self, req: LLMRequest) -> LLMResponse:
        modelo = req.modelo or self.modelo_por_defecto
        inicio = time.perf_counter()
        ultimo: LLMProviderError | None = None
        intentos = 1 + self._reintentos_salida
        for _ in range(intentos):
            try:
                return await self._una_llamada(req, modelo, inicio)
            except LLMProviderError as e:
                if e.tipo != TipoErrorLLM.SALIDA_INVALIDA:
                    raise
                ultimo = e
        raise LLMProviderError(
            TipoErrorLLM.SALIDA_INVALIDA,
            f"{ultimo} (tras {intentos} intento{'s' if intentos > 1 else ''})",
            _ms(inicio),
        )

    async def _post(self, cuerpo: dict, timeout: float) -> httpx.Response:
        if self._cliente is not None:
            return await self._cliente.post(f"{self.url}/api/chat", json=cuerpo, timeout=timeout)
        async with httpx.AsyncClient() as cliente:
            return await cliente.post(f"{self.url}/api/chat", json=cuerpo, timeout=timeout)

    async def _una_llamada(self, req: LLMRequest, modelo: str, inicio: float) -> LLMResponse:
        try:
            resp = await self._post(self._cuerpo(req, modelo), req.timeout_s)
        except httpx.TimeoutException:
            raise LLMProviderError(TipoErrorLLM.TIMEOUT, "Tiempo de espera agotado (modelo local)", _ms(inicio))
        except httpx.HTTPError as e:
            raise LLMProviderError(TipoErrorLLM.CONEXION,
                                   f"No se pudo conectar con el modelo local ({type(e).__name__})", _ms(inicio))

        if resp.status_code == 404:
            raise LLMProviderError(TipoErrorLLM.PROVEEDOR,
                                   f"HTTP 404: el modelo {modelo!r} no está descargado en Ollama", _ms(inicio))
        if resp.status_code >= 400:
            raise LLMProviderError(TipoErrorLLM.PROVEEDOR, f"HTTP {resp.status_code} del modelo local", _ms(inicio))

        try:
            cuerpo = resp.json()
        except ValueError:
            raise LLMProviderError(TipoErrorLLM.PROVEEDOR, "Respuesta del modelo local no es JSON", _ms(inicio))
        contenido = ((cuerpo.get("message") or {}).get("content") or "") if isinstance(cuerpo, dict) else ""
        if cuerpo.get("done_reason") == "length":
            raise LLMProviderError(
                TipoErrorLLM.SALIDA_INVALIDA,
                f"Respuesta truncada: se alcanzó el máximo de {req.max_tokens_salida} tokens de salida",
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
            data = req.schema.model_validate(datos)
        except ValidationError as e:
            campos = ", ".join(f"{'.'.join(map(str, x['loc']))}:{x['type']}" for x in e.errors()[:5])
            raise LLMProviderError(TipoErrorLLM.SALIDA_INVALIDA, f"La salida no cumple el schema ({campos})",
                                   _ms(inicio))
        return LLMResponse(
            data=data,
            proveedor=self.nombre,
            modelo=cuerpo.get("model") or modelo,
            tokens_entrada=cuerpo.get("prompt_eval_count"),
            tokens_salida=cuerpo.get("eval_count"),
            latencia_ms=_ms(inicio),
        )
