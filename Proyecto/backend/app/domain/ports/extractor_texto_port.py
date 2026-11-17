"""Puerto de extracción de texto plano de archivos de evidencia (PDF, DOCX, TXT)."""
from __future__ import annotations

from typing import Protocol


class ArchivoIlegibleError(ValueError):
    codigo = "ARCHIVO_ILEGIBLE"


class ExtractorTextoPort(Protocol):
    def extraer_texto(self, contenido: bytes) -> str:
        """Texto plano del archivo para el NER y el LLM (normaliza viñetas). Lanza ArchivoIlegibleError."""
        ...
