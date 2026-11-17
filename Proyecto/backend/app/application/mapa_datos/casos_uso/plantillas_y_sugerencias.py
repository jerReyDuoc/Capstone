"""Mapa de datos: plantillas por rubro y sugerencias desde la evaluación (C4)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.application.mapa_datos import plantillas as mod_plantillas
from app.application.mapa_datos import sugerencias as mod_sugerencias
from app.application.mapa_datos.casos_uso.comun import MapaDatosError, _ahora, elemento_de_fila
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.models.mapa_datos import MapaDatos, MapaElemento, MapaFlujo


class PlantillasYSugerenciasMixin:
    """Depende de los atributos que fija MapaDatosCasos.__init__ (db, actor, empresa_id, bitacora, ...)."""

    # ================================================================ plantillas (C4)
    async def plantillas(self) -> dict:
        return {"plantillas": mod_plantillas.catalogo_plantillas(await self.rubro()),
                "version": mod_plantillas.VERSION_PLANTILLAS}

    async def aplicar_plantilla(self, codigo: str, version: int) -> dict:
        plantilla = mod_plantillas.PLANTILLAS.get((codigo or "").strip())
        if plantilla is None:
            raise MapaDatosError(422, "PLANTILLA_INVALIDA", "Elige una de las plantillas disponibles.")
        mapa, el, fl, antes = await self._iniciar(version)
        por_clave = {r.clave: r.id for r in el if r.clave}
        por_nombre = {(r.tipo, r.nombre.casefold()): r.id for r in el}
        nuevos: list[MapaElemento] = []
        for ep in plantilla.elementos:
            existente = por_clave.get(ep.clave) or por_nombre.get((ep.tipo, ep.nombre.casefold()))
            if existente:
                por_clave[ep.clave] = existente
                continue
            nuevos.append(self._nuevo_elemento(mapa.id, {
                "tipo": ep.tipo, "subtipo": ep.subtipo, "nombre": ep.nombre, "descripcion": ep.descripcion,
                "pais": ep.pais, "responsable": ep.responsable, "proveedor": ep.proveedor,
                "categorias_datos": list(ep.datos), "categorias_titulares": list(ep.titulares),
                "nna_declarado": ep.nna, "rol_tercero": ep.rol}, origen="plantilla", clave=ep.clave,
                pendiente_revision=True))
        if len(el) + len(nuevos) > settings.MAPA_MAX_ELEMENTOS:
            raise MapaDatosError(422, "LIMITE_ELEMENTOS", f"Con esta plantilla el mapa superaría los "
                                 f"{settings.MAPA_MAX_ELEMENTOS} elementos permitidos.")
        self.db.add_all(nuevos)
        await self.db.flush()
        por_clave.update({r.clave: r.id for r in nuevos})
        claves_flujo = {r.clave for r in fl if r.clave}
        pares = {(r.origen_id, r.destino_id, (r.finalidad or "").casefold()) for r in fl}
        ahora = _ahora()
        flujos_nuevos = []
        for fp in plantilla.flujos:
            o, d = por_clave.get(fp.origen), por_clave.get(fp.destino)
            clave = f"{fp.origen}>{fp.destino}"
            if not o or not d or clave in claves_flujo or (o, d, fp.finalidad.casefold()) in pares:
                continue
            flujos_nuevos.append(MapaFlujo(
                mapa_id=mapa.id, origen_id=o, destino_id=d, finalidad=fp.finalidad, categorias_datos=list(fp.datos),
                categorias_titulares=list(fp.titulares), nna_declarado=fp.nna, frecuencia=fp.frecuencia,
                medio=fp.medio, cifrado=None, garantia=None, origen="plantilla", clave=clave,
                pendiente_revision=True, fecha_creacion=ahora, fecha_actualizacion=ahora))
        if len(fl) + len(flujos_nuevos) > settings.MAPA_MAX_FLUJOS:
            raise MapaDatosError(422, "LIMITE_FLUJOS", f"Con esta plantilla el mapa superaría los "
                                 f"{settings.MAPA_MAX_FLUJOS} flujos permitidos.")
        if not nuevos and not flujos_nuevos:
            await self.db.rollback()
            raise MapaDatosError(409, "PLANTILLA_SIN_CAMBIOS",
                                 "Tu mapa ya tiene todo lo que trae esta plantilla.")
        self.db.add_all(flujos_nuevos)
        if not mapa.plantilla_inicial:
            mapa.plantilla_inicial = plantilla.codigo
        resumen = (f"Se aplicó la plantilla «{plantilla.nombre}»: {len(nuevos)} elemento"
                   f"{'s' if len(nuevos) != 1 else ''} y {len(flujos_nuevos)} flujo"
                   f"{'s' if len(flujos_nuevos) != 1 else ''} por confirmar.")
        return await self._guardar(mapa, "plantilla_aplicada", Accion.MAPA_PLANTILLA_APLICADA, antes,
                                   {"plantilla": plantilla.codigo, "elementos_agregados": len(nuevos),
                                    "flujos_agregados": len(flujos_nuevos)}, resumen)

    # ================================================================ sugerencias desde la evaluación (C4)
    async def _respuestas_evaluacion(self) -> tuple[int | None, dict[str, bool]]:
        from app.application.use_cases.historial_empresa import evaluacion_mas_reciente
        from app.domain.models.pregunta_filtro import PreguntaFiltro
        from app.domain.models.respuesta_filtro import RespuestaFiltro

        ev = (await evaluacion_mas_reciente(self.db, self.empresa_id)
              or await evaluacion_mas_reciente(self.db, self.empresa_id, solo_completadas=False))
        if ev is None:
            return None, {}
        filas = (await self.db.execute(
            select(PreguntaFiltro.codigo, RespuestaFiltro.respuesta)
            .join(RespuestaFiltro, RespuestaFiltro.pregunta_id == PreguntaFiltro.id_pregunta)
            .where(RespuestaFiltro.evaluacion_id == ev))).all()
        return ev, {codigo: bool(resp) for codigo, resp in filas}

    async def sugerencias(self) -> dict:
        mapa, els, _fls = await self.dominio()
        ev, respuestas = await self._respuestas_evaluacion()
        descartadas = set((mapa.sugerencias_descartadas or []) if mapa else [])
        lista = mod_sugerencias.calcular(respuestas, els, descartadas)
        nombres = {e.id: e.nombre for e in els}
        return {
            "evaluacion_id": ev, "sin_evaluacion": ev is None,
            "sugerencias": [s.como_dict(nombres) for s in lista],
            "descartadas": len(descartadas),
        }

    async def aceptar_sugerencia(self, clave: str, version: int, origen_id: int | None) -> dict:
        _ev, respuestas = await self._respuestas_evaluacion()
        mapa, el, fl, antes = await self._iniciar(version)
        els = [elemento_de_fila(r) for r in el]
        s = mod_sugerencias.sugerencia(respuestas, els, clave, set(mapa.sugerencias_descartadas or []))
        if s is None:
            raise MapaDatosError(404, "SUGERENCIA_NO_DISPONIBLE",
                                 "Esta sugerencia ya no está disponible: puede que ya la hayas aplicado.")
        ids = {r.id for r in el}
        mapa_claves = {r.clave: r.id for r in el if r.clave}
        if origen_id is not None:
            if not s.conector or origen_id not in ids:
                raise MapaDatosError(422, "DATOS_INVALIDOS", "Elige un elemento de tu mapa como origen.",
                                     campo="origen_id")
            mapa_claves[s.conector] = origen_id
        elif s.usa_existente:
            mapa_claves[s.conector] = s.usa_existente
        nuevos = []
        for ep in s.elementos:
            if ep.clave in mapa_claves:
                continue
            nuevos.append(self._nuevo_elemento(mapa.id, {
                "tipo": ep.tipo, "subtipo": ep.subtipo, "nombre": ep.nombre, "descripcion": ep.descripcion,
                "pais": ep.pais, "responsable": ep.responsable, "categorias_datos": list(ep.datos),
                "categorias_titulares": list(ep.titulares), "nna_declarado": ep.nna, "rol_tercero": ep.rol},
                origen="evaluacion", clave=ep.clave, pendiente_revision=True))
        nombres = {(r.tipo, r.nombre.casefold()) for r in el}
        for n in nuevos:                   # mismo nombre que algo existente: se distingue
            if (n.tipo, n.nombre.casefold()) in nombres:
                n.nombre = f"{n.nombre} (sugerido)"[:120]
        if len(el) + len(nuevos) > settings.MAPA_MAX_ELEMENTOS:
            raise MapaDatosError(422, "LIMITE_ELEMENTOS", f"El mapa admite hasta {settings.MAPA_MAX_ELEMENTOS} elementos.")
        self.db.add_all(nuevos)
        await self.db.flush()
        mapa_claves.update({n.clave: n.id for n in nuevos})
        ahora = _ahora()
        creados = 0
        for i, f in enumerate(s.flujos):
            extremos = []
            for ref in (f.origen, f.destino):
                tipo, _, valor = ref.partition(":")
                extremos.append(int(valor) if tipo == "id" else mapa_claves.get(valor))
            o, d = extremos
            if not o or not d or o == d or o not in ids | {n.id for n in nuevos} or d not in ids | {n.id for n in nuevos}:
                continue
            self.db.add(MapaFlujo(
                mapa_id=mapa.id, origen_id=o, destino_id=d, finalidad=f.finalidad, categorias_datos=list(f.datos),
                categorias_titulares=list(f.titulares), nna_declarado=f.nna, frecuencia=f.frecuencia, medio=f.medio,
                cifrado=None, garantia=None, origen="evaluacion", clave=f"{s.clave}:{i}", pendiente_revision=True,
                fecha_creacion=ahora, fecha_actualizacion=ahora))
            creados += 1
        if len(fl) + creados > settings.MAPA_MAX_FLUJOS:
            raise MapaDatosError(422, "LIMITE_FLUJOS", f"El mapa admite hasta {settings.MAPA_MAX_FLUJOS} flujos.")
        return await self._guardar(mapa, "sugerencia_aceptada", Accion.MAPA_SUGERENCIA_ACEPTADA, antes,
                                   {"sugerencia": s.clave, "elementos_agregados": len(nuevos), "flujos_agregados": creados},
                                   f"Se agregó la sugerencia de la evaluación «{s.titulo}» (por confirmar).")

    async def descartar_sugerencia(self, clave: str, restablecer: bool = False) -> dict:
        """Descartar no cambia el contenido del mapa (no crea versión), pero queda en el audit_log."""
        mapa = await self._mapa(bloquear=True)
        if mapa is None:
            ahora = _ahora()
            mapa = MapaDatos(empresa_id=self.empresa_id, version=0, sugerencias_descartadas=[],
                             usuario_definitivo_id=self.usuario_id, fecha_creacion=ahora, fecha_actualizacion=ahora)
            self.db.add(mapa)
            try:
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()
                raise MapaDatosError(409, "MAPA_DESACTUALIZADO", "Actualiza la página y vuelve a intentarlo.")
        actuales = list(mapa.sugerencias_descartadas or [])
        if restablecer:
            nuevas: list[str] = []
        else:
            validas = {"llm_externo", "base_vectorial", "ia_nube", "datos_sensibles", "agente_ia",
                       "decisiones_automatizadas", "entrenamiento"}
            if clave not in validas:
                raise MapaDatosError(404, "SUGERENCIA_NO_DISPONIBLE", "Esta sugerencia no existe.")
            nuevas = sorted(set(actuales) | {clave})
        if nuevas != actuales:
            mapa.sugerencias_descartadas = nuevas
            self.bitacora.registrar(
                accion=Accion.MAPA_SUGERENCIA_DESCARTADA, entidad="mapa_datos", entidad_id=mapa.id, actor=self.actor,
                detalle={"sugerencia": None if restablecer else clave, "restablecidas": restablecer,
                         "descartadas": len(nuevas)})
            await self.db.commit()
        return await self.sugerencias()
