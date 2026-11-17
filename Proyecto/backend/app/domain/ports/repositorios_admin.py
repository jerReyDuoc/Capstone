"""Puertos de los repositorios del panel interno (rubros y empresas cliente / evaluaciones)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_contratacion import SolicitudContratacion


class RubrosRepositoryPort(Protocol):
    """Consultas y altas del catálogo de rubros (mantenedor del admin)."""

    async def conteo_evaluaciones_por_rubro(self) -> dict[int, int]: ...

    async def conteo_empresas_por_rubro(self) -> dict[int, int]: ...

    async def listar(self) -> list[Rubro]: ...

    async def obtener(self, rubro_id: int) -> Rubro | None: ...

    async def existe_nombre(self, nombre: str, excepto: int | None = None) -> bool:
        """Compara sin distinguir mayúsculas ni espacios de borde."""
        ...

    async def intentar_agregar(self, nombre: str) -> Rubro | None:
        """Calcula el id siguiente y hace flush; devuelve None (tras rollback) si choca el id."""
        ...


@dataclass(frozen=True)
class DatosEvaluacionPanel:
    """Evaluación con su rubro y puntaje general, tal como la muestra el panel interno."""
    evaluacion: Evaluacion
    rubro_id: int | None
    rubro: str | None
    puntaje: float | None
    empresa_razon_social: str | None = None


@dataclass(frozen=True)
class PaginaEvaluacionesPanel:
    filas: list[DatosEvaluacionPanel]
    total: int
    conteo_por_estado: dict[str | None, int]


class PanelClientesRepositoryPort(Protocol):
    """Consultas de lectura del panel interno (evaluaciones y empresas)."""

    async def datos_evaluacion(self, evaluacion_id: int) -> DatosEvaluacionPanel | None: ...

    async def listar_evaluaciones(self, *, estado: str | None, origen: str | None, empresa_id: int | None,
                                  incluir_prueba: bool, page: int, size: int) -> PaginaEvaluacionesPanel: ...

    async def obtener_empresa(self, empresa_id: int) -> Empresa | None: ...


class SolicitudContratacionRepositoryPort(Protocol):
    """Consultas de las solicitudes de contratación (HU-31)."""

    async def obtener_por_evaluacion(self, evaluacion_id: int) -> SolicitudContratacion | None: ...


class EventoSeguridadRepositoryPort(Protocol):
    """Eventos de seguridad (HU-09/HU-10). `update` hace commit y refresca (comportamiento histórico)."""

    async def get(self, evento_id: int) -> EventoSeguridad | None: ...

    async def update(self, evento: EventoSeguridad) -> EventoSeguridad: ...
