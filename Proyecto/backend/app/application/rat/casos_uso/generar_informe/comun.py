"""Constantes, error y utilidades compartidas del informe RAT."""
from __future__ import annotations

from datetime import datetime, timezone

from app.application.informes.formato import ZONA
from app.application.rat import armado_informe_rat as I

FORMATOS = ("pdf", "xlsx")
MAX_HISTORIAL = 50


class InformeRatError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _naive(d: datetime) -> datetime:
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None



def marca_de_revision(r) -> I.MarcaRevision | None:
    """La marca que lleva el informe a partir de una fila de rat_revision revisada (HU-40)."""
    if r is None or r.fecha_revision is None:
        return None
    res = r.resumen or {}
    return I.MarcaRevision(
        id=r.id, numero=r.numero, fecha=r.fecha_revision, revisor=r.revisor_nombre or "", cargo=r.revisor_cargo,
        version_rat=r.version_rat or 0, puntos=int(res.get("revisados") or 0), aceptados=int(res.get("aceptados") or 0),
        observaciones=int((res.get("observaciones") or {}).get("cerradas") or 0))


def _fecha_txt(d: datetime | None) -> str:
    if d is None:
        return "—"
    return d.replace(tzinfo=timezone.utc).astimezone(ZONA).strftime("%d-%m-%Y a las %H:%M")
