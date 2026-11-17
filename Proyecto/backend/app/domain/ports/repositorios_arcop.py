"""Puertos de repositorio de los derechos ARCOP: lectura de los datos del titular para su exportación (HU-32)."""
from __future__ import annotations

from typing import Protocol

from app.domain.models.dominio import Dominio
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import Evidencia
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.respuesta_filtro import RespuestaFiltro
from app.domain.models.resumen import Resumen
from app.domain.models.solicitud_arcop import SolicitudARCOP
from app.domain.models.usuario_definitivo import UsuarioDefinitivo
from app.domain.models.usuario_temporal import UsuarioTemporal


class ExportacionDatosRepositoryPort(Protocol):
    """Lecturas de lo que la plataforma guarda del titular de una solicitud ARCOP. No escribe ni hace commit."""

    async def solicitudes_del_titular(self, solicitud: SolicitudARCOP) -> list[SolicitudARCOP]:
        """Todas las solicitudes del mismo titular (usuario definitivo, evaluación o usuario temporal), por id."""
        ...

    async def nombre_rubro(self, rubro_id: int) -> str | None: ...

    async def usuario_definitivo(self, usuario_id: int) -> UsuarioDefinitivo | None: ...

    async def empresa(self, empresa_id: int) -> Empresa | None: ...

    async def usuario_temporal(self, usuario_id: int) -> UsuarioTemporal | None: ...

    async def evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def evaluaciones_de_usuario_temporal(self, usuario_id: int) -> list[Evaluacion]: ...

    async def respuestas_filtro(self, evaluacion_id: int) -> list[RespuestaFiltro]: ...

    async def respuestas_con_control(self, evaluacion_id: int) -> list[tuple[Respuesta, MatrizControl | None]]: ...

    async def evidencias_de_respuestas(self, respuesta_ids: list[int]) -> list[Evidencia]: ...

    async def resumen_con_dominio(self, evaluacion_id: int) -> list[tuple[Resumen, Dominio | None]]: ...
