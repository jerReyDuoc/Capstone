"""Puerto de envío de correo (informes, activación de cuenta, avisos). Sin dependencias de transporte."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CorreoNoDisponibleError(Exception):
    pass


class CorreoFallidoError(Exception):
    pass


@dataclass(frozen=True)
class Adjunto:
    nombre: str
    contenido: bytes
    tipo: str = "application/pdf"


class CorreoPort(Protocol):
    async def enviar(self, destino: str, asunto: str, texto: str, html: str | None,
                     adjuntos: list[Adjunto]) -> str:
        """Envía (o guarda) el mensaje. Devuelve el modo usado: "smtp" o "archivo"."""
        ...
