"""Clasificaciones de la bandeja: candidatas, motivos, filtrado, orden y paginación."""
from __future__ import annotations

from datetime import date

from app.application.evaluacion.casos_uso.bandeja_revision.comun import MAX_CANDIDATAS, MOTIVOS, rango_criticidad
from app.application.evaluacion.casos_uso.bandeja_revision.modelos_bandeja import FiltrosBandeja, _Fila, _evidencias_llm, _iso
from app.application.evaluacion.casos_uso.bandeja_revision.reglas_motivos import calcular_motivos, clave_prioridad, es_prioritaria, esta_pendiente, ultima_del_llm


class ClasificacionesBandejaMixin:
    async def _candidatas(self, f: FiltrosBandeja) -> list[_Fila]:
        filas = [_Fila(respuesta=r, control=c, dominio=d, evaluacion=ev, empresa=emp)
                 for r, c, d, ev, emp in await self.repo.candidatas(f.evaluacion_id, f.dominio_id, MAX_CANDIDATAS)]
        if f.criticidad:
            filas = [x for x in filas if rango_criticidad(x.control.criticidad if x.control else None)
                     == rango_criticidad(f.criticidad)]
        ids = [x.respuesta.id for x in filas]
        conteo_eventos: dict[int, int] = {}
        if ids:
            conteo_eventos = await self.repo.conteo_eventos_por_respuesta(ids)
        for x in filas:
            r = x.respuesta
            evs = _evidencias_llm(r)
            x.eventos = conteo_eventos.get(r.id, 0)
            x.ultima = ultima_del_llm(evs)
            x.motivos = calcular_motivos(
                declarado=r.estado_clasificacion, estado_final=r.estado_clasificacion_final,
                fuente=r.fuente_clasificacion, evidencias=evs, con_evento=x.eventos > 0, umbral=self.umbral)
        return filas

    def _item_respuesta(self, x: _Fila) -> dict:
        r, c, ev = x.respuesta, x.control, x.evaluacion
        pendiente = esta_pendiente(r.clasificacion_revisada, r.fuente_clasificacion)
        return {
            "tipo_item": "respuesta",
            "id": r.id,
            "evaluacion": {
                "id": r.evaluacion_id,
                "origen": ev.origen if ev else None,
                "estado_progreso": ev.estado_progreso if ev else None,
                "cerrada": bool(ev and ev.esta_cerrada),
                "es_prueba": bool(ev and ev.es_prueba),
                "empresa": x.empresa,
            },
            "control": {
                "id": c.id_control if c else r.matriz_controles_id_control,
                "codigo": c.codigo_control if c else None,
                "pregunta": c.pregunta_evaluacion if c else None,
                "criticidad": c.criticidad if c else None,
                "dominio_id": c.dominio_id if c else None,
                "dominio": x.dominio,
            },
            "declarado": r.estado_clasificacion,
            "estado_final": r.estado_clasificacion_final,
            "fuente": r.fuente_clasificacion,
            "llm": ({"clasificacion": x.ultima.clasificacion_llm, "confianza": x.ultima.confianza,
                     "fecha": _iso(x.ultima.fecha), "evidencia_id": x.ultima.id,
                     "bajo_umbral": x.ultima.confianza is not None and x.ultima.confianza < self.umbral}
                    if x.ultima else None),
            "motivos": x.motivos,
            "eventos_seguridad": x.eventos,
            "pendiente": pendiente,
            "revision": ({"clasificacion": r.clasificacion_revisada, "decision": r.decision_revision,
                          "fecha": _iso(r.fecha_revision), "comentario": r.comentario_revision,
                          "vigente": not pendiente}
                         if r.clasificacion_revisada else None),
            "fecha_referencia": _iso(r.fecha_validacion or (x.ultima.fecha if x.ultima else None)),
        }

    @staticmethod
    def _filtrar_estado(filas: list[_Fila], estado: str) -> list[_Fila]:
        if estado == "pendiente":
            return [x for x in filas if esta_pendiente(x.respuesta.clasificacion_revisada, x.respuesta.fuente_clasificacion)]
        if estado == "revisada":
            return [x for x in filas if not esta_pendiente(x.respuesta.clasificacion_revisada, x.respuesta.fuente_clasificacion)]
        return filas

    async def clasificaciones(self, f: FiltrosBandeja) -> tuple[list[dict], int, dict]:
        filas = self._filtrar_estado(await self._candidatas(f), f.estado)
        # Las revisadas se muestran siempre (ya pasaron por la bandeja); entre las pendientes,
        # solo las que tienen un motivo prioritario, salvo que se pida otro motivo.
        conteo = {m: sum(1 for x in filas if m in x.motivos) for m in MOTIVOS}
        if f.motivo:
            filas = [x for x in filas if f.motivo in x.motivos]
        elif f.estado == "pendiente":
            filas = [x for x in filas if es_prioritaria(x.motivos)]
        else:
            filas = [x for x in filas if x.motivos or x.respuesta.clasificacion_revisada]
        if f.orden == "reciente":
            filas.sort(key=lambda x: (x.respuesta.fecha_validacion or date.min, x.respuesta.id), reverse=True)
        else:
            filas.sort(key=lambda x: clave_prioridad(
                x.motivos, x.control.criticidad if x.control else None,
                x.respuesta.fecha_validacion))
        total = len(filas)
        pagina = filas[(f.page - 1) * f.size: f.page * f.size]
        return [self._item_respuesta(x) for x in pagina], total, conteo
