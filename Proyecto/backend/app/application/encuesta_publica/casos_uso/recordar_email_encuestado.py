"""Email OPCIONAL del encuestado (HU-19) y "recordar mi correo" al enviar el informe (HU-21)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas


class RecordarEmailEncuestadoUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.informes = fabricas().informes(db)

    async def usuario_de_evaluacion(self, evaluacion_id: int, exigir_vinculo: bool = False) -> Any | None:
        """Usuario temporal dueño de la evaluación, o None si no existe.

        `exigir_vinculo=True` devuelve None también cuando la evaluación no tiene usuario_temporal_id.
        """
        evaluacion = await self.informes.evaluacion(evaluacion_id)
        if evaluacion is None or (exigir_vinculo and not evaluacion.usuario_temporal_id):
            return None
        return await self.informes.usuario_temporal(evaluacion.usuario_temporal_id)

    async def guardar_email(self, usuario: Any, email: str | None) -> None:
        """Guarda (o borra, con None) el correo del usuario temporal y confirma."""
        await self.informes.actualizar_email_usuario_temporal(usuario, email)
        await self.db.commit()
