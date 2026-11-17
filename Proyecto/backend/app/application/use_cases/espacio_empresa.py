"""HU-28/29/30 · Lecturas del espacio de la empresa del usuario definitivo (rol cliente)."""
from __future__ import annotations

from typing import Any

from app.domain.ports.repositorios_empresa import EspacioEmpresaRepositoryPort


class EmpresaNoEncontradaError(Exception):
    """El usuario no tiene empresa (obtener_actor ya lo comprobó; defensa en profundidad)."""


class EspacioEmpresa:
    def __init__(self, repo: EspacioEmpresaRepositoryPort):
        self.repo = repo

    async def empresa_del_usuario(self, usuario_id: int) -> Any:
        empresa = await self.repo.empresa_de_usuario(usuario_id)
        if empresa is None:
            raise EmpresaNoEncontradaError()
        return empresa

    async def nombre_rubro(self, rubro_id: int) -> str | None:
        return await self.repo.nombre_rubro(rubro_id)

    async def evaluaciones(self, empresa_id: int) -> list[tuple[Any, float | None]]:
        """(evaluación, puntaje medio), la más reciente primero."""
        return await self.repo.evaluaciones_con_puntaje(empresa_id)

    async def constancias(self, empresa_id: int) -> list[dict]:
        """Constancias de módulos completados, la más reciente primero."""
        filas = await self.repo.avances_con_constancia(empresa_id)
        return [{
            "ruta_id": a.ruta_formativa_id, "modulo": nombre or f"Ruta {a.ruta_formativa_id}",
            "fecha_completado": a.fecha_completado, "codigo": a.codigo_constancia,
            "url": f"/api/formacion/modulos/{a.ruta_formativa_id}/constancia",
        } for a, nombre in filas if a.completado]
