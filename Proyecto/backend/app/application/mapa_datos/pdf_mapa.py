"""
HU-34 criterio 3 · Informe PDF del mapa de datos personales (descarga y adjunto del correo).

A4 horizontal (el mapa y las tablas son anchos), con reportlab: texto real y seleccionable.

  1. Portada: empresa, versión del mapa y su huella, fecha de emisión, filtros aplicados,
     indicadores (sistemas, bases, terceros, flujos, transferencias, sensibles, NNA) y el
     porcentaje de completitud.
  2. Diagrama del mapa (misma disposición que el panel: app/domain/mapa_datos/disposicion.py),
     con la leyenda.
  3. Hallazgos de riesgo priorizados, con recomendación y referencia normativa.
  4. Inventario de sistemas y bases de datos · terceros y destinatarios · flujos.
  5. Transferencias internacionales con su garantía.
  6. Base para el registro de actividades de tratamiento (RAT): por categoría de datos, dónde
     está, de qué titulares, con quién se comparte y en qué países.
  7. Historial reciente de versiones y verificación (huella).

Con filtros (criterio 3), el diagrama y las tablas muestran solo lo filtrado; los indicadores y
los hallazgos de la portada son siempre los del mapa completo (se aclara en el informe).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos import analisis, disposicion
from app.domain.mapa_datos.modelo import Elemento, Flujo

ZONA = ZoneInfo("America/Santiago")

# Paleta para papel (la del informe de evaluación, app/application/informes/pdf_informe.py)
VERDE = "#0b7a5a"
VERDE_SUAVE = "#e3f4ee"
TINTA = "#14201b"
GRIS = "#5b6b64"
LINEA = "#d5ddd9"
PISTA = "#e7ecea"
AVISO_FONDO = "#f6f4ee"
AVISO_BORDE = "#8a6200"
COLOR_SEVERIDAD = {"Crítica": "#b4233f", "Alta": "#c4561b", "Media": "#8a6200", "Baja": "#2f7d4f"}
# Nodos por tipo: relleno y borde
COLOR_TIPO = {
    "sistema": ("#e3f4ee", "#0b7a5a"),
    "base_datos": ("#e8ecfb", "#3d4fa8"),
    "tercero": ("#fdf0e4", "#b3541e"),
}
ETIQUETA_CORTA = {"sistema": "SISTEMA", "base_datos": "BASE DE DATOS", "tercero": "TERCERO"}
COLOR_FLUJO = "#7d8b85"
COLOR_INTERNACIONAL = "#9a6a00"
COLOR_SENSIBLE = "#b4233f"
COLOR_NNA = "#6b3fa0"

AVISO = ("Este informe describe el mapa de datos que registró la propia empresa en ComplianceIA. Es una herramienta "
         "de apoyo a la gestión y no constituye asesoría legal: las referencias normativas son orientativas y deben "
         "validarse con el encargado de protección de datos o un asesor.")


class PdfNoDisponibleError(Exception):
    pass


@dataclass(frozen=True)
class VersionResumen:
    numero: int
    fecha: datetime
    resumen: str


@dataclass
class DatosInformeMapa:
    razon_social: str
    rubro: str | None
    version: int
    fecha_version: datetime | None
    huella: str
    elementos: list[Elemento]
    flujos: list[Flujo]
    filtros: analisis.FiltrosMapa
    generado: datetime
    historial: list[VersionResumen] = field(default_factory=list)


def nombre_archivo(version: int, fecha: datetime) -> str:
    return f"mapa_datos_personales_v{version}_{fecha:%Y-%m-%d}.pdf"


def _esc(texto: str | None) -> str:
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fecha(v: datetime | None, con_hora: bool = True) -> str:
    if v is None:
        return "—"
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    v = v.astimezone(ZONA)
    return f"{v:%d-%m-%Y %H:%M}" if con_hora else f"{v:%d-%m-%Y}"


def huella_legible(h: str) -> str:
    h = (h or "").upper()
    return " ".join(h[i:i + 4] for i in range(0, min(len(h), 32), 4))


def _recortar(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[:maximo - 1].rstrip() + "…"


def _partir(texto: str, ancho: int, lineas: int = 2) -> list[str]:
    """Parte un nombre en hasta `lineas` líneas de `ancho` caracteres (la última se recorta)."""
    palabras, salida, actual = texto.split(), [], ""
    for p in palabras:
        if len(actual) + len(p) + (1 if actual else 0) <= ancho:
            actual = f"{actual} {p}".strip()
        else:
            if actual:
                salida.append(actual)
            actual = p
        if len(salida) == lineas:
            break
    if actual and len(salida) < lineas:
        salida.append(actual)
    consumido = len(" ".join(salida))
    if consumido < len(texto.strip()) and salida:
        salida[-1] = _recortar(salida[-1] + " " + texto.strip()[consumido:].strip(), ancho)
    return [_recortar(s, ancho) for s in salida] or [""]


def generar_pdf_mapa(d: DatosInformeMapa) -> bytes:
    try:
        from reportlab.graphics.shapes import Drawing, Group, Line, Path, Polygon, Rect, String
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import (
            KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise PdfNoDisponibleError("Falta reportlab (pip install -r requirements.txt).") from e

    c = colors.HexColor
    pagina = landscape(A4)
    ancho = pagina[0] - 30 * mm
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=c(TINTA))
    chico = ParagraphStyle("chico", parent=base, fontSize=7.8, leading=10)
    gris = ParagraphStyle("gris", parent=base, textColor=c(GRIS))
    gris_chico = ParagraphStyle("gris_chico", parent=chico, textColor=c(GRIS))
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=8,
                        spaceAfter=4, textColor=c(VERDE))
    h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6)
    cabecera = ParagraphStyle("cab", parent=chico, fontName="Helvetica-Bold", textColor=colors.white)
    etiqueta = ParagraphStyle("etq", parent=chico, textColor=c(GRIS))
    valor = ParagraphStyle("val", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13)
    cifra = ParagraphStyle("cifra", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=21)

    estilo_tabla = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), c(VERDE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, c(LINEA)),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])

    def p(texto, estilo=chico):
        return Paragraph(texto, estilo)

    def tabla(filas, anchos, extra=()):
        t = Table(filas, colWidths=[ancho * w for w in anchos], repeatRows=1)
        t.setStyle(TableStyle(list(estilo_tabla.getCommands()) + list(extra)))
        return t

    def lista_cat(codigos, sensibles=True) -> str:
        if not codigos:
            return '<font color="%s">Sin informar</font>' % GRIS
        partes = []
        for x in codigos:
            nombre = _esc(cat.nombre_dato(x))
            partes.append(f'<font color="{COLOR_SENSIBLE}"><b>{nombre}</b></font>' if sensibles and cat.es_sensible(x)
                          else nombre)
        return ", ".join(partes)

    def lista_tit(codigos, nna: bool) -> str:
        txt = ", ".join(_esc(cat.nombre_titular(x)) for x in codigos) if codigos else \
            '<font color="%s">Sin informar</font>' % GRIS
        if nna and "nna" not in (codigos or []):
            txt += f' · <font color="{COLOR_NNA}"><b>incluye NNA</b></font>'
        return txt

    def si_no(v: bool | None, si="Sí", no="No") -> str:
        return "Por confirmar" if v is None else (si if v else no)

    # -------------------------------------------------------------- datos
    todos_e, todos_f = d.elementos, d.flujos
    por_id = {e.id: e for e in todos_e}
    ids_e, ids_f = analisis.aplicar_filtros(todos_e, todos_f, d.filtros)
    elementos = [e for e in todos_e if e.id in ids_e]
    flujos = [f for f in todos_f if f.id in ids_f]
    res = analisis.resumen(todos_e, todos_f)
    comp = analisis.completitud(todos_e, todos_f)
    hall = analisis.hallazgos(todos_e, todos_f)
    cuenta = analisis.contar_hallazgos(hall)
    der = {f.id: analisis.derivados_flujo(f, por_id) for f in todos_f}

    historia: list = []

    # -------------------------------------------------------------- 1. portada
    historia += [
        p("ComplianceIA de Therion Labs · Protección de datos personales", gris_chico),
        Spacer(1, 2),
        p("Mapa de datos personales", h1),
        Spacer(1, 2),
        p(f"Sistemas, bases de datos, terceros y flujos donde <b>{_esc(d.razon_social)}</b> trata datos personales: "
          "qué datos, de quién, dónde están y con quién se comparten.", gris),
        Spacer(1, 8),
    ]
    celdas = [
        ("Empresa", _esc(d.razon_social)), ("Rubro", _esc(d.rubro) if d.rubro else "Sin rubro informado"),
        ("Versión del mapa", f"N.º {d.version}" + (f" · {_fecha(d.fecha_version)}" if d.fecha_version else "")),
        ("Emitido el", _fecha(d.generado) + '<font size=7> (hora de Chile)</font>'),
        ("Huella de la versión", huella_legible(d.huella) or "—"),
        ("Vista", _esc(d.filtros.describir(por_id)).capitalize()),
    ]
    filas = []
    for i in range(0, len(celdas), 3):
        trio = celdas[i:i + 3]
        filas.append([p(e, etiqueta) for e, _ in trio])
        filas.append([p(v, valor) for _, v in trio])
    t = Table(filas, colWidths=[ancho / 3] * 3)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, c(LINEA)), ("LINEBELOW", (0, 1), (-1, 1), 0.4, c(LINEA)),
        ("LINEAFTER", (0, 0), (1, -1), 0.4, c(LINEA)),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 6), ("TOPPADDING", (0, 2), (-1, 2), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6), ("BOTTOMPADDING", (0, 3), (-1, 3), 6),
    ]))
    historia += [t, Spacer(1, 10)]

    indicadores = [
        ("Sistemas", res["sistemas"], None), ("Bases de datos", res["bases_datos"], None),
        ("Terceros", res["terceros"], None), ("Flujos", res["flujos"], f"{res['flujos_a_terceros']} hacia terceros"),
        ("Transferencias internacionales", res["transferencias_internacionales"],
         f"{res['transferencias_sin_garantia']} sin garantía" if res["transferencias_internacionales"] else None),
        ("Con datos sensibles", res["elementos_con_sensibles"], "elementos"),
        ("Con datos de NNA", res["elementos_con_nna"], "elementos"),
    ]
    fila_et = [p(n, etiqueta) for n, _, _ in indicadores]
    fila_ci = [p(str(v), cifra) for _, v, _ in indicadores]
    fila_ex = [p(_esc(x or ""), gris_chico) for _, _, x in indicadores]
    t = Table([fila_et, fila_ci, fila_ex], colWidths=[ancho / len(indicadores)] * len(indicadores))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c(VERDE_SUAVE)), ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
    ]))
    historia += [t, Spacer(1, 8)]

    # Completitud (barra) y resumen de hallazgos
    barra_ancho = ancho * 0.35
    dib = Drawing(barra_ancho, 12)
    dib.add(Rect(0, 2, barra_ancho, 8, fillColor=c(PISTA), strokeColor=None))
    dib.add(Rect(0, 2, barra_ancho * comp["porcentaje"] / 100, 8, fillColor=c(VERDE), strokeColor=None))
    partes_h = [f'<font color="{COLOR_SEVERIDAD[s]}"><b>{n} {s.lower()}{"s" if n != 1 else ""}</b></font>'
                for s, n in cuenta.items() if n]
    t = Table([[p(f"<b>Completitud del mapa: {comp['porcentaje']} %</b>", base), dib,
                p("Hallazgos de riesgo: " + (" · ".join(partes_h) if partes_h else "ninguno"), base)]],
              colWidths=[ancho * 0.22, barra_ancho + 10, ancho * 0.43 - 10])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    historia += [t, Spacer(1, 4)]
    if comp["pendientes"]:
        historia.append(p(f"{len(comp['pendientes'])} elemento(s) o flujo(s) tienen información por completar o "
                          "confirmar. Completarlos mejora la precisión de los hallazgos.", gris_chico))
    if res["paises"]:
        historia.append(p("Países donde se alojan los datos: " + ", ".join(
            f"{_esc(x['nombre'])} ({x['elementos']})" for x in res["paises"]), gris_chico))
    historia.append(Spacer(1, 8))
    aviso = Table([[p(AVISO, gris_chico)]], colWidths=[ancho])
    aviso.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c(AVISO_FONDO)), ("LINEBEFORE", (0, 0), (0, -1), 3, c(AVISO_BORDE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    historia.append(aviso)
    if d.filtros.activos:
        historia += [Spacer(1, 4), p(
            f"Vista filtrada ({_esc(d.filtros.describir(por_id))}): el diagrama y las tablas muestran "
            f"{len(elementos)} de {len(todos_e)} elementos y {len(flujos)} de {len(todos_f)} flujos. Los indicadores y "
            "los hallazgos son los del mapa completo.", gris_chico)]

    # -------------------------------------------------------------- 2. diagrama
    historia.append(PageBreak())
    historia.append(p("Diagrama del mapa", h2))
    if not elementos:
        historia.append(p("No hay elementos para mostrar con los filtros elegidos.", gris))
    else:
        lay = disposicion.calcular([(e.id, e.tipo, e.nombre) for e in elementos],
                                   [(f.id, f.origen_id, f.destino_id) for f in flujos])
        alto_disp = pagina[1] - 16 * mm - 20 * mm - 28 * mm
        escala = min(ancho / lay.ancho, alto_disp / lay.alto, 1.0)
        dib = Drawing(lay.ancho * escala, lay.alto * escala)
        g = Group()
        H = lay.alto
        W, A = disposicion.ANCHO_NODO, disposicion.ALTO_NODO

        def y_pdf(y: float) -> float:
            return H - y

        # Flujos: curva de la derecha del origen a la izquierda del destino
        pares: dict[tuple[int, int], int] = {}
        for f in flujos:
            o, de = lay.nodos.get(f.origen_id), lay.nodos.get(f.destino_id)
            if o is None or de is None:
                continue
            clave_par = (min(f.origen_id, f.destino_id), max(f.origen_id, f.destino_id))
            desfase = pares.get(clave_par, 0)
            pares[clave_par] = desfase + 1
            dy = (desfase * 10) - (5 if desfase else 0)
            x1, y1 = o.x + W, o.y + A / 2 + dy
            x2, y2 = de.x, de.y + A / 2 + dy
            dfl = der[f.id]
            color = COLOR_INTERNACIONAL if dfl.internacional else (COLOR_SENSIBLE if f.sensibles else COLOR_FLUJO)
            ruta = Path(strokeColor=c(color), strokeWidth=1.6 if (f.sensibles or dfl.internacional) else 1.1,
                        fillColor=None, strokeDashArray=[5, 3] if dfl.internacional else None)
            ruta.moveTo(x1, y_pdf(y1))
            if de.columna <= o.columna:
                # Hacia atrás o en la misma columna: rodea por fuera
                x2 = de.x + W
                curva = max(x1, x2) + 70
                ruta.curveTo(curva, y_pdf(y1), curva, y_pdf(y2), x2 + 6, y_pdf(y2))
                punta = (x2, y2, 1)
            else:
                # Pasa por los puntos de paso de las columnas intermedias (entre los nodos)
                cx, cy = x1, y1
                for px_, py_ in lay.pasos.get(f.id, []):
                    dx = max(30.0, (px_ - cx) / 2)
                    ruta.curveTo(cx + dx, y_pdf(cy), px_ - dx, y_pdf(py_), px_, y_pdf(py_))
                    ruta.lineTo(px_ + W, y_pdf(py_))
                    cx, cy = px_ + W, py_
                dx = max(30.0, (x2 - cx) / 2)
                ruta.curveTo(cx + dx, y_pdf(cy), x2 - dx, y_pdf(y2), x2 - 6, y_pdf(y2))
                punta = (x2, y2, -1)
            g.add(ruta)
            px, py, sentido = punta
            g.add(Polygon([px, y_pdf(py), px + 9 * sentido, y_pdf(py) + 4.5, px + 9 * sentido, y_pdf(py) - 4.5],
                          fillColor=c(color), strokeColor=None))

        # Nodos
        for e in elementos:
            n = lay.nodos[e.id]
            relleno, borde = COLOR_TIPO.get(e.tipo, ("#ffffff", GRIS))
            x, y = n.x, y_pdf(n.y + A)
            g.add(Rect(x, y, W, A, rx=8, ry=8, fillColor=c(relleno), strokeColor=c(borde),
                       strokeWidth=1.8 if e.sensibles else 1))
            g.add(Rect(x, y + 6, 4, A - 12, fillColor=c(borde), strokeColor=None))
            g.add(String(x + 12, y + A - 13, ETIQUETA_CORTA.get(e.tipo, ""), fontName="Helvetica-Bold",
                         fontSize=8, fillColor=c(borde)))
            lineas = _partir(e.nombre, 24, 2)
            for i, linea in enumerate(lineas):
                g.add(String(x + 12, y + A - 27 - i * 12.5, linea, fontName="Helvetica-Bold", fontSize=11.5,
                             fillColor=c(TINTA)))
            pais = analisis.pais_efectivo(e)
            g.add(String(x + 12, y + 6, (pais or "¿país?"), fontName="Helvetica-Bold", fontSize=9,
                         fillColor=c(COLOR_INTERNACIONAL if e.fuera_de_chile else GRIS)))
            marcas = ([("NNA", COLOR_NNA)] if e.incluye_nna else []) + \
                     ([("SENSIBLE", COLOR_SENSIBLE)] if e.sensibles else [])
            xm = x + W - 8
            for texto, color in marcas:
                largo = len(texto) * 5.6 + 10
                xm -= largo
                g.add(Rect(xm, y + 4, largo, 13, rx=6, ry=6, fillColor=c(color), strokeColor=None))
                g.add(String(xm + 5, y + 7.5, texto, fontName="Helvetica-Bold", fontSize=8, fillColor=colors.white))
                xm -= 4
        g.scale(escala, escala)
        dib.add(g)
        historia.append(dib)
        historia.append(Spacer(1, 6))
        ley = Drawing(ancho, 14)
        xl = 0
        for texto, relleno, borde in (("Sistema", *COLOR_TIPO["sistema"]), ("Base de datos", *COLOR_TIPO["base_datos"]),
                                      ("Tercero", *COLOR_TIPO["tercero"])):
            ley.add(Rect(xl, 2, 14, 10, rx=3, ry=3, fillColor=c(relleno), strokeColor=c(borde)))
            ley.add(String(xl + 18, 4, texto, fontName="Helvetica", fontSize=8, fillColor=c(TINTA)))
            xl += 90
        for texto, color, guion in (("Flujo", COLOR_FLUJO, None), ("Con datos sensibles", COLOR_SENSIBLE, None),
                                    ("Transferencia internacional", COLOR_INTERNACIONAL, [5, 3])):
            ley.add(Line(xl, 7, xl + 22, 7, strokeColor=c(color), strokeWidth=1.6, strokeDashArray=guion))
            ley.add(String(xl + 27, 4, texto, fontName="Helvetica", fontSize=8, fillColor=c(TINTA)))
            xl += 40 + len(texto) * 4.4
        historia.append(ley)
        if escala < 0.55:
            historia.append(p("El mapa es grande y se redujo para caber en la página: el detalle de cada elemento está "
                              "en las tablas siguientes.", gris_chico))

    # -------------------------------------------------------------- 3. hallazgos
    historia.append(PageBreak())
    historia.append(p("Hallazgos de riesgo", h2))
    historia.append(p("Riesgos que se desprenden del mapa completo, del más grave al más leve. Cada uno indica qué "
                      "elementos o flujos afecta, qué hacer y en qué se basa.", gris_chico))
    historia.append(Spacer(1, 4))
    if hall:
        filas = [[p(x, cabecera) for x in ("Severidad", "Hallazgo", "Qué hacer", "Referencia")]]
        for h in hall:
            filas.append([
                p(f'<font color="{COLOR_SEVERIDAD[h.severidad]}"><b>{h.severidad}</b></font>'),
                p(f"<b>{_esc(h.titulo)}</b><br/>{_esc(h.detalle)}"), p(_esc(h.recomendacion)),
                p(_esc(h.referencia), gris_chico)])
        historia.append(tabla(filas, (0.09, 0.40, 0.33, 0.18)))
    else:
        historia.append(p("No se detectaron riesgos con la información registrada.", base))

    # -------------------------------------------------------------- 4. inventario
    internos = [e for e in elementos if not e.es_tercero]
    terceros = [e for e in elementos if e.es_tercero]
    historia.append(p("Sistemas y bases de datos", h2))
    if internos:
        filas = [[p(x, cabecera) for x in ("Nombre", "Tipo", "Proveedor", "País", "Responsable interno",
                                           "Categorías de datos", "Titulares")]]
        for e in sorted(internos, key=lambda x: (x.tipo, x.nombre.lower())):
            nombre = f"<b>{_esc(e.nombre)}</b>"
            if e.descripcion:
                nombre += f'<br/><font color="{GRIS}">{_esc(_recortar(e.descripcion, 160))}</font>'
            if e.pendiente_revision:
                nombre += f'<br/><font color="{AVISO_BORDE}">Por confirmar</font>'
            filas.append([
                p(nombre), p(f"{_esc(cat.etiqueta('tipo', e.tipo))}<br/>{_esc(cat.etiqueta_subtipo(e.tipo, e.subtipo))}"),
                p(_esc(e.proveedor or "—")), p(_esc(cat.nombre_pais(analisis.pais_efectivo(e)))),
                p(_esc(e.responsable) if e.responsable else f'<font color="{COLOR_SEVERIDAD["Alta"]}">Sin asignar</font>'),
                p(lista_cat(e.categorias_datos)), p(lista_tit(e.categorias_titulares, e.incluye_nna))])
        historia.append(tabla(filas, (0.17, 0.11, 0.10, 0.08, 0.12, 0.26, 0.16)))
    else:
        historia.append(p("No hay sistemas ni bases de datos en esta vista.", gris))

    historia.append(p("Terceros y destinatarios", h2))
    if terceros:
        filas = [[p(x, cabecera) for x in ("Tercero", "Categoría", "Rol", "País", "Contrato", "Datos que recibe",
                                           "Titulares")]]
        for e in sorted(terceros, key=lambda x: x.nombre.lower()):
            recibidos = sorted({x for f in todos_f if f.destino_id == e.id for x in f.categorias_datos}
                               | set(e.categorias_datos))
            requiere = e.rol_tercero is None or e.rol_tercero in cat.ROLES_CON_CONTRATO
            contrato = ("No requiere" if not requiere else si_no(e.contrato_firmado, "Firmado", "Sin contrato"))
            color = COLOR_SEVERIDAD["Alta"] if requiere and e.contrato_firmado is not True else TINTA
            filas.append([
                p(f"<b>{_esc(e.nombre)}</b>" + (f"<br/>{_esc(e.proveedor)}" if e.proveedor else "")),
                p(_esc(cat.etiqueta_subtipo(e.tipo, e.subtipo))), p(_esc(cat.etiqueta("rol", e.rol_tercero))),
                p(_esc(cat.nombre_pais(e.pais))), p(f'<font color="{color}">{contrato}</font>'),
                p(lista_cat(recibidos)), p(lista_tit(e.categorias_titulares, e.incluye_nna))])
        historia.append(tabla(filas, (0.17, 0.12, 0.13, 0.08, 0.09, 0.25, 0.16)))
    else:
        historia.append(p("No hay terceros en esta vista.", gris))

    historia.append(p("Flujos de datos", h2))
    if flujos:
        filas = [[p(x, cabecera) for x in ("Origen → destino", "Finalidad", "Categorías de datos", "Titulares",
                                           "Frecuencia y medio", "Cifrado", "Transferencia")]]
        for f in sorted(flujos, key=lambda x: (por_id[x.origen_id].nombre.lower(), por_id[x.destino_id].nombre.lower())):
            dfl = der[f.id]
            trans = "—"
            if dfl.internacional:
                trans = (f'<font color="{COLOR_INTERNACIONAL}"><b>Internacional</b></font><br/>'
                         f"{_esc(cat.nombre_pais(dfl.pais_origen))} → {_esc(cat.nombre_pais(dfl.pais_destino))}")
            filas.append([
                p(f"<b>{_esc(por_id[f.origen_id].nombre)}</b> → <b>{_esc(por_id[f.destino_id].nombre)}</b>"),
                p(_esc(f.finalidad or "Sin informar")), p(lista_cat(f.categorias_datos)),
                p(lista_tit(f.categorias_titulares, f.incluye_nna)),
                p(f"{_esc(cat.etiqueta('frecuencia', f.frecuencia))}<br/>{_esc(cat.etiqueta('medio', f.medio))}"),
                p(si_no(f.cifrado)), p(trans)])
        historia.append(tabla(filas, (0.20, 0.17, 0.20, 0.13, 0.11, 0.07, 0.12)))
    else:
        historia.append(p("No hay flujos en esta vista.", gris))

    # -------------------------------------------------------------- 5. transferencias internacionales
    intl = [f for f in flujos if der[f.id].internacional]
    historia.append(p("Transferencias internacionales", h2))
    if intl:
        filas = [[p(x, cabecera) for x in ("Flujo", "País de destino", "Datos", "Garantía", "Estado")]]
        for f in intl:
            dfl = der[f.id]
            if dfl.garantia_valida:
                estado = f'<font color="{COLOR_SEVERIDAD["Baja"]}"><b>Con garantía</b></font>'
            elif f.sensibles or f.incluye_nna:
                estado = f'<font color="{COLOR_SEVERIDAD["Crítica"]}"><b>Sin garantía · datos sensibles o NNA</b></font>'
            else:
                estado = f'<font color="{COLOR_SEVERIDAD["Alta"]}"><b>Sin garantía</b></font>'
            filas.append([
                p(f"{_esc(por_id[f.origen_id].nombre)} → {_esc(por_id[f.destino_id].nombre)}"),
                p(_esc(cat.nombre_pais(dfl.pais_destino))), p(lista_cat(f.categorias_datos)),
                p(_esc(cat.etiqueta("garantia", f.garantia)) if f.garantia else "Sin informar"), p(estado)])
        historia.append(tabla(filas, (0.28, 0.12, 0.28, 0.17, 0.15)))
    else:
        historia.append(p("No hay transferencias internacionales en esta vista.", gris))

    # -------------------------------------------------------------- 6. base RAT
    historia.append(PageBreak())
    historia.append(p("Base para el registro de actividades de tratamiento", h2))
    historia.append(p("Por cada categoría de datos: dónde está, de qué titulares, con quién se comparte y en qué países. "
                      "Usa las mismas categorías del catálogo con que se arma el registro de actividades de tratamiento "
                      "(RAT).", gris_chico))
    historia.append(Spacer(1, 4))
    rat = analisis.base_rat(elementos, flujos)
    if rat:
        filas = [[p(x, cabecera) for x in ("Categoría de datos", "Dónde está", "Titulares", "Se comparte con",
                                           "Países")]]
        for r in rat:
            nombre = f"<b>{_esc(r['nombre'])}</b>"
            if r["sensible"]:
                nombre = f'<font color="{COLOR_SENSIBLE}">{nombre}</font><br/><font color="{GRIS}">Dato sensible</font>'
            paises = ", ".join(_esc(x) for x in r["paises"]) or "—"
            if r["internacional"]:
                paises += f'<br/><font color="{COLOR_INTERNACIONAL}">Sale del país</font>'
            filas.append([p(nombre), p(", ".join(_esc(x) for x in r["elementos"]) or "—"),
                          p(", ".join(_esc(x) for x in r["titulares"]) or "—"),
                          p(", ".join(_esc(x) for x in r["terceros"]) or "—"), p(paises)])
        historia.append(tabla(filas, (0.17, 0.27, 0.18, 0.24, 0.14)))
    else:
        historia.append(p("Aún no hay categorías de datos registradas.", gris))

    # -------------------------------------------------------------- 7. historial y verificación
    if d.historial:
        historia.append(p("Historial reciente de cambios", h2))
        filas = [[p(x, cabecera) for x in ("Versión", "Fecha", "Cambio")]]
        for v in d.historial:
            filas.append([p(f"N.º {v.numero}"), p(_fecha(v.fecha)), p(_esc(v.resumen))])
        historia.append(tabla(filas, (0.09, 0.14, 0.77)))
    historia.append(Spacer(1, 10))
    historia.append(KeepTogether([
        p("Verificación", h3),
        p(f"Versión del mapa <b>N.º {d.version}</b> · huella <b>{huella_legible(d.huella)}</b>.", chico),
        p("La huella resume el contenido completo de esta versión del mapa: si cambia cualquier elemento o flujo, "
          "cambia la huella. Cada versión queda registrada en el historial del mapa y en el registro de auditoría.",
          gris_chico),
    ]))

    izquierda = f"ComplianceIA | Mapa de datos de {_recortar(d.razon_social, 60)} | Versión {d.version}"

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
                self._pie(total)
                super().showPage()
            super().save()

        def _pie(self, total: int):
            self.saveState()
            self.setStrokeColor(c(VERDE))
            self.setLineWidth(2)
            self.line(15 * mm, pagina[1] - 10 * mm, pagina[0] - 15 * mm, pagina[1] - 10 * mm)
            self.setStrokeColor(c(LINEA))
            self.setLineWidth(0.5)
            self.line(15 * mm, 12.5 * mm, pagina[0] - 15 * mm, 12.5 * mm)
            self.setFont("Helvetica", 7)
            self.setFillColor(c(GRIS))
            self.drawString(15 * mm, 8 * mm, izquierda)
            self.drawRightString(pagina[0] - 15 * mm, 8 * mm, f"Página {self._pageNumber} de {total}")
            self.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=pagina, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Mapa de datos personales · versión {d.version}", author="ComplianceIA (Therion Labs)",
        subject="Sistemas, bases de datos, terceros y flujos de datos personales",
        keywords=f"mapa de datos, RAT, RoPA, versión {d.version}",
    )
    doc.build(historia, canvasmaker=_Lienzo)
    return buffer.getvalue()


def cuerpo_correo(razon_social: str, version: int, res: dict, cuenta: dict[str, int], completitud: int) -> tuple[str, str]:
    """(texto plano, html) del correo con el informe. Sin datos personales: solo cifras del mapa."""
    from html import escape

    graves = cuenta.get("Crítica", 0) + cuenta.get("Alta", 0)
    texto = (
        "Hola,\n\n"
        f"Te enviamos el informe del mapa de datos personales de {razon_social} (versión {version}).\n\n"
        f"Sistemas: {res['sistemas']} · Bases de datos: {res['bases_datos']} · Terceros: {res['terceros']}\n"
        f"Flujos: {res['flujos']} · Transferencias internacionales: {res['transferencias_internacionales']}\n"
        f"Hallazgos críticos o altos: {graves} · Completitud del mapa: {completitud} %\n\n"
        "El informe completo va adjunto en PDF: incluye el diagrama, el inventario, los flujos, las "
        "transferencias internacionales, los hallazgos de riesgo y la base para el registro de actividades "
        "de tratamiento.\n\n"
        "Este correo se generó automáticamente; no es necesario responderlo.\nComplianceIA\n"
    )
    empresa = escape(razon_social)

    def celda(titulo: str, cifra, pie: str) -> str:
        return (f'<td style="padding:14px;font-size:12px;color:#5b6b64">{titulo}<br>'
                f'<span style="font-size:22px;font-weight:bold;color:#14201b">{cifra}</span><br>{pie}</td>')

    html = f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#14201b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;border-top:4px solid #0b7a5a">
<tr><td style="padding:28px 28px 8px">
<p style="margin:0 0 4px;font-size:12px;color:#5b6b64">ComplianceIA · Protección de datos</p>
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">Mapa de datos personales de {empresa}</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.5">Adjuntamos el informe de la <b>versión {version}</b> del mapa: qué datos personales trata tu empresa, de quién, dónde están y con quién se comparten.</p>
</td></tr>
<tr><td style="padding:0 28px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e3f4ee;border-radius:8px"><tr>
{celda("Elementos", res["elementos"], f"{res['sistemas']} sistemas · {res['bases_datos']} bases · {res['terceros']} terceros")}
{celda("Flujos", res["flujos"], f"{res['transferencias_internacionales']} internacionales")}
{celda("Riesgos", graves, "críticos o altos")}
{celda("Completitud", f"{completitud}&nbsp;%", "del mapa")}
</tr></table>
</td></tr>
<tr><td style="padding:20px 28px 28px;font-size:12px;line-height:1.5;color:#5b6b64">
Este correo se generó automáticamente; no es necesario responderlo. El informe es una herramienta de apoyo a la gestión y no constituye asesoría legal.
</td></tr></table>
</td></tr></table></body></html>"""
    return texto, html
