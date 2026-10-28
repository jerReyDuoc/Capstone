"""
HU-26 criterio 3: constancia de un módulo formativo completado (PDF, reportlab).

Una página A4 horizontal con la empresa, el módulo (dimensión, nivel, horas y modalidad),
la fecha en que se aprobó la actividad de verificación, la nota y un código único de
verificación. Deja dicho que la constancia acredita formación y NO cambia el puntaje de
madurez (eso solo pasa con evidencia nueva, HU-17).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.application.informes.pdf_informe import GRIS, LINEA, TINTA, VERDE, VERDE_SUAVE, PdfNoDisponibleError, _esc, _fmt

__all__ = ["DatosConstancia", "generar_constancia", "nombre_constancia", "PdfNoDisponibleError"]


@dataclass(frozen=True)
class DatosConstancia:
    razon_social: str
    rut: str
    participante: str
    modulo: str
    dominio: str | None
    nivel: str | None
    horas: int | None
    modalidad: str | None
    objetivo: str | None
    fecha_completado: datetime
    puntaje: float | None
    codigo: str


def nombre_constancia(d: DatosConstancia) -> str:
    return f"constancia_{d.codigo}.pdf"


def _fecha_chile(f: datetime) -> datetime:
    if f.tzinfo is None:
        f = f.replace(tzinfo=timezone.utc)
    return f.astimezone(ZoneInfo("America/Santiago"))


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")


def fecha_larga(f: datetime) -> str:
    f = _fecha_chile(f)
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def generar_constancia(d: DatosConstancia) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise PdfNoDisponibleError("Falta reportlab (pip install -r requirements.txt).") from e

    c = colors.HexColor
    pagina = landscape(A4)
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=11, leading=15, textColor=c(TINTA), alignment=TA_CENTER)
    gris = ParagraphStyle("g", parent=base, fontSize=9, leading=12, textColor=c(GRIS))
    titulo = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=c(VERDE))
    modulo = ParagraphStyle("m", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22)
    empresa = ParagraphStyle("e", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=19)
    dato_l = ParagraphStyle("dl", parent=gris, fontSize=8, leading=10)
    dato_v = ParagraphStyle("dv", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14)

    def p(t, s=base):
        return Paragraph(t, s)

    datos = [
        ("Dimensión", d.dominio or "—"),
        ("Nivel", d.nivel or "—"),
        ("Duración", f"{d.horas} horas" if d.horas else "—"),
        ("Modalidad", d.modalidad or "—"),
        ("Actividad de verificación", f"{_fmt(d.puntaje)} / 100" if d.puntaje is not None else "—"),
    ]
    tabla = Table(
        [[p(_esc(et), dato_l) for et, _ in datos], [p(_esc(v), dato_v) for _, v in datos]],
        colWidths=[(pagina[0] - 60 * mm) / len(datos)] * len(datos),
    )
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c(VERDE_SUAVE)),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, c(LINEA)),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    historia = [
        Spacer(1, 24 * mm),
        p("ComplianceIA · Therion Labs", gris),
        Spacer(1, 6),
        p("Constancia de formación", titulo),
        Spacer(1, 16),
        p("Se deja constancia de que", base),
        Spacer(1, 4),
        p(_esc(d.razon_social), empresa),
        p(f"RUT {_esc(d.rut)} · registrado por {_esc(d.participante)}", gris),
        Spacer(1, 10),
        p("completó el módulo formativo", base),
        Spacer(1, 4),
        p(_esc(d.modulo), modulo),
        Spacer(1, 4),
        p(_esc(d.objetivo) if d.objetivo else "", gris),
        Spacer(1, 10),
        tabla,
        Spacer(1, 12),
        p(f"Completado el {fecha_larga(d.fecha_completado)}", base),
        Spacer(1, 14),
        p(f"Código de verificación <b>{_esc(d.codigo)}</b>", base),
        Spacer(1, 18),
        p("Esta constancia acredita la formación realizada en la plataforma. No modifica el puntaje de "
          "madurez de la evaluación: las brechas se cierran al validar evidencia nueva del control.", gris),
    ]

    def marco(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(c(VERDE))
        canvas.setLineWidth(2.5)
        canvas.rect(12 * mm, 12 * mm, pagina[0] - 24 * mm, pagina[1] - 24 * mm)
        canvas.setLineWidth(0.6)
        canvas.rect(15 * mm, 15 * mm, pagina[0] - 30 * mm, pagina[1] - 30 * mm)
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=pagina, leftMargin=30 * mm, rightMargin=30 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Constancia de formación · {d.modulo}", author="ComplianceIA", subject=d.codigo,
    )
    doc.build(historia, onFirstPage=marco)
    return buffer.getvalue()
