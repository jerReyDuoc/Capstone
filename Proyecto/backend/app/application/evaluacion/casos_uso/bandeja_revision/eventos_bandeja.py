"""Eventos de seguridad de la bandeja y armado de la respuesta completa de la bandeja."""
from __future__ import annotations

from app.domain.models.evento_seguridad import EventoSeguridad
from app.application.evaluacion.casos_uso.bandeja_revision.comun import MOTIVOS
from app.application.evaluacion.casos_uso.bandeja_revision.modelos_bandeja import FiltrosBandeja, _iso
from app.application.evaluacion.casos_uso.bandeja_revision.reglas_motivos import es_prioritaria


class EventosBandejaMixin:
    @staticmethod
    def _item_evento(ev: EventoSeguridad, codigo: str | None, pregunta: str | None) -> dict:
        return {
            "tipo_item": "evento",
            "id": ev.id_evento,
            "fecha": _iso(ev.fecha),
            "tipo": ev.tipo,
            "regla": ev.regla,  # HU-33: qué regla bloqueó (para decidir si fue un falso positivo)
            "origen": ev.origen,
            "evaluacion_id": ev.evaluacion_id,
            "respuesta_id": ev.respuesta_id,
            "evidencia_id": ev.evidencia_id,
            "control": {"id": ev.matriz_control_id, "codigo": codigo, "pregunta": pregunta}
            if ev.matriz_control_id else None,
            "extracto": ev.extracto,
            "pendiente": not ev.revisado,
            "revision": ({"resolucion": ev.resolucion, "comentario": ev.comentario_revision,
                          "fecha": _iso(ev.fecha_revision)} if ev.revisado else None),
        }

    async def eventos(self, f: FiltrosBandeja) -> tuple[list[dict], int]:
        total = await self.repo.contar_eventos(f.estado, f.evaluacion_id, f.origen)
        filas = await self.repo.listar_eventos(f.estado, f.evaluacion_id, f.origen,
                                               (f.page - 1) * f.size, f.size)
        return [self._item_evento(ev, cod, preg) for ev, cod, preg in filas], total

    async def eventos_pendientes(self, f: FiltrosBandeja) -> int:
        return await self.repo.contar_eventos("pendiente", f.evaluacion_id, None)

    async def bandeja(self, f: FiltrosBandeja) -> dict:
        cuenta_f = FiltrosBandeja(estado="pendiente", evaluacion_id=f.evaluacion_id,
                                  dominio_id=f.dominio_id, criticidad=f.criticidad)
        pendientes = self._filtrar_estado(await self._candidatas(cuenta_f), "pendiente")
        conteo_pend = {m: sum(1 for x in pendientes if m in x.motivos) for m in MOTIVOS}
        clasif_pend = sum(1 for x in pendientes if es_prioritaria(x.motivos))
        eventos_pend = await self.eventos_pendientes(f)
        if f.vista == "eventos":
            items, total = await self.eventos(f)
        else:
            items, total, _ = await self.clasificaciones(f)
        return {
            "vista": f.vista, "estado": f.estado, "motivo": f.motivo,
            "items": items, "total": total, "page": f.page, "size": f.size,
            "pages": (total + f.size - 1) // f.size if f.size else 0,
            "pendientes": {"clasificaciones": clasif_pend, "eventos": eventos_pend,
                           "por_motivo": conteo_pend},
            "umbral_confianza": self.umbral,
        }
