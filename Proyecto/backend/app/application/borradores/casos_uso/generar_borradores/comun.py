"""Constantes, errores y helpers compartidos de los borradores."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.application.borradores import generador_markdown as generador
from app.domain.models.borrador_modelo import BorradorDocumento

logger = logging.getLogger("app.application.borradores.casos_uso.generar_borradores")
ZONA = ZoneInfo("America/Santiago")
MAX_PENDIENTES_LISTA = 20
MIME_MD = "text/markdown"
MIME_PDF = "application/pdf"
# Mensajes para el usuario cuando el borrador se armó sin el Agente IA
AVISOS = {
    "ia_deshabilitada": "El Agente IA no está habilitado: el borrador se armó con la plantilla y tu evaluación.",
    "ia_no_solicitada": None,
    "cuota_ia_agotada": "Tu empresa usó los borradores con IA de hoy: este se armó con la plantilla y tu evaluación. "
                        "Podrás adaptarlos con IA después del reinicio.",
    "ia_no_disponible": "El Agente IA no respondió: el borrador se armó con la plantilla y tu evaluación. "
                        "Puedes generarlo de nuevo más tarde.",
    "salida_ia_descartada": "Descartamos lo que propuso el Agente IA porque no pasó la validación de seguridad: "
                            "el borrador se armó con la plantilla y tu evaluación.",
}
MENSAJE_BLOQUEO = ("Tus instrucciones contienen texto que intenta cambiar las reglas del Agente IA, así que no se "
                   "procesaron. Escríbelas como preferencias de redacción (por ejemplo, \"somos una clínica que usa "
                   "un chatbot de agendamiento\").")
MENSAJE_ETICA = ("No podemos redactar eso: el documento no puede aparentar un cumplimiento que no existe ni ocultar el "
                 "uso de IA, un incidente o un derecho de los titulares (Ley 21.719). Ajusta tus instrucciones.")


class BorradorError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def borrador_a_dict(b: BorradorDocumento, con_contenido: bool = False) -> dict:
    pend = generador.pendientes(b.contenido)
    d = {
        "id": b.id, "tipo": b.tipo, "titulo": b.titulo, "estado": b.estado, "version": b.version,
        "editable": b.editable, "adaptado_ia": bool(b.adaptado_ia), "evaluacion_id": b.evaluacion_id,
        "version_plantillas": b.version_plantillas, "pendientes": len(pend),
        "notas": list(b.notas or []), "advertencias": list(b.advertencias or []),
        "fecha_creacion": _iso(b.fecha_creacion), "fecha_actualizacion": _iso(b.fecha_actualizacion),
        "fecha_consolidacion": _iso(b.fecha_consolidacion), "documento_id": b.documento_id,
        "descargas": {"md": f"/api/borradores/{b.id}/descarga?formato=md",
                      "pdf": f"/api/borradores/{b.id}/descarga?formato=pdf"},
    }
    if con_contenido:
        d["contenido"] = b.contenido
        d["pendientes_detalle"] = pend[:MAX_PENDIENTES_LISTA]
    return d
