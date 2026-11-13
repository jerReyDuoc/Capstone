"""
HU-37 criterio 4 · El informe RoPA en una planilla Excel (XLSX).

Mismo contenido que el PDF (los dos leen InformeRopa de app/application/ropa/informe.py), para filtrar,
ordenar o pegarlo en el formato que pida el cliente o socio:

  Portada              identificación (código, versión, fecha, partes incluidas).
  Organización         contacto de la empresa y delegado de protección de datos.
  Como responsable     una fila por actividad con los campos del RoPA (si se incluye esa parte).
  Como encargado       una fila por actividad, con la organización por cuenta de la cual se actúa.
  Transferencias       una fila por transferencia internacional.
  Aviso legal          el texto completo y su versión.

Seguridad: ningún texto se escribe como fórmula (inyección en planillas, OWASP) y se quitan los caracteres
de control que Excel no admite.
"""
from __future__ import annotations

import io
import math

from app.application.informes import motor_pdf as M
from app.application.ropa import informe as R

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class XlsxNoDisponibleError(Exception):
    pass


def _hex(color: str) -> str:
    return color.lstrip("#").upper()


def generar_xlsx_ropa(inf: R.InformeRopa) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise XlsxNoDisponibleError("Falta openpyxl (pip install -r requirements.txt).") from e

    fill_cab = PatternFill("solid", fgColor=_hex(M.VERDE))
    fill_suave = PatternFill("solid", fgColor=_hex(M.VERDE_SUAVE))
    fill_cebra = PatternFill("solid", fgColor=_hex(M.CEBRA))
    fill_aviso = PatternFill("solid", fgColor=_hex(M.AVISO_FONDO))
    f_cab = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    f_titulo = Font(name="Calibri", bold=True, size=16, color=_hex(M.TINTA))
    f_sub = Font(name="Calibri", size=10, color=_hex(M.GRIS))
    f_negrita = Font(name="Calibri", bold=True, size=10)
    f_normal = Font(name="Calibri", size=10)
    f_alerta = Font(name="Calibri", bold=True, size=10, color=_hex(M.COLOR_NIVEL["Crítico"]))
    borde = Border(bottom=Side(style="thin", color=_hex(M.LINEA)))
    envolver = Alignment(wrap_text=True, vertical="top")
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    wb.properties.title = f"{R.TITULO} · {inf.empresa}"
    wb.properties.subject = R.TITULO
    wb.properties.creator = "ComplianceIA (Therion Labs)"
    wb.properties.keywords = f"RoPA, {inf.codigo or 'vista previa'}, versión {inf.version or '-'}"
    wb.properties.description = inf.aviso.pie

    def poner(ws, fila: int, col: int, valor, font=None, fill=None, alin=None, borde_=None):
        celda = ws.cell(row=fila, column=col, value=ILLEGAL_CHARACTERS_RE.sub("", valor) if isinstance(valor, str) else valor)
        if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@"):
            celda.data_type = "s"          # nunca una fórmula: texto tal cual
        if font:
            celda.font = font
        if fill:
            celda.fill = fill
        celda.alignment = alin or envolver
        if borde_:
            celda.border = borde_
        return celda

    def alto_fila(ws, fila: int, valores: list, cols_w: list[float]):
        lineas = 1
        for v, w in zip(valores, cols_w):
            if v is None:
                continue
            por_linea = max(8, int(w * 1.15))
            lineas = max(lineas, sum(max(1, math.ceil(len(parte) / por_linea)) for parte in str(v).split("\n")))
        ws.row_dimensions[fila].height = min(409, 14.5 * lineas + 3)

    def preparar(ws, titulo: str, cols_w: list[float], horizontal: bool = True) -> int:
        for i, w in enumerate(cols_w, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape" if horizontal else "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.oddFooter.left.text = f"ComplianceIA · {inf.codigo or 'Vista previa'} · RoPA versión {inf.version or '-'}"
        ws.oddFooter.left.size = 8
        ws.oddFooter.center.text = inf.aviso.pie
        ws.oddFooter.center.size = 7
        ws.oddFooter.right.text = "Página &P de &N"
        ws.oddFooter.right.size = 8
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(cols_w))
        poner(ws, 1, 1, titulo, f_titulo, alin=Alignment(vertical="center"))
        ws.row_dimensions[1].height = 26
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(cols_w))
        poner(ws, 2, 1, f"{inf.empresa} · código {inf.codigo or 'vista previa'} · versión {inf.version or '-'} · "
                        f"emitido el {M.fecha_local(inf.generado)} (hora de Chile)", f_sub, alin=Alignment(vertical="center"))
        return 4

    def tabla(ws, fila: int, titulos: list[str], datos: list[list], cols_w: list[float], alertas=()) -> int:
        for i, t in enumerate(titulos, start=1):
            poner(ws, fila, i, t, f_cab, fill_cab, centro)
        ws.row_dimensions[fila].height = 30
        inicio = fila
        for n, valores in enumerate(datos):
            fila += 1
            for i, v in enumerate(valores, start=1):
                c = poner(ws, fila, i, v, f_normal, fill_cebra if n % 2 else None, envolver, borde)
                if (n, i) in alertas:
                    c.font = f_alerta
            alto_fila(ws, fila, valores, cols_w)
        if datos:
            ws.auto_filter.ref = f"A{inicio}:{get_column_letter(len(titulos))}{fila}"
        ws.freeze_panes = ws.cell(row=inicio + 1, column=1)
        return fila + 1

    def ficha(ws, fila: int, pares: list[tuple[str, str]], cols_w: list[float]) -> int:
        for etiqueta, valor in pares:
            poner(ws, fila, 1, etiqueta, f_negrita, fill_suave, borde_=borde)
            poner(ws, fila, 2, valor, f_normal, borde_=borde)
            alto_fila(ws, fila, [etiqueta, valor], cols_w)
            fila += 1
        return fila

    def junto(lineas: list[str]) -> str:
        return "\n".join(lineas)

    r = inf.resumen
    d = inf.datos

    # ================================================================ Portada
    ws = wb.active
    ws.title = "Portada"
    w = [30, 100]
    fila = preparar(ws, R.TITULO, w, horizontal=False)
    incluye = []
    if "responsable" in inf.partes:
        incluye.append(f"Como responsable: {r['responsable']} actividad(es)")
    if "encargado" in inf.partes:
        incluye.append(f"Como encargado: {r['encargado']} actividad(es) de {r['organizaciones']} organización(es)")
    hojas = ["Organización"] + [R.NOMBRE_PARTE[x] for x in inf.partes] + ["Transferencias", "Aviso legal"]
    fila = ficha(ws, fila, [
        ("Empresa", inf.empresa), ("RUT", inf.rut or "—"), ("Código", inf.codigo or "Vista previa (sin código)"),
        ("Versión del informe", f"N.º {inf.version}" if inf.version else "—"),
        ("Emitido el", f"{M.fecha_local(inf.generado)} (hora de Chile)"), ("Idioma", "Español"),
        ("Incluye", "\n".join(incluye) or "Sin actividades vigentes"),
        ("Hojas", " · ".join(hojas)),
    ], w)
    fila += 1
    poner(ws, fila, 1, inf.aviso.titulo, f_negrita, fill_aviso)
    poner(ws, fila, 2, inf.aviso.pie + " (ver la hoja Aviso legal).", f_normal, fill_aviso)

    # ================================================================ Organización
    ws = wb.create_sheet("Organización")
    w = [34, 90]
    fila = preparar(ws, "Organización", w, horizontal=False)
    pares = [("Razón social", inf.empresa), ("RUT", inf.rut or "—"), ("Dirección", d.get("direccion") or "Sin indicar"),
             ("Correo de contacto", d.get("correo") or "Sin indicar")]
    if d.get("telefono"):
        pares.append(("Teléfono", d["telefono"]))
    pares.append(("Delegado de protección de datos", R.texto_delegado(inf)))
    fila = ficha(ws, fila, pares, w)
    if "encargado" in inf.partes and inf.encargado:
        fila += 1
        poner(ws, fila, 1, "Organizaciones por cuenta de las cuales actúa como encargado", f_negrita)
        fila += 1
        for g in inf.encargado:
            fila = ficha(ws, fila, [(g.nombre, junto(R.texto_mandante(g)[1:]))], w)

    # ================================================================ Como responsable
    if "responsable" in inf.partes:
        ws = wb.create_sheet(R.NOMBRE_PARTE["responsable"])
        titulos = ["N.º", "Actividad", "Área", "Versión"] + [t for k, t in R.CAMPOS_RESPONSABLE if k != "responsable"]
        w = [6, 30, 22, 10, 40, 30, 36, 36, 40, 40, 44]
        fila = preparar(ws, R.TITULO_PARTE["responsable"], w)
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=len(w))
        poner(ws, 3, 1, "Responsable: " + " · ".join(R.texto_contacto_empresa(inf))
              + f" · Delegado de protección de datos: {R.texto_delegado(inf)}", f_sub)
        datos = []
        for a in inf.responsable:
            campos = {k: lineas for k, _, lineas in R.campos_responsable(inf, a)}
            datos.append([a.numero, a.nombre, a.area or "—", f"N.º {a.version}" if a.version else "—"]
                         + [junto(campos[k]) for k, _ in R.CAMPOS_RESPONSABLE if k != "responsable"])
        tabla(ws, fila, titulos, datos, w)

    # ================================================================ Como encargado
    if "encargado" in inf.partes:
        ws = wb.create_sheet(R.NOMBRE_PARTE["encargado"])
        titulos = (["N.º", "Actividad", "Área", "Versión", "Por cuenta de", "Contacto de la organización"]
                   + [t for k, t in R.CAMPOS_ENCARGADO if k not in ("encargado", "mandante")])
        w = [6, 30, 22, 10, 26, 36, 44, 40, 44]
        fila = preparar(ws, R.TITULO_PARTE["encargado"], w)
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=len(w))
        poner(ws, 3, 1, "Encargado: " + " · ".join(R.texto_contacto_empresa(inf))
              + f" · Delegado de protección de datos: {R.texto_delegado(inf)}", f_sub)
        datos = []
        for g in inf.encargado:
            for a in g.actividades:
                campos = {k: lineas for k, _, lineas in R.campos_encargado(inf, g, a)}
                datos.append([a.numero, a.nombre, a.area or "—", f"N.º {a.version}" if a.version else "—", g.nombre,
                              junto(R.texto_mandante(g)[1:])]
                             + [junto(campos[k]) for k, _ in R.CAMPOS_ENCARGADO if k not in ("encargado", "mandante")])
        tabla(ws, fila, titulos, datos, w)

    # ================================================================ Transferencias
    ws = wb.create_sheet("Transferencias")
    w = [34, 18, 32, 20, 34]
    fila = preparar(ws, "Transferencias internacionales", w)
    trans = inf.transferencias
    if trans:
        alertas = {(n, 5) for n, t in enumerate(trans) if not t["con_garantia"]}
        tabla(ws, fila, ["Actividad", "Rol", "Destino", "País", "Garantía"],
              [[t["actividad"], R.NOMBRE_PARTE[t["rol"]], t["destino"], t["pais"], t["garantia"]] for t in trans], w,
              alertas)
    else:
        poner(ws, fila, 1, "Los datos de las actividades incluidas no salen de Chile.", f_normal)

    # ================================================================ Aviso legal
    ws = wb.create_sheet("Aviso legal")
    w = [110]
    fila = preparar(ws, inf.aviso.titulo, w, horizontal=False)
    for parrafo in inf.aviso.texto:
        poner(ws, fila, 1, parrafo, f_normal, fill_aviso)
        alto_fila(ws, fila, [parrafo], w)
        fila += 1
    poner(ws, fila + 1, 1, f"Versión del aviso: {inf.aviso.version}.", f_sub)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
