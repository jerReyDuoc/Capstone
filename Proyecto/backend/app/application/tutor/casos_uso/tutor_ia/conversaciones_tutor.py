"""Crear, cambiar de nivel y eliminar conversaciones del tutor."""
from __future__ import annotations

from app.application.ai.schemas.tutor import NivelTutor
from app.core.config import settings
from app.domain.models.tutor_conversaciones import ConversacionTutor
from app.domain.auditoria.acciones import Accion
from app.application.tutor.casos_uso.tutor_ia.comun import TutorError, _ahora, _nivel, conversacion_a_dict


class ConversacionesMixin:
    """Crear, cambiar de nivel y eliminar conversaciones del tutor."""

    async def crear(self, ruta_id: int | None, nivel: str | None) -> dict:
        ctx = await self._cargar(ruta_id)
        if await self.repo.contar(self.empresa.id) >= settings.TUTOR_MAX_CONVERSACIONES:
            raise TutorError(409, "LIMITE_CONVERSACIONES",
                             f"Tu empresa tiene el máximo de {settings.TUTOR_MAX_CONVERSACIONES} conversaciones. "
                             "Elimina alguna para abrir otra.")
        n = _nivel(nivel, ctx.nivel_sugerido())
        ahora = _ahora()
        c = ConversacionTutor(
            empresa_id=self.empresa.id, usuario_definitivo_id=self.usuario.id, evaluacion_id=ctx.evaluacion_id,
            ruta_formativa_id=ctx.foco.id if ctx.foco else None, nivel=n.value, huella_contexto=ctx.huella(),
            mensajes_total=0, fecha_creacion=ahora, fecha_ultimo_mensaje=ahora,
        )
        self.repo.agregar(c)
        await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.TUTOR_CONVERSACION_CREADA, entidad="conversacion_tutor", entidad_id=c.id,
            actor=self.cliente.actor,
            detalle={"empresa_id": self.empresa.id, "evaluacion_id": ctx.evaluacion_id, "nivel": n.value,
                     "ruta_id": c.ruta_formativa_id, "nivel_sugerido": ctx.nivel_sugerido().value,
                     "brechas_en_contexto": len(ctx.brechas)},
        )
        await self.db.commit()
        return {"conversacion": conversacion_a_dict(c, ctx.evaluacion_id), "mensajes": [],
                "contexto": {**ctx.resumen(), "niveles": NivelTutor.valores()}, "cuota": await self.cuota()}
    async def cambiar_nivel(self, conversacion_id: int, nivel: str) -> dict:
        c = await self._conversacion(conversacion_id)
        n = _nivel(nivel, NivelTutor(c.nivel))
        anterior = c.nivel
        if n.value != anterior:
            c.nivel = n.value
            self.bitacora.registrar(
                accion=Accion.TUTOR_NIVEL_CAMBIADO, entidad="conversacion_tutor", entidad_id=c.id,
                actor=self.cliente.actor, detalle={"anterior": anterior, "nuevo": n.value})
            await self.db.commit()
        return {"conversacion": conversacion_a_dict(c, await self._evaluacion_vigente())}

    async def eliminar(self, conversacion_id: int) -> None:
        c = await self._conversacion(conversacion_id)
        await self.repo.eliminar(c.id)
        self.bitacora.registrar(
            accion=Accion.TUTOR_CONVERSACION_ELIMINADA, entidad="conversacion_tutor", entidad_id=conversacion_id,
            actor=self.cliente.actor, detalle={"motivo": "usuario", "mensajes": c.mensajes_total or 0})
        await self.db.commit()
