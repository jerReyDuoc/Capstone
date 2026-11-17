"""Asistente RAT: anonimización, eventos de seguridad, núcleo "proponer" y respuesta a cada pregunta."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.application.ai.anonimizador import AnonimizacionError
from app.application.ai.gateway import CapaIAError
from app.application.ai.prompts.asistente_rat import PROMPT_VERSION, ContextoAsistente
from app.application.rat.asistente import anclaje, banco, contexto_asistente as contexto, inconsistencias
from app.application.rat.casos_uso.asistente_rat.comun import (
    AVISOS, MENSAJE_BLOQUEO, MENSAJE_ETICA, MENSAJE_FALLA_IA, MENSAJES_FALLA_IA, TEXTO_BLOQUEADO, TEXTO_NO_GUARDADO,
    TEXTO_OMITIDA, AsistenteError, _ahora, propuesta_a_dict,
)
from app.application.seguridad.huella import huella
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.models.asistente import AsistenteMensaje, AsistentePropuesta, AsistenteSesion
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.ports.limitador_port import LimitadorNoDisponibleError
from app.domain.ports.registro_ia_port import ContextoLlamada

logger = logging.getLogger(__name__)


class ConversacionMixin:
    """Depende de los atributos que fija AsistenteRat.__init__ (db, repo, limitador, agente, ...)."""

    # ------------------------------------------------------------------ anonimización (HU-06)
    async def _anon(self, texto: str | None) -> str | None:
        if texto is None or self.anonimizador is None:
            return texto
        return await self.anonimizador.anonimizar(texto)

    async def _anon_payload(self, tipo: str, payload: dict) -> dict:
        """Defensa en profundidad: lo que escribió el modelo también pasa por el NER antes de guardarse."""
        d = dict(payload)
        for campo in ("nombre", "descripcion", "proveedor", "responsable", "finalidad", "area", "interes_legitimo"):
            if isinstance(d.get(campo), str):
                d[campo] = await self._anon(d[campo])
        if tipo == "actividad":
            d["finalidades"] = [await self._anon(f) for f in d.get("finalidades") or []]
            d["plazos"] = [{**pl, "fundamento": await self._anon(pl.get("fundamento"))} for pl in d.get("plazos") or []]
        return d

    # ------------------------------------------------------------------ eventos y bitácora
    async def _evento(self, texto: str, tipo: str | None, origen: str, regla: str | None = None) -> None:
        if self.registrar_evento is not None:
            await self.registrar_evento.execute(texto, origen, tipo=tipo or "prompt_injection", regla=regla)

    # ------------------------------------------------------------------ núcleo: proponer (C1-C5)
    async def _proponer(self, *, respuesta: str, documento_texto: str, area: str, pregunta: str | None,
                        origen: str, sesion_id: int | None, documento_id: int | None, tipo_documento: str | None,
                        cuota: str, previos: list[str]) -> dict:
        """
        Llama al agente y guarda las propuestas como "sugeridas" (sin tocar el mapa ni el RAT). Devuelve
        {motivo_sin_ia, propuestas: [AsistentePropuesta], resumen, preguntas, traza_id, prompt_version,
         textos_sanitizados, entidades, neutralizados, bloqueado, motivo, regla}.
        """
        info: dict = {"motivo_sin_ia": None, "propuestas": [], "resumen": None, "preguntas": [], "traza_id": None,
                      "prompt_version": None, "modelo": None, "textos_sanitizados": {}, "entidades": 0,
                      "neutralizados": [], "bloqueado": False, "motivo": None, "regla": None, "descartes": []}
        if not self.ia_habilitada():
            info["motivo_sin_ia"] = "ia_deshabilitada"
            return info
        reserva = None
        if self.limitador is not None:
            try:
                reserva = await self._reservar(cuota)
            except LimitadorNoDisponibleError:
                info["motivo_sin_ia"] = "ia_no_disponible"
                return info
            if reserva is None:
                info["motivo_sin_ia"] = "cuota_ia_agotada"
                return info

        version, elementos, flujos = await self._mapa()
        actividades = await self._actividades()
        todas = await self._propuestas()
        pendientes = [p for p in todas if p.estado == "sugerida"]
        if len(pendientes) >= settings.ASISTENTE_MAX_PENDIENTES:
            if reserva is not None:
                await reserva.devolver()
            raise AsistenteError(409, "DEMASIADAS_PENDIENTES",
                                 f"Tienes {len(pendientes)} propuestas por revisar. Acepta o descarta algunas antes de "
                                 "seguir: así nada se te acumula.")
        referenciables = [p for p in todas if p.estado in ("sugerida", "aceptada", "editada")]
        # Corrección 13-11: el modelo ve solo las pendientes MÁS RECIENTES (las aceptadas ya están en el mapa con
        # su id). Antes iban todas en cada llamada y el prompt crecía con cada pregunta hasta agotar el límite de
        # tokens por minuto del proveedor. El anclaje sigue validando contra TODAS (ctx_anclaje, más abajo).
        en_prompt = pendientes[:settings.ASISTENTE_PENDIENTES_EN_PROMPT]
        mapa_txt = contexto.mapa_texto(
            elementos, flujos, [a for a in actividades if a["estado"] != "archivada"],
            [{"clave": p.clave, "tipo": p.tipo, "nombre": propuesta_a_dict(p)["nombre"]} for p in en_prompt])
        ctx = ContextoAsistente(area=area, area_nombre=banco.area(area).nombre if area in banco.AREAS_POR_CODIGO
                                else "Documento", pregunta=pregunta, catalogos=contexto.catalogos_texto(),
                                pendientes=tuple(p.clave for p in en_prompt), tipo_documento=tipo_documento)
        from app.application.ai.agente import SkillIA

        try:
            # Corrección 13-11: tiempo TOTAL acotado (anonimización + reintentos del proveedor + LLM). Antes un
            # 429 del proveedor con sus reintentos podía tardar varios minutos: el navegador se rendía a los 90 s
            # y la respuesta quedaba "colgada".
            salida = await asyncio.wait_for(self.agente.ejecutar(
                SkillIA.ASISTENTE_RAT,
                textos={"respuesta": respuesta, "documento": documento_texto, "mapa": mapa_txt},
                datos={"contexto": ctx, "previos_usuario": previos},
                contexto=ContextoLlamada(),
            ), timeout=settings.ASISTENTE_TIEMPO_MAXIMO_S)
        except CapaIAError as e:
            if reserva is not None:
                await reserva.devolver()   # no fue culpa del usuario: no gasta su cuota
            info.update(motivo_sin_ia="ia_no_disponible", error_ia=e.tipo_error)
            return info
        except asyncio.TimeoutError:
            if reserva is not None:
                await reserva.devolver()
            logger.warning("HU-39: la ayuda automática superó %ss", settings.ASISTENTE_TIEMPO_MAXIMO_S)
            info.update(motivo_sin_ia="ia_no_disponible", error_ia="timeout")
            return info

        info["neutralizados"] = list(salida.neutralizados)
        if salida.bloqueado:
            if reserva is not None:
                await reserva.devolver()
            info.update(bloqueado=True, motivo=salida.motivo, regla=salida.regla)
            return info
        resultado = salida.resultado
        info.update(traza_id=resultado.traza_id, prompt_version=resultado.prompt_version, modelo=resultado.modelo,
                    textos_sanitizados=dict(resultado.textos_sanitizados),
                    entidades=resultado.entidades_anonimizadas)
        if salida.salida_bloqueada:
            await self._evento(respuesta or documento_texto[:2000], "fuga_prompt_salida",
                               OrigenEvento.ASISTENTE.value if origen == "entrevista"
                               else OrigenEvento.ASISTENTE_DOCUMENTO.value, regla="salida.fuga_prompt")
            info["motivo_sin_ia"] = "salida_ia_descartada"
            return info

        data = resultado.data
        ctx_anclaje = anclaje.ContextoAnclaje(
            ids_elementos={e.id for e in elementos}, ids_flujos={f.id for f in flujos},
            pendientes={p.clave: p.tipo for p in referenciables},
            claves_usadas={p.clave for p in todas} | set(await self.repo.claves_de_propuestas(self.empresa_id)))
        anclado = anclaje.anclar(data, ctx_anclaje)
        info["descartes"] = anclado.descartes
        alias = {p.clave: p.entidad_destino_id for p in referenciables
                 if p.estado in ("aceptada", "editada") and p.entidad_destino_id}
        evaluacion = inconsistencias.evaluar_propuestas(
            [{"tipo": a.tipo, "clave": a.clave, "payload": a.payload} for a in anclado.propuestas],
            [{"tipo": p.tipo, "clave": p.clave, "payload": p.payload_propuesto} for p in pendientes],
            elementos, flujos, actividades, alias)
        try:
            info["resumen"] = await self._anon(data.resumen)
            info["preguntas"] = [await self._anon(q) for q in data.preguntas_pendientes[:3]]
            ahora = _ahora()
            for a in anclado.propuestas:
                ev = evaluacion.get(a.clave) or {}
                fila = AsistentePropuesta(
                    empresa_id=self.empresa_id, sesion_id=sesion_id, documento_id=documento_id, origen=origen,
                    area=area if area in banco.AREAS_POR_CODIGO else None, tipo=a.tipo, clave=a.clave,
                    estado="sugerida", payload_propuesto=await self._anon_payload(a.tipo, a.payload),
                    explicaciones={k: await self._anon(v) for k, v in a.explicaciones.items()},
                    inconsistencias=ev.get("inconsistencias") or [], riesgo_nivel=ev.get("riesgo"),
                    confianza=a.confianza, modelo=(resultado.modelo or "desconocido")[:80],
                    prompt_version=resultado.prompt_version or PROMPT_VERSION, traza_id=resultado.traza_id,
                    version_mapa_base=version, fecha_creacion=ahora)
                if a.riesgo_sugerido and "riesgo" not in fila.explicaciones:
                    fila.explicaciones = {**fila.explicaciones, "riesgo": (
                        f"La ayuda automática lo estimó en {a.riesgo_sugerido.lower()}; el nivel que ves lo calcula "
                        "la plataforma con su matriz de riesgos.")}
                self.db.add(fila)
                info["propuestas"].append(fila)
        except AnonimizacionError:
            for fila in info["propuestas"]:
                self.db.expunge(fila)
            info.update(propuestas=[], resumen=None, preguntas=[], motivo_sin_ia="anonimizacion")
            return info
        if not info["propuestas"]:
            info["motivo_sin_ia"] = info["motivo_sin_ia"] or "sin_propuestas"
        await self.db.flush()
        return info

    async def _registrar_neutralizados(self, neutralizados: list[dict]) -> None:
        for n in neutralizados:
            origen = OrigenEvento.ASISTENTE_DOCUMENTO.value if n.get("campo") == "documento" else OrigenEvento.ASISTENTE.value
            await self._evento(n.get("texto") or "", n.get("categoria"), origen, regla=n.get("regla"))

    # ------------------------------------------------------------------ responder (C1)
    async def responder(self, sesion_id: int, texto: str | None, omitir: bool = False, sin_ia: bool = False) -> dict:
        """
        `omitir`: salta la pregunta. `sin_ia`: guarda la respuesta sin llamar a la ayuda automática (lo elige el
        usuario cuando la ayuda falló). Si la ayuda falla por algo pasajero (cuota por minuto del proveedor, tiempo
        de espera, conexión), la pregunta no avanza y se responde 503 AYUDA_NO_DISPONIBLE para reintentar.
        """
        # Corrección 13-11: la sesión se lee SIN bloquearla. Antes quedaba bloqueada (SELECT … FOR UPDATE) durante
        # toda la llamada al LLM: si el navegador se rendía y el usuario reenviaba, la segunda petición esperaba
        # el bloqueo de la primera y el asistente "dejaba de responder". Ahora se bloquea solo al guardar.
        s = await self._sesion(sesion_id)
        if s.estado != "activa":
            raise AsistenteError(409, "SESION_CERRADA", "Esta entrevista ya terminó. Abre una nueva.")
        p = banco.pregunta(s.area_actual, s.paso)
        if p is None:
            raise AsistenteError(409, "ENTREVISTA_TERMINADA", "Ya respondiste todas las preguntas. Revisa las propuestas "
                                 "o elige un área para agregar más información.")
        clave_proceso = await self._tomar_turno(s.id)
        try:
            return await self._responder(s, p, texto, omitir, sin_ia)
        finally:
            await self._soltar_turno(clave_proceso)

    async def _responder(self, s: AsistenteSesion, p: banco.Pregunta, texto: str | None, omitir: bool,
                         sin_ia: bool) -> dict:
        sesion_id, area_pregunta, paso_pregunta = s.id, s.area_actual, s.paso
        texto = (texto or "").strip()
        if not omitir:
            if not texto:
                raise AsistenteError(422, "RESPUESTA_VACIA", "Escribe tu respuesta o elige «Saltar pregunta».")
            if len(texto) > settings.ASISTENTE_MAX_CHARS_RESPUESTA:
                raise AsistenteError(422, "RESPUESTA_DEMASIADO_LARGA",
                                     f"La respuesta supera los {settings.ASISTENTE_MAX_CHARS_RESPUESTA} caracteres.",
                                     max_caracteres=settings.ASISTENTE_MAX_CHARS_RESPUESTA)
        ahora = _ahora()
        area_respondida = s.area_actual

        if omitir or sin_ia:
            info = {"motivo_sin_ia": "sin_ayuda" if sin_ia else None, "propuestas": [], "resumen": None,
                    "preguntas": [], "traza_id": None, "prompt_version": None, "textos_sanitizados": {}, "entidades": 0,
                    "neutralizados": [], "bloqueado": False, "descartes": []}
            if omitir:
                contenido_usuario = TEXTO_OMITIDA
            else:
                try:
                    contenido_usuario = await self._anon(texto) if self.anonimizador else TEXTO_NO_GUARDADO
                except AnonimizacionError:
                    contenido_usuario = TEXTO_NO_GUARDADO
        else:
            previos = [m.contenido for m in await self.repo.mensajes_usuario_no_bloqueados(s.id, 2)][::-1]
            info = await self._proponer(respuesta=texto, documento_texto="", area=s.area_actual, pregunta=p.texto,
                                        origen="entrevista", sesion_id=s.id, documento_id=None, tipo_documento=None,
                                        cuota="dia", previos=previos)
            if info["bloqueado"]:
                return await self._bloqueada(s, p, texto, info, ahora)
            if info["motivo_sin_ia"] == "ia_no_disponible":
                await self._falla_ia(s, p, texto, info)
            await self._registrar_neutralizados(info["neutralizados"])
            # Lo que se guarda es EXACTAMENTE lo que vio el LLM (ya sanitizado); sin IA, se anonimiza aquí
            contenido_usuario = info["textos_sanitizados"].get("respuesta")
            if not contenido_usuario:
                try:
                    contenido_usuario = await self._anon(texto) if self.anonimizador else TEXTO_NO_GUARDADO
                except AnonimizacionError:
                    contenido_usuario = TEXTO_NO_GUARDADO

        # Ahora sí se bloquea la sesión, solo para avanzar la pregunta, y se confirma que nadie la avanzó mientras
        # la IA trabajaba (otra pestaña): en ese caso no se guarda nada de esta respuesta.
        s = await self._sesion(sesion_id, bloquear=True)
        if s.estado != "activa" or (s.area_actual, s.paso) != (area_pregunta, paso_pregunta):
            await self.db.rollback()
            raise AsistenteError(409, "PREGUNTA_YA_RESPONDIDA", "Esta pregunta ya se respondió en otra pestaña. "
                                 "Recargamos la entrevista para que sigas desde donde va.")
        self.db.add(AsistenteMensaje(sesion_id=s.id, rol="usuario", area=area_respondida, pregunta_codigo=p.codigo,
                                     contenido=contenido_usuario, bloqueado=False, traza_id=info.get("traza_id"),
                                     fecha=ahora))
        s.area_actual, s.paso, s.areas_completadas = banco.siguiente(s.area_actual, s.paso,
                                                                     list(s.areas_completadas or []))
        s.fecha_actualizacion = ahora
        siguiente = banco.pregunta(s.area_actual, s.paso)
        texto_asistente = self._texto_asistente(info, siguiente, omitir)
        self.db.add(AsistenteMensaje(sesion_id=s.id, rol="asistente", area=s.area_actual,
                                     pregunta_codigo=siguiente.codigo if siguiente else None,
                                     contenido=texto_asistente, bloqueado=False, motivo_sin_ia=info["motivo_sin_ia"],
                                     traza_id=info.get("traza_id"), prompt_version=info.get("prompt_version"),
                                     fecha=ahora))
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_RESPUESTA, entidad="asistente_sesion", entidad_id=s.id, actor=self.actor,
            detalle={"area": area_respondida, "pregunta": p.codigo, "omitida": omitir,
                     "propuestas": len(info["propuestas"]), "motivo_sin_ia": info["motivo_sin_ia"],
                     "traza_id": info.get("traza_id"), "prompt_version": info.get("prompt_version"),
                     "entidades_anonimizadas": info.get("entidades", 0),
                     "lineas_omitidas": len(info.get("neutralizados") or []),
                     "descartes": (info.get("descartes") or [])[:20], "error_ia": info.get("error_ia"),
                     "huella_respuesta": huella(texto) if texto else None, "largo": len(texto)})
        await self.db.commit()
        return {**await self.estado(), "nuevas": [p_.id for p_ in info["propuestas"]],
                "aviso": AVISOS.get(info["motivo_sin_ia"] or "")}

    async def _falla_ia(self, s: AsistenteSesion, p: banco.Pregunta, texto: str, info: dict) -> None:
        """La ayuda falló (la cuota ya se devolvió): no se guarda nada, queda auditado y se pide reintentar."""
        tipo = info.get("error_ia")
        sesion_id = s.id   # antes del rollback: después el objeto queda expirado
        await self.db.rollback()
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_RESPUESTA, entidad="asistente_sesion", entidad_id=sesion_id,
            actor=self.actor, resultado=RESULTADO_RECHAZADO,
            detalle={"area": p.codigo.split(".")[0], "pregunta": p.codigo, "motivo_sin_ia": "ia_no_disponible",
                     "error_ia": tipo, "huella_respuesta": huella(texto), "largo": len(texto)})
        await self.db.commit()
        raise AsistenteError(503, "AYUDA_NO_DISPONIBLE", MENSAJES_FALLA_IA.get(tipo or "", MENSAJE_FALLA_IA),
                             tipo_error=tipo, reintentar_en_s=30 if tipo == "rate_limit" else None)

    @staticmethod
    def _texto_asistente(info: dict, siguiente: banco.Pregunta | None, omitida: bool) -> str:
        partes: list[str] = []
        if info.get("resumen"):
            partes.append(info["resumen"])
        n = len(info.get("propuestas") or [])
        if n:
            partes.append(f"Te dejé {n} propuesta{'s' if n != 1 else ''} para revisar: acéptalas, edítalas o "
                          "descártalas. Nada se guarda sin tu confirmación.")
        elif not omitida and info.get("motivo_sin_ia") == "sin_propuestas":
            partes.append("Con esta respuesta no encontré nada nuevo que proponer.")
        aviso = AVISOS.get(info.get("motivo_sin_ia") or "")
        if aviso:
            partes.append(aviso)
        for q in info.get("preguntas") or []:
            partes.append(f"Para completar: {q}")
        partes.append(siguiente.texto if siguiente else
                      "¡Terminamos la entrevista! Revisa las propuestas pendientes y las alertas del registro. Luego "
                      "puedes descargar el informe del mapa de datos y el del registro de actividades.")
        return "\n\n".join(partes)

    async def _bloqueada(self, s: AsistenteSesion, p: banco.Pregunta, texto: str, info: dict, ahora: datetime) -> dict:
        """HU-18: un ataque en la respuesta no llega al NER ni al LLM; no se guarda su texto y queda auditado."""
        await self._evento(texto, info.get("motivo"), OrigenEvento.ASISTENTE.value, regla=info.get("regla"))
        self.db.add(AsistenteMensaje(sesion_id=s.id, rol="usuario", area=s.area_actual, pregunta_codigo=p.codigo,
                                     contenido=TEXTO_BLOQUEADO, bloqueado=True,
                                     motivo_bloqueo=(info.get("motivo") or "inyeccion")[:30], fecha=ahora))
        etica = info.get("motivo") == "uso_indebido"
        self.db.add(AsistenteMensaje(sesion_id=s.id, rol="asistente", area=s.area_actual, pregunta_codigo=p.codigo,
                                     contenido=(MENSAJE_ETICA if etica else MENSAJE_BLOQUEO) + "\n\n" + p.texto,
                                     bloqueado=False, fecha=ahora))
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_RESPUESTA_BLOQUEADA, entidad="asistente_sesion", entidad_id=s.id,
            actor=self.actor, resultado=RESULTADO_RECHAZADO,
            detalle={"area": s.area_actual, "pregunta": p.codigo, "categoria": info.get("motivo"),
                     "regla": info.get("regla"), "huella_respuesta": huella(texto), "largo": len(texto)})
        await self.db.commit()
        return {**await self.estado(), "nuevas": [], "bloqueado": True,
                "aviso": MENSAJE_ETICA if etica else MENSAJE_BLOQUEO}
