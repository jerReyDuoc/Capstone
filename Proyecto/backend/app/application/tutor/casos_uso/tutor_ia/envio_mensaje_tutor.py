"""Envío de un mensaje al tutor: cuota, llamada al agente y persistencia (C3)."""
from __future__ import annotations

from app.application.ai.agente import HabilidadIA
from app.application.ai.anonimizador import AnonimizacionError
from app.application.ai.gateway import CapaIAError
from app.application.ai.prompts.tutor import texto_antecedentes, turno_historial
from app.application.ai.schemas.tutor import TutorRespuesta
from app.application.tutor.contexto_tutor import ContextoTutor
from app.application.encuesta_publica.casos_uso.limites_encuesta import Reserva, ventana_diaria
from app.application.seguridad.huella import huella
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.models.tutor_conversaciones import MensajeTutor, RolMensajeTutor, TipoMensajeTutor
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.domain.auditoria.acciones import Accion
from app.application.tutor.casos_uso.tutor_ia.comun import TutorError, _ahora, mensaje_a_dict, conversacion_a_dict


class EnvioMixin:
    """Envío de un mensaje al tutor: cuota, llamada al agente y persistencia (C3)."""

    # ------------------------------------------------------------------ mensajes
    async def _reservar_cuota(self) -> Reserva:
        fecha, ventana, reinicio = ventana_diaria()
        reserva = Reserva(self.limitador)
        pasos = [
            (f"tutor:min:{self.empresa.id}", settings.TUTOR_MENSAJES_MINUTO_EMPRESA, 60, "TUTOR_RAFAGA",
             "Estás enviando mensajes muy rápido. Espera unos segundos e inténtalo de nuevo."),
            (self._clave_dia(fecha), settings.TUTOR_MENSAJES_DIA_EMPRESA, ventana, "CUOTA_TUTOR_AGOTADA",
             f"Tu empresa usó los {settings.TUTOR_MENSAJES_DIA_EMPRESA} mensajes del tutor de hoy. "
             "Podrás seguir conversando después del reinicio."),
            (f"llm:global:{fecha}", settings.LLM_CUOTA_DIARIA_GLOBAL, ventana, "CUOTA_LLM_GLOBAL_AGOTADA",
             "El servicio de IA alcanzó su capacidad diaria. Inténtalo después del reinicio."),
        ]
        for clave, limite, ventana_s, codigo, mensaje in pasos:
            if limite <= 0:
                continue
            consumo = await self.limitador.consumir(clave, limite, ventana_s)
            reserva.claves.append(clave)
            if not consumo.permitido:
                await reserva.devolver()
                raise TutorError(429, codigo, mensaje, reintentar_en_s=consumo.reintentar_en_s,
                                 reinicia_en=reinicio.isoformat().replace("+00:00", "Z"))
        return reserva

    async def _anon(self, texto: str | None) -> str | None:
        return await self.anonimizador.anonimizar(texto) if self.anonimizador else texto

    async def _anon_salida(self, texto: str | None) -> str | None:
        """Correcciones 05-11: lo del modelo, anonimizado y sin etiquetas usadas como vocativo."""
        from app.application.ai.agente.salida_tutor import sin_vocativos_anonimizados
        return sin_vocativos_anonimizados(await self._anon(texto))

    async def _respuesta_anonimizada(self, r: TutorRespuesta, ctx: ContextoTutor) -> tuple[str, dict]:
        """Defensa en profundidad: lo que escribió el modelo también pasa por el NER antes de guardarse."""
        pasos = []
        for p in r.pasos:
            pasos.append({
                "orden": p.orden, "accion": await self._anon_salida(p.accion),
                # lista cerrada (v1.1): no puede traer datos personales
                "responsable_sugerido": p.responsable_sugerido.value if p.responsable_sugerido else None,
                "evidencia_esperada": await self._anon_salida(p.evidencia_esperada),
            })
        por_ref = {b.ref: b for b in ctx.brechas}
        brechas = [{
            "ref": ref, "codigo": por_ref[ref].codigo, "dominio": por_ref[ref].dominio,
            "severidad": por_ref[ref].severidad, "estado": por_ref[ref].estado,
            "ruta_id": por_ref[ref].ruta_id, "respuesta_id": por_ref[ref].respuesta_id,
            # Correcciones 05-11: el chat nombra la brecha por su descripción (texto del catálogo)
            "descripcion": por_ref[ref].descripcion,
        } for ref in r.brechas_referenciadas if ref in por_ref]
        datos = {
            "pasos": pasos, "brechas": brechas,
            # salen de la matriz de controles (v1.1), no del modelo
            "referencias_normativas": list(r.referencias_normativas),
            "sugerencias": [await self._anon_salida(x) for x in r.sugerencias],
        }
        return await self._anon_salida(r.respuesta) or "", datos

    async def enviar(self, conversacion_id: int, texto: str | None) -> dict:
        """HU-18: cualquier rechazo (validación, cuota, conversación ajena...) también queda auditado."""
        try:
            return await self._enviar(conversacion_id, texto)
        except TutorError as e:
            if not e.auditado:
                await self.db.rollback()
                self.bitacora.registrar(
                    accion=Accion.TUTOR_MENSAJE, entidad="conversacion_tutor", entidad_id=conversacion_id,
                    actor=self.cliente.actor, resultado=RESULTADO_RECHAZADO,
                    detalle={"codigo": e.codigo, "status": e.status, "largo": len(texto or ""),
                             "huella_mensaje": huella((texto or "").strip()) if texto else None},
                )
                await self.db.commit()
            raise

    async def _enviar(self, conversacion_id: int, texto: str | None) -> dict:
        texto = (texto or "").strip()
        if not texto:
            raise TutorError(422, "MENSAJE_VACIO", "Escribe tu pregunta para el tutor.")
        if len(texto) > settings.TUTOR_MAX_CHARS_MENSAJE:
            raise TutorError(422, "MENSAJE_DEMASIADO_LARGO",
                             f"El mensaje supera los {settings.TUTOR_MAX_CHARS_MENSAJE} caracteres.",
                             max_caracteres=settings.TUTOR_MAX_CHARS_MENSAJE)
        c = await self._conversacion(conversacion_id)
        ctx = await self._cargar(c.ruta_formativa_id, tolerar_foco=True)
        if ctx.evaluacion_id != c.evaluacion_id:
            raise TutorError(409, "CONVERSACION_DESACTUALIZADA",
                             "Tu empresa tiene una evaluación más reciente. Abre una conversación nueva para "
                             "que el tutor use tus brechas vigentes.", evaluacion_vigente=ctx.evaluacion_id)
        if self.agente is None:
            raise TutorError(503, "TUTOR_NO_DISPONIBLE", "El tutor no está disponible en este momento.")

        reserva = await self._reservar_cuota()
        previos = await self.repo.historial(c.id, settings.TUTOR_HISTORIAL_MENSAJES)
        historial = [turno_historial(m.rol, m.contenido, (m.datos or {}).get("pasos")) for m in previos]
        # Brechas en foco: las que nombra el mensaje o, si no, las de la última respuesta del
        # tutor (seguimiento: "explícame el paso 1"); si tampoco, las más prioritarias.
        citadas_antes = next((" ".join(b.get("ref", "") for b in (m.datos or {}).get("brechas", []))
                              for m in reversed(previos) if m.rol == RolMensajeTutor.TUTOR.value), "")
        foco = ctx.brechas_nombradas([texto])[:3] or ctx.brechas_en_foco([citadas_antes])
        # HU-18: los dos mensajes anteriores del usuario (ya anonimizados) para ataques en varios turnos
        previos_usuario = [m.contenido for m in previos if m.rol == RolMensajeTutor.USUARIO.value][-2:]
        try:
            salida = await self.agente.ejecutar(
                HabilidadIA.TUTOR,
                textos={"mensaje": texto, "antecedentes": texto_antecedentes(ctx, foco)},
                datos={"contexto": ctx, "nivel": c.nivel, "historial": historial, "foco": foco,
                       "previos_usuario": previos_usuario},
                contexto=ContextoLlamada(evaluacion_id=ctx.evaluacion_id, conversacion_id=c.id),
            )
        except CapaIAError as e:
            await reserva.devolver()  # no fue culpa del usuario: no gasta su cuota
            self._auditar_rechazo(c, e.tipo_error)
            await self.db.commit()
            err = TutorError(503, "TUTOR_NO_DISPONIBLE", e.mensaje_usuario, tipo_error=e.tipo_error)
            err.auditado = True
            raise err

        ahora = _ahora()
        if salida.bloqueado:
            return await self._bloqueado(c, ctx, texto, salida.motivo, salida.regla, ahora)
        for n in salida.neutralizados:  # antecedente de la empresa con inyección: se omitió
            await self._evento(n.get("texto") or "", n.get("categoria"), ctx, origen=OrigenEvento.TUTOR_ANTECEDENTE.value,
                              regla=n.get("regla"))

        r: TutorRespuesta = salida.resultado.data
        try:
            # El texto del usuario que se guarda es EXACTAMENTE el que vio el LLM (ya sanitizado)
            pregunta = salida.resultado.textos_sanitizados.get("mensaje") or await self._anon(texto)
            contenido, datos = await self._respuesta_anonimizada(r, ctx)
        except AnonimizacionError as e:
            self._auditar_rechazo(c, "anonimizacion")
            await self.db.commit()
            err = TutorError(503, "TUTOR_NO_DISPONIBLE", str(e))
            err.auditado = True
            raise err

        # HU-18: la salida filtró el system prompt -> se mostró un rechazo fijo; es un ataque logrado
        advertencia = None
        if salida.salida_bloqueada:
            await self._evento(texto, "fuga_prompt_salida", ctx, regla="salida.fuga_prompt")
            advertencia = await self._contar_bloqueo(c, ctx)

        m_usuario = MensajeTutor(
            conversacion_id=c.id, rol=RolMensajeTutor.USUARIO.value, tipo=TipoMensajeTutor.PREGUNTA.value,
            contenido=pregunta, nivel=c.nivel, bloqueado=False, traza_id=salida.resultado.traza_id,
            huella_contexto=ctx.huella(), fecha=ahora,
        )
        m_tutor = MensajeTutor(
            conversacion_id=c.id, rol=RolMensajeTutor.TUTOR.value,
            tipo=TipoMensajeTutor.BLOQUEADO.value if salida.salida_bloqueada else r.tipo.value, contenido=contenido,
            nivel=c.nivel, datos=datos, bloqueado=bool(salida.salida_bloqueada),
            motivo_bloqueo=salida.salida_bloqueada, traza_id=salida.resultado.traza_id,
            prompt_version=salida.resultado.prompt_version, advertencias=salida.advertencias or None,
            huella_contexto=ctx.huella(), fecha=ahora,
        )
        self._registrar_mensajes(c, ctx, pregunta, [m_usuario, m_tutor], ahora)
        self.bitacora.registrar(
            accion=Accion.TUTOR_SALIDA_BLOQUEADA if salida.salida_bloqueada else Accion.TUTOR_MENSAJE,
            entidad="conversacion_tutor", entidad_id=c.id, actor=self.cliente.actor,
            resultado=RESULTADO_RECHAZADO if salida.salida_bloqueada else RESULTADO_OK,
            detalle={"evaluacion_id": ctx.evaluacion_id, "nivel": c.nivel, "tipo": r.tipo.value,
                     "brechas_referenciadas": len(datos["brechas"]), "pasos": len(datos["pasos"]),
                     "advertencias": salida.advertencias, "traza_id": salida.resultado.traza_id,
                     "prompt_version": salida.resultado.prompt_version,
                     # HU-18: NER local y filtro, sin texto
                     "entidades_anonimizadas": salida.resultado.entidades_anonimizadas,
                     "antecedentes_omitidos": len(salida.neutralizados),
                     "salida_bloqueada": salida.salida_bloqueada,
                     "huella_mensaje": huella(texto)},
        )
        await self.db.commit()
        respuesta = {"mensaje_usuario": mensaje_a_dict(m_usuario), "respuesta": mensaje_a_dict(m_tutor),
                     "conversacion": conversacion_a_dict(c, ctx.evaluacion_id), "cuota": await self.cuota()}
        if advertencia:
            respuesta["advertencia"] = advertencia
        return respuesta
