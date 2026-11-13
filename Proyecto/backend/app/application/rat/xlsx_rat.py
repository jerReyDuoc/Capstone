"""
HU-36 criterio 3 · El informe del Registro de Actividades de Tratamiento en una planilla Excel (XLSX).

Mismo contenido que el PDF (los dos leen InformeRat de app/application/rat/informe.py), pensado para
filtrar, ordenar o cargarlo en otra herramienta:

  Portada            identificación (código verificable, versión del RAT, fecha, estado) y aviso legal.
  Resumen            indicadores, estado del registro y bases de licitud.
  Actividades        el RAT: una fila por actividad con sus 13 campos, estado, versión y riesgo.
  Datos y plazos     una fila por categoría de datos de cada actividad, con su plazo de conservación.
  Destinatarios      terceros que reciben datos, su rol, país y contrato.
  Transferencias     envíos fuera de Chile y su garantía.
  Decisiones         decisiones automatizadas y perfilamiento.
  Matriz de riesgos  mapa de calor 5 × 5 y el detalle por actividad.
  Verificación       huella del registro y de cada versión incluida.

Borrador (criterio 4): franja roja "BORRADOR" al inicio de cada hoja y en el encabezado de impresión.
Seguridad: ningún texto se escribe como fórmula (inyección en planillas, OWASP) y se quitan los
caracteres de control que Excel no admite.
"""
from __future__ import annotations

import io
import math

from app.application.informes import motor_pdf as M
from app.application.rat import informe as I
from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat
from app.domain.rat import riesgos as rg

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class XlsxNoDisponibleError(Exception):
    pass


def _sin_hash(color: str) -> str:
    return color.lstrip("#").upper()


def generar_xlsx_rat(inf: I.InformeRat) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise XlsxNoDisponibleError("Falta openpyxl (pip install -r requirements.txt).") from e

    verde = _sin_hash(M.VERDE)
    fill_cab = PatternFill("solid", fgColor=verde)
    fill_suave = PatternFill("solid", fgColor=_sin_hash(M.VERDE_SUAVE))
    fill_cebra = PatternFill("solid", fgColor=_sin_hash(M.CEBRA))
    fill_borrador = PatternFill("solid", fgColor=_sin_hash(M.ALERTA_FONDO))
    fill_aviso = PatternFill("solid", fgColor=_sin_hash(M.AVISO_FONDO))
    f_cab = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    f_titulo = Font(name="Calibri", bold=True, size=16, color=_sin_hash(M.TINTA))
    f_sub = Font(name="Calibri", size=10, color=_sin_hash(M.GRIS))
    f_negrita = Font(name="Calibri", bold=True, size=10)
    f_normal = Font(name="Calibri", size=10)
    f_borrador = Font(name="Calibri", bold=True, size=11, color=_sin_hash(M.ALERTA_BORDE))
    linea = Side(style="thin", color=_sin_hash(M.LINEA))
    borde = Border(bottom=linea)
    envolver = Alignment(wrap_text=True, vertical="top")
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    wb.properties.title = f"Registro de Actividades de Tratamiento · {inf.empresa}"
    wb.properties.subject = "Registro de Actividades de Tratamiento (Ley N.º 21.719)"
    wb.properties.creator = "ComplianceIA (Therion Labs)"
    wb.properties.keywords = f"RAT, {inf.codigo or 'vista previa'}, versión {inf.version_rat or '-'}"
    wb.properties.description = inf.aviso.pie

    def limpio(v):
        if isinstance(v, str):
            return ILLEGAL_CHARACTERS_RE.sub("", v)
        return v

    def poner(ws, fila: int, col: int, valor, font=None, fill=None, alin=None, borde_=None):
        celda = ws.cell(row=fila, column=col, value=limpio(valor))
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

    def anchos(ws, valores: list[float]):
        for i, w in enumerate(valores, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    def alto_fila(ws, fila: int, valores: list, cols_w: list[float]):
        lineas = 1
        for v, w in zip(valores, cols_w):
            if v is None:
                continue
            texto = str(v)
            por_linea = max(8, int(w * 1.15))
            n = sum(max(1, math.ceil(len(parte) / por_linea)) for parte in texto.split("\n"))
            lineas = max(lineas, n)
        ws.row_dimensions[fila].height = min(409, 14.5 * lineas + 3)

    def preparar(ws, titulo: str, ancho_cols: list[float], horizontal: bool = True) -> int:
        """Encabezado común de la hoja; devuelve la primera fila libre."""
        anchos(ws, ancho_cols)
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape" if horizontal else "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True
        ws.oddFooter.left.text = f"ComplianceIA · {inf.codigo or 'Vista previa'} · RAT versión {inf.version_rat or '-'}"
        ws.oddFooter.left.size = 8
        ws.oddFooter.right.text = "Página &P de &N"
        ws.oddFooter.right.size = 8
        ws.oddFooter.center.text = inf.aviso.pie
        ws.oddFooter.center.size = 7
        fila = 1
        if inf.borrador:
            ws.oddHeader.center.text = "BORRADOR · no apto para presentación oficial"
            ws.oddHeader.center.color = _sin_hash(M.ALERTA_BORDE)
            ws.oddHeader.center.size = 11
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(ancho_cols))
            poner(ws, 1, 1, "BORRADOR · No apto para presentación oficial: hay actividades que no están vigentes "
                            "(ver la hoja Portada).", f_borrador, fill_borrador, Alignment(vertical="center"))
            ws.row_dimensions[1].height = 22
            fila = 2
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=len(ancho_cols))
        poner(ws, fila, 1, titulo, f_titulo, alin=Alignment(vertical="center"))
        ws.row_dimensions[fila].height = 26
        ws.merge_cells(start_row=fila + 1, start_column=1, end_row=fila + 1, end_column=len(ancho_cols))
        poner(ws, fila + 1, 1, f"{inf.empresa} · código {inf.codigo or 'vista previa'} · versión del RAT "
                               f"{inf.version_rat or '-'} · emitido el {M.fecha_local(inf.generado)} (hora de Chile)",
              f_sub, alin=Alignment(vertical="center"))
        return fila + 3

    def cabecera(ws, fila: int, titulos: list[str]):
        for i, t in enumerate(titulos, start=1):
            poner(ws, fila, i, t, f_cab, fill_cab, centro)
        ws.row_dimensions[fila].height = 30

    def filas_tabla(ws, fila: int, datos: list[list], cols_w: list[float], colores: dict | None = None) -> int:
        for n, valores in enumerate(datos):
            for i, v in enumerate(valores, start=1):
                c = poner(ws, fila, i, v, f_normal, fill_cebra if n % 2 else None, envolver, borde)
                if colores and (fila, i) in colores:
                    c.font = colores[(fila, i)]
            alto_fila(ws, fila, valores, cols_w)
            fila += 1
        return fila

    def tabla(ws, fila: int, titulos: list[str], datos: list[list], cols_w: list[float], filtro=True,
              colores=None) -> int:
        cabecera(ws, fila, titulos)
        inicio = fila
        fin = filas_tabla(ws, fila + 1, datos, cols_w, colores)
        if filtro and datos:
            ws.auto_filter.ref = f"A{inicio}:{get_column_letter(len(titulos))}{fin - 1}"
        ws.freeze_panes = ws.cell(row=inicio + 1, column=1)
        return fin

    acts = list(inf.actividades)
    riesgo_de = {x.actividad_id: x for x in inf.riesgos}
    r = inf.resumen

    # ================================================================ Portada
    ws = wb.active
    ws.title = "Portada"
    w = [30, 100]
    fila = preparar(ws, "Registro de Actividades de Tratamiento", w, horizontal=False)
    datos = [
        ("Empresa", inf.empresa), ("RUT", inf.rut or "—"), ("Rubro", inf.rubro or "Sin rubro informado"),
        ("Código verificable", inf.codigo or "Vista previa (sin código)"),
        ("Versión del RAT", f"N.º {inf.version_rat}" if inf.version_rat else "—"),
        ("Estado del informe", inf.estado_texto),
        ("Emitido el", f"{M.fecha_local(inf.generado)} (hora de Chile)"),
        ("Actividades incluidas", f"{r['actividades']}" + (f" ({r['archivadas_excluidas']} archivada(s) no se incluyen)"
                                                          if r["archivadas_excluidas"] else "")),
        ("Huella del registro", inf.huella),
        # HU-40: la marca de la revisión interna de esta versión
        ("Uso previsto", I.USO_PREVISTO),
    ]
    if inf.revision_aplica:
        datos.insert(-1, ("Revisión interna", (f"{inf.revision.texto} (revisión N.º {inf.revision.numero})"
                                               if inf.revision else
                                               "Esta versión todavía no tiene una revisión interna registrada.")))
    for etiqueta, valor in datos:
        poner(ws, fila, 1, etiqueta, f_negrita, fill_suave, borde_=borde)
        c = poner(ws, fila, 2, valor, f_normal, borde_=borde)
        if etiqueta == "Estado del informe" and inf.borrador:
            c.font = f_borrador
        alto_fila(ws, fila, [etiqueta, valor], w)
        fila += 1
    fila += 1
    if inf.borrador:
        poner(ws, fila, 1, "Por qué es un borrador", f_borrador, fill_borrador)
        poner(ws, fila, 2, "\n".join(list(inf.motivos_borrador) + [inf.nota_borrador]), f_normal, fill_borrador)
        alto_fila(ws, fila, ["", "\n".join(inf.motivos_borrador) + "\nx"], w)
        fila += 2
    poner(ws, fila, 1, inf.aviso.titulo, f_negrita, fill_aviso)
    poner(ws, fila, 2, "\n\n".join(inf.aviso.texto) + f"\n\nVersión del aviso: {inf.aviso.version}.", f_normal, fill_aviso)
    alto_fila(ws, fila, ["", "\n\n".join(inf.aviso.texto) + "\n\nx"], w)
    fila += 2
    poner(ws, fila, 1, "Contenido", f_negrita)
    poner(ws, fila, 2, "Resumen · Actividades (el registro) · Datos y plazos · Destinatarios · Transferencias · "
                       "Decisiones · Matriz de riesgos · Verificación", f_sub)

    # ================================================================ Resumen
    ws = wb.create_sheet("Resumen")
    w = [42, 14, 70]
    fila = preparar(ws, "Resumen ejecutivo", w, horizontal=False)
    indicadores = [
        ["Actividades incluidas", r["actividades"], f"{r['por_estado']['vigente']} vigentes, "
                                                    f"{r['por_estado']['en_revision']} en revisión y "
                                                    f"{r['por_estado']['borrador']} en borrador"],
        ["Actividades sin versión vigente", r["sin_version_vigente"], "Se informan con su contenido actual"],
        ["Actividades con datos sensibles", r["con_sensibles"], ", ".join(r["categorias_sensibles"]) or "—"],
        ["Actividades con datos de niños, niñas o adolescentes", r["con_nna"], ""],
        ["Transferencias internacionales", r["transferencias"],
         (f"{r['transferencias_sin_garantia']} sin garantía · destinos: " + ", ".join(r["paises_destino"]))
         if r["transferencias"] else "Los datos no salen de Chile"],
        ["Actividades con decisiones automatizadas", r["con_decisiones"],
         f"{r['con_perfilamiento']} con perfilamiento · {r['decisiones_sin_revision_humana']} sin revisión humana "
         "confirmada" if r["con_decisiones"] else "Ninguna"],
        ["Terceros destinatarios", r["terceros"], f"{r['terceros_sin_contrato']} sin contrato confirmado"],
        ["Actividades en que la empresa es encargada", r["como_encargado"], ""],
        ["Actividades con riesgo alto o crítico", r["riesgos_altos"],
         " · ".join(f"{n}: {r['riesgos'][n]}" for n in reversed(rg.NIVELES))],
    ]
    fila = tabla(ws, fila, ["Indicador", "Valor", "Detalle"], indicadores, w, filtro=False) + 1
    fila = tabla(ws, fila, ["Base de licitud", "Actividades", ""],
                 [[k, v, ""] for k, v in r["bases_licitud"].items()], w, filtro=False)
    ws.freeze_panes = None

    # ================================================================ Actividades (el RAT)
    ws = wb.create_sheet("Actividades")
    titulos_campos = [t for _, t, _ in I.campos_legibles(acts[0])] if acts else []
    cols = (["N.º", "Actividad", "Área responsable", "Estado", "Versión informada", "Fecha de la versión",
             "Observación", "Descripción"] + titulos_campos + ["Riesgo", "Puntaje (de 25)", "Huella de la versión"])
    w = [6, 30, 22, 13, 11, 14, 32, 40] + [40] * len(titulos_campos) + [11, 10, 30]
    fila = preparar(ws, "Registro de Actividades de Tratamiento", w)
    datos, colores = [], {}
    for n, a in enumerate(acts):
        rv = riesgo_de.get(a.id)
        datos.append([
            a.numero, a.nombre, a.contenido.get("area") or "—", a.estado_nombre,
            f"N.º {a.version}" if a.version else "Sin versión vigente",
            M.fecha_local(a.fecha_version, con_hora=False) if a.fecha_version else "—",
            a.pendiente or ("Faltan: " + ", ".join(a.faltantes) if a.faltantes else ""),
            a.contenido.get("descripcion") or "",
            *[texto for _, _, texto in I.campos_legibles(a)],
            rv.nivel if rv else "—", rv.puntaje if rv else None, a.huella_version or "—",
        ])
        if rv:
            colores[(fila + 1 + n, len(cols) - 2)] = Font(name="Calibri", bold=True, size=10,
                                                         color=_sin_hash(M.COLOR_NIVEL[rv.nivel]))
        if a.pendiente:
            colores[(fila + 1 + n, 4)] = Font(name="Calibri", bold=True, size=10, color=_sin_hash(M.AVISO_BORDE))
    tabla(ws, fila, cols, datos, w, colores=colores)
    ws.freeze_panes = ws.cell(row=fila + 1, column=3)

    # ================================================================ Datos y plazos
    ws = wb.create_sheet("Datos y plazos")
    w = [6, 30, 32, 10, 9, 10, 36, 36]
    fila = preparar(ws, "Categorías de datos y plazos de conservación", w)
    datos = []
    for a in acts:
        plazos = {p["categoria"]: p for p in a.contenido.get("plazos") or []}
        for t in a.mapa.get("tipos_datos") or []:
            pl = plazos.get(t["codigo"], {})
            datos.append([a.numero, a.nombre, t.get("nombre") or cat_mapa.nombre_dato(t["codigo"]),
                          "Sí" if t.get("sensible") else "No", pl.get("plazo"),
                          cat.nombre(cat.UNIDADES_POR_CODIGO, pl.get("unidad")) or "",
                          cat.nombre(cat.INICIOS_POR_CODIGO, pl.get("desde")) or "",
                          pl.get("fundamento") or ("Sin plazo definido" if not pl.get("plazo") else "")])
    tabla(ws, fila, ["N.º", "Actividad", "Categoría de datos", "Sensible", "Plazo", "Unidad", "Desde",
                     "Fundamento"], datos, w)

    # ================================================================ Destinatarios
    ws = wb.create_sheet("Destinatarios")
    w = [6, 30, 30, 26, 16, 22]
    fila = preparar(ws, "Terceros destinatarios", w)
    datos = []
    for a in acts:
        terceros = a.mapa.get("terceros") or []
        if not terceros:
            datos.append([a.numero, a.nombre, "No se comunican a terceros" if a.contenido.get("sin_destinatarios")
                          else "Sin indicar", "", "", ""])
        for t in terceros:
            requiere = t.get("rol_tercero") in cat_mapa.ROLES_CON_CONTRATO
            datos.append([a.numero, a.nombre, t.get("nombre", "?"),
                          cat_mapa.etiqueta("rol", t.get("rol_tercero")) if t.get("rol_tercero") else "Sin indicar",
                          cat_mapa.nombre_pais(t.get("pais")) if t.get("pais") else "Sin indicar",
                          ("Firmado" if t.get("contrato_firmado") is True else "Sin contrato confirmado")
                          if requiere else "No requiere"])
    tabla(ws, fila, ["N.º", "Actividad", "Tercero", "Rol", "País", "Contrato de tratamiento"], datos, w)

    # ================================================================ Transferencias
    ws = wb.create_sheet("Transferencias")
    w = [6, 30, 36, 18, 34, 14]
    fila = preparar(ws, "Transferencias internacionales", w)
    datos = [[a.numero, a.nombre, t.get("nombre"), t.get("pais_nombre") or cat_mapa.nombre_pais(t.get("pais_destino")),
              t.get("garantia_nombre") or "Sin garantía registrada", "Sí" if t.get("garantia_valida") else "No"]
             for a in acts for t in a.transferencias]
    if not datos:
        datos = [["", "Los datos de las actividades del registro no salen de Chile.", "", "", "", ""]]
    tabla(ws, fila, ["N.º", "Actividad", "Envío", "País de destino", "Garantía", "Garantía válida"], datos, w)

    # ================================================================ Decisiones
    ws = wb.create_sheet("Decisiones")
    w = [6, 30, 20, 50, 40, 18]
    fila = preparar(ws, "Decisiones automatizadas y perfilamiento", w)
    datos = []
    for a in acts:
        d = a.decisiones
        if not d.get("existe"):
            continue
        rev = d.get("intervencion_humana")
        datos.append([a.numero, a.nombre, "Perfilamiento" if d.get("perfilamiento") else "Decisión automatizada",
                      d.get("logica") or "Sin describir", d.get("consecuencias") or "",
                      "Sí" if rev is True else "No" if rev is False else "Sin confirmar"])
    if not datos:
        datos = [["", "Ninguna actividad toma decisiones automatizadas ni arma perfiles.", "", "", "", ""]]
    tabla(ws, fila, ["N.º", "Actividad", "Tipo", "Lógica", "Efectos para las personas", "Revisión humana"], datos, w)

    # ================================================================ Matriz de riesgos
    ws = wb.create_sheet("Matriz de riesgos")
    w = [6, 30, 13, 13, 13, 13, 13, 50, 60, 40]
    fila = preparar(ws, "Matriz de riesgos (probabilidad × impacto)", w)
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=len(w))
    poner(ws, fila, 1, rg.METODOLOGIA, f_sub)
    ws.row_dimensions[fila].height = 48
    fila += 2
    celdas = rg.mapa_calor(list(inf.riesgos))
    poner(ws, fila, 2, "Probabilidad \\ Impacto", f_negrita, alin=centro)
    for i in range(5):
        poner(ws, fila, 3 + i, f"{i + 1} · {rg.ETIQUETA_IMPACTO[i + 1]}", f_negrita, fill_suave, centro)
    for fi in range(5):
        prob = 5 - fi
        fila_x = fila + 1 + fi
        poner(ws, fila_x, 2, f"{prob} · {rg.ETIQUETA_PROBABILIDAD[prob]}", f_negrita, fill_suave, centro)
        for co in range(5):
            niv = rg.nivel_de(prob * (co + 1))
            n = celdas[fi][co]
            poner(ws, fila_x, 3 + co, n or "", Font(name="Calibri", bold=True, size=13,
                                                    color=_sin_hash(M.COLOR_NIVEL[niv])),
                  PatternFill("solid", fgColor=_sin_hash(M.FONDO_NIVEL[niv])), centro,
                  Border(left=Side(style="thin", color="FFFFFF"), right=Side(style="thin", color="FFFFFF"),
                         top=Side(style="thin", color="FFFFFF"), bottom=Side(style="thin", color="FFFFFF")))
        ws.row_dimensions[fila_x].height = 26
    fila += 7
    conteo = rg.conteo_niveles(list(inf.riesgos))
    poner(ws, fila, 2, "Actividades por nivel: " + " · ".join(f"{n}: {conteo[n]}" for n in reversed(rg.NIVELES)),
          f_negrita)
    fila += 2
    datos, colores = [], {}
    numero_de = {a.id: a.numero for a in acts}
    for n, rv in enumerate(inf.riesgos):
        datos.append([numero_de.get(rv.actividad_id), rv.nombre, rv.probabilidad, rv.impacto, rv.puntaje, rv.nivel,
                      f"Probabilidad {rg.ETIQUETA_PROBABILIDAD[rv.probabilidad].lower()}, impacto "
                      f"{rg.ETIQUETA_IMPACTO[rv.impacto].lower()}", "\n".join(f"• {f.titulo}: {f.detalle}" for f in rv.factores) or "Sin factores relevantes",
                      "\n".join(f"• {t}" for t in rv.tratamientos) or "Mantener los controles actuales.",
                      # HU-38: evaluación de impacto recomendada y por qué
                      ("Recomendada: " + " ".join(rv.motivos_pia)) if rv.requiere_pia else "No requerida"])
        colores[(fila + 1 + n, 6)] = Font(name="Calibri", bold=True, size=10, color=_sin_hash(M.COLOR_NIVEL[rv.nivel]))
    tabla(ws, fila, ["N.º", "Actividad", "Probabilidad", "Impacto", "Puntaje", "Nivel", "Lectura", "Factores",
                     "Tratamiento sugerido", "Evaluación de impacto"], datos, w, colores=colores)
    ws.freeze_panes = None

    # ================================================================ Verificación
    ws = wb.create_sheet("Verificación")
    w = [6, 40, 18, 70]
    fila = preparar(ws, "Verificación del informe", w, horizontal=False)
    for etiqueta, valor in (("Código verificable", inf.codigo or "Vista previa"),
                            ("Versión del RAT", f"N.º {inf.version_rat}" if inf.version_rat else "—"),
                            ("Huella del registro (SHA-256)", inf.huella),
                            *((("Revisión interna", inf.revision.texto if inf.revision else "Sin revisión interna"),)
                              if inf.revision_aplica else ())):
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=2)
        poner(ws, fila, 1, etiqueta, f_negrita, fill_suave, borde_=borde)
        ws.merge_cells(start_row=fila, start_column=3, end_row=fila, end_column=4)
        poner(ws, fila, 3, valor, f_normal, borde_=borde)
        fila += 1
    fila += 1
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=4)
    poner(ws, fila, 1, "La huella resume lo que afirma el registro (la versión y el contenido de cada actividad), no la "
                       "fecha de emisión: dos informes con la misma huella dicen lo mismo. Quien reciba este documento "
                       "puede pedir a la empresa que confirme el código en ComplianceIA.", f_sub)
    ws.row_dimensions[fila].height = 44
    fila += 2
    tabla(ws, fila, ["N.º", "Actividad", "Versión", "Huella de la versión (SHA-256)"],
          [[a.numero, a.nombre, f"N.º {a.version}" if a.version else "Sin versión vigente", a.huella_version or "—"]
           for a in acts], w, filtro=False)
    ws.freeze_panes = None

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
