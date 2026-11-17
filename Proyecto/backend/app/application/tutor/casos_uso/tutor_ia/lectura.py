"""Contexto, cuota y lectura de conversaciones del tutor."""
from __future__ import annotations

from app.application.ai.schemas.tutor import NivelTutor
from app.application.tutor.contexto_tutor import ContextoTutor, ContextoTutorError, cargar_contexto_tutor
from app.application.encuesta_publica.casos_uso.limites_encuesta import ventana_diaria
from app.core.config import settings
from app.domain.models.tutor_conversaciones import ConversacionTutor
from app.application.tutor.casos_uso.tutor_ia.comun import TutorError, mensaje_a_dict, conversacion_a_dict


class LecturaMixin:
    """Contexto, cuota y lectura de conversaciones del tutor."""

    # ------------------------------------------------------------------ contexto
    async def _cargar(self, ruta_id: int | None = None, tolerar_foco: bool = False) -> ContextoTutor:
        try:
            return await cargar_contexto_tutor(self.db, self.empresa.id, ruta_id, settings.TUTOR_MAX_BRECHAS_CONTEXTO)
        except ContextoTutorError as e:
            if tolerar_foco and ruta_id is not None and e.codigo == "RUTA_NO_ENCONTRADA":
                # El módulo salió del plan (p. ej. su brecha se cerró con evidencia): sin foco
                return await self._cargar(None)
            raise TutorError(e.status, e.codigo, e.mensaje)

    async def _evaluacion_vigente(self) -> int | None:
        try:
            return (await self._cargar()).evaluacion_id
        except TutorError:
            return None

    async def _conversacion(self, conversacion_id: int) -> ConversacionTutor:
        c = await self.repo.obtener(conversacion_id, self.empresa.id)
        if c is None:  # de otra empresa o inexistente: misma respuesta
            raise TutorError(404, "CONVERSACION_NO_ENCONTRADA", "Conversación no encontrada.")
        return c

    async def cuota(self) -> dict:
        fecha, _, reinicio = ventana_diaria()
        limite = settings.TUTOR_MENSAJES_DIA_EMPRESA
        usados = await self.limitador.usados(self._clave_dia(fecha)) if self.limitador else 0
        return {
            "usados": usados, "limite": limite or None,
            "restantes": max(0, limite - usados) if limite > 0 else None,
            "reinicia_en": reinicio.isoformat().replace("+00:00", "Z"),
        }

    def _clave_dia(self, fecha: str) -> str:
        return f"tutor:dia:{self.empresa.id}:{fecha}"

    async def contexto(self, ruta_id: int | None = None) -> dict:
        ctx = await self._cargar(ruta_id)
        return {**ctx.resumen(), "niveles": NivelTutor.valores(), "cuota": await self.cuota(),
                "max_caracteres": settings.TUTOR_MAX_CHARS_MENSAJE}

    # ------------------------------------------------------------------ conversaciones
    async def listar(self) -> dict:
        vigente = await self._evaluacion_vigente()
        filas = await self.repo.listar(self.empresa.id, settings.TUTOR_MAX_CONVERSACIONES)
        return {"evaluacion_vigente": vigente, "items": [conversacion_a_dict(c, vigente) for c in filas]}
    async def obtener(self, conversacion_id: int) -> dict:
        c = await self._conversacion(conversacion_id)
        vigente = await self._evaluacion_vigente()
        return {"conversacion": conversacion_a_dict(c, vigente),
                "mensajes": [mensaje_a_dict(m) for m in await self.repo.mensajes(c.id)],
                "cuota": await self.cuota()}
