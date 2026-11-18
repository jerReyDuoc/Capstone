"""Puertos de repositorio del espacio de la empresa (HU-28/29/30) y de la retención (HU-25)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol


class EspacioEmpresaRepositoryPort(Protocol):
    """Lecturas del espacio de la empresa del usuario definitivo."""

    async def empresa_de_usuario(self, usuario_id: int) -> Any | None:
        """Empresa del usuario definitivo, o None si el usuario o la empresa no existen."""
        ...

    async def nombre_rubro(self, rubro_id: int) -> str | None:
        """Nombre del rubro, o None si no existe."""
        ...

    async def evaluaciones_con_puntaje(self, empresa_id: int) -> list[tuple[Any, float | None]]:
        """(evaluación, puntaje medio) de la empresa, la más reciente primero."""
        ...

    async def avances_con_constancia(self, empresa_id: int) -> list[tuple[Any, str | None]]:
        """(avance formativo, nombre de la ruta) con constancia emitida, el más reciente primero."""
        ...


@dataclass(frozen=True)
class ConfiguracionRetencionLeida:
    """Columnas de la fila única de configuración_retencion (no la entidad ORM: el bloqueo se actualiza con UPDATE)."""
    fuente_plazo: str
    plazo_titular_dias: int | None
    fecha_actualizacion: datetime | None
    ejecucion_desde: datetime | None


class RetencionRepositoryPort(Protocol):
    """Consultas y escrituras de la retención de datos (HU-25, T-06, HU-15). Ninguna hace commit."""

    async def contar_usuarios_sin_vencimiento(self) -> int:
        """Usuarios temporales no anonimizados y sin fecha de expiración."""
        ...

    # ---- configuración y bloqueo de ejecución (HU-25)
    async def existe_configuracion(self) -> bool: ...

    async def crear_configuracion_inicial(self) -> None:
        """Crea la fila única en modo 'entorno' y hace flush. Lanza ConflictoIntegridadError si ya existe."""
        ...

    async def leer_configuracion(self) -> ConfiguracionRetencionLeida: ...

    async def actualizar_configuracion(self, fuente_plazo: str, plazo_titular_dias: int | None,
                                       ahora: datetime) -> None: ...

    async def tomar_bloqueo(self, marca: datetime, abandonada: datetime) -> bool:
        """UPDATE condicional atómico: True si esta ejecución quedó marcada como en curso."""
        ...

    async def liberar_bloqueo(self, marca: datetime) -> None: ...

    # ---- R1 titulares
    async def contar_titulares_vencidos_con_arcop_abierta(self, limite: date) -> int: ...

    async def ids_titulares_vencidos_sin_arcop_abierta(self, limite: date) -> list[int]: ...

    async def ids_evaluaciones_publicas(self, usuario_id: int) -> list[int]: ...

    async def marcar_titular_anonimizado(self, usuario_id: int, ahora: datetime) -> None: ...

    # ---- R2 solicitudes ARCOP
    async def solicitudes_arcop_cerradas_sin_anonimizar(self, limite: datetime,
                                                        actor_sistema: str) -> list[tuple[int, str]]:
        """(id, estado) de las solicitudes cerradas antes de `limite` sin evento de anonimización del sistema."""
        ...

    async def anonimizar_textos_solicitudes_arcop(self, ids: list[int], ahora: datetime) -> None: ...

    def agregar_evento_anonimizacion(self, solicitud_id: int, estado: str, ahora: datetime,
                                     actor_sistema: str) -> None:
        """Agrega (sin flush) el evento 'anonimizacion' al historial de la solicitud."""
        ...

    # ---- R3 eventos de seguridad
    async def contar_eventos_seguridad_revisados(self, limite: datetime) -> int: ...

    async def ids_eventos_seguridad_revisados(self, limite: datetime) -> list[int]: ...

    async def borrar_extracto_eventos(self, ids: list[int]) -> int:
        """Deja el extracto en NULL; devuelve las filas afectadas."""
        ...

    # ---- R7 empresas con la gracia vencida (T-17)
    async def empresas_pendientes_de_borrado(self, ids: list[int]) -> tuple[list[int], int]:
        """(empresas por procesar sin ARCOP abierta, cuántas se omiten por tenerla); excluye las ya procesadas."""
        ...

    async def ids_usuarios_definitivos_de_empresa(self, empresa_id: int) -> list[int]: ...

    async def borrar_documentos_empresa(self, empresa_id: int) -> tuple[int, list[str]]:
        """(filas borradas, rutas de archivo a borrar tras el commit)."""
        ...

    async def eliminar_evidencias_empresa(self, empresa_id: int, ahora: datetime) -> tuple[int, list[str]]:
        """(evidencias vaciadas, rutas de archivo a borrar tras el commit); conserva clasificación y puntajes."""
        ...

    async def borrar_conversaciones_tutor_empresa(self, empresa_id: int) -> int: ...

    async def marcar_empresa_datos_eliminados(self, empresa_id: int, ahora: datetime) -> None: ...
