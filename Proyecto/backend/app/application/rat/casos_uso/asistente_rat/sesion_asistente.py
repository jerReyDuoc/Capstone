"""Asistente RAT: cuota diaria, disponibilidad de la IA, estado de la pantalla y ciclo de la entrevista."""
from __future__ import annotations

import logging

from app.application.rat.asistente import banco, inconsistencias
from app.application.rat.casos_uso.asistente_rat.comun import (
    MAX_MENSAJES_VISTA, MAX_PROPUESTAS_VISTA, AsistenteError, _ahora, documento_a_dict, mensaje_a_dict,
    propuesta_a_dict, sesion_a_dict,
)
from app.application.encuesta_publica.casos_uso.limites_encuesta import Reserva, ventana_diaria
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.models.asistente import AsistentePropuesta, AsistenteSesion
from app.domain.ports.limitador_port import LimitadorNoDisponibleError

logger = logging.getLogger(__name__)


class SesionMixin:
    """Depende de los atributos que fija AsistenteRat.__init__ (db, repo, limitador, agente, ...)."""

    # ------------------------------------------------------------------ cuota (C5)
    def _clave(self, tipo: str, fecha: str) -> str:
        return f"asistente:{tipo}:{self.empresa_id}:{fecha}"

    def _clave_rafaga(self) -> str:
        return f"asistente:min:{self.empresa_id}:{self.usuario_id}"

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
            # Corrección 18-11: la ráfaga es de la PERSONA (empresa + usuario), no solo de la empresa. La cuota
            # diaria sigue siendo de la empresa (lógica de negocio, sin cambios).
            pasos.append((self._clave_rafaga(), settings.ASISTENTE_RESPUESTAS_MINUTO_EMPRESA, 60, True))
        limite = settings.ASISTENTE_RESPUESTAS_DIA_EMPRESA if tipo == "dia" else settings.ASISTENTE_DOCUMENTOS_DIA_EMPRESA
        pasos += [(self._clave(tipo, fecha), limite, ventana, False),
                  (f"llm:global:{fecha}", settings.LLM_CUOTA_DIARIA_GLOBAL, ventana, False)]
        for clave, limite, ventana_s, es_rafaga in pasos:
            if limite <= 0:
                continue
            consumo = await self.limitador.consumir(clave, limite, ventana_s)
            reserva.claves.append(clave)
            if es_rafaga:
                # TEMPORAL (verificación del falso 429, 18-11): quitar cuando se confirme el arreglo en staging.
                logger.warning("[RAFAGA-DEBUG] empresa=%s usuario=%s clave=%s usados=%s limite=%s reintentar_en_s=%s "
                            "permitido=%s", self.empresa_id, self.usuario_id, clave, consumo.usados, limite,
                            getattr(consumo, "reintentar_en_s", None), consumo.permitido)
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
        s = await self.repo.sesion(sesion_id, self.empresa_id, bloquear=bloquear)
        if s is None:                      # lo de otra empresa no existe (404, no 403)
            raise AsistenteError(404, "SESION_NO_ENCONTRADA", "No encontramos esa entrevista.")
        return s

    async def _sesion_activa(self) -> AsistenteSesion | None:
        return await self.repo.sesion_activa(self.empresa_id)

    async def _propuesta(self, propuesta_id: int, bloquear: bool = False) -> AsistentePropuesta:
        p = await self.repo.propuesta(propuesta_id, self.empresa_id, bloquear=bloquear)
        if p is None:
            raise AsistenteError(404, "PROPUESTA_NO_ENCONTRADA", "No encontramos esa propuesta.")
        return p

    async def _propuestas(self) -> list[AsistentePropuesta]:
        return await self.repo.propuestas_recientes(self.empresa_id, MAX_PROPUESTAS_VISTA)

    async def _mapa(self):
        from app.application.mapa_datos.casos_uso import MapaDatosCasos

        mapa, elementos, flujos = await MapaDatosCasos(self.db, self.cliente).dominio()
        return (mapa.version if mapa else 0), elementos, flujos

    async def _actividades(self) -> list[dict]:
        filas = await self.repo.actividades(self.empresa_id)
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
            mensajes = (await self.repo.mensajes_recientes(s.id, MAX_MENSAJES_VISTA))[::-1]
        version, elementos, flujos = await self._mapa()
        actividades = await self._actividades()
        propuestas = await self._propuestas()
        documentos = await self.repo.documentos_recientes(self.empresa_id, 20)
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
            self.repo.agregar(s)
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

    async def _tomar_turno(self, sesion_id: int) -> str | None:
        """Una respuesta a la vez por entrevista (doble clic, otra pestaña o reenvío mientras la IA trabaja)."""
        if self.limitador is None:
            return None
        clave = f"asistente:procesando:{sesion_id}"
        try:
            consumo = await self.limitador.consumir(clave, 1, int(settings.ASISTENTE_TIEMPO_MAXIMO_S) + 30)
        except LimitadorNoDisponibleError:
            return None
        if not consumo.permitido:
            await self.limitador.devolver(clave)         # deshace solo este intento; el turno sigue tomado
            raise AsistenteError(409, "RESPUESTA_EN_PROCESO", "Todavía estamos analizando tu respuesta anterior. "
                                 "Espera unos segundos: aparecerá aquí apenas termine.")
        return clave

    async def _soltar_turno(self, clave: str | None) -> None:
        if clave is not None and self.limitador is not None:
            await self.limitador.reiniciar(clave)
