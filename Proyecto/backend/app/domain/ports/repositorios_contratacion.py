"""Puerto de repositorio de la contratación (HU-27/30/31): solicitudes, empresas cliente y contratos."""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import Any, Protocol

from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.domain.models.usuario_definitivo import UsuarioDefinitivo


class ContratacionRepositoryPort(Protocol):
    """Consultas y altas de solicitudes de contratación, empresas cliente y su contrato."""

    def traducir_integridad(self) -> AbstractAsyncContextManager[None]:
        """Dentro del bloque, una violación de integridad de la persistencia sale como ConflictoIntegridadError."""
        ...

    # ------------------------------------------------------------ solicitudes (HU-31)
    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def existe_solicitud_de_evaluacion(self, evaluacion_id: int) -> bool:
        """True si ya hay una solicitud para esa evaluación."""
        ...

    def agregar_solicitud(self, solicitud: SolicitudContratacion) -> None: ...

    async def conteo_solicitudes_por_estado(self) -> list[tuple[str, int]]: ...

    async def listar_solicitudes(self, estado: str | None, page: int, size: int
                                 ) -> tuple[list[SolicitudContratacion], int]:
        """(página de solicitudes, total) con filtro opcional por estado, la más reciente primero."""
        ...

    async def obtener_solicitud(self, solicitud_id: int) -> SolicitudContratacion | None: ...

    async def puntaje_medio_evaluacion(self, evaluacion_id: int) -> Any | None:
        """Promedio del puntaje de los resúmenes de la evaluación, o None si no tiene."""
        ...

    # ------------------------------------------------------------ empresa cliente (HU-27)
    async def obtener_rubro(self, rubro_id: int) -> Rubro | None: ...

    async def existe_empresa_con_rut(self, rut: str) -> bool: ...

    async def existe_usuario_con_email(self, email: str) -> bool:
        """Comparación sin distinguir mayúsculas."""
        ...

    def agregar_empresa(self, empresa: Empresa) -> None: ...

    def agregar_usuario_definitivo(self, usuario: UsuarioDefinitivo) -> None: ...

    async def obtener_empresa(self, empresa_id: int) -> Empresa | None: ...

    async def usuario_de_empresa(self, empresa_id: int) -> UsuarioDefinitivo | None: ...

    async def listar_empresas(self, page: int, size: int
                              ) -> tuple[list[tuple[Empresa, UsuarioDefinitivo | None, int | None]], int]:
        """((empresa, usuario, nº de evaluaciones) de la página, total), la más reciente primero."""
        ...

    async def evaluaciones_de_empresa(self, empresa_id: int) -> list[Evaluacion]: ...

    # ------------------------------------------------------------ contrato (HU-30)
    async def obtener_empresa_para_actualizar(self, empresa_id: int) -> Empresa | None:
        """La empresa bloqueada (FOR UPDATE) y refrescada desde la base, o None."""
        ...

    async def empresas_con_termino_vencido(self, hoy: date) -> list[Empresa]:
        """Empresas con la fecha de término anterior a `hoy` o con el contrato terminado."""
        ...
