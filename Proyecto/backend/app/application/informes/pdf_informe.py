"""
PDF del informe de la evaluación: resultado, comparativa, brechas priorizadas (HU-11)
y plan formativo (HU-12). Lo usan la descarga directa (GET …/informe.pdf) y el envío
por correo (POST …/informe/enviar), así el adjunto es idéntico a lo descargado.

HU-21 (presentar al directorio o a un auditor):
  - Portada con la ficha de identificación: código de evaluación con dígito verificador,
    fecha de la evaluación, fecha de emisión y versión de la matriz de controles.
  - Aviso legal (HU-04) completo en la primera página y resumido en el pie de TODAS.
  - Los 5 puntajes de HU-03 (Global y las 4 dimensiones), siempre, con barra 0–100 y meta.
  - Pie con "Página X de Y" y el código, para que una hoja suelta se identifique.
  - Cierre con la huella de los datos, que el auditor compara con GET …/informe/ficha.

Con reportlab (texto real y seleccionable, fuentes base Helvetica, sin archivos
externos). Se importa aquí y no al iniciar la app: si faltara la dependencia, solo
fallan estos endpoints (503), no toda la API.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.application.informes.ficha import FichaInforme, huella_legible
from app.application.informes.analisis import (
    ETIQUETA_ESTADO,
    ETIQUETA_MADUREZ,
    GUIA_SEVERIDAD,
    SEVERIDADES,
    Brecha,
    ComparativaDominio,
    FiltrosBrechas,
    PlanFormativo,
    contar_por_severidad,
    nivel_madurez,
)

# Paleta para papel: la del panel (TherionLabs) oscurecida para que contraste en blanco.
VERDE = "#0b7a5a"
VERDE_SUAVE = "#e3f4ee"
TINTA = "#14201b"
GRIS = "#5b6b64"
LINEA = "#d5ddd9"
VERDE_BARRA = "#3f9e80"
PISTA = "#e7ecea"
AVISO_FONDO = "#f6f4ee"
AVISO_BORDE = "#8a6200"
COLOR_SEVERIDAD = {
    "Crítica": "#b4233f",
    "Alta": "#c4561b",
    "Media": "#8a6200",
    "Baja": "#2f7d4f",
    "Sin clasificar": "#5b6b64",
}


class PdfNoDisponibleError(Exception):
    pass


@dataclass(frozen=True)
class DatosInforme:
    evaluacion_id: int
    rubro: str | None
    puntaje_general: float
    controles_evaluados: int
    en_revision: int
    comparativa: list[ComparativaDominio]
    brechas_total: int
    brechas: list[Brecha]              # ya filtradas
    filtros: FiltrosBrechas
    plan: PlanFormativo
    generado: datetime
    # HU-21: ficha de identificación (None solo en pruebas antiguas que arman el PDF a mano:
    # el PDF sale igual, con el aviso legal y los puntajes de la comparativa)
    ficha: FichaInforme | None = None
    # Todas las brechas, sin filtrar (la huella y el resumen de la portada no dependen del filtro)
    brechas_completas: tuple[Brecha, ...] = ()


def _fmt(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{n:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _esc(texto: str | None) -> str:
    """Escapa para los párrafos de reportlab (mini-HTML)."""
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nombre_archivo(evaluacion_id: int, fecha: datetime) -> str:
    return f"informe_evaluacion-{evaluacion_id}_{fecha:%Y-%m-%d}.pdf"


ZONA = ZoneInfo("America/Santiago")


def _fecha_local(v: datetime | None, con_hora: bool = False) -> str:
    if v is None:
        return "—"
    if v.tzinfo is None:  # en la BD las fechas van en UTC sin zona
        from datetime import timezone
        v = v.replace(tzinfo=timezone.utc)
    v = v.astimezone(ZONA)
    return f"{v:%d-%m-%Y %H:%M}" if con_hora else f"{v:%d-%m-%Y}"


def _ficha_basica(d: "DatosInforme") -> FichaInforme:
    """Ficha mínima para quien arma DatosInforme sin ella (pruebas antiguas)."""
    from app.application.informes.analisis import DominioResultado
    from app.application.informes.ficha import AVISO_INFORME, cinco_puntajes, codigo_evaluacion

    dominios = [DominioResultado(None, c.dominio, c.tu_puntaje, None, 1 if c.tu_puntaje is not None else 0)
                for c in d.comparativa]
    return FichaInforme(
        codigo=codigo_evaluacion(d.evaluacion_id, d.generado.year), fecha_evaluacion=None,
        fecha_completado=None, version_matriz="sin registro", version_matriz_registrada=False,
        aviso=AVISO_INFORME, aviso_aceptado_version=None, aviso_aceptado_fecha=None,
        puntajes=cinco_puntajes(d.puntaje_general, d.controles_evaluados, dominios), huella="0" * 64,
    )


def generar_pdf(d: DatosInforme) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.graphics.shapes import Drawing, Line, Rect
        from reportlab.lib.units import mm
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import (
            KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise PdfNoDisponibleError("Falta reportlab (pip install -r requirements.txt).") from e

    c = colors.HexColor
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=c(TINTA), alignment=TA_LEFT)
    chico = ParagraphStyle("chico", parent=base, fontSize=8, leading=10.5)
    gris = ParagraphStyle("gris", parent=base, textColor=c(GRIS))
    gris_chico = ParagraphStyle("gris_chico", parent=chico, textColor=c(GRIS))
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                        spaceBefore=10, spaceAfter=4, textColor=c(VERDE))
    h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6)
    cabecera = ParagraphStyle("cab", parent=chico, fontName="Helvetica-Bold", textColor=colors.white)
    cifra = ParagraphStyle("cifra", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=19)

    estilo_tabla = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), c(VERDE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, c(LINEA)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])

    def p(texto, estilo=base):
        return Paragraph(texto, estilo)

    def sev(s: str):
        return p(f'<font color="{COLOR_SEVERIDAD.get(s, GRIS)}"><b>{_esc(s)}</b></font>', chico)

    ancho = A4[0] - 30 * mm
    historia = []

    # ------------------------------------------------------------ HU-21 · portada
    f = d.ficha or _ficha_basica(d)
    meta = d.comparativa[0].meta if d.comparativa else settings.META_CUMPLIMIENTO_PUNTAJE
    etiqueta = ParagraphStyle("etq", parent=chico, textColor=c(GRIS))
    valor = ParagraphStyle("val", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13)
    aviso_t = ParagraphStyle("aviso_t", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                             textColor=c(TINTA))
    aviso_p = ParagraphStyle("aviso_p", parent=chico, fontSize=8.2, leading=11, spaceAfter=3)

    historia += [
        p("ComplianceIA de Therion Labs: gobernanza de IA y protección de datos personales", gris_chico),
        Spacer(1, 2),
        p("Informe de autodiagnóstico", h1),
        Spacer(1, 2),
        p("Puntajes por dimensión, brechas priorizadas y rutas recomendadas"
          + (f" para una organización del rubro {_esc(d.rubro)}" if d.rubro else ""), gris),
        Spacer(1, 8),
    ]

    # Ficha de identificación (criterio 3: fecha, código de evaluación y versión de la matriz)
    version_txt = _esc(f.version_matriz)
    if not f.version_matriz_registrada:
        version_txt += '<br/><font size=7 color="%s">Vigente al emitir: la evaluación es anterior al registro de versión</font>' % GRIS
    celdas = [
        ("Código de evaluación", _esc(f.codigo)),
        ("Fecha de la evaluación", _fecha_local(f.fecha_completado, True) if f.fecha_completado
         else (f"{f.fecha_evaluacion:%d-%m-%Y}" if f.fecha_evaluacion else "—")),
        ("Emitido el", _fecha_local(d.generado, True) + '<font size=7> (hora de Chile)</font>'),
        ("Versión de la matriz", version_txt),
        ("Aviso legal", f"Versión {_esc(f.aviso.version)}"),
        ("Rubro", _esc(d.rubro) if d.rubro else "Sin rubro informado"),
    ]
    filas_ficha = []
    for i in range(0, len(celdas), 3):
        trio = celdas[i:i + 3]
        filas_ficha.append([p(e, etiqueta) for e, _ in trio])
        filas_ficha.append([p(v, valor) for _, v in trio])
    t = Table(filas_ficha, colWidths=[ancho / 3] * 3)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, c(LINEA)),
        ("LINEBELOW", (0, 1), (-1, 1), 0.4, c(LINEA)),
        ("LINEAFTER", (0, 0), (1, -1), 0.4, c(LINEA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 6), ("TOPPADDING", (0, 2), (-1, 2), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6), ("BOTTOMPADDING", (0, 3), (-1, 3), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    historia += [t, Spacer(1, 8)]

    # Aviso legal completo en la primera página (HU-04 criterio 2)
    caja = [[[p(_esc(f.aviso.titulo), aviso_t), Spacer(1, 3)] + [p(_esc(x), aviso_p) for x in f.aviso.texto]
             + ([p(f"El encuestado aceptó el aviso legal versión {_esc(f.aviso_aceptado_version)}"
                   + (f" el {_fecha_local(f.aviso_aceptado_fecha)}" if f.aviso_aceptado_fecha else "")
                   + " antes de responder.", gris_chico)] if f.aviso_aceptado_version else [])]]
    t = Table(caja, colWidths=[ancho])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c(AVISO_FONDO)),
        ("LINEBEFORE", (0, 0), (0, -1), 3, c(AVISO_BORDE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    historia += [t, Spacer(1, 4)]

    # Los 5 puntajes (HU-03): Global y las 4 dimensiones, con barra 0–100 y la meta punteada
    historia.append(p("Puntajes de madurez", h2))
    historia.append(p(
        f"Escala de 0 a 100. Las preguntas que no aplican a la organización no cuentan. La línea punteada "
        f"marca la meta de {_fmt(meta)} puntos: prácticas definidas, documentadas y con responsables.", gris_chico))
    historia.append(Spacer(1, 4))
    col_barra = ancho * 0.33
    ancho_barra = col_barra - 10  # descuenta el relleno de la celda

    def barra(puntaje: float | None, destacado: bool):
        alto = 11 if destacado else 8
        dib = Drawing(ancho_barra, alto + 4)
        dib.add(Rect(0, 2, ancho_barra, alto, fillColor=c(PISTA), strokeColor=None))
        if puntaje is not None:
            dib.add(Rect(0, 2, ancho_barra * max(0.0, min(puntaje, 100.0)) / 100, alto,
                         fillColor=c(VERDE if destacado else VERDE_BARRA), strokeColor=None))
        x = ancho_barra * meta / 100
        dib.add(Line(x, 0, x, alto + 4, strokeColor=c(TINTA), strokeWidth=0.8, strokeDashArray=[1.5, 1.5]))
        return dib

    filas = [[p(x, cabecera) for x in ("Dimensión", "Puntaje", "Nivel", "Preguntas", "0 a 100")]]
    estilos_extra = []
    for i, pt in enumerate(f.puntajes, start=1):
        num = (f"{_fmt(pt.puntaje)}" if pt.puntaje is not None else "—")
        estilo_num = cifra if pt.es_global else ParagraphStyle("n", parent=base, fontName="Helvetica-Bold",
                                                                fontSize=11, leading=13)
        nombre = "Puntaje global" if pt.es_global else _esc(pt.nombre)
        filas.append([
            p(f"<b>{nombre}</b>" if pt.es_global else nombre, base),
            p(num, estilo_num), p(_esc(pt.nivel), chico),
            p(str(pt.preguntas) if pt.preguntas else "—", chico), barra(pt.puntaje, pt.es_global),
        ])
        if pt.es_global:
            estilos_extra.append(("BACKGROUND", (0, i), (-1, i), c(VERDE_SUAVE)))
    t = Table(filas, colWidths=[ancho * w for w in (0.28, 0.11, 0.16, 0.12)] + [col_barra], repeatRows=1)
    t.setStyle(TableStyle(list(estilo_tabla.getCommands()) + [("VALIGN", (0, 1), (-1, -1), "MIDDLE")] + estilos_extra))
    historia.append(t)
    historia.append(Spacer(1, 4))
    completas = list(d.brechas_completas) or d.brechas
    cuenta_total = contar_por_severidad(completas)
    resumen_brechas = ", ".join(f"{cuenta_total[s]} {s.lower()}" for s in SEVERIDADES if cuenta_total[s])
    historia.append(p(
        f"{d.controles_evaluados} preguntas evaluadas. {d.brechas_total} brecha(s) detectada(s)"
        + (f" ({resumen_brechas})" if resumen_brechas else "")
        + f". El plan recomienda {d.plan.modulos} módulo(s) formativo(s) con {d.plan.horas} horas en total.",
        chico))
    if d.en_revision:
        historia.append(p(f"{d.en_revision} pregunta(s) siguen en revisión y no suman puntaje todavía.", gris_chico))
    historia.append(PageBreak())

    # ------------------------------------------------------------ comparativa
    historia.append(p("Comparativa por dimensión normativa", h2))
    historia.append(p(
        f"La meta es el nivel que debería alcanzar cada dimensión ({_fmt(d.comparativa[0].meta if d.comparativa else 75)} "
        "puntos: prácticas definidas, documentadas y con responsables). El promedio del rubro solo aparece "
        f"cuando al menos {settings.K_ANONIMATO_MINIMO} empresas distintas del sector completaron la evaluación: "
        "con menos, se oculta para que nadie pueda deducir el resultado de una empresa en particular.",
        gris_chico))
    historia.append(Spacer(1, 4))
    filas = [[p(x, cabecera) for x in ("Dimensión", "Tu puntaje", "Nivel", "Meta", "Frente a la meta",
                                       "Promedio del rubro")]]
    for cm in d.comparativa:
        dif = None if cm.tu_puntaje is None else round(cm.tu_puntaje - cm.meta, 1)
        if dif is None:
            frente = "—"
        elif dif >= 0:
            frente = f'<font color="{COLOR_SEVERIDAD["Baja"]}"><b>Cumple (+{_fmt(dif)})</b></font>'
        else:
            frente = f'<font color="{COLOR_SEVERIDAD["Crítica"]}"><b>Faltan {_fmt(-dif)} pts</b></font>'
        # HU-10: con menos de k empresas no se publica el promedio ni cuántas hay
        prom = (_fmt(cm.promedio_industria) if cm.promedio_industria is not None
                else f"Oculto: menos de {settings.K_ANONIMATO_MINIMO} empresas")
        filas.append([
            p(_esc(cm.dominio), chico), p(_fmt(cm.tu_puntaje), chico),
            p(ETIQUETA_MADUREZ[nivel_madurez(cm.tu_puntaje)], chico), p(_fmt(cm.meta), chico),
            p(frente, chico), p(prom, chico),
        ])
    t = Table(filas, colWidths=[ancho * w for w in (0.26, 0.12, 0.14, 0.09, 0.19, 0.20)], repeatRows=1)
    t.setStyle(estilo_tabla)
    historia.append(t)

    # ------------------------------------------------------------ brechas
    historia.append(p("Brechas priorizadas", h2))
    if d.filtros.activos:
        historia.append(p(f"Vista filtrada: {_esc(d.filtros.describir())} · {len(d.brechas)} de "
                          f"{d.brechas_total} brechas. La prioridad (#) es la del listado completo.", gris_chico))
    else:
        cuenta = contar_por_severidad(d.brechas)
        partes = [f'<font color="{COLOR_SEVERIDAD[s]}"><b>{cuenta[s]} {s.lower()}</b></font>'
                  for s in SEVERIDADES if cuenta[s]]
        historia.append(p(" · ".join(partes) if partes else "Sin brechas: todas las prácticas evaluadas se cumplen.",
                          chico))
    historia.append(Spacer(1, 4))
    if d.brechas:
        # Correcciones 29-10: el informe es del cliente; no lleva los códigos internos del catálogo.
        filas = [[p(x, cabecera) for x in ("#", "Severidad", "Dimensión", "Estado",
                                           "Brecha detectada", "Acción sugerida")]]
        for b in d.brechas:
            filas.append([
                p(str(b.prioridad), chico), sev(b.severidad), p(_esc(b.dominio), chico),
                p(ETIQUETA_ESTADO[b.estado], chico), p(_esc(b.descripcion), chico), p(_esc(b.accion or "—"), chico),
            ])
        t = Table(filas, colWidths=[ancho * w for w in (0.05, 0.11, 0.15, 0.12, 0.35, 0.22)], repeatRows=1)
        t.setStyle(estilo_tabla)
        historia.append(t)
        historia.append(Spacer(1, 4))
        historia.append(p("Guía: " + " · ".join(f"<b>{s}</b> {GUIA_SEVERIDAD[s].lower()}"
                                                 for s in SEVERIDADES[:4]), gris_chico))

    # ------------------------------------------------------------ plan formativo
    plan = d.plan
    historia.append(PageBreak())
    historia.append(p("Plan formativo recomendado", h2))
    historia.append(p(
        f"{plan.modulos} módulo(s) · {plan.horas} horas en total · {plan.brechas_mapeadas} de "
        f"{plan.brechas_total} brechas tienen una ruta del catálogo asociada. El nivel de cada dimensión "
        "se asigna según su puntaje: hasta 50 Inicial, hasta 75 Intermedio y sobre 75 Avanzado.", gris_chico))
    for dim in plan.dimensiones:
        bloque = [
            p(f"{_esc(dim.dominio)} — nivel {dim.nivel_asignado}", h3),
            p(f"Puntaje {_fmt(dim.puntaje)} · {dim.brechas_dimension} brecha(s) · {dim.horas} h. "
              f"{_esc(dim.objetivo_nivel)}", gris_chico),
            Spacer(1, 3),
        ]
        filas = [[p(x, cabecera) for x in ("Nivel", "Módulo y objetivo", "Horas", "Por qué")]]
        for m in dim.modulos:
            motivo = ("Base del nivel asignado" if m.motivo == "nivel"
                      else f"Cubre {len(m.brechas)} brecha(s) de esta dimensión")
            objetivo = f"<b>{_esc(m.ruta.nombre)}</b>"
            if m.ruta.objetivo:
                objetivo += f"<br/>{_esc(m.ruta.objetivo)}"
            if m.ruta.objetivos_especificos:
                objetivo += "".join(f"<br/>• {_esc(o)}" for o in m.ruta.objetivos_especificos)
            prioridad = "" if m.prioridad == "Complementario" else (
                f'<br/><font color="{COLOR_SEVERIDAD.get(m.prioridad, GRIS)}"><b>{_esc(m.prioridad)}</b></font>')
            filas.append([p(m.nivel, chico), p(objetivo, chico), p(str(m.ruta.horas or "—"), chico),
                          p(motivo + prioridad, chico)])
        t = Table(filas, colWidths=[ancho * w for w in (0.12, 0.56, 0.08, 0.24)], repeatRows=1)
        t.setStyle(estilo_tabla)
        # El título de la dimensión no queda huérfano al pie de una página
        historia.append(KeepTogether(bloque + [t]) if len(filas) <= 6 else KeepTogether(bloque))
        if len(filas) > 6:
            historia.append(t)
    if plan.brechas_sin_ruta:
        historia.append(Spacer(1, 6))
        historia.append(p(f"{len(plan.brechas_sin_ruta)} brecha(s) aún no tienen un módulo formativo asociado; "
                          "Therion Labs te orientará sobre ellas.", gris_chico))

    # ------------------------------------------------------------ HU-21 · verificación
    historia.append(Spacer(1, 12))
    bloque = [
        p("Identificación y verificación", h3),
        p(f"Código de evaluación <b>{_esc(f.codigo)}</b>. Versión de la matriz <b>{_esc(f.version_matriz)}</b>. "
          f"Huella de los resultados <b>{huella_legible(f.huella)}</b>.", chico),
        p("La huella resume los puntajes, las brechas y las rutas de esta evaluación (no la fecha de emisión): "
          "dos copias con la misma huella afirman lo mismo. Para confirmar que una copia no fue alterada, pida a "
          "Therion Labs la ficha del informe de este código y compare la huella.", gris_chico),
    ]
    historia.append(KeepTogether(bloque))

    pie_aviso = f.aviso.pie
    izquierda = f"ComplianceIA | {f.codigo} | Matriz {f.version_matriz}"

    class _Lienzo(Canvas):
        """Dibuja el pie al final, cuando ya se conoce el total de páginas ("Página X de Y")."""

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
                self._pie(total)
                super().showPage()
            super().save()

        def _pie(self, total: int):
            self.saveState()
            self.setStrokeColor(c(VERDE))
            self.setLineWidth(2)
            self.line(15 * mm, A4[1] - 10 * mm, A4[0] - 15 * mm, A4[1] - 10 * mm)
            self.setStrokeColor(c(LINEA))
            self.setLineWidth(0.5)
            self.line(15 * mm, 14.5 * mm, A4[0] - 15 * mm, 14.5 * mm)
            self.setFont("Helvetica", 7)
            self.setFillColor(c(TINTA))
            self.drawString(15 * mm, 11 * mm, pie_aviso)  # HU-04: el aviso en el pie de cada página
            self.setFillColor(c(GRIS))
            self.drawString(15 * mm, 7.5 * mm, izquierda)
            self.drawRightString(A4[0] - 15 * mm, 7.5 * mm, f"Página {self._pageNumber} de {total}")
            self.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"Informe de autodiagnóstico {f.codigo}", author="ComplianceIA (Therion Labs)",
        subject="Puntajes por dimensión, brechas priorizadas y rutas recomendadas",
        keywords=f"{f.codigo}, matriz {f.version_matriz}, aviso {f.aviso.version}",
    )
    doc.build(historia, canvasmaker=_Lienzo)
    return buffer.getvalue()
