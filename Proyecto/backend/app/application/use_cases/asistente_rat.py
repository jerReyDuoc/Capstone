"""
HU-39 · Asistente de IA para armar el mapa de datos, el RAT y los informes.

Como Usuario Definitivo (cliente), quiero un agente de IA que me guíe para armar el mapa de datos, el RAT
y los informes, para completarlos sin ser experto en protección de datos y en menos tiempo.

  C1  Entrevista guiada por área (personas, clientes, proveedores, marketing, TI y uso de IA) en lenguaje
      simple (app/application/asistente/banco.py). A partir de cada respuesta propone sistemas, flujos y
      actividades con sus campos pre-llenados.
  C2  Sugiere base de licitud, plazos y nivel de riesgo explicando por qué. Las inconsistencias (dato
      sensible sin base, transferencia sin garantía, actividad sin plazo, flujo sin actividad) y el riesgo
      los CALCULA el backend (app/application/asistente/inconsistencias.py), no el modelo.
  C3  Lee documentos de la empresa (políticas, contratos con proveedores, avisos): extracción y RAG local
      de HU-17, detector con contexto de HU-33 (línea por línea, perfil "evidencia") y NER antes del LLM.
  C4  Human-in-the-Loop: nada entra al mapa ni al RAT sin confirmación. Cada propuesta se acepta (tal cual
      o editada) o se descarta y queda marcada con el modelo, la versión del prompt y la traza. Al aceptar
      se usan los MISMOS casos de uso del mapa (HU-34) y del RAT (HU-35): mismas validaciones, versiones,
      revisión de actividades afectadas y bitácora. Las actividades entran como borrador.
  C5  Mismos guardarraíles que el tutor (HU-18): skill "asistente_rat" del agente con scope locking,
      filtro de entrada (la respuesta se bloquea; el documento y los nombres del mapa se neutralizan línea
      por línea), canario y revisión de la salida, NER del gateway antes del LLM (R1-R6), cuota diaria por
      empresa y bitácora encadenada sin texto (solo huellas, códigos y conteos). NUNCA se envían datos de
      titulares al LLM: además del NER, las preguntas piden procesos (no personas) y un documento con
      demasiadas entidades personales (un listado de personas) se rechaza antes del LLM.
  C6  Sin IA (deshabilitada, caída o sin cuota) la entrevista sigue igual: las respuestas se guardan, se
      ofrecen las sugerencias de la evaluación y las plantillas del mapa (HU-34) y todo se completa a mano
      (misma degradación que HU-16: se avisa por qué y nada se pierde).

Solo el usuario definitivo con contrato VIGENTE (la ruta usa empresa_con_servicio, HU-30).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ai.anonimizador import AnonimizacionError, AnonimizadorPII
from app.application.ai.gateway import CapaIAError
from app.application.ai.prompts.asistente_rat import PROMPT_VERSION, ContextoAsistente
from app.application.asistente import anclaje, banco, contexto, documento, inconsistencias
from app.application.use_cases.limites_encuesta import Reserva, ventana_diaria
from app.core.cliente import huella
from app.core.config import settings
from app.domain.models.asistente import (
    DECIDIDAS, MOTIVOS_DESCARTE, AsistenteDocumento, AsistenteMensaje, AsistentePropuesta, AsistenteSesion,
)
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO
from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.models.rat import RatActividad
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

MAX_MENSAJES_VISTA = 80
MAX_PROPUESTAS_VISTA = 200
MUESTRA_DENSIDAD = 30000
MIN_CARACTERES_DOCUMENTO = 200
TEXTO_BLOQUEADO = "[Respuesta bloqueada por seguridad: no se guardó su contenido]"
TEXTO_OMITIDA = "(Pregunta omitida)"
TEXTO_NO_GUARDADO = "(Respuesta no guardada: el servicio de anonimización no está disponible)"

AVISOS = {
    "ia_deshabilitada": "La ayuda automática no está activada. Puedes seguir respondiendo y completar todo a mano; "
                        "te mostramos sugerencias según tu evaluación.",
    "cuota_ia_agotada": "Tu empresa usó la ayuda automática de hoy. Puedes seguir respondiendo y completar todo a "
                        "mano; mañana podrás volver a usarla.",
    "ia_no_disponible": "La ayuda automática no respondió esta vez. Tu respuesta quedó guardada: puedes seguir y "
                        "completar a mano, o volver a intentarlo más tarde.",
    "salida_ia_descartada": "Descartamos lo que propuso la ayuda automática porque no pasó la revisión de seguridad. "
                            "Puedes seguir y completar a mano.",
    "anonimizacion": "No pudimos proteger los datos de esta respuesta, así que no usamos la ayuda automática. "
                     "Puedes seguir y completar a mano.",
    "sin_propuestas": None,
}
MENSAJE_BLOQUEO = ("Tu respuesta contiene texto que intenta cambiar las reglas del asistente, así que no la "
                   "procesamos. Cuéntanos con tus palabras qué hace tu empresa (por ejemplo, «usamos un sistema de "
                   "remuneraciones en la nube»).")
MENSAJE_ETICA = ("No podemos ayudarte con eso: el registro debe reflejar lo que tu empresa realmente hace, sin ocultar "
                 "tratamientos, transferencias ni el uso de IA (Ley 21.719).")
ESTADO_DOCUMENTO_MENSAJE = {
    "ilegible": "No pudimos leer el archivo. Revisa que no esté dañado ni protegido con contraseña.",
    "sin_texto": "No encontramos texto en el archivo (¿es un documento escaneado?). Sube una versión con texto "
                 "seleccionable.",
    "rechazado_pii": "Este archivo parece una lista o planilla con datos de personas. Sube la política, el contrato "
                     "o el aviso, no la base de datos: el asistente describe procesos, no personas.",
}


class AsistenteError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def etiqueta_ia(modelo: str | None, prompt_version: str | None) -> str | None:
    """«Sugerido por IA · Modelo X · Guía v1.0.0» (lo que ve el usuario, sin jerga)."""
    if not modelo or modelo == "sin_ia":
        return None
    version = (prompt_version or "").split("/")[-1] or "?"
    return f"Sugerido por IA · Modelo {modelo} · Guía v{version}"


def propuesta_a_dict(p: AsistentePropuesta) -> dict:
    payload = p.payload_final if p.payload_final is not None else p.payload_propuesto
    return {
        "id": p.id, "tipo": p.tipo, "clave": p.clave, "estado": p.estado, "origen": p.origen, "area": p.area,
        "nombre": (payload.get("finalidad") or "Flujo de datos") if p.tipo == "flujo" else payload.get("nombre"),
        "payload": p.payload_propuesto, "payload_final": p.payload_final, "campos_editados": p.campos_editados or [],
        "explicaciones": p.explicaciones or {}, "inconsistencias": p.inconsistencias or [],
        "riesgo_nivel": p.riesgo_nivel, "confianza": p.confianza,
        "ia": {"modelo": p.modelo, "prompt_version": p.prompt_version, "traza_id": p.traza_id,
               "etiqueta": etiqueta_ia(p.modelo, p.prompt_version)},
        "entidad_destino": p.entidad_destino, "entidad_destino_id": p.entidad_destino_id,
        "motivo_descarte": p.motivo_descarte, "documento_id": p.documento_id,
        "fecha_creacion": _iso(p.fecha_creacion), "fecha_decision": _iso(p.fecha_decision),
    }


def mensaje_a_dict(m: AsistenteMensaje) -> dict:
    return {"id": m.id, "rol": m.rol, "area": m.area, "pregunta_codigo": m.pregunta_codigo, "contenido": m.contenido,
            "bloqueado": bool(m.bloqueado), "motivo_sin_ia": m.motivo_sin_ia, "fecha": _iso(m.fecha)}


def documento_a_dict(d: AsistenteDocumento) -> dict:
    return {"id": d.id, "nombre_archivo": d.nombre_archivo, "tipo_documento": d.tipo_documento,
            "tipo_documento_nombre": documento.NOMBRES_TIPO.get(d.tipo_documento, "Otro documento"),
            "estado": d.estado, "lineas_omitidas": d.lineas_omitidas, "pasajes_usados": d.pasajes_usados,
            "pasajes_total": d.pasajes_total, "motivo_sin_ia": d.motivo_sin_ia, "fecha": _iso(d.fecha)}


def sesion_a_dict(s: AsistenteSesion) -> dict:
    completadas = list(s.areas_completadas or [])
    p = banco.pregunta(s.area_actual, s.paso)
    a = banco.area(s.area_actual)
    return {
        "id": s.id, "estado": s.estado, "area_actual": s.area_actual, "area_nombre": a.nombre, "paso": s.paso,
        "total_pasos": len(a.preguntas), "areas": banco.resumen_areas(s.area_actual, completadas),
        "pregunta": p.como_dict() if p else None,
        "terminada": banco.terminada(s.area_actual, s.paso, completadas),
        "fecha_actualizacion": _iso(s.fecha_actualizacion),
    }


# ============================================================================ caso de uso
class AsistenteRat:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, agente=None, anonimizador: AnonimizadorPII | None = None,
                 limitador: Limitador | None = None, registrar_evento=None):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.usuario_id: int = cliente.usuario.id
        self.agente = agente
        self.anonimizador = anonimizador
        self.limitador = limitador
        self.registrar_evento = registrar_evento
        self.bitacora = BitacoraRepository(db)

    # ------------------------------------------------------------------ cuota (C5)
    def _clave(self, tipo: str, fecha: str) -> str:
        return f"asistente:{tipo}:{self.empresa_id}:{fecha}"

    async def cuota(self) -> dict:
        fecha, _, reinicio = ventana_diaria()
        salida = {"reinicia_en": reinicio.isoformat().replace("+00:00", "Z")}
        for tipo, limite in (("dia", settings.ASISTENTE_RESPUESTAS_DIA_EMPRESA),
                             ("doc", settings.ASISTENTE_DOCUMENTOS_DIA_EMPRESA)):
            try:
                usados = await self.limitador.usados(self._clave(tipo, fecha)) if self.limitador else 0
            except LimitadorNoDisponibleError:
                usados = 0
            salida["respuestas" if tipo == "dia" else "documentos"] = {
                "usados": usados, "limite": limite or None,
                "restantes": max(0, limite - usados) if limite > 0 else None}
        return salida

    def ia_habilitada(self) -> bool:
        return bool(settings.ASISTENTE_IA_HABILITADA) and self.agente is not None

    async def _reservar(self, tipo: str) -> Reserva | None:
        """None si la cuota diaria (de la empresa o global) se agotó: se sigue sin IA (C6). La ráfaga es 429."""
        fecha, ventana, _ = ventana_diaria()
        reserva = Reserva(self.limitador)
        pasos = []
        if tipo == "dia":
            pasos.append((f"asistente:min:{self.empresa_id}", settings.ASISTENTE_RESPUESTAS_MINUTO_EMPRESA, 60, True))
        limite = settings.ASISTENTE_RESPUESTAS_DIA_EMPRESA if tipo == "dia" else settings.ASISTENTE_DOCUMENTOS_DIA_EMPRESA
        pasos += [(self._clave(tipo, fecha), limite, ventana, False),
                  (f"llm:global:{fecha}", settings.LLM_CUOTA_DIARIA_GLOBAL, ventana, False)]
        for clave, limite, ventana_s, es_rafaga in pasos:
            if limite <= 0:
                continue
            consumo = await self.limitador.consumir(clave, limite, ventana_s)
            reserva.claves.append(clave)
            if not consumo.permitido:
                await reserva.devolver()
                if es_rafaga:
                    raise AsistenteError(429, "ASISTENTE_RAFAGA", "Estás respondiendo muy rápido. Espera unos "
                                         "segundos e inténtalo de nuevo.",
                                         reintentar_en_s=getattr(consumo, "reintentar_en_s", None))
                return None
        return reserva

    # ------------------------------------------------------------------ lectura
    async def _sesion(self, sesion_id: int, bloquear: bool = False) -> AsistenteSesion:
        q = select(AsistenteSesion).where(AsistenteSesion.id == sesion_id,
                                          AsistenteSesion.empresa_id == self.empresa_id)
        if bloquear:
            q = q.with_for_update()
        s = (await self.db.execute(q)).scalar_one_or_none()
        if s is None:                      # lo de otra empresa no existe (404, no 403)
            raise AsistenteError(404, "SESION_NO_ENCONTRADA", "No encontramos esa entrevista.")
        return s

    async def _sesion_activa(self) -> AsistenteSesion | None:
        return (await self.db.execute(
            select(AsistenteSesion).where(AsistenteSesion.empresa_id == self.empresa_id,
                                          AsistenteSesion.estado == "activa")
            .order_by(AsistenteSesion.id.desc()).limit(1))).scalar_one_or_none()

    async def _propuesta(self, propuesta_id: int, bloquear: bool = False) -> AsistentePropuesta:
        q = select(AsistentePropuesta).where(AsistentePropuesta.id == propuesta_id,
                                             AsistentePropuesta.empresa_id == self.empresa_id)
        if bloquear:
            q = q.with_for_update()
        p = (await self.db.execute(q)).scalar_one_or_none()
        if p is None:
            raise AsistenteError(404, "PROPUESTA_NO_ENCONTRADA", "No encontramos esa propuesta.")
        return p

    async def _propuestas(self) -> list[AsistentePropuesta]:
        return list((await self.db.execute(
            select(AsistentePropuesta).where(AsistentePropuesta.empresa_id == self.empresa_id)
            .order_by(AsistentePropuesta.id.desc()).limit(MAX_PROPUESTAS_VISTA))).scalars().all())

    async def _mapa(self):
        from app.application.use_cases.mapa_datos import MapaDatosCasos

        mapa, elementos, flujos = await MapaDatosCasos(self.db, self.cliente).dominio()
        return (mapa.version if mapa else 0), elementos, flujos

    async def _actividades(self) -> list[dict]:
        filas = (await self.db.execute(
            select(RatActividad).where(RatActividad.empresa_id == self.empresa_id).order_by(RatActividad.nombre)
        )).scalars().all()
        return [{"id": f.id, "nombre": f.nombre, "estado": f.estado, "contenido": f.contenido} for f in filas]

    @staticmethod
    def _referencias(elementos, flujos, propuestas: list[AsistentePropuesta]) -> dict:
        """Nombres legibles de las referencias de las propuestas ("id:3", "nuevo:crm") para la pantalla."""
        por_el = {e.id: e for e in elementos}
        refs = {"elementos": {f"id:{e.id}": e.nombre for e in elementos}, "flujos": {}}
        for f in flujos:
            o, d = por_el.get(f.origen_id), por_el.get(f.destino_id)
            refs["flujos"][f"id:{f.id}"] = f"{o.nombre if o else '?'} → {d.nombre if d else '?'}"
        for p in propuestas:
            datos = p.payload_final or p.payload_propuesto
            if p.tipo == "elemento":
                refs["elementos"][f"nuevo:{p.clave}"] = datos.get("nombre") or p.clave
            elif p.tipo == "flujo":
                refs["flujos"][f"nuevo:{p.clave}"] = datos.get("finalidad") or "Flujo propuesto"
        return refs

    async def estado(self) -> dict:
        """Todo lo que muestra la pantalla del asistente."""
        s = await self._sesion_activa()
        mensajes = []
        if s is not None:
            mensajes = list((await self.db.execute(
                select(AsistenteMensaje).where(AsistenteMensaje.sesion_id == s.id)
                .order_by(AsistenteMensaje.id.desc()).limit(MAX_MENSAJES_VISTA))).scalars().all())[::-1]
        version, elementos, flujos = await self._mapa()
        actividades = await self._actividades()
        propuestas = await self._propuestas()
        documentos = list((await self.db.execute(
            select(AsistenteDocumento).where(AsistenteDocumento.empresa_id == self.empresa_id)
            .order_by(AsistenteDocumento.id.desc()).limit(20))).scalars().all())
        return {
            "sesion": sesion_a_dict(s) if s else None,
            "mensajes": [mensaje_a_dict(m) for m in mensajes],
            "propuestas": [propuesta_a_dict(p) for p in propuestas],
            "pendientes": sum(1 for p in propuestas if p.estado == "sugerida"),
            "referencias": self._referencias(elementos, flujos, propuestas),
            "documentos": [documento_a_dict(d) for d in documentos],
            "revision": inconsistencias.globales(elementos, flujos, actividades),
            "mapa": {"version": version, "elementos": len(elementos), "flujos": len(flujos),
                     "actividades": sum(1 for a in actividades if a["estado"] != "archivada")},
            "areas": [a.como_dict() for a in banco.AREAS],
            # Lo que se muestra: si la ayuda automática está activada (si además responde, se sabe al usarla)
            "ia": {"habilitada": bool(settings.ASISTENTE_IA_HABILITADA), "cuota": await self.cuota()},
            "limites": {"max_caracteres": settings.ASISTENTE_MAX_CHARS_RESPUESTA,
                        "max_mb_documento": settings.ASISTENTE_DOCUMENTO_MAX_MB,
                        "max_pendientes": settings.ASISTENTE_MAX_PENDIENTES},
        }

    # ------------------------------------------------------------------ sesión (C1)
    async def iniciar(self, area: str | None = None) -> dict:
        """Abre una entrevista (o reanuda la activa). `area` permite partir por otra área."""
        if area is not None and area not in banco.AREAS_POR_CODIGO:
            raise AsistenteError(422, "AREA_INVALIDA", "Elige un área de la lista.")
        s = await self._sesion_activa()
        ahora = _ahora()
        if s is None:
            s = AsistenteSesion(empresa_id=self.empresa_id, usuario_definitivo_id=self.usuario_id,
                                area_actual=area or banco.ORDEN_AREAS[0], paso=0, areas_completadas=[],
                                estado="activa", fecha_creacion=ahora, fecha_actualizacion=ahora)
            self.db.add(s)
            await self.db.flush()
            self.bitacora.registrar(accion=Accion.ASISTENTE_SESION_CREADA, entidad="asistente_sesion",
                                    entidad_id=s.id, actor=self.actor,
                                    detalle={"empresa_id": self.empresa_id, "area": s.area_actual})
        elif area is not None and area != s.area_actual:
            s.area_actual, s.paso, s.fecha_actualizacion = area, 0, ahora
        await self.db.commit()
        return await self.estado()

    async def cambiar_area(self, sesion_id: int, area: str) -> dict:
        s = await self._sesion(sesion_id)
        if s.estado != "activa":
            raise AsistenteError(409, "SESION_CERRADA", "Esta entrevista ya terminó. Abre una nueva.")
        return await self.iniciar(area)

    async def cerrar(self, sesion_id: int) -> dict:
        s = await self._sesion(sesion_id)
        s.estado, s.fecha_actualizacion = "cerrada", _ahora()
        await self.db.commit()
        return await self.estado()

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
        mapa_txt = contexto.mapa_texto(
            elementos, flujos, [a for a in actividades if a["estado"] != "archivada"],
            [{"clave": p.clave, "tipo": p.tipo, "nombre": propuesta_a_dict(p)["nombre"]} for p in pendientes])
        ctx = ContextoAsistente(area=area, area_nombre=banco.area(area).nombre if area in banco.AREAS_POR_CODIGO
                                else "Documento", pregunta=pregunta, catalogos=contexto.catalogos_texto(),
                                pendientes=tuple(p.clave for p in referenciables), tipo_documento=tipo_documento)
        from app.application.ai.agente import SkillIA

        try:
            salida = await self.agente.ejecutar(
                SkillIA.ASISTENTE_RAT,
                textos={"respuesta": respuesta, "documento": documento_texto, "mapa": mapa_txt},
                datos={"contexto": ctx, "previos_usuario": previos},
                contexto=ContextoLlamada(),
            )
        except CapaIAError as e:
            if reserva is not None:
                await reserva.devolver()   # no fue culpa del usuario: no gasta su cuota
            info.update(motivo_sin_ia="ia_no_disponible", error_ia=e.tipo_error)
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
            claves_usadas={p.clave for p in todas} | set(await self._todas_las_claves()))
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

    async def _todas_las_claves(self) -> list[str]:
        return list((await self.db.execute(
            select(AsistentePropuesta.clave).where(AsistentePropuesta.empresa_id == self.empresa_id))).scalars().all())

    async def _registrar_neutralizados(self, neutralizados: list[dict]) -> None:
        for n in neutralizados:
            origen = OrigenEvento.ASISTENTE_DOCUMENTO.value if n.get("campo") == "documento" else OrigenEvento.ASISTENTE.value
            await self._evento(n.get("texto") or "", n.get("categoria"), origen, regla=n.get("regla"))

    # ------------------------------------------------------------------ responder (C1)
    async def responder(self, sesion_id: int, texto: str | None, omitir: bool = False) -> dict:
        s = await self._sesion(sesion_id, bloquear=True)
        if s.estado != "activa":
            raise AsistenteError(409, "SESION_CERRADA", "Esta entrevista ya terminó. Abre una nueva.")
        p = banco.pregunta(s.area_actual, s.paso)
        if p is None:
            raise AsistenteError(409, "ENTREVISTA_TERMINADA", "Ya respondiste todas las preguntas. Revisa las propuestas "
                                 "o elige un área para agregar más información.")
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

        if omitir:
            info = {"motivo_sin_ia": None, "propuestas": [], "resumen": None, "preguntas": [], "traza_id": None,
                    "prompt_version": None, "textos_sanitizados": {}, "entidades": 0, "neutralizados": [],
                    "bloqueado": False, "descartes": []}
            contenido_usuario = TEXTO_OMITIDA
        else:
            previos = [m.contenido for m in (await self.db.execute(
                select(AsistenteMensaje).where(AsistenteMensaje.sesion_id == s.id, AsistenteMensaje.rol == "usuario",
                                               AsistenteMensaje.bloqueado.is_(False))
                .order_by(AsistenteMensaje.id.desc()).limit(2))).scalars().all()][::-1]
            info = await self._proponer(respuesta=texto, documento_texto="", area=s.area_actual, pregunta=p.texto,
                                        origen="entrevista", sesion_id=s.id, documento_id=None, tipo_documento=None,
                                        cuota="dia", previos=previos)
            if info["bloqueado"]:
                return await self._bloqueada(s, p, texto, info, ahora)
            await self._registrar_neutralizados(info["neutralizados"])
            # Lo que se guarda es EXACTAMENTE lo que vio el LLM (ya sanitizado); sin IA, se anonimiza aquí
            contenido_usuario = info["textos_sanitizados"].get("respuesta")
            if not contenido_usuario:
                try:
                    contenido_usuario = await self._anon(texto) if self.anonimizador else TEXTO_NO_GUARDADO
                except AnonimizacionError:
                    contenido_usuario = TEXTO_NO_GUARDADO

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
                     "descartes": (info.get("descartes") or [])[:20],
                     "huella_respuesta": huella(texto) if texto else None, "largo": len(texto)})
        await self.db.commit()
        return {**await self.estado(), "nuevas": [p_.id for p_ in info["propuestas"]],
                "aviso": AVISOS.get(info["motivo_sin_ia"] or "")}

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

    # ------------------------------------------------------------------ documentos (C3)
    async def analizar_documento(self, nombre: str | None, contenido: bytes, sesion_id: int | None = None) -> dict:
        from app.application.evidencias.archivos import (
            ArchivoIlegibleError, ArchivoNoAdmitidoError, detectar_tipo, extraer_texto,
        )

        maximo = settings.ASISTENTE_DOCUMENTO_MAX_MB * 1024 * 1024
        if not contenido:
            raise AsistenteError(422, "ARCHIVO_VACIO", "El archivo está vacío.")
        if len(contenido) > maximo:
            raise AsistenteError(413, "ARCHIVO_DEMASIADO_GRANDE",
                                 f"El archivo supera los {settings.ASISTENTE_DOCUMENTO_MAX_MB} MB.")
        try:
            tipo_archivo = detectar_tipo(nombre, contenido)
        except ArchivoNoAdmitidoError as e:
            raise AsistenteError(422, "TIPO_NO_ADMITIDO", str(e) or "Sube un PDF, un Word (.docx) o un texto (.txt).")
        if sesion_id is not None:
            await self._sesion(sesion_id)
        try:
            nombre_seguro = (await self.anonimizador.anonimizar_nombre_archivo(nombre) if self.anonimizador
                             else "documento")
        except AnonimizacionError:
            nombre_seguro = "documento"
        doc = AsistenteDocumento(
            empresa_id=self.empresa_id, sesion_id=sesion_id, usuario_definitivo_id=self.usuario_id,
            nombre_archivo=nombre_seguro[:255], tipo_archivo=tipo_archivo, tipo_documento="otro",
            huella_sha256=hashlib.sha256(contenido).hexdigest(), estado="listo", lineas_omitidas=0,
            entidades_anonimizadas=0, fecha=_ahora())

        info: dict | None = None
        try:
            texto = extraer_texto(contenido)
        except ArchivoIlegibleError:
            texto, doc.estado = "", "ilegible"
        del contenido   # el archivo no se guarda: solo su huella y sus metadatos
        if doc.estado == "listo" and len(texto.strip()) < MIN_CARACTERES_DOCUMENTO:
            doc.estado = "sin_texto"
        if doc.estado == "listo":
            doc.tipo_documento = documento.tipo_documento(texto)
            if await self._es_listado_de_personas(texto):
                doc.estado = "rechazado_pii"
        if doc.estado == "listo":
            pasajes, rag = documento.pasajes_relevantes(texto, settings.ASISTENTE_MAX_CHARS_DOCUMENTO_LLM)
            doc.pasajes_total, doc.pasajes_usados = rag.get("pasajes_total"), rag.get("pasajes_usados")
            self.db.add(doc)
            await self.db.flush()
            info = await self._proponer(respuesta="", documento_texto=pasajes, area="documento", pregunta=None,
                                        origen="documento", sesion_id=sesion_id, documento_id=doc.id,
                                        tipo_documento=doc.tipo_documento, cuota="doc", previos=[])
            await self._registrar_neutralizados(info["neutralizados"])
            doc.lineas_omitidas = sum(1 for n in info["neutralizados"] if n.get("campo") == "documento")
            doc.entidades_anonimizadas = info.get("entidades") or 0
            doc.traza_id = info.get("traza_id")
            if info["motivo_sin_ia"] and info["motivo_sin_ia"] != "sin_propuestas":
                doc.estado, doc.motivo_sin_ia = "sin_ia", info["motivo_sin_ia"]
        else:
            self.db.add(doc)
            await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_DOCUMENTO_ANALIZADO, entidad="asistente_documento", entidad_id=doc.id,
            actor=self.actor, resultado=RESULTADO_RECHAZADO if doc.estado in ESTADO_DOCUMENTO_MENSAJE else RESULTADO_OK,
            detalle={"tipo_archivo": doc.tipo_archivo, "tipo_documento": doc.tipo_documento, "estado": doc.estado,
                     "huella_archivo": doc.huella_sha256[:16], "propuestas": len(info["propuestas"]) if info else 0,
                     "lineas_omitidas": doc.lineas_omitidas, "pasajes_usados": doc.pasajes_usados,
                     "entidades_anonimizadas": doc.entidades_anonimizadas, "motivo_sin_ia": doc.motivo_sin_ia,
                     "traza_id": doc.traza_id})
        await self.db.commit()
        aviso = ESTADO_DOCUMENTO_MENSAJE.get(doc.estado) or (AVISOS.get(info["motivo_sin_ia"] or "") if info else None)
        if info and not info["propuestas"] and doc.estado == "listo":
            aviso = "Leímos el documento, pero no encontramos actividades nuevas que proponer."
        if doc.lineas_omitidas:
            aviso = ((aviso + " ") if aviso else "") + (
                f"Omitimos {doc.lineas_omitidas} línea{'s' if doc.lineas_omitidas != 1 else ''} del documento por "
                "seguridad.")
        return {**await self.estado(), "documento": documento_a_dict(doc),
                "nuevas": [p.id for p in (info["propuestas"] if info else [])], "aviso": aviso}

    async def _es_listado_de_personas(self, texto: str) -> bool:
        """Densidad de entidades personales con el mismo motor NER (fail-closed: si falla, no se envía)."""
        if self.anonimizador is None or not self.anonimizador.habilitado:
            return False
        muestra = texto[:MUESTRA_DENSIDAD]
        try:
            res = await asyncio.to_thread(self.anonimizador.sanitizer.sanitizar, muestra)
        except Exception:  # noqa: BLE001 - el gateway volvería a fallar: mejor no seguir
            return True
        return documento.parece_listado_de_personas(len(res.entidades), len(muestra),
                                                    settings.ASISTENTE_MAX_DENSIDAD_PII)

    # ------------------------------------------------------------------ decisiones (C4)
    async def _resolver(self, ref: str | None, tipo: str) -> int:
        """'id:<n>' -> n; 'nuevo:<clave>' -> id de lo que creó esa propuesta (debe estar aceptada)."""
        p = anclaje.parsear_ref(ref)
        if p is None:
            raise AsistenteError(422, "REFERENCIA_INVALIDA", "Falta elegir a qué sistema o flujo corresponde.")
        if p[0] == "id":
            return int(p[1])
        dep = (await self.db.execute(select(AsistentePropuesta).where(
            AsistentePropuesta.empresa_id == self.empresa_id, AsistentePropuesta.clave == p[1]))).scalar_one_or_none()
        if dep is None or dep.tipo != tipo or dep.estado == "descartada":
            raise AsistenteError(409, "DEPENDENCIA_NO_DISPONIBLE",
                                 "Esta propuesta usa algo que descartaste o que ya no existe. Edítala y elige otro "
                                 "elemento del mapa.")
        if dep.estado not in ("aceptada", "editada") or not dep.entidad_destino_id:
            nombre = propuesta_a_dict(dep)["nombre"]
            raise AsistenteError(409, "DEPENDENCIA_PENDIENTE",
                                 f"Primero acepta «{nombre}»: esta propuesta lo necesita.", dependencia=dep.id)
        return dep.entidad_destino_id

    async def aceptar(self, propuesta_id: int, payload_editado: dict | None = None,
                      version_mapa: int | None = None) -> dict:
        from app.application.use_cases.mapa_datos import MapaDatosCasos, MapaDatosError
        from app.application.use_cases.registro_actividades import RatError, RegistroActividadesCasos

        p = await self._propuesta(propuesta_id)
        if p.estado != "sugerida":
            raise AsistenteError(409, "PROPUESTA_DECIDIDA", "Esta propuesta ya fue revisada.")
        if payload_editado is not None and not isinstance(payload_editado, dict):
            raise AsistenteError(422, "DATOS_INVALIDOS", "Los cambios no son válidos.")
        final, cambiados = anclaje.aplicar_edicion(p.tipo, p.payload_propuesto, payload_editado)
        datos_ia = {"modelo": p.modelo, "prompt_version": p.prompt_version, "traza_id": p.traza_id}
        try:
            if p.tipo in ("elemento", "flujo"):
                casos = MapaDatosCasos(self.db, self.cliente)
                version = version_mapa if version_mapa is not None else (await self._mapa())[0]
                if p.tipo == "elemento":
                    datos = {k: v for k, v in final.items() if k in anclaje.CAMPOS_ELEMENTO}
                    await casos.crear_elemento(datos, version, origen="ia", propuesta_ia_id=p.id)
                    destino = "mapa_elemento"
                else:
                    datos = {k: v for k, v in final.items() if k not in ("origen", "destino")}
                    datos["origen_id"] = await self._resolver(final.get("origen"), "elemento")
                    datos["destino_id"] = await self._resolver(final.get("destino"), "elemento")
                    await casos.crear_flujo(datos, version, origen="ia", propuesta_ia_id=p.id)
                    destino = "mapa_flujo"
                destino_id = casos.ultimo_id
            else:
                contenido = await self._contenido_actividad(final)
                r = await RegistroActividadesCasos(self.db, self.cliente).crear(contenido, origen="ia",
                                                                                propuesta_ia_id=p.id)
                destino, destino_id = "rat_actividad", r["actividad"]["id"]
        except (MapaDatosError, RatError) as e:
            raise AsistenteError(e.status, e.codigo, e.mensaje, **e.extra)

        # El elemento, flujo o actividad ya quedó guardado (y en la bitácora) por su propio caso de uso.
        # Ahora se cierra la propuesta (Human-in-the-Loop): quién decidió, cuándo y si la editó.
        p = await self._propuesta(propuesta_id)
        editada = bool(cambiados)
        p.estado = "editada" if editada else "aceptada"
        p.payload_final = final
        p.campos_editados = cambiados or None
        p.entidad_destino, p.entidad_destino_id = destino, destino_id
        p.decidido_por, p.fecha_decision = self.usuario_id, _ahora()
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_PROPUESTA_EDITADA if editada else Accion.ASISTENTE_PROPUESTA_ACEPTADA,
            entidad="asistente_propuesta", entidad_id=p.id, actor=self.actor,
            detalle={"tipo": p.tipo, "destino": destino, "destino_id": destino_id, "campos_editados": cambiados,
                     **datos_ia})
        await self.db.commit()
        return {**await self.estado(), "aceptada": {"propuesta_id": p.id, "destino": destino,
                                                    "destino_id": destino_id}}

    async def _contenido_actividad(self, final: dict) -> dict:
        """El contenido del RAT con las referencias resueltas a ids del mapa (y todas sus categorías)."""
        _, elementos, flujos = await self._mapa()
        por_el, por_fl = {e.id: e for e in elementos}, {f.id: f for f in flujos}
        contenido = {k: v for k, v in final.items() if k in anclaje.CAMPOS_ACTIVIDAD and k not in ("elementos", "flujos")}
        contenido["elementos"], contenido["flujos"] = [], []
        for ref in final.get("elementos") or []:
            e = por_el.get(await self._resolver(ref, "elemento"))
            if e is not None:
                contenido["elementos"].append({"id": e.id, "categorias_datos": list(e.categorias_datos),
                                               "categorias_titulares": list(e.categorias_titulares)})
        for ref in final.get("flujos") or []:
            f = por_fl.get(await self._resolver(ref, "flujo"))
            if f is not None:
                contenido["flujos"].append({"id": f.id, "categorias_datos": list(f.categorias_datos),
                                            "categorias_titulares": list(f.categorias_titulares)})
        return contenido

    async def descartar(self, propuesta_id: int, motivo: str | None) -> dict:
        p = await self._propuesta(propuesta_id, bloquear=True)
        if p.estado != "sugerida":
            raise AsistenteError(409, "PROPUESTA_DECIDIDA", "Esta propuesta ya fue revisada.")
        motivo = motivo or "otro"
        if motivo not in MOTIVOS_DESCARTE:
            raise AsistenteError(422, "MOTIVO_INVALIDO", "Elige un motivo de la lista.")
        p.estado, p.motivo_descarte = "descartada", motivo
        p.decidido_por, p.fecha_decision = self.usuario_id, _ahora()
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_PROPUESTA_DESCARTADA, entidad="asistente_propuesta", entidad_id=p.id,
            actor=self.actor, detalle={"tipo": p.tipo, "motivo": motivo, "modelo": p.modelo,
                                       "prompt_version": p.prompt_version, "traza_id": p.traza_id})
        await self.db.commit()
        return await self.estado()

    async def contar_pendientes(self) -> int:
        return (await self.db.execute(select(func.count()).select_from(AsistentePropuesta).where(
            AsistentePropuesta.empresa_id == self.empresa_id, AsistentePropuesta.estado == "sugerida"))).scalar() or 0


__all__ = ["AsistenteRat", "AsistenteError", "AVISOS", "DECIDIDAS", "etiqueta_ia", "propuesta_a_dict"]
