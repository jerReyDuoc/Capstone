"""
HU-06 — Anonimización ANTES de persistir (BD, disco y logs).

El gateway de IA ya anonimiza lo que sale hacia el LLM; este servicio aplica el
mismo motor (SanitizerPort, etiquetas fijas [RUT_ANON], [NOMBRE_ANON], [CORREO_ANON],
[TEL_ANON], [DIRECCION_ANON], [DATO_CODIFICADO_ANON]) a lo que se GUARDA:

  - justificación del usuario      -> antes de escribir respuestas.justificacion_usuario
  - nombre del archivo de evidencia -> antes de escribir evidencias.nombre_archivo
  - contenido de la evidencia       -> el worker reemplaza el archivo cifrado por
                                       este texto anonimizado al terminar de validarla

Reglas:
  - Fail-closed: si el motor falla se lanza AnonimizacionError y NO se guarda nada
    (es preferible rechazar la petición que persistir PII en claro).
  - Si no se detecta ninguna entidad el texto se devuelve tal cual (el motor
    normaliza el texto; así no se altera lo que escribió el usuario sin motivo).
  - Con SANITIZER_ENABLED=false (solo depuración, prohibido en producción) no se
    anonimiza, igual que en el gateway (R6).
  - Las excepciones no incluyen el texto original (podría contener PII).
"""
from __future__ import annotations

import asyncio
import os
import re

from app.domain.ports.sanitizer_port import SanitizerPort

_EXTENSION_SEGURA = re.compile(r"^\.[A-Za-z0-9]{1,10}$")
MAX_NOMBRE_ARCHIVO = 255


class AnonimizacionError(RuntimeError):
    """No se pudo anonimizar: el dato NO debe persistirse. El mensaje es seguro (sin PII)."""


class AnonimizadorPII:
    def __init__(self, sanitizer: SanitizerPort | None, habilitado: bool = True):
        if habilitado and sanitizer is None:
            raise ValueError("Se requiere un SanitizerPort cuando la anonimización está habilitada")
        self.sanitizer = sanitizer
        self.habilitado = habilitado

    async def anonimizar(self, texto: str | None) -> str | None:
        """Texto con la PII reemplazada por etiquetas fijas (o el mismo si no tiene PII)."""
        if texto is None or not texto.strip() or not self.habilitado:
            return texto
        try:
            # El NER es CPU puro: en un hilo para no bloquear el event loop (T-04).
            resultado = await asyncio.to_thread(self.sanitizer.sanitizar, texto)
        except Exception as e:  # SanitizacionError o cualquier otra cosa
            raise AnonimizacionError(
                "No se pudo anonimizar el texto; por seguridad no se guardó."
            ) from e
        return resultado.texto if resultado.entidades else texto

    async def anonimizar_nombre_archivo(self, nombre: str | None) -> str:
        """
        "contrato_12.345.678-5.pdf" -> "contrato_[RUT_ANON].pdf". Los "_" se leen como
        espacios para que el motor reconozca nombres ("CV_Juan_Perez" -> "CV [NOMBRE_ANON]").
        La extensión se conserva solo si es simple (letras y números).
        """
        nombre = os.path.basename(nombre or "") or "evidencia"
        raiz, ext = os.path.splitext(nombre)
        if not _EXTENSION_SEGURA.match(ext or ""):
            raiz, ext = nombre, ""
        legible = raiz.replace("_", " ")
        anonimo = await self.anonimizar(legible)
        if anonimo == legible:
            return nombre[:MAX_NOMBRE_ARCHIVO]
        return (anonimo.replace(" ", "_") + ext)[:MAX_NOMBRE_ARCHIVO]
