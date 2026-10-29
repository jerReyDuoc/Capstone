"""
PDF del informe de la evaluación: resultado, comparativa, brechas priorizadas (HU-11)
y plan formativo (HU-12). Lo usan la descarga directa (GET …/informe.pdf) y el envío
por correo (POST …/informe/enviar), así el adjunto es idéntico a lo descargado.

Con reportlab (texto real y seleccionable, fuentes base Helvetica, sin archivos
externos). Se importa aquí y no al iniciar la app: si faltara la dependencia, solo
fallan estos endpoints (503), no toda la API.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

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


def _fmt(n: float | None) -> str:
    if n is None:
        return "—"
    return f"{n:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _esc(texto: str | None) -> str:
    """Escapa para los párrafos de reportlab (mini-HTML)."""
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nombre_archivo(evaluacion_id: int, fecha: datetime) -> str:
    return f"informe_evaluacion-{evaluacion_id}_{fecha:%Y-%m-%d}.pdf"


def generar_pdf(d: DatosInforme) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
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

    # ------------------------------------------------------------ portada / resumen
    fecha = d.generado.astimezone(ZoneInfo("America/Santiago"))
    historia += [
        p("ComplianceIA · Gobernanza de IA y protección de datos", gris_chico),
        Spacer(1, 2),
        p("Informe de diagnóstico", h1),
        Spacer(1, 4),
        p(f"Evaluación #{d.evaluacion_id}" + (f" · Rubro {_esc(d.rubro)}" if d.rubro else "")
          + f" · Generado el {fecha:%d-%m-%Y %H:%M} (hora de Chile)", gris),
        Spacer(1, 10),
    ]
    nivel = ETIQUETA_MADUREZ[nivel_madurez(d.puntaje_general)]
    tiles = [
        [p("Puntaje general", gris_chico), p("Nivel de madurez", gris_chico),
         p("Preguntas evaluadas", gris_chico), p("Brechas detectadas", gris_chico)],
        [p(f"{_fmt(d.puntaje_general)}<font size=9> / 100</font>", cifra), p(nivel, cifra),
         p(str(d.controles_evaluados), cifra), p(str(d.brechas_total), cifra)],
    ]
    t = Table(tiles, colWidths=[ancho / 4] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c(VERDE_SUAVE)),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    historia += [t, Spacer(1, 6)]
    if d.en_revision:
        historia.append(p(f"{d.en_revision} pregunta(s) siguen en revisión y no suman puntaje todavía.", gris_chico))

    # ------------------------------------------------------------ comparativa
    historia.append(p("Comparativa por dimensión normativa", h2))
    historia.append(p(
        f"La meta es el nivel que debería alcanzar cada dimensión ({_fmt(d.comparativa[0].meta if d.comparativa else 75)} "
        "puntos: prácticas definidas, documentadas y con responsables). El promedio del rubro aparece cuando "
        "hay suficientes evaluaciones completadas para que sea representativo.", gris_chico))
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
        prom = (_fmt(cm.promedio_industria) if cm.promedio_industria is not None
                else f"Sin referencia aún ({cm.muestras} eval.)")
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

    historia.append(Spacer(1, 12))
    historia.append(p("Este informe es una autoevaluación orientativa y no constituye asesoría legal.", gris_chico))

    def pie(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(c(GRIS))
        canvas.drawString(15 * mm, 10 * mm, f"ComplianceIA · Evaluación #{d.evaluacion_id}")
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Página {doc.page}")
        canvas.setStrokeColor(c(VERDE))
        canvas.setLineWidth(2)
        canvas.line(15 * mm, A4[1] - 10 * mm, A4[0] - 15 * mm, A4[1] - 10 * mm)
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Informe de diagnóstico · Evaluación {d.evaluacion_id}", author="ComplianceIA",
        subject="Brechas normativas y plan formativo",
    )
    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return buffer.getvalue()
