"""Adaptación con el Agente IA: cuota, eventos de seguridad y llamada al agente."""
from __future__ import annotations

from app.application.ai.agente import HabilidadIA
from app.application.ai.gateway import CapaIAError
from app.application.borradores import generador_markdown as generador
from app.application.borradores.generador_markdown import AdaptacionIA
from app.application.encuesta_publica.casos_uso.limites_encuesta import Reserva, ventana_diaria
from app.application.seguridad.huella import huella
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.domain.ports.limitador_port import LimitadorNoDisponibleError
from app.domain.auditoria.acciones import Accion
from app.application.borradores.casos_uso.generar_borradores.comun import MENSAJE_BLOQUEO, MENSAJE_ETICA, BorradorError


class AdaptacionMixin:
    """Adaptación con el Agente IA: cuota, eventos de seguridad y llamada al agente."""

    async def _reservar_cuota(self) -> Reserva | None:
        """None si la cuota de la empresa o la global se agotó (el borrador se arma sin IA)."""
        fecha, ventana, _ = ventana_diaria()
        reserva = Reserva(self.limitador)
        for clave, limite in ((self._clave_dia(fecha), settings.BORRADORES_IA_DIA_EMPRESA),
                              (f"llm:global:{fecha}", settings.LLM_CUOTA_DIARIA_GLOBAL)):
            if limite <= 0:
                continue
            consumo = await self.limitador.consumir(clave, limite, ventana)
            reserva.claves.append(clave)
            if not consumo.permitido:
                await reserva.devolver()
                return None
        return reserva

    async def _evento(self, texto: str, tipo: str | None, evaluacion_id: int | None,
                      regla: str | None = None) -> None:
        if self.registrar_evento is not None:
            await self.registrar_evento.execute(texto, OrigenEvento.BORRADOR.value, evaluacion_id=evaluacion_id,
                                                tipo=tipo or "prompt_injection", regla=regla)

    async def _adaptar(self, plantilla, ctx, instrucciones: str) -> tuple[AdaptacionIA, dict]:
        """Llama al Agente IA. Devuelve la adaptación (vacía si no se pudo) y lo que se audita."""
        info: dict = {"adaptado_ia": False, "motivo_sin_ia": None, "traza_id": None, "prompt_version": None,
                      "advertencias": [], "entidades_anonimizadas": 0}
        if not settings.BORRADORES_IA_HABILITADA or self.agente is None:
            info["motivo_sin_ia"] = "ia_deshabilitada"
            return AdaptacionIA(), info
        reserva = None
        if self.limitador is not None:
            try:
                reserva = await self._reservar_cuota()
            except LimitadorNoDisponibleError:
                info["motivo_sin_ia"] = "ia_no_disponible"
                return AdaptacionIA(), info
            if reserva is None:
                info["motivo_sin_ia"] = "cuota_ia_agotada"
                return AdaptacionIA(), info
        prioritarias = generador.clausulas_prioritarias(plantilla, ctx)
        try:
            salida = await self.agente.ejecutar(
                HabilidadIA.BORRADOR, textos={"instrucciones": instrucciones},
                datos={"plantilla": plantilla, "contexto": ctx, "prioritarias": prioritarias},
                contexto=ContextoLlamada(evaluacion_id=ctx.evaluacion_id),
            )
        except CapaIAError as e:
            if reserva is not None:
                await reserva.devolver()   # no fue culpa del usuario: no gasta su cuota
            info.update(motivo_sin_ia="ia_no_disponible", error_ia=e.tipo_error)
            return AdaptacionIA(), info

        if salida.bloqueado:
            await self._evento(instrucciones, salida.motivo, ctx.evaluacion_id, regla=salida.regla)
            self.bitacora.registrar(
                accion=Accion.BORRADOR_INSTRUCCIONES_BLOQUEADAS, entidad="borrador_documento", entidad_id=None,
                actor=self.cliente.actor, resultado=RESULTADO_RECHAZADO,
                detalle={"empresa_id": self.empresa.id, "tipo": plantilla.tipo.value, "categoria": salida.motivo,
                         "regla": salida.regla, "huella_instrucciones": huella(instrucciones),
                         "largo": len(instrucciones)},
            )
            await self.db.commit()
            etica = salida.motivo == "uso_indebido"
            raise BorradorError(422, "INSTRUCCIONES_BLOQUEADAS", MENSAJE_ETICA if etica else MENSAJE_BLOQUEO,
                                categoria=salida.motivo)

        resultado = salida.resultado
        info.update(traza_id=resultado.traza_id, prompt_version=resultado.prompt_version,
                    advertencias=list(salida.advertencias), entidades_anonimizadas=resultado.entidades_anonimizadas)
        if salida.salida_bloqueada:
            # HU-18: la salida filtró el system prompt; es un ataque logrado. Se usa la plantilla base.
            await self._evento(instrucciones, "fuga_prompt_salida", ctx.evaluacion_id, regla="salida.fuga_prompt")
            info["motivo_sin_ia"] = "salida_ia_descartada"
            return AdaptacionIA(), info
        data = resultado.data
        adaptacion = AdaptacionIA(
            introduccion=data.introduccion or None,
            secciones={s.clausula_id: s.texto for s in data.secciones},
            notas=tuple(data.notas_revision),
        )
        info["adaptado_ia"] = bool(adaptacion.secciones or adaptacion.introduccion)
        return adaptacion, info
