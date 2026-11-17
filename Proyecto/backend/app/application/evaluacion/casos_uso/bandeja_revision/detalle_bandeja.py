"""Detalle de una respuesta, su historial de revisiones y el resumen de verdad de referencia."""
from __future__ import annotations

from datetime import date

from app.application.ai.metricas import precision_clasificacion
from app.application.fabricas import fabricas
from app.domain.models.evento_seguridad import ResolucionEvento
from app.domain.models.respuesta import DecisionRevision, EstadoClasificacion
from app.domain.auditoria.acciones import Accion
from app.application.evaluacion.casos_uso.bandeja_revision.modelos_bandeja import _Fila, _evidencias_llm, _iso
from app.application.evaluacion.casos_uso.bandeja_revision.reglas_motivos import calcular_motivos, ultima_del_llm


class DetalleBandejaMixin:
    async def detalle_respuesta(self, respuesta_id: int) -> dict | None:
        fila = await self.repo.fila_respuesta(respuesta_id)
        if fila is None:
            return None
        r, c, d, ev, emp = fila
        eventos = await self.repo.eventos_de_respuesta(r.id)
        evs = _evidencias_llm(r)
        x = _Fila(respuesta=r, control=c, dominio=d, evaluacion=ev, empresa=emp, eventos=len(eventos),
                  ultima=ultima_del_llm(evs))
        x.motivos = calcular_motivos(declarado=r.estado_clasificacion, estado_final=r.estado_clasificacion_final,
                                     fuente=r.fuente_clasificacion, evidencias=evs, con_evento=bool(eventos),
                                     umbral=self.umbral)
        item = self._item_respuesta(x)
        item["justificacion_usuario"] = r.justificacion_usuario
        if c is not None:
            item["control"].update({"obligacion": c.obligacion, "evidencia_esperada": c.evidencia_esperada,
                                    "articulo_referencia": c.articulo_referencia})
        item["evidencias"] = [
            {"id": e.id_evidencia, "nombre_archivo": e.nombre_archivo, "origen": e.origen,
             "estado_validacion": e.estado_validacion, "estado_declarado": e.estado_declarado,
             "clasificacion_llm": e.clasificacion_llm, "confianza": e.confianza,
             "justificacion_llm": e.justificacion_llm, "errores": e.errores_validacion or [],
             "fecha_subida": _iso(e.fecha_subida), "fecha_procesada": _iso(e.fecha_procesada),
             "eliminada": e.eliminada}
            for e in sorted(r.evidencias or [], key=lambda e: (e.fecha_procesada or date.min, e.id_evidencia),
                            reverse=True)
        ]
        item["eventos"] = [self._item_evento(e, c.codigo_control if c else None,
                                             c.pregunta_evaluacion if c else None) for e in eventos]
        item["historial"] = await self.historial(r.id)
        item["opciones"] = EstadoClasificacion.resolutivos()
        return item

    async def historial(self, respuesta_id: int) -> list[dict]:
        """C3: las revisiones de la respuesta, leídas del audit_log (lo inmutable manda)."""
        filas, _ = await fabricas().bitacora(self.s).listar(
            entidad="respuestas", entidad_id=respuesta_id, accion=Accion.RESPUESTA_REVISADA, size=50)
        ids_admin = {f.actor_id for f in filas if f.actor_id}
        correos: dict[int, str] = {}
        if ids_admin:
            correos = await self.repo.correos_admin(ids_admin)
        return [{
            "audit_id": f.id, "fecha": _iso(f.fecha), "actor_rol": f.actor_rol, "actor_id": f.actor_id,
            "revisor": correos.get(f.actor_id) if f.actor_id else None,
            "anterior": (f.detalle or {}).get("estado_final_anterior"),
            "nueva": (f.detalle or {}).get("estado_final_nuevo"),
            "decision": (f.detalle or {}).get("decision"),
            "clasificacion_llm": (f.detalle or {}).get("clasificacion_llm"),
            "con_comentario": bool((f.detalle or {}).get("comentario_huella")),
        } for f in filas]

    # ------------------------------------------------------------ verdad de referencia
    async def resumen(self) -> dict:
        revisadas = await self.repo.respuestas_revisadas()
        pares = []
        confirmadas = corregidas = 0
        for r in revisadas:
            if r.decision_revision == DecisionRevision.CONFIRMADA.value:
                confirmadas += 1
            elif r.decision_revision == DecisionRevision.CORREGIDA.value:
                corregidas += 1
            ultima = ultima_del_llm(_evidencias_llm(r))
            if ultima and ultima.clasificacion_llm:
                pares.append((ultima.clasificacion_llm, r.clasificacion_revisada))
        eventos = await self.repo.conteo_resoluciones_eventos()
        confirmados = eventos.get(ResolucionEvento.ATAQUE_CONFIRMADO.value, 0)
        falsos = eventos.get(ResolucionEvento.FALSO_POSITIVO.value, 0)
        return {
            "revisadas": len(revisadas),
            "confirmadas": confirmadas,
            "corregidas": corregidas,
            "precision_llm": precision_clasificacion(pares),
            "eventos": {
                "ataques_confirmados": confirmados,
                "falsos_positivos": falsos,
                "sin_veredicto": sum(n for k, n in eventos.items() if k is None),
                "precision_deteccion": round(confirmados / (confirmados + falsos), 3)
                if confirmados + falsos else None,
            },
            "umbral_confianza": self.umbral,
        }
