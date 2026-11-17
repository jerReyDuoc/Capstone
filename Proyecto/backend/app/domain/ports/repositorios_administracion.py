"""Puertos de repositorio de administración: matriz normativa, métricas de IA y recálculo del benchmark."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.models.llamada_llm import LlamadaLlm
from app.domain.models.matriz_version import MatrizVersion
from app.domain.models.sanitizacion import Sanitizacion


class MatrizRepositoryPort(Protocol):
    """Acceso a la matriz normativa versionada (HU-24)."""

    async def publicada(self) -> MatrizVersion | None: ...

    async def borrador(self) -> MatrizVersion | None: ...

    async def obtener(self, version_id: int) -> MatrizVersion | None: ...

    async def listar(self) -> list[MatrizVersion]: ...

    async def anterior_publicada(self, version_id: int) -> MatrizVersion | None:
        """La versión no borrador de mayor id menor a `version_id`."""
        ...

    async def existe_etiqueta(self, etiqueta: str) -> bool: ...

    async def etiquetas(self) -> list[str]:
        """Todas las etiquetas ya usadas (las versiones sin etiqueta no cuentan)."""
        ...

    async def email_admin(self, admin_id: int) -> str | None: ...

    async def evaluaciones_por_version(self) -> dict[int, int]: ...

    async def contenido_desde_tablas(self) -> dict: ...

    async def aplicar(self, contenido: dict) -> dict: ...

    async def agregar(self, version: MatrizVersion) -> None:
        """Agrega la versión y hace flush."""
        ...

    async def agregar_borrador(self, borrador: MatrizVersion) -> None:
        """Agrega y hace flush; lanza `ConflictoIntegridadError` si ya existe otro borrador."""
        ...

    async def eliminar(self, version: MatrizVersion) -> None: ...


class MetricasIARepositoryPort(Protocol):
    """Lecturas de métricas de la capa de IA (llamadas, sanitizaciones, eventos y revisiones)."""

    async def llamadas(self, desde: datetime | None, hasta: datetime | None,
                       tarea: str | None, modelo: str | None) -> list[LlamadaLlm]:
        """Ordenadas por fecha ascendente."""
        ...

    async def clasificaciones_revisadas(self, respuesta_ids: set[int]) -> dict[int, str]:
        """{respuesta_id: clasificación revisada por un humano} (solo las revisadas)."""
        ...

    async def sanitizaciones(self, desde: datetime | None, hasta: datetime | None) -> list[Sanitizacion]: ...

    async def eventos_tutor(self, desde: datetime | None, hasta: datetime | None) -> list[tuple[str, str, int]]:
        """(tipo, origen, cantidad) de eventos de seguridad del tutor y sus antecedentes."""
        ...

    async def alertas_salida_llm(self, desde: datetime | None, hasta: datetime | None) -> dict[str, int]:
        """{tipo: cantidad} de alertas con origen salida_llm."""
        ...


class RecalculoBenchmarkRepositoryPort(Protocol):
    """Lecturas y reemplazo de la tabla benchmark para el recálculo (cron y al completar)."""

    async def candidatas(self) -> list[tuple[int, int | None, int | None, int | None]]:
        """(evaluacion_id, empresa_id, usuario_temporal_id, rubro_id) de evaluaciones completadas y no de prueba."""
        ...

    async def resumenes(self, evaluacion_ids: list[int]) -> list[tuple[int, int | None, float | None, int | None]]:
        """(evaluacion_id, dominio_id, puntaje_obtenido, total_controles_evaluados)."""
        ...

    async def reemplazar(self, filas: list[dict]) -> None:
        """Borra todo el benchmark y agrega `filas` (campos de Benchmark), sin commit."""
        ...
