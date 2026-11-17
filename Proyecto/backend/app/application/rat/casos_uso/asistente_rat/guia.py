"""
Asistente de registro como GUÍA dentro del mapa de datos y del registro de actividades.

  resumen_guia()   lo que muestra el panel: la revisión del registro (alertas calculadas por el backend),
                   cuántas cosas tiene y si la ayuda automática está disponible.
  guiar()          responde una duda en pocas frases (skill "guia_registro" del agente). NO arma ni
                   propone registros: la persona completa el mapa y el registro a mano.

La conversación no se guarda en la BD: la lleva el navegador y llega en cada pregunta como texto NO
confiable (pasa por el filtro del agente y por el NER del gateway). En la bitácora solo quedan la vista,
huellas, conteos y la traza de la llamada (nunca el texto). Usa la misma cuota diaria de la empresa que la
entrevista del asistente.
"""
from __future__ import annotations

import asyncio
import logging

from app.application.ai.gateway import CapaIAError
from app.application.ai.prompts.guia_registro import ContextoGuia
from app.application.rat.asistente import contexto_asistente as contexto, inconsistencias
from app.application.rat.casos_uso.asistente_rat.comun import MENSAJE_ETICA, AsistenteError
from app.application.seguridad.huella import huella
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.ports.limitador_port import LimitadorNoDisponibleError
from app.domain.ports.registro_ia_port import ContextoLlamada

logger = logging.getLogger(__name__)

VISTAS = ("mapa", "registro")
MAX_TURNOS_HISTORIAL = 6
MAX_CARACTERES_TURNO = 600
MAX_LINEAS_REGISTRO = 40
MAX_ALERTAS_PROMPT = 8

# Sin ayuda automática (desactivada, sin cuota o anonimización caída) la guía igual orienta con un texto fijo
GUIA_FIJA = {
    "mapa": ("Empieza por lo que más usas: con «Agregar elemento» registra tus sistemas (por ejemplo, el de "
             "remuneraciones o el CRM) y los proveedores que reciben datos. Después, con «Agregar flujo», une los "
             "elementos que se envían datos entre sí. En la pestaña «Riesgos» verás lo que falta completar."),
    "registro": ("Crea una actividad por cada cosa que hace tu empresa con datos personales (por ejemplo, pagar "
                 "remuneraciones o enviar publicidad) con «Nueva actividad». Complétala paso a paso eligiendo los "
                 "sistemas y flujos de tu mapa; queda como borrador hasta que la dejes vigente."),
}
AVISOS_SIN_IA = {
    "ia_deshabilitada": "La ayuda automática no está activada, así que te dejo la guía básica:",
    "cuota_ia_agotada": "Tu empresa usó la ayuda automática de hoy (mañana se renueva). Mientras, la guía básica:",
    "anonimizacion": "No pudimos proteger los datos de tu pregunta, así que no usé la ayuda automática. La guía básica:",
}
MENSAJE_BLOQUEO_GUIA = ("Tu pregunta contiene texto que intenta cambiar las reglas del asistente, así que no la "
                        "procesé. Pregúntame con tus palabras qué necesitas para tu mapa o tu registro.")
MENSAJE_FALLA ="La guía no pudo responder esta vez. Tu pregunta no se perdió: vuelve a enviarla en unos segundos."
SUGERENCIAS_INICIALES = {
    "mapa": ["¿Por dónde empiezo mi mapa de datos?", "¿Qué es un flujo de datos?",
             "¿Qué hago con un proveedor que está fuera de Chile?"],
    "registro": ["¿Qué es una actividad de tratamiento?", "¿Cómo elijo la base legal?",
                 "¿Cuánto tiempo debo guardar los datos?"],
}


def _vista(vista: str | None) -> str:
    return vista if vista in VISTAS else "mapa"


class GuiaMixin:
    """Depende de los atributos que fija AsistenteRat.__init__ y de SesionMixin / ConversacionMixin."""

    async def _registro_actual(self):
        _, elementos, flujos = await self._mapa()
        actividades = await self._actividades()
        vigentes = [a for a in actividades if a["estado"] != "archivada"]
        return elementos, flujos, vigentes, inconsistencias.globales(elementos, flujos, actividades)

    async def resumen_guia(self) -> dict:
        elementos, flujos, actividades, revision = await self._registro_actual()
        cuota = await self.cuota()
        return {
            "revision": revision,
            "mapa": {"elementos": len(elementos), "flujos": len(flujos), "actividades": len(actividades)},
            "ia": {"habilitada": self.ia_habilitada(), "cuota": cuota["respuestas"], "reinicia_en": cuota["reinicia_en"]},
            "limites": {"max_caracteres": settings.ASISTENTE_MAX_CHARS_RESPUESTA},
            "sugerencias": SUGERENCIAS_INICIALES,
        }

    @staticmethod
    def _historial(turnos: list[dict] | None) -> tuple[str, list[str]]:
        """(texto de la conversación anterior, preguntas anteriores del usuario para el filtro multi-turno)."""
        lineas, previos = [], []
        for t in (turnos or [])[-MAX_TURNOS_HISTORIAL:]:
            texto = " ".join(str(t.get("texto") or "").split())[:MAX_CARACTERES_TURNO]
            if not texto:
                continue
            if t.get("rol") == "usuario":
                previos.append(texto)
                lineas.append(f"Usuario: {texto}")
            else:
                lineas.append(f"Guía: {texto}")
        return "\n".join(lineas), previos[-2:]

    async def guiar(self, texto: str | None, vista: str | None, historial: list[dict] | None = None) -> dict:
        texto = (texto or "").strip()
        vista = _vista(vista)
        if not texto:
            raise AsistenteError(422, "PREGUNTA_VACIA", "Escribe tu pregunta.")
        if len(texto) > settings.ASISTENTE_MAX_CHARS_RESPUESTA:
            raise AsistenteError(422, "PREGUNTA_DEMASIADO_LARGA",
                                 f"Tu pregunta supera los {settings.ASISTENTE_MAX_CHARS_RESPUESTA} caracteres.")

        motivo = None
        reserva = None
        if not self.ia_habilitada():
            motivo = "ia_deshabilitada"
        elif self.limitador is not None:
            try:
                reserva = await self._reservar("dia")      # la ráfaga responde 429 (ASISTENTE_RAFAGA)
            except LimitadorNoDisponibleError:
                raise AsistenteError(503, "AYUDA_NO_DISPONIBLE", MENSAJE_FALLA)
            if reserva is None:
                motivo = "cuota_ia_agotada"
        if motivo:
            return await self._sin_ia(texto, vista, motivo)

        elementos, flujos, actividades, revision = await self._registro_actual()
        registro_txt = "\n".join(contexto.mapa_texto(elementos, flujos, actividades).splitlines()[:MAX_LINEAS_REGISTRO])
        alertas = "\n".join(f"[alerta] {a['severidad']}: {a['texto']}" for a in revision[:MAX_ALERTAS_PROMPT])
        historial_txt, previos = self._historial(historial)
        ctx = ContextoGuia(vista=vista, elementos=len(elementos), flujos=len(flujos), actividades=len(actividades),
                           alertas=len(revision))
        from app.application.ai.agente import HabilidadIA

        try:
            salida = await asyncio.wait_for(self.agente.ejecutar(
                HabilidadIA.GUIA_REGISTRO,
                textos={"mensaje": texto, "historial": historial_txt,
                        "registro": "\n".join(x for x in (registro_txt, alertas) if x)},
                datos={"contexto": ctx, "previos_usuario": previos},
                contexto=ContextoLlamada(),
            ), timeout=settings.ASISTENTE_TIEMPO_MAXIMO_S)
        except (CapaIAError, asyncio.TimeoutError) as e:
            if reserva is not None:
                await reserva.devolver()   # no fue culpa del usuario: no gasta su cuota
            tipo = getattr(e, "tipo_error", None) or "timeout"
            if tipo == "sanitizacion":
                return await self._sin_ia(texto, vista, "anonimizacion")
            self._bitacora_guia(vista, texto, motivo_sin_ia="ia_no_disponible", error_ia=tipo, rechazado=True)
            await self.db.commit()
            raise AsistenteError(503, "AYUDA_NO_DISPONIBLE", MENSAJE_FALLA, tipo_error=tipo,
                                 reintentar_en_s=30 if tipo == "rate_limit" else None)

        for n in salida.neutralizados:
            await self._evento(n.get("texto") or "", n.get("categoria"), OrigenEvento.ASISTENTE.value, regla=n.get("regla"))
        if salida.bloqueado:
            if reserva is not None:
                await reserva.devolver()
            await self._evento(texto, salida.motivo, OrigenEvento.ASISTENTE.value, regla=salida.regla)
            etica = salida.motivo == "uso_indebido"
            self.bitacora.registrar(
                accion=Accion.ASISTENTE_GUIA_BLOQUEADA, entidad="asistente_guia", entidad_id=self.empresa_id,
                actor=self.actor, resultado=RESULTADO_RECHAZADO,
                detalle={"vista": vista, "categoria": salida.motivo, "regla": salida.regla,
                         "huella_pregunta": huella(texto), "largo": len(texto)})
            await self.db.commit()
            return {"respuesta": MENSAJE_ETICA if etica else MENSAJE_BLOQUEO_GUIA,
                    "sugerencias": SUGERENCIAS_INICIALES[vista][:2], "bloqueado": True, "sin_ia": None,
                    "cuota": (await self.cuota())["respuestas"]}

        resultado = salida.resultado
        data = resultado.data
        if salida.salida_bloqueada:
            await self._evento(texto, "fuga_prompt_salida", OrigenEvento.ASISTENTE.value, regla="salida.fuga_prompt")
            self.bitacora.registrar(
                accion=Accion.ASISTENTE_GUIA_BLOQUEADA, entidad="asistente_guia", entidad_id=self.empresa_id,
                actor=self.actor, resultado=RESULTADO_RECHAZADO,
                detalle={"vista": vista, "categoria": "fuga_prompt_salida", "traza_id": resultado.traza_id})
        else:
            self._bitacora_guia(vista, texto, traza_id=resultado.traza_id, prompt_version=resultado.prompt_version,
                                entidades=resultado.entidades_anonimizadas,
                                fuera_de_alcance=bool(data.fuera_de_alcance),
                                lineas_omitidas=len(salida.neutralizados))
        await self.db.commit()
        return {"respuesta": data.respuesta, "sugerencias": list(data.sugerencias), "bloqueado": False,
                "sin_ia": None, "cuota": (await self.cuota())["respuestas"]}

    async def _sin_ia(self, texto: str, vista: str, motivo: str) -> dict:
        self._bitacora_guia(vista, texto, motivo_sin_ia=motivo)
        await self.db.commit()
        return {"respuesta": f"{AVISOS_SIN_IA[motivo]} {GUIA_FIJA[vista]}", "sugerencias": [], "bloqueado": False,
                "sin_ia": motivo, "cuota": (await self.cuota())["respuestas"]}

    def _bitacora_guia(self, vista: str, texto: str, *, rechazado: bool = False, **detalle) -> None:
        extra = {"resultado": RESULTADO_RECHAZADO} if rechazado else {}
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_GUIA_CONSULTA, entidad="asistente_guia", entidad_id=self.empresa_id,
            actor=self.actor, detalle={"vista": vista, "huella_pregunta": huella(texto), "largo": len(texto),
                                       **{k: v for k, v in detalle.items() if v is not None}},
            **extra)
