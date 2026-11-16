"""Puerto de la bitácora de auditoría (audit_log)."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.auth.actor import Actor
from app.domain.models.bitacora_auditoria import RESULTADO_OK, BitacoraAuditoria


class BitacoraPort(Protocol):
    """Registra y consulta eventos de auditoría. `registrar` solo agrega a la unidad de trabajo."""

    def registrar(self, *, accion: str, entidad: str, entidad_id: int | None = None,
                  actor: Actor | None = None, actor_rol: str | None = None, actor_id: int | None = None,
                  detalle: dict | None = None, resultado: str = RESULTADO_OK,
                  fecha: datetime | None = None, ip: str | None = None) -> BitacoraAuditoria: ...

    async def listar(self, *, entidad: str | None = None, entidad_id: int | None = None,
                     accion: str | None = None, page: int = 1, size: int = 50,
                     desde: datetime | None = None, hasta: datetime | None = None,
                     categoria: str | None = None, resultado: str | None = None,
                     actor_rol: str | None = None) -> tuple[list[BitacoraAuditoria], int]: ...
