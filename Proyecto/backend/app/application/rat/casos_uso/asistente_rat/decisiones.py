"""Asistente RAT: decisiones del usuario sobre las propuestas (Human-in-the-Loop): aceptar, descartar, contar."""
from __future__ import annotations

from app.application.rat.asistente import anclaje
from app.application.rat.casos_uso.asistente_rat.comun import AsistenteError, _ahora, propuesta_a_dict
from app.domain.auditoria.acciones import Accion
from app.domain.models.asistente import MOTIVOS_DESCARTE


class DecisionesMixin:
    """Depende de los atributos que fija AsistenteRat.__init__ (db, repo, limitador, agente, ...)."""

    # ------------------------------------------------------------------ decisiones (C4)
    async def _resolver(self, ref: str | None, tipo: str) -> int:
        """'id:<n>' -> n; 'nuevo:<clave>' -> id de lo que creó esa propuesta (debe estar aceptada)."""
        p = anclaje.parsear_ref(ref)
        if p is None:
            raise AsistenteError(422, "REFERENCIA_INVALIDA", "Falta elegir a qué sistema o flujo corresponde.")
        if p[0] == "id":
            return int(p[1])
        dep = await self.repo.propuesta_por_clave(self.empresa_id, p[1])
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
        from app.application.mapa_datos.casos_uso import MapaDatosCasos, MapaDatosError
        from app.application.rat.casos_uso.registro_actividades_casos import RatError, RegistroActividadesCasos

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
        return await self.repo.contar_pendientes(self.empresa_id)
