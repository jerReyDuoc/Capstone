"""
AIGateway: capa de Políticas e IA entre la lógica de negocio y el proveedor LLM.

Pipeline de `ejecutar(tarea, textos, datos, contexto)`:
  1. Router        -> PoliticaTarea de la tarea (prompt, schema, límites).
  2. Sanitización  -> cada texto no confiable pasa por el motor NER.
                      Excepción => se ABORTA (no se llama al LLM) y se registra.
  3. Auditoría     -> el mapa de entidades se guarda cifrado en BD (no va al LLM).
                      Si no se puede guardar => se aborta.
  4. Prompt        -> plantilla versionada, construida SOLO con texto sanitizado.
  5. Proveedor     -> LLMProviderPort (Groq hoy; intercambiable por config).
  6. Validación    -> schema Pydantic (en el proveedor) + reglas post-salida.
  7. Métricas      -> una fila en llamadas_llm por ejecución, con éxito o error.

Reglas de negocio implementadas aquí:
  R1 El texto original nunca se envía al LLM, solo el sanitizado.
  R2 El mapa de entidades se guarda en BD y no se envía al proveedor.
  R3 Si la sanitización falla se aborta y se registra el error.
  R4 Si el LLM falla se registra la métrica con exito=False y el tipo de error.
  R5 Etiquetas fijas por tipo (responsabilidad del SanitizerPort).
  R6 SANITIZER_ENABLED=false desactiva la sanitización (solo debug; la config
     impide arrancar así en producción).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.application.ai.politicas import PoliticaTarea, TareaIA
from app.domain.ports.llm_provider_port import LLMProviderError, LLMProviderPort, LLMRequest
from app.domain.ports.registro_ia_port import (
    ContextoLlamada,
    RegistroIAPort,
    RegistroLlamada,
    RegistroSanitizacion,
)
from app.domain.ports.sanitizer_port import SanitizacionError, SanitizerPort

logger = logging.getLogger("capa_ia")


# ---------------------------------------------------------------- errores tipados
class CapaIAError(Exception):
    """Error de la capa de IA. `mensaje_usuario` es seguro de mostrar (sin PII)."""
    tipo_error = "desconocido"

    def __init__(self, mensaje_usuario: str, tipo_error: str | None = None):
        super().__init__(mensaje_usuario)
        self.mensaje_usuario = mensaje_usuario
        if tipo_error:
            self.tipo_error = tipo_error


class SanitizacionAbortadaError(CapaIAError):
    tipo_error = "sanitizacion"


class AuditoriaNoDisponibleError(CapaIAError):
    tipo_error = "auditoria"


class LLMNoDisponibleError(CapaIAError):
    pass  # tipo_error = el TipoErrorLLM del proveedor


@dataclass
class ResultadoIA:
    data: BaseModel
    traza_id: str
    prompt_version: str
    modelo: str
    advertencias: list[str] = field(default_factory=list)
    sanitizado: bool = True


@dataclass(frozen=True)
class PreciosModelo:
    """USD por millón de tokens (para estimar costo en las métricas)."""
    entrada_usd_1m: float = 0.0
    salida_usd_1m: float = 0.0

    def costo(self, tin: int | None, tout: int | None) -> float | None:
        if tin is None or tout is None:
            return None
        return round((tin * self.entrada_usd_1m + tout * self.salida_usd_1m) / 1_000_000, 8)


# ---------------------------------------------------------------- gateway
class AIGateway:
    def __init__(
        self,
        provider: LLMProviderPort,
        sanitizer: SanitizerPort,
        registro: RegistroIAPort,
        politicas: dict[TareaIA, PoliticaTarea],
        sanitizer_enabled: bool = True,
        precios: PreciosModelo | None = None,
    ):
        self.provider = provider
        self.sanitizer = sanitizer
        self.registro = registro
        self.politicas = politicas
        self.sanitizer_enabled = sanitizer_enabled
        self.precios = precios or PreciosModelo()

    async def ejecutar(
        self,
        tarea: TareaIA,
        textos: dict[str, str | None],
        datos: dict[str, Any],
        contexto: ContextoLlamada | None = None,
    ) -> ResultadoIA:
        """
        `textos`: SOLO los campos no confiables declarados en la política (se sanitizan).
        `datos`:  datos de negocio confiables (control, respuesta...) que usa el prompt.
        """
        politica = self.politicas.get(tarea)
        if politica is None:
            raise ValueError(f"Tarea de IA sin política registrada: {tarea}")
        esperados = set(politica.campos_no_confiables)
        if set(textos) != esperados:
            # Evita que un texto de usuario entre al prompt por un camino no sanitizado
            raise ValueError(f"La tarea {tarea.value} espera exactamente los campos {sorted(esperados)}")

        contexto = contexto or ContextoLlamada()
        traza_id = uuid.uuid4().hex
        modelo = politica.modelo or self.provider.modelo_por_defecto
        base = dict(
            tarea=tarea.value,
            proveedor=self.provider.nombre,
            modelo=modelo,
            prompt_version=politica.prompt_version,
            contexto=contexto,
            traza_id=traza_id,
        )

        # 2-3. Sanitización + mapa de entidades -------------------------------
        textos_seguros, n_entidades = await self._sanitizar(politica, textos, contexto, traza_id, base)

        # 4. Prompt (solo con texto sanitizado) ------------------------------
        prompt = politica.construir_prompt(textos_seguros, datos)

        # 5-6. Proveedor + validación de salida ------------------------------
        inicio = time.perf_counter()
        try:
            respuesta = await self.provider.generar(LLMRequest(
                system=prompt.system,
                user=prompt.user,
                schema=politica.schema,
                modelo=politica.modelo,
                temperatura=politica.temperatura,
                max_tokens_salida=politica.max_tokens_salida,
                timeout_s=politica.timeout_s,
            ))
        except LLMProviderError as e:
            await self._metrica(
                base, exito=False, tipo_error=e.tipo.value, detalle_error=str(e)[:300],
                latencia_ms=e.latencia_ms or _ms(inicio), sanitizado=self.sanitizer_enabled,
                entidades=n_entidades,
            )
            logger.error("LLM falló (tarea=%s, tipo=%s, traza=%s)", tarea.value, e.tipo.value, traza_id)
            raise LLMNoDisponibleError(
                f"El servicio de IA no respondió correctamente ({e.tipo.value}).", e.tipo.value
            ) from e
        except Exception as e:  # error no previsto del adaptador: también es R4
            await self._metrica(
                base, exito=False, tipo_error="desconocido", detalle_error=type(e).__name__,
                latencia_ms=_ms(inicio), sanitizado=self.sanitizer_enabled, entidades=n_entidades,
            )
            logger.exception("Error inesperado del proveedor LLM (traza=%s)", traza_id)
            raise LLMNoDisponibleError("Error inesperado del servicio de IA.", "desconocido") from e

        advertencias = politica.validar_salida(respuesta.data)

        # 7. Métrica de éxito -----------------------------------------------
        await self._metrica(
            {**base, "modelo": respuesta.modelo or modelo},
            exito=True,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_estimado_usd=self.precios.costo(respuesta.tokens_entrada, respuesta.tokens_salida),
            latencia_ms=respuesta.latencia_ms or _ms(inicio),
            sanitizado=self.sanitizer_enabled,
            entidades=n_entidades,
            clasificacion=getattr(respuesta.data, "clasificacion", None),
            confianza=getattr(respuesta.data, "confianza", None),
            advertencias=advertencias,
        )
        return ResultadoIA(
            data=respuesta.data,
            traza_id=traza_id,
            prompt_version=politica.prompt_version,
            modelo=respuesta.modelo or modelo,
            advertencias=advertencias,
            sanitizado=self.sanitizer_enabled,
        )

    # ---------------------------------------------------------------- helpers
    async def _sanitizar(self, politica, textos, contexto, traza_id, base) -> tuple[dict[str, str], int]:
        if not self.sanitizer_enabled:
            # R6: modo debug. Nunca en producción (Settings lo impide).
            logger.critical(
                "SANITIZER_ENABLED=false: se envía texto SIN anonimizar al LLM (traza=%s). "
                "Solo para depuración.", traza_id,
            )
            return {
                campo: (textos[campo] or "")[:limite] if limite else (textos[campo] or "")
                for campo, limite in politica.campos_no_confiables.items()
            }, 0

        seguros: dict[str, str] = {}
        registros: list[RegistroSanitizacion] = []
        inicio = time.perf_counter()
        try:
            for campo, limite in politica.campos_no_confiables.items():
                # T-04: el NER es CPU puro; en un hilo para no bloquear el event loop
                # del worker (heartbeat de Redis, otras tareas, consultas a la BD).
                res = await asyncio.to_thread(self.sanitizer.sanitizar, textos[campo] or "", max_chars=limite)
                seguros[campo] = res.texto
                registros.append(RegistroSanitizacion(
                    campo=campo, entidades=res.entidades, motor=res.motor,
                    duracion_ms=res.duracion_ms, truncado=res.truncado,
                    contexto=contexto, traza_id=traza_id,
                ))
        except Exception as e:  # R3: SanitizacionError o cualquier otra cosa
            detalle = str(e) if isinstance(e, SanitizacionError) else type(e).__name__
            await self._metrica(base, exito=False, tipo_error="sanitizacion",
                                detalle_error=detalle[:300], latencia_ms=_ms(inicio))
            logger.error("Sanitización falló; NO se llama al LLM (traza=%s): %s", traza_id, detalle)
            raise SanitizacionAbortadaError(
                "No se pudo anonimizar el contenido; por seguridad no se envió al servicio de IA."
            ) from e

        try:
            await self.registro.guardar_sanitizaciones(registros)  # R2
        except Exception as e:
            await self._metrica(base, exito=False, tipo_error="auditoria",
                                detalle_error=type(e).__name__, latencia_ms=_ms(inicio))
            logger.exception("No se pudo guardar el mapa de entidades; se aborta (traza=%s)", traza_id)
            raise AuditoriaNoDisponibleError(
                "No se pudo registrar la auditoría de anonimización; no se envió al servicio de IA."
            ) from e

        return seguros, sum(len(r.entidades) for r in registros)

    async def _metrica(self, base: dict, *, exito: bool, entidades: int = 0,
                       sanitizado: bool = True, **campos) -> None:
        """Las métricas nunca rompen el flujo: si fallan, solo se loguea."""
        try:
            await self.registro.guardar_llamada(RegistroLlamada(
                **base, exito=exito, fecha=datetime.now(timezone.utc).replace(tzinfo=None),
                sanitizado=sanitizado, entidades_anonimizadas=entidades, **campos,
            ))
        except Exception:
            logger.exception("No se pudo registrar la métrica de IA (traza=%s)", base.get("traza_id"))


def _ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 2)
