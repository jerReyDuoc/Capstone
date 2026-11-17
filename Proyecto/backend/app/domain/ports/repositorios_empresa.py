"""Puertos de repositorio del espacio de la empresa (HU-28/29/30) y de la retención (HU-25)."""
from __future__ import annotations

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


class RetencionRepositoryPort(Protocol):
    """Consultas de la retención de usuarios temporales."""

    async def contar_usuarios_sin_vencimiento(self) -> int:
        """Usuarios temporales no anonimizados y sin fecha de expiración."""
        ...
