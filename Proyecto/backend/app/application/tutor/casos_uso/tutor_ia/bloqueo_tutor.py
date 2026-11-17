"""Bloqueos, eventos de seguridad y registro de mensajes del tutor (HU-18)."""
from __future__ import annotations

from datetime import datetime

from app.application.tutor.contexto_tutor import ContextoTutor
from app.application.seguridad.huella import huella
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.models.tutor_conversaciones import ConversacionTutor, MensajeTutor, RolMensajeTutor, TipoMensajeTutor
from app.domain.auditoria.acciones import Accion
from app.application.tutor.casos_uso.tutor_ia.comun import (
    MAX_TITULO,
    TEXTO_BLOQUEADO_USUARIO,
    ADVERTENCIA_ABUSO,
    respuesta_de_bloqueo,
    mensaje_a_dict,
    conversacion_a_dict,
)

class BloqueoMixin:
    """Bloqueos, eventos de seguridad y registro de mensajes del tutor (HU-18)."""

    def _registrar_mensajes(self, c: ConversacionTutor, ctx: ContextoTutor, titulo_base: str | None,
                            mensajes: list[MensajeTutor], ahora: datetime) -> None:
        for m in mensajes:
            self.repo.agregar(m)
        c.mensajes_total = (c.mensajes_total or 0) + len(mensajes)
        c.fecha_ultimo_mensaje = ahora
        c.huella_contexto = ctx.huella()
        if not c.titulo and titulo_base:
            t = " ".join(titulo_base.split())
            c.titulo = t if len(t) <= MAX_TITULO else t[:MAX_TITULO - 1].rstrip() + "…"

    async def _evento(self, texto: str, tipo: str | None, ctx: ContextoTutor, origen: str | None = None,
                      regla: str | None = None) -> None:
        if self.registrar_evento is not None:
            await self.registrar_evento.execute(texto, origen or OrigenEvento.TUTOR.value,
                                                evaluacion_id=ctx.evaluacion_id, tipo=tipo or "prompt_injection",
                                                regla=regla)

    async def _contar_bloqueo(self, c: ConversacionTutor, ctx: ContextoTutor) -> str | None:
        """
        HU-18: cuenta los bloqueos de la empresa en una ventana. Desde el umbral se muestra una
        advertencia (no se bloquea el tutor) y, al alcanzarlo, se alerta con un evento de seguridad.
        """
        umbral = settings.TUTOR_BLOQUEOS_ADVERTENCIA
        if umbral <= 0 or self.limitador is None:
            return None
        consumo = await self.limitador.consumir(f"tutor:bloqueos:{self.empresa.id}", 10**6,
                                                settings.TUTOR_VENTANA_BLOQUEOS_MIN * 60)
        if consumo.usados < umbral:
            return None
        if consumo.usados == umbral:
            await self._evento(f"{consumo.usados} mensajes bloqueados en {settings.TUTOR_VENTANA_BLOQUEOS_MIN} min",
                               "abuso_reiterado", ctx)
        self.bitacora.registrar(
            accion=Accion.TUTOR_ADVERTENCIA_ABUSO, entidad="conversacion_tutor", entidad_id=c.id,
            actor=self.cliente.actor, resultado=RESULTADO_RECHAZADO,
            detalle={"empresa_id": self.empresa.id, "bloqueos_en_ventana": consumo.usados,
                     "ventana_min": settings.TUTOR_VENTANA_BLOQUEOS_MIN},
        )
        return ADVERTENCIA_ABUSO

    async def _bloqueado(self, c: ConversacionTutor, ctx: ContextoTutor, texto: str, motivo: str | None,
                         regla: str | None, ahora: datetime) -> dict:
        """Ataque detectado por el filtro: no se llamó al NER ni al LLM. Queda el evento (extracto anonimizado)."""
        await self._evento(texto, motivo, ctx, regla=regla)
        respuesta, sugerencias = respuesta_de_bloqueo(motivo)
        m_usuario = MensajeTutor(
            conversacion_id=c.id, rol=RolMensajeTutor.USUARIO.value, tipo=TipoMensajeTutor.PREGUNTA.value,
            contenido=TEXTO_BLOQUEADO_USUARIO, nivel=c.nivel, bloqueado=True, motivo_bloqueo=motivo,
            huella_contexto=ctx.huella(), fecha=ahora,
        )
        m_tutor = MensajeTutor(
            conversacion_id=c.id, rol=RolMensajeTutor.TUTOR.value, tipo=TipoMensajeTutor.BLOQUEADO.value,
            contenido=respuesta, nivel=c.nivel, bloqueado=True, motivo_bloqueo=motivo,
            datos={"pasos": [], "brechas": [], "referencias_normativas": [], "sugerencias": sugerencias},
            huella_contexto=ctx.huella(), fecha=ahora,
        )
        self._registrar_mensajes(c, ctx, None, [m_usuario, m_tutor], ahora)
        self.bitacora.registrar(
            accion=Accion.TUTOR_MENSAJE_BLOQUEADO, entidad="conversacion_tutor", entidad_id=c.id,
            actor=self.cliente.actor, resultado=RESULTADO_RECHAZADO,
            detalle={"evaluacion_id": ctx.evaluacion_id, "motivo": motivo, "categoria": motivo, "regla": regla,
                     "huella_mensaje": huella(texto), "largo": len(texto)},
        )
        advertencia = await self._contar_bloqueo(c, ctx)
        await self.db.commit()
        salida = {"mensaje_usuario": mensaje_a_dict(m_usuario), "respuesta": mensaje_a_dict(m_tutor),
                  "conversacion": conversacion_a_dict(c, ctx.evaluacion_id), "cuota": await self.cuota()}
        if advertencia:
            salida["advertencia"] = advertencia
        return salida

    def _auditar_rechazo(self, c: ConversacionTutor, tipo_error: str | None) -> None:
        self.bitacora.registrar(
            accion=Accion.TUTOR_MENSAJE, entidad="conversacion_tutor", entidad_id=c.id, actor=self.cliente.actor,
            resultado=RESULTADO_RECHAZADO, detalle={"error": tipo_error or "desconocido"})
