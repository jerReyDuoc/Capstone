"""Formato común de fechas y texto de los informes (puro, sin reportlab ni openpyxl). Antes en motor_pdf.py (A-14)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Santiago")


def esc(texto) -> str:
    """Escapa para los párrafos de reportlab (mini-HTML)."""
    return ("" if texto is None else str(texto)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fecha_local(v: datetime | None, con_hora: bool = True) -> str:
    if v is None:
        return "—"
    if v.tzinfo is None:          # en la BD las fechas van en UTC sin zona
        v = v.replace(tzinfo=timezone.utc)
    v = v.astimezone(ZONA)
    return f"{v:%d-%m-%Y %H:%M}" if con_hora else f"{v:%d-%m-%Y}"
