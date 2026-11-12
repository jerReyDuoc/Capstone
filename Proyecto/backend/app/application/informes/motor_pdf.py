"""
Motor común de los informes PDF (HU-21, extendido por HU-36).

Las piezas que comparten los informes que la empresa presenta a terceros, con la misma paleta,
tipografía y pie que el informe de evaluación (app/application/informes/pdf_informe.py):

  Estilos            estilos de párrafo (base, chico, gris, títulos, cabecera de tabla, cifras).
  lienzo()           Canvas que dibuja al final, cuando ya se sabe el total de páginas, la línea
                     superior, el aviso legal en el pie de TODAS las páginas (HU-04), la identificación
                     ("código | versión") y "Página X de Y"; con `marca_agua`, además, la marca
                     diagonal de BORRADOR en cada página (HU-36 criterio 4).
  ficha()            la grilla de identificación de la portada (etiqueta / valor en 3 columnas).
  caja_aviso()       el aviso legal completo de la primera página.
  caja_alerta()      un recuadro de advertencia (p. ej. por qué el informe es un borrador).
  indicadores()      la fila de cifras destacadas de un resumen.
  tabla()            tabla con cabecera verde, filas cebra suaves y cabecera repetida en cada página.

Con reportlab (texto real y seleccionable, fuentes base Helvetica, sin archivos externos). Se
importa dentro de las funciones: si faltara la dependencia, solo fallan los endpoints de PDF (503).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Paleta para papel (la del informe de evaluación)
VERDE = "#0b7a5a"
VERDE_SUAVE = "#e3f4ee"
VERDE_BARRA = "#3f9e80"
TINTA = "#14201b"
GRIS = "#5b6b64"
LINEA = "#d5ddd9"
PISTA = "#e7ecea"
CEBRA = "#f7f9f8"
AVISO_FONDO = "#f6f4ee"
AVISO_BORDE = "#8a6200"
ALERTA_FONDO = "#fbecef"
ALERTA_BORDE = "#b4233f"
MARCA_AGUA = "#b4233f"
COLOR_NIVEL = {"Crítico": "#b4233f", "Alto": "#c4561b", "Medio": "#8a6200", "Bajo": "#2f7d4f"}
FONDO_NIVEL = {"Crítico": "#f6d5db", "Alto": "#f9e1d2", "Medio": "#f6ecd0", "Bajo": "#dcefe3"}
SENSIBLE = "#b4233f"
NNA = "#6b3fa0"
INTERNACIONAL = "#9a6a00"

ZONA = ZoneInfo("America/Santiago")


class PdfNoDisponibleError(Exception):
    pass


def importar():
    """Los módulos de reportlab que usan los informes (o PdfNoDisponibleError)."""
    try:
        import reportlab  # noqa: F401
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise PdfNoDisponibleError("Falta reportlab (pip install -r requirements.txt).") from e


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


@dataclass
class Estilos:
    base: object
    chico: object
    mini: object
    gris: object
    gris_chico: object
    h1: object
    h2: object
    h3: object
    cabecera: object
    etiqueta: object
    valor: object
    cifra: object
    cifra_chica: object
    aviso_titulo: object
    aviso_texto: object


def estilos() -> Estilos:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle

    c = colors.HexColor
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=c(TINTA))
    chico = ParagraphStyle("chico", parent=base, fontSize=8, leading=10.5)
    return Estilos(
        base=base,
        chico=chico,
        mini=ParagraphStyle("mini", parent=base, fontSize=7, leading=9),
        gris=ParagraphStyle("gris", parent=base, textColor=c(GRIS)),
        gris_chico=ParagraphStyle("gris_chico", parent=chico, textColor=c(GRIS)),
        h1=ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24),
        h2=ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=10,
                          spaceAfter=4, textColor=c(VERDE)),
        h3=ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6),
        cabecera=ParagraphStyle("cab", parent=chico, fontName="Helvetica-Bold", textColor=colors.white),
        etiqueta=ParagraphStyle("etq", parent=chico, textColor=c(GRIS)),
        valor=ParagraphStyle("val", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13),
        cifra=ParagraphStyle("cifra", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=21),
        cifra_chica=ParagraphStyle("cifra2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=16),
        aviso_titulo=ParagraphStyle("aviso_t", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12),
        aviso_texto=ParagraphStyle("aviso_p", parent=chico, fontSize=8.2, leading=11, spaceAfter=3),
    )


# ============================================================ piezas
def tabla(filas, anchos, extra=(), cebra: bool = True, repetir: int = 1):
    """Tabla con cabecera verde (fila 0), líneas suaves y filas alternadas."""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    c = colors.HexColor
    t = Table(filas, colWidths=list(anchos), repeatRows=repetir)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), c(VERDE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, c(LINEA)),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if cebra:
        estilo += [("BACKGROUND", (0, i), (-1, i), c(CEBRA)) for i in range(2, len(filas), 2)]
    t.setStyle(TableStyle(estilo + list(extra)))
    return t


def ficha(celdas: list[tuple[str, str]], ancho: float, e: Estilos, columnas: int = 3):
    """Grilla de identificación: [(etiqueta, valor HTML)] en filas de `columnas`."""
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    c = colors.HexColor
    filas, estilo = [], [
        ("BOX", (0, 0), (-1, -1), 0.6, c(LINEA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i in range(0, len(celdas), columnas):
        grupo = list(celdas[i:i + columnas])
        grupo += [("", "")] * (columnas - len(grupo))
        fila = len(filas)
        filas.append([Paragraph(et, e.etiqueta) for et, _ in grupo])
        filas.append([Paragraph(v, e.valor) for _, v in grupo])
        estilo += [("TOPPADDING", (0, fila), (-1, fila), 6), ("BOTTOMPADDING", (0, fila + 1), (-1, fila + 1), 6)]
        if fila:
            estilo.append(("LINEABOVE", (0, fila), (-1, fila), 0.4, c(LINEA)))
    estilo.append(("LINEAFTER", (0, 0), (columnas - 2, -1), 0.4, c(LINEA)))
    t = Table(filas, colWidths=[ancho / columnas] * columnas)
    t.setStyle(TableStyle(estilo))
    return t


def _caja(contenido: list, ancho: float, fondo: str, borde: str):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    c = colors.HexColor
    t = Table([[contenido]], colWidths=[ancho])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c(fondo)),
        ("LINEBEFORE", (0, 0), (0, -1), 3, c(borde)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def caja_aviso(aviso, ancho: float, e: Estilos, nota: str | None = None):
    """El aviso legal completo (AvisoInforme de app/application/informes/ficha.py)."""
    from reportlab.platypus import Paragraph, Spacer

    contenido = [Paragraph(esc(aviso.titulo), e.aviso_titulo), Spacer(1, 3)]
    contenido += [Paragraph(esc(x), e.aviso_texto) for x in aviso.texto]
    contenido.append(Paragraph(f"Versión del aviso: {esc(aviso.version)}." + (f" {esc(nota)}" if nota else ""),
                               e.gris_chico))
    return _caja(contenido, ancho, AVISO_FONDO, AVISO_BORDE)


def caja_alerta(titulo: str, lineas: list[str], ancho: float, e: Estilos):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer

    titulo_e = ParagraphStyle("alerta_t", parent=e.aviso_titulo, textColor=_hex(ALERTA_BORDE), fontSize=10.5,
                              leading=13)
    contenido = [Paragraph(esc(titulo), titulo_e), Spacer(1, 3)]
    contenido += [Paragraph("• " + esc(x), e.aviso_texto) for x in lineas]
    return _caja(contenido, ancho, ALERTA_FONDO, ALERTA_BORDE)


def _hex(color: str):
    from reportlab.lib import colors
    return colors.HexColor(color)


def indicadores(items: list[tuple[str, str, str | None, str | None]], ancho: float, e: Estilos):
    """Fila de cifras: [(etiqueta, cifra, pie, color de la cifra o None)]."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    c = colors.HexColor
    fila_et, fila_ci, fila_pie = [], [], []
    for etiqueta, cifra, pie, color in items:
        estilo = ParagraphStyle(f"ci_{len(fila_ci)}", parent=e.cifra, textColor=c(color or TINTA))
        fila_et.append(Paragraph(esc(etiqueta), e.etiqueta))
        fila_ci.append(Paragraph(esc(cifra), estilo))
        fila_pie.append(Paragraph(esc(pie or ""), e.gris_chico))
    t = Table([fila_et, fila_ci, fila_pie], colWidths=[ancho / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c(VERDE_SUAVE)),
        ("LINEAFTER", (0, 0), (-2, -1), 1.2, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def lienzo(pagina, pie_aviso: str, izquierda: str, marca_agua: str | None = None):
    """
    Clase Canvas para doc.build(canvasmaker=...). Dibuja el encabezado, el pie (aviso legal,
    identificación y "Página X de Y") y, si corresponde, la marca de agua diagonal, al final:
    cuando ya se conoce el total de páginas.
    """
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas

    c = colors.HexColor
    ancho_p, alto_p = pagina

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
                if marca_agua:
                    self._marca()
                self._pie(total)
                super().showPage()
            super().save()

        def _marca(self):
            self.saveState()
            self.setFillColor(c(MARCA_AGUA))
            self.setFillAlpha(0.09)
            self.setStrokeColor(c(MARCA_AGUA))
            self.setStrokeAlpha(0.14)
            self.translate(ancho_p / 2, alto_p / 2)
            self.rotate(35)
            tam = 96 if ancho_p < alto_p else 120
            self.setFont("Helvetica-Bold", tam)
            self.drawCentredString(0, -tam / 3, marca_agua)
            self.setFont("Helvetica-Bold", 14)
            self.setFillAlpha(0.16)
            self.drawCentredString(0, -tam / 3 - 30, "No apto para presentación oficial")
            self.restoreState()

        def _pie(self, total: int):
            self.saveState()
            self.setStrokeColor(c(VERDE))
            self.setLineWidth(2)
            self.line(15 * mm, alto_p - 10 * mm, ancho_p - 15 * mm, alto_p - 10 * mm)
            if marca_agua:
                self.setFont("Helvetica-Bold", 7.5)
                self.setFillColor(c(MARCA_AGUA))
                self.drawRightString(ancho_p - 15 * mm, alto_p - 8.2 * mm, f"{marca_agua} · no apto para presentación oficial")
            self.setStrokeColor(c(LINEA))
            self.setLineWidth(0.5)
            self.line(15 * mm, 14.5 * mm, ancho_p - 15 * mm, 14.5 * mm)
            self.setFont("Helvetica", 7)
            self.setFillColor(c(TINTA))
            self.drawString(15 * mm, 11 * mm, pie_aviso)     # HU-04: el aviso en el pie de cada página
            self.setFillColor(c(GRIS))
            self.drawString(15 * mm, 7.5 * mm, izquierda)
            self.drawRightString(ancho_p - 15 * mm, 7.5 * mm, f"Página {self._pageNumber} de {total}")
            self.restoreState()

    return _Lienzo
