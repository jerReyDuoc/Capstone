"""Puertos de consulta del ciclo de la evaluación (remediación, bandeja de revisión, migración, cierre, encuesta)."""
from __future__ import annotations

from typing import Any, Protocol

from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.evidencia import Evidencia
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.domain.models.usuario_temporal import UsuarioTemporal


class RemediacionRepositoryPort(Protocol):
    """Lecturas y alta de evidencias de la remediación de controles (HU-17)."""

    async def filas_resumen(self, evaluacion_id: int) -> list[Any]:
        """Filas (puntaje_obtenido, total_controles_evaluados) del resumen de la evaluación."""
        ...

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def obtener_respuesta(self, respuesta_id: int) -> Respuesta | None: ...

    async def obtener_evidencia(self, evidencia_id: int) -> Evidencia | None: ...

    async def controles_por_ids(self, ids: list[int]) -> dict[int, MatrizControl]: ...

    async def rutas_completadas(self, empresa_id: int) -> set[int]:
        """Ids de rutas formativas completadas por la empresa."""
        ...

    async def evidencias_remediacion(self, respuesta_ids: list[int]) -> list[Evidencia]:
        """Evidencias de remediación (y del registro) de las respuestas, por id ascendente."""
        ...

    async def mejoras(self, evaluacion_id: int) -> list[Any]:
        """Filas (fecha_procesada, puntaje_previo, puntaje_resultante, respuesta_id, estado_previo, estado_resultante)."""
        ...

    async def contar_en_proceso(self, respuesta_id: int) -> int:
        """Evidencias de remediación de la respuesta aún sin terminar de validar."""
        ...

    def agregar_evidencia(self, evidencia: Evidencia) -> None: ...


class BandejaRevisionRepositoryPort(Protocol):
    """Consultas de la bandeja de revisión del Oficial de Cumplimiento (HU-22)."""

    async def candidatas(self, evaluacion_id: int | None, dominio_id: int | None, limite: int) -> list[Any]:
        """Filas (respuesta, control, dominio, evaluación, empresa) con evidencias cargadas."""
        ...

    async def conteo_eventos_por_respuesta(self, respuesta_ids: list[int]) -> dict[int, int]: ...

    async def contar_eventos(self, estado: str, evaluacion_id: int | None, origen: str | None) -> int: ...

    async def listar_eventos(self, estado: str, evaluacion_id: int | None, origen: str | None,
                             offset: int, limite: int) -> list[Any]:
        """Filas (evento, codigo_control, pregunta_evaluacion), del más reciente al más antiguo."""
        ...

    async def fila_respuesta(self, respuesta_id: int) -> Any | None:
        """Fila (respuesta, control, dominio, evaluación, empresa) o None."""
        ...

    async def eventos_de_respuesta(self, respuesta_id: int) -> list[EventoSeguridad]: ...

    async def correos_admin(self, ids: set[int]) -> dict[int, str]: ...

    async def respuestas_revisadas(self) -> list[Respuesta]: ...

    async def conteo_resoluciones_eventos(self) -> dict[str | None, int]: ...


class MigracionEvaluacionRepositoryPort(Protocol):
    """Bloqueos y conteos de la migración de una evaluación a la empresa (HU-27)."""

    async def bloquear_solicitud(self, solicitud_id: int) -> SolicitudContratacion | None: ...

    async def bloquear_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def bloquear_usuario_temporal(self, usuario_id: int) -> UsuarioTemporal | None: ...

    async def contar_contenido(self, evaluacion_id: int) -> tuple[int, int, int]:
        """(respuestas, evidencias, dimensiones del resumen)."""
        ...

    async def hay_arcop_abierta(self, evaluacion_id: int, usuario_temporal_id: int | None) -> bool: ...


class CierreEvaluacionRepositoryPort(Protocol):
    """Consultas del cierre de la evaluación y de la generación del resumen."""

    async def bloquear_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def contar_evidencias_sin_terminar(self, evaluacion_id: int) -> int: ...

    async def respuestas_con_evidencia(self, respuesta_ids: list[int]) -> set[int]: ...

    async def version_matriz_publicada(self) -> tuple[int, str] | None:
        """(id, version_texto) de la versión de matriz publicada, o None."""
        ...

    async def respuestas_con_control(self, evaluacion_id: int) -> list[Any]:
        """Filas (respuesta, control) de la evaluación, por id de respuesta."""
        ...

    async def eliminar_resumenes(self, evaluacion_id: int) -> None:
        """Borra los resúmenes previos y hace flush."""
        ...

    def agregar_resumen(self, resumen: Resumen) -> None: ...


class LimitesEncuestaRepositoryPort(Protocol):
    """Conteos para los límites de la encuesta pública (HU-19)."""

    async def origen_de_evaluacion(self, evaluacion_id: int) -> str | None: ...

    async def contar_evidencias(self, evaluacion_id: int) -> int: ...

    async def evaluacion_de_respuesta(self, respuesta_id: int) -> int | None: ...


class EncuestaPublicaRepositoryPort(Protocol):
    """Alta de la encuesta pública y acceso a la evaluación para su clave."""

    async def existe_rubro(self, rubro_id: int) -> bool: ...

    def agregar_usuario_temporal(self, usuario: UsuarioTemporal) -> None: ...

    def agregar_evaluacion(self, evaluacion: Evaluacion) -> None: ...

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...
