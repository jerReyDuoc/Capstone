"""
HU-15 · Agente IA Tutor del panel de formación.

Como Oficial de Cumplimiento o Encargado de Datos, quiero interactuar con un Agente IA
Tutor especializado dentro de cada ruta formativa, para recibir orientaciones paso a paso,
explicaciones normativas adaptadas y recomendaciones contextuales que me permitan cerrar
las brechas de gobernanza identificadas.

  C1  Carga AISLADA del contexto: solo las brechas no conformes (no cumplido y
      parcialmente cumplido) de la evaluación más reciente de LA empresa del token
      (app/application/tutor/contexto.py). Se recarga en cada mensaje.
  C2  Explicaciones y planes de acción por nivel (Inicial, Intermedio, Avanzado). Por
      defecto el nivel de la ruta (la del módulo desde el que se abrió, o la de la brecha
      más prioritaria); el usuario lo puede cambiar.
  C3  Asistencia conversacional en tiempo real en el panel de formación: respuesta
      síncrona (la UI muestra "escribiendo…"), con la salida ya validada y anclada antes de
      mostrarse.

Reglas:
  - Solo el usuario definitivo con contrato VIGENTE (lo exige la ruta con
    empresa_con_servicio, HU-30).
  - El LLM no toca la BD: este caso de uso carga el contexto, llama al agente (LangGraph)
    y persiste. El agente bloquea el prompt injection ANTES del LLM y del NER.
  - En mensaje_tutor solo queda texto anonimizado (el mismo que vio el LLM; la respuesta
    del tutor se vuelve a anonimizar). Un mensaje bloqueado no guarda su texto.
  - Cuota diaria por empresa (TUTOR_MENSAJES_DIA_EMPRESA, 60 por defecto) + ráfaga por
    minuto + cuota global del LLM. Si el servicio de IA falla, la cuota se devuelve.
  - Toda acción queda en la bitácora (HU-09) sin el texto de los mensajes.

HU-18 (el agente cumple los mismos estándares que el sistema exige a las empresas):
  - El filtro de entrada clasifica el ataque (inyeccion, jailbreak, fuga_prompt,
    delimitadores, codificado, uso_indebido) y bloquea SIN llamar al NER ni al LLM; mira
    también los dos mensajes anteriores del usuario (ataques en varios turnos). Un
    antecedente de la empresa con inyección se omite en vez de bloquear todo.
  - La salida se valida: si filtra el system prompt (canario) se reemplaza por un rechazo.
  - TODA interacción queda en la bitácora inmutable (cadena de hashes): mensajes, bloqueos,
    salidas bloqueadas y también los rechazos (cuota, validación, conversación ajena), con la
    categoría, las entidades enmascaradas y una huella HMAC del mensaje, nunca su texto.
  - Abuso reiterado: desde el TUTOR_BLOQUEOS_ADVERTENCIA-ésimo bloqueo (3) en
    TUTOR_VENTANA_BLOQUEOS_MIN (10) minutos se muestra una advertencia y se alerta al Oficial
    de Cumplimiento con un evento de seguridad. No bloquea el tutor (decisión del equipo, 28-oct).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.application.ai.agente import AgenteIA, SkillIA
from app.application.ai.agente.salida import RESPUESTA_FUGA, SUGERENCIAS_FUGA
from app.application.ai.anonimizador import AnonimizacionError, AnonimizadorPII
from app.application.ai.gateway import CapaIAError
from app.application.ai.prompts.tutor import texto_antecedentes, turno_historial
from app.application.schemas.tutor import NivelTutor, TutorRespuesta
from app.application.tutor.contexto import ContextoTutor, ContextoTutorError, cargar_contexto_tutor
from app.application.use_cases.limites_encuesta import Reserva, ventana_diaria
from app.core.cliente import huella
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.models.tutor import ConversacionTutor, MensajeTutor, RolMensajeTutor, TipoMensajeTutor
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.infrastructure.cache.limitador import Limitador
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository
from app.infrastructure.repositories.tutor_repository import TutorRepository

MAX_TITULO = 80
TEXTO_BLOQUEADO_USUARIO = "[Mensaje bloqueado por seguridad: no se guardó su contenido]"
RESPUESTA_BLOQUEADO = (
    "No puedo procesar ese mensaje porque contiene instrucciones que intentan cambiar mis reglas. "
    "Reformula tu pregunta sobre las brechas de tu empresa y con gusto te ayudo."
)
SUGERENCIAS_BLOQUEO = ["¿Qué brecha debería cerrar primero?", "Explícame la brecha más crítica de mi evaluación."]
# HU-18: respuesta fija ante un pedido de fraude u ocultamiento (no se llama al LLM)
RESPUESTA_ETICA = (
    "No puedo ayudarte con eso: falsificar o adulterar evidencia, aparentar un cumplimiento que no existe u ocultar "
    "un incidente va contra la Ley 21.719 y contra la gobernanza que esta plataforma evalúa. Sí puedo ayudarte a "
    "preparar la evidencia real del control o a entender cómo y cuándo notificar un incidente."
)
SUGERENCIAS_ETICA = ["¿Qué evidencia real necesito para este control?", "¿Cómo se notifica un incidente de datos personales?"]
ADVERTENCIA_ABUSO = (
    "Hemos bloqueado varios mensajes seguidos que intentaban cambiar las reglas del tutor. El tutor sigue disponible "
    "para tus brechas de gobernanza; estos intentos quedan registrados y se informan al equipo de Therion Labs."
)


def respuesta_de_bloqueo(categoria: str | None) -> tuple[str, list[str]]:
    if categoria == "uso_indebido":
        return RESPUESTA_ETICA, SUGERENCIAS_ETICA
    if categoria == "fuga_prompt":
        return RESPUESTA_FUGA, SUGERENCIAS_FUGA
    return RESPUESTA_BLOQUEADO, SUGERENCIAS_BLOQUEO


class TutorError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra
        self.auditado = False  # HU-18: ya quedó en la bitácora (no registrarlo dos veces)


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _nivel(valor: str | None, por_defecto: NivelTutor) -> NivelTutor:
    if valor is None or valor == "":
        return por_defecto
    n = NivelTutor.normalizar(valor)
    if n is None:
        raise TutorError(422, "NIVEL_INVALIDO", "El nivel debe ser Inicial, Intermedio o Avanzado.",
                         niveles=NivelTutor.valores())
    return n


def mensaje_a_dict(m: MensajeTutor) -> dict:
    datos = m.datos or {}
    return {
        "id": m.id, "rol": m.rol, "tipo": m.tipo, "contenido": m.contenido, "nivel": m.nivel,
        "bloqueado": bool(m.bloqueado), "fecha": _iso(m.fecha),
        "pasos": datos.get("pasos", []), "brechas": datos.get("brechas", []),
        "referencias_normativas": datos.get("referencias_normativas", []),
        "sugerencias": datos.get("sugerencias", []),
    }


def conversacion_a_dict(c: ConversacionTutor, evaluacion_vigente: int | None) -> dict:
    vigente = evaluacion_vigente is not None and c.evaluacion_id == evaluacion_vigente
    return {
        "id": c.id, "titulo": c.titulo, "nivel": c.nivel, "evaluacion_id": c.evaluacion_id,
        "ruta_id": c.ruta_formativa_id, "mensajes_total": c.mensajes_total or 0,
        "fecha_creacion": _iso(c.fecha_creacion), "fecha_ultimo_mensaje": _iso(c.fecha_ultimo_mensaje),
        # Una conversación de una evaluación anterior queda de solo lectura
        "estado": "activa" if vigente else "solo_lectura",
    }


class TutorIA:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db, cliente, agente: AgenteIA | None, anonimizador: AnonimizadorPII | None,
                 limitador: Limitador | None, registrar_evento=None):
        self.db = db
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.usuario = cliente.usuario
        self.agente = agente
        self.anonimizador = anonimizador
        self.limitador = limitador
        self.registrar_evento = registrar_evento
        self.repo = TutorRepository(db)
        self.bitacora = BitacoraRepository(db)

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

    async def obtener(self, conversacion_id: int) -> dict:
        c = await self._conversacion(conversacion_id)
        vigente = await self._evaluacion_vigente()
        return {"conversacion": conversacion_a_dict(c, vigente),
                "mensajes": [mensaje_a_dict(m) for m in await self.repo.mensajes(c.id)],
                "cuota": await self.cuota()}

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

    async def _respuesta_anonimizada(self, r: TutorRespuesta, ctx: ContextoTutor) -> tuple[str, dict]:
        """Defensa en profundidad: lo que escribió el modelo también pasa por el NER antes de guardarse."""
        pasos = []
        for p in r.pasos:
            pasos.append({
                "orden": p.orden, "accion": await self._anon(p.accion),
                # lista cerrada (v1.1): no puede traer datos personales
                "responsable_sugerido": p.responsable_sugerido.value if p.responsable_sugerido else None,
                "evidencia_esperada": await self._anon(p.evidencia_esperada),
            })
        por_ref = {b.ref: b for b in ctx.brechas}
        brechas = [{
            "ref": ref, "codigo": por_ref[ref].codigo, "dominio": por_ref[ref].dominio,
            "severidad": por_ref[ref].severidad, "estado": por_ref[ref].estado,
            "ruta_id": por_ref[ref].ruta_id, "respuesta_id": por_ref[ref].respuesta_id,
        } for ref in r.brechas_referenciadas if ref in por_ref]
        datos = {
            "pasos": pasos, "brechas": brechas,
            # salen de la matriz de controles (v1.1), no del modelo
            "referencias_normativas": list(r.referencias_normativas),
            "sugerencias": [await self._anon(x) for x in r.sugerencias],
        }
        return await self._anon(r.respuesta) or "", datos

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
                SkillIA.TUTOR,
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
            await self._evento(n.get("texto") or "", n.get("categoria"), ctx, origen=OrigenEvento.TUTOR_ANTECEDENTE.value)

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
            await self._evento(texto, "fuga_prompt_salida", ctx)
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

    async def _evento(self, texto: str, tipo: str | None, ctx: ContextoTutor, origen: str | None = None) -> None:
        if self.registrar_evento is not None:
            await self.registrar_evento.execute(texto, origen or OrigenEvento.TUTOR.value,
                                                evaluacion_id=ctx.evaluacion_id, tipo=tipo or "prompt_injection")

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
        await self._evento(texto, motivo, ctx)
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

