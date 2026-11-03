"""
HU-16 · PDF de un borrador a partir de su Markdown (criterio 1: plantillas en Markdown/PDF).

Se usa en la descarga previa a la consolidación (criterio 3) y al consolidar, cuando el PDF
se guarda en "Mis documentos" (HU-29). El Markdown lo escribe el sistema y luego lo edita
el usuario, así que se trata como texto NO confiable: todo se escapa antes de pasarlo a
reportlab (que interpreta un mini-HTML en Paragraph) y solo se reconoce un subconjunto
cerrado de Markdown:

  # / ## / ###   títulos              - / *   viñetas         1.   listas numeradas
  > texto        cita / recuadro      | a | b |  tablas         ---  separador
  **negrita**  *cursiva*  `código`     (sin enlaces, imágenes ni HTML: se imprimen como texto)

Con reportlab (Helvetica base, sin archivos externos), igual que el informe de HU-21.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass


class PdfNoDisponibleError(Exception):
    """Falta reportlab: solo fallan las descargas en PDF (503), no la API."""


VERDE = "#0b7a5a"
TINTA = "#14201b"
GRIS = "#5b6b64"
LINEA = "#d5ddd9"
AVISO_FONDO = "#f6f4ee"
AVISO_BORDE = "#8a6200"
PENDIENTE = "#8a6200"
MARCA = "#eef2f0"

_TABLA_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_NUMERADA = re.compile(r"^\s*(\d{1,3})[.)]\s+(.*)$")
_VINETA = re.compile(r"^\s*[-*•]\s+(.*)$")
_TITULO = re.compile(r"^(#{1,3})\s+(.*)$")
_PENDIENTE = re.compile(r"\[COMPLETAR:[^\]\n]{0,200}\]")


@dataclass(frozen=True)
class Bloque:
    tipo: str                 # titulo1 | titulo2 | titulo3 | parrafo | vineta | numerada | cita | tabla | separador
    texto: str = ""
    filas: tuple[tuple[str, ...], ...] = ()
    numero: str = ""


def _esc(texto: str) -> str:
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def en_linea(texto: str) -> str:
    """Markdown en línea -> mini-HTML de reportlab, con TODO el texto escapado primero."""
    t = _esc(texto)
    t = re.sub(r"`([^`\n]{1,200})`", r'<font face="Courier">\1</font>', t)
    t = re.sub(r"\*\*([^*\n]+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?![*\w])", r"<i>\1</i>", t)
    t = re.sub(r"\[COMPLETAR:[^\]\n]{0,200}\]", lambda m: f'<font color="{PENDIENTE}"><b>{m.group(0)}</b></font>', t)
    return t


def _celdas(linea: str) -> tuple[str, ...]:
    s = linea.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return tuple(c.strip() for c in s.split("|"))


def parsear(markdown: str) -> list[Bloque]:
    """Markdown -> bloques. Puro: se prueba sin reportlab."""
    lineas = (markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    bloques: list[Bloque] = []
    parrafo: list[str] = []
    i = 0

    def cerrar_parrafo():
        if parrafo:
            bloques.append(Bloque("parrafo", " ".join(x.strip() for x in parrafo)))
            parrafo.clear()

    while i < len(lineas):
        linea = lineas[i]
        s = linea.strip()
        if not s:
            cerrar_parrafo()
            i += 1
            continue
        if m := _TITULO.match(s):
            cerrar_parrafo()
            bloques.append(Bloque(f"titulo{len(m.group(1))}", m.group(2).strip()))
            i += 1
            continue
        if s in ("---", "***", "___"):
            cerrar_parrafo()
            bloques.append(Bloque("separador"))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lineas) and _TABLA_SEP.match(lineas[i + 1]):
            cerrar_parrafo()
            filas = [_celdas(s)]
            i += 2
            while i < len(lineas) and lineas[i].strip().startswith("|"):
                filas.append(_celdas(lineas[i]))
                i += 1
            ancho = max(len(f) for f in filas)
            bloques.append(Bloque("tabla", filas=tuple(tuple(f) + ("",) * (ancho - len(f)) for f in filas)))
            continue
        if s.startswith(">"):
            cerrar_parrafo()
            cita = []
            while i < len(lineas) and lineas[i].strip().startswith(">"):
                cita.append(lineas[i].strip()[1:].strip())
                i += 1
            bloques.append(Bloque("cita", " ".join(x for x in cita if x)))
            continue
        if m := _VINETA.match(linea):
            cerrar_parrafo()
            bloques.append(Bloque("vineta", m.group(1).strip()))
            i += 1
            continue
        if m := _NUMERADA.match(linea):
            cerrar_parrafo()
            bloques.append(Bloque("numerada", m.group(2).strip(), numero=m.group(1)))
            i += 1
            continue
        parrafo.append(s)
        i += 1
    cerrar_parrafo()
    return bloques


def generar_pdf_borrador(markdown: str, *, titulo: str, pie: str, marca_agua: str | None = None) -> bytes:
    """
    `pie`: texto del pie de cada página (p. ej. "ACME SpA · Borrador en revisión").
    `marca_agua`: texto diagonal tenue en cada página (p. ej. "BORRADOR"); None en la versión consolidada.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.platypus.flowables import HRFlowable
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise PdfNoDisponibleError("Falta reportlab (pip install -r requirements.txt).") from e

    c = colors.HexColor
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13, textColor=c(TINTA), spaceAfter=5)
    chico = ParagraphStyle("chico", parent=base, fontSize=8, leading=10.5, spaceAfter=0)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                        spaceBefore=10, spaceAfter=4, textColor=c(VERDE))
    h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6)
    cita = ParagraphStyle("cita", parent=base, fontSize=9, leading=12.5, backColor=c(AVISO_FONDO),
                          borderColor=c(AVISO_BORDE), borderWidth=0.6, borderPadding=6, spaceBefore=4, spaceAfter=10)
    cabecera = ParagraphStyle("cab", parent=chico, fontName="Helvetica-Bold", textColor=colors.white)
    estilos = {"titulo1": h1, "titulo2": h2, "titulo3": h3}

    ancho = A4[0] - 36 * mm
    historia: list = []
    lista: list = []
    numerada = False

    def cerrar_lista():
        nonlocal lista
        if lista:
            historia.append(ListFlowable(
                [ListItem(Paragraph(t, base), leftIndent=12, value=int(n) if n else None) for t, n in lista],
                bulletType="1" if numerada else "bullet", start=None, leftIndent=14,
                bulletFontSize=8 if not numerada else 9, bulletFontName="Helvetica",
            ))
            lista = []

    for b in parsear(markdown):
        es_item = b.tipo in ("vineta", "numerada")
        if not es_item or (lista and numerada != (b.tipo == "numerada")):
            cerrar_lista()
        if es_item:
            numerada = b.tipo == "numerada"
            lista.append((en_linea(b.texto), b.numero))
        elif b.tipo in estilos:
            historia.append(Paragraph(en_linea(b.texto), estilos[b.tipo]))
        elif b.tipo == "parrafo":
            historia.append(Paragraph(en_linea(b.texto), base))
        elif b.tipo == "cita":
            historia.append(Paragraph(en_linea(b.texto), cita))
        elif b.tipo == "separador":
            historia += [Spacer(1, 4), HRFlowable(width="100%", thickness=0.5, color=c(LINEA)), Spacer(1, 4)]
        elif b.tipo == "tabla" and b.filas:
            columnas = len(b.filas[0])
            datos = [[Paragraph(en_linea(x), cabecera if r == 0 else chico) for x in fila]
                     for r, fila in enumerate(b.filas)]
            t = Table(datos, colWidths=[ancho / columnas] * columnas, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), c(VERDE)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, c(LINEA)),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            historia += [t, Spacer(1, 8)]
    cerrar_lista()
    if not historia:
        historia.append(Paragraph("(Documento vacío)", base))

    pie_texto = pie[:150]

    class _Lienzo(Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._paginas: list[dict] = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._decorar(total)
                super().showPage()
            super().save()

        def _decorar(self, total: int):
            self.saveState()
            self.setStrokeColor(c(VERDE))
            self.setLineWidth(2)
            self.line(18 * mm, A4[1] - 11 * mm, A4[0] - 18 * mm, A4[1] - 11 * mm)
            self.setStrokeColor(c(LINEA))
            self.setLineWidth(0.5)
            self.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
            self.setFont("Helvetica", 7)
            self.setFillColor(c(GRIS))
            self.drawString(18 * mm, 9 * mm, pie_texto)
            self.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Página {self._pageNumber} de {total}")
            self.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
        title=titulo[:150], author="ComplianceAI (Therion Labs)", subject="Borrador de documento de cumplimiento",
    )
    def _marca(lienzo, _doc):
        """La marca de agua se dibuja al EMPEZAR cada página: queda debajo del texto."""
        if not marca_agua:
            return
        lienzo.saveState()
        lienzo.setFont("Helvetica-Bold", 64)
        lienzo.setFillColor(c(MARCA))
        lienzo.translate(A4[0] / 2, A4[1] / 2)
        lienzo.rotate(45)
        lienzo.drawCentredString(0, 0, marca_agua[:20])
        lienzo.restoreState()

    doc.build(historia, canvasmaker=_Lienzo, onFirstPage=_marca, onLaterPages=_marca)
    return buffer.getvalue()
