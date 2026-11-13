"""
HU-36 criterios 1, 2 y 4 · PDF del Registro de Actividades de Tratamiento.

Se arma en el servidor con el motor de informes de HU-21 (app/application/informes/motor_pdf.py),
desde InformeRat (app/application/rat/informe.py), en A4 vertical:

  1. Portada            empresa, código verificable, versión del RAT, fecha de emisión, estado
                        (oficial o borrador, con los motivos), uso previsto y el aviso legal completo.
  2. Resumen ejecutivo  actividades, datos sensibles, transferencias internacionales, decisiones
                        automatizadas, terceros y riesgos; estado del registro y bases de licitud.
  3. Actividades        índice con estado, versión, base de licitud y nivel de riesgo.
  4. Detalle            los 13 campos de cada actividad (los 11 del reglamento, medidas y rol), los
                        plazos de conservación por categoría y la huella de su versión vigente.
  5. Matriz de riesgos  mapa de calor 5 × 5 y el detalle de factores y tratamientos por actividad.
  6. Verificación       código, huella del registro y huella de cada versión incluida.

Borrador (criterio 4): marca de agua diagonal en todas las páginas, aviso en el encabezado de cada
página y el recuadro con los motivos en la portada.
"""
from __future__ import annotations

import io

from app.application.informes import motor_pdf as M
from app.application.rat import informe as I
from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat
from app.domain.rat import riesgos as rg

PdfNoDisponibleError = M.PdfNoDisponibleError
esc = M.esc


def nombre_archivo(inf: I.InformeRat, extension: str) -> str:
    """registro_actividades_v3_2026-11-12.pdf (con _borrador si lo es). Solo [A-Za-z0-9_.-]."""
    fecha = M.fecha_local(inf.generado, con_hora=False)
    dd, mm, aaaa = fecha.split("-")
    v = f"v{inf.version_rat}" if inf.version_rat else "vista-previa"
    return f"registro_actividades_{v}_{aaaa}-{mm}-{dd}{'_borrador' if inf.borrador else ''}.{extension}"


def _marcar_sensibles(texto: str) -> str:
    t = esc(texto)
    return (t.replace("(sensible)", f'<font color="{M.SENSIBLE}"><b>(sensible)</b></font>')
             .replace("(NNA)", f'<font color="{M.NNA}"><b>(NNA)</b></font>'))


def generar_pdf_rat(inf: I.InformeRat) -> bytes:
    M.importar()
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    c = colors.HexColor
    e = M.estilos()
    ancho = A4[0] - 30 * mm
    r = inf.resumen
    acts = list(inf.actividades)
    riesgo_de = {x.actividad_id: x for x in inf.riesgos}

    def p(texto, estilo=None):
        return Paragraph(texto, estilo or e.chico)

    def cab(*titulos):
        return [p(esc(t), e.cabecera) for t in titulos]

    def nivel(n: str) -> str:
        return f'<font color="{M.COLOR_NIVEL.get(n, M.GRIS)}"><b>{esc(n)}</b></font>'

    historia: list = []

    # ================================================================ 1. portada
    historia += [
        p("ComplianceIA de Therion Labs · Protección de datos personales", e.gris_chico),
        Spacer(1, 3),
        p("Registro de Actividades de Tratamiento", e.h1),
        Spacer(1, 3),
        p(f"Actividades en que <b>{esc(inf.empresa)}</b> trata datos personales, con la información que exigen la "
          "Ley N.º 21.719 y su reglamento: finalidades, datos, titulares, bases de licitud, destinatarios, "
          "transferencias internacionales, plazos de conservación, decisiones automatizadas y medidas de "
          "seguridad.", e.gris),
        Spacer(1, 10),
    ]
    if inf.borrador:
        historia += [M.caja_alerta(
            "BORRADOR: este informe no corresponde a una versión oficial del registro",
            list(inf.motivos_borrador) + [inf.nota_borrador], ancho, e), Spacer(1, 8)]

    estado = (f'<font color="{M.MARCA_AGUA}">Borrador</font>' if inf.borrador
              else f'<font color="{M.VERDE}">Oficial</font>')
    celdas = [
        ("Empresa", esc(inf.empresa)),
        ("RUT", esc(inf.rut) if inf.rut else "—"),
        ("Rubro", esc(inf.rubro) if inf.rubro else "Sin rubro informado"),
        ("Código verificable", esc(inf.codigo) if inf.codigo else "Vista previa (sin código)"),
        ("Versión del RAT", f"N.º {inf.version_rat}" if inf.version_rat else "—"),
        ("Estado del informe", estado),
        ("Emitido el", M.fecha_local(inf.generado) + '<font size=7> (hora de Chile)</font>'),
        ("Actividades incluidas", f"{r['actividades']}"
         + (f'<font size=7> · {r["archivadas_excluidas"]} archivada(s) no se incluyen</font>'
            if r["archivadas_excluidas"] else "")),
        ("Huella del registro", I.huella_legible(inf.huella)),
    ]
    historia += [M.ficha(celdas, ancho, e), Spacer(1, 6)]
    historia.append(p(f"<b>Uso previsto:</b> {esc(I.USO_PREVISTO)}.", e.gris_chico))
    historia.append(Spacer(1, 8))
    historia.append(M.caja_aviso(inf.aviso, ancho, e))
    historia.append(Spacer(1, 10))
    historia.append(p("Contenido", e.h3))
    for i, t in enumerate(("Resumen ejecutivo", "Actividades del registro", "Detalle por actividad",
                           "Matriz de riesgos", "Verificación del informe"), start=1):
        historia.append(p(f"{i}. {t}", e.chico))

    # ================================================================ 2. resumen ejecutivo
    historia.append(PageBreak())
    historia.append(p("1. Resumen ejecutivo", e.h2))
    historia.append(p("Las cifras consideran todas las actividades del registro que no están archivadas. Cada "
                      "actividad se informa con su última versión vigente; las que nunca han estado vigentes se "
                      "informan con su contenido actual.", e.gris_chico))
    historia.append(Spacer(1, 6))
    historia.append(M.indicadores([
        ("Actividades", str(r["actividades"]), f"{r['por_estado']['vigente']} vigentes", None),
        ("Con datos sensibles", str(r["con_sensibles"]), f"{r['con_nna']} con datos de NNA",
         M.SENSIBLE if r["con_sensibles"] else None),
        ("Transferencias internacionales", str(r["transferencias"]),
         f"{r['transferencias_sin_garantia']} sin garantía" if r["transferencias"] else "ninguna",
         M.INTERNACIONAL if r["transferencias_sin_garantia"] else None),
        ("Decisiones automatizadas", str(r["con_decisiones"]),
         f"{r['con_perfilamiento']} con perfilamiento" if r["con_decisiones"] else "ninguna", None),
        ("Terceros destinatarios", str(r["terceros"]),
         f"{r['terceros_sin_contrato']} sin contrato" if r["terceros_sin_contrato"] else "con contrato o no requieren",
         None),
        ("Riesgo alto o crítico", str(r["riesgos_altos"]), "actividades",
         M.COLOR_NIVEL["Crítico"] if r["riesgos_altos"] else None),
    ], ancho, e))
    historia.append(Spacer(1, 10))

    # Estado del registro (barra apilada)
    total = max(1, r["actividades"])
    tramos = [("Vigentes", r["por_estado"]["vigente"], M.VERDE), ("En revisión", r["por_estado"]["en_revision"], "#c48a1b"),
              ("En borrador", r["por_estado"]["borrador"], "#9aa7a1")]
    dib = Drawing(ancho - 12, 34)
    x = 0.0
    for _, n, color in tramos:
        if n:
            w = (ancho - 12) * n / total
            dib.add(Rect(x, 16, w, 12, fillColor=c(color), strokeColor=colors.white, strokeWidth=1))
            x += w
    xl = 0.0
    for nombre, n, color in tramos:
        dib.add(Rect(xl, 2, 8, 8, fillColor=c(color), strokeColor=None))
        etiqueta = f"{nombre}: {n}"
        dib.add(String(xl + 12, 3, etiqueta, fontName="Helvetica", fontSize=8, fillColor=c(M.TINTA)))
        xl += 22 + len(etiqueta) * 4.6
    dib.hAlign = "CENTER"
    historia += [p("Estado del registro", e.h3), dib, Spacer(1, 4)]

    # Datos sensibles
    historia.append(p("Datos sensibles y de niños, niñas y adolescentes", e.h3))
    con_sens = [a for a in acts if a.sensibles or a.incluye_nna]
    if con_sens:
        filas = [cab("Actividad", "Datos sensibles", "Titulares NNA", "Base para tratar los datos sensibles")]
        for a in con_sens:
            filas.append([
                p(f"<b>{a.numero}. {esc(a.nombre)}</b>"),
                p(", ".join(esc(t.get("nombre")) for t in a.sensibles) or "—"),
                p("Sí" if a.incluye_nna else "No"),
                p(esc(cat.nombre(cat.BASES_SENSIBLES_POR_CODIGO, a.contenido.get("base_sensibles")) or
                      ("Sin indicar" if a.sensibles else "No aplica")))])
        historia.append(M.tabla(filas, [ancho * w for w in (0.30, 0.34, 0.11, 0.25)]))
    else:
        historia.append(p("Ninguna actividad trata datos sensibles ni datos de niños, niñas o adolescentes.", e.gris))

    # Transferencias internacionales
    historia.append(p("Transferencias internacionales", e.h3))
    trans = [(a, t) for a in acts for t in a.transferencias]
    if trans:
        filas = [cab("Actividad", "Envío", "País de destino", "Garantía", "Estado")]
        for a, t in trans:
            ok = t.get("garantia_valida")
            filas.append([
                p(f"{a.numero}. {esc(a.nombre)}"), p(esc(t.get("nombre"))),
                p(esc(t.get("pais_nombre") or cat_mapa.nombre_pais(t.get("pais_destino")))),
                p(esc(t.get("garantia_nombre") or "Sin garantía registrada")),
                p(f'<font color="{M.COLOR_NIVEL["Bajo"] if ok else M.COLOR_NIVEL["Crítico"]}"><b>'
                  f'{"Con garantía" if ok else "Sin garantía válida"}</b></font>')])
        historia.append(M.tabla(filas, [ancho * w for w in (0.24, 0.27, 0.14, 0.21, 0.14)]))
        if r["paises_destino"]:
            historia.append(p("Países de destino: " + ", ".join(esc(x) for x in r["paises_destino"]) + ".", e.gris_chico))
    else:
        historia.append(p("Los datos de las actividades del registro no salen de Chile.", e.gris))

    # Decisiones automatizadas
    historia.append(p("Decisiones automatizadas y perfilamiento", e.h3))
    dec = [a for a in acts if a.tiene_decisiones]
    if dec:
        filas = [cab("Actividad", "Tipo", "Revisión humana", "Lógica y efectos")]
        for a in dec:
            d = a.decisiones
            rev = d.get("intervencion_humana")
            logica = esc(d.get("logica") or "Sin describir")
            if d.get("consecuencias"):
                logica += f"<br/><font color='{M.GRIS}'>Efectos: {esc(d['consecuencias'])}</font>"
            filas.append([
                p(f"{a.numero}. {esc(a.nombre)}"),
                p("Perfilamiento" if d.get("perfilamiento") else "Decisión automatizada"),
                p("Sí" if rev is True else f'<font color="{M.COLOR_NIVEL["Alto"]}"><b>{"No" if rev is False else "Sin confirmar"}</b></font>'),
                p(logica)])
        historia.append(M.tabla(filas, [ancho * w for w in (0.25, 0.16, 0.14, 0.45)]))
    else:
        historia.append(p("Ninguna actividad toma decisiones automatizadas ni arma perfiles de las personas.", e.gris))

    # Bases de licitud
    historia.append(p("Bases de licitud", e.h3))
    filas = [cab("Base de licitud", "Actividades")]
    for nombre, n in r["bases_licitud"].items():
        filas.append([p(esc(nombre)), p(str(n))])
    historia.append(M.tabla(filas, [ancho * 0.8, ancho * 0.2]))

    # ================================================================ 3. índice de actividades
    historia.append(CondPageBreak(70 * mm))
    historia.append(p("2. Actividades del registro", e.h2))
    historia.append(p("Cada actividad se detalla en la sección siguiente con el mismo número.", e.gris_chico))
    historia.append(Spacer(1, 4))
    filas = [cab("#", "Actividad", "Área responsable", "Estado", "Versión informada", "Base de licitud", "Riesgo")]
    for a in acts:
        rv = riesgo_de.get(a.id)
        estado_txt = esc(a.estado_nombre)
        if a.pendiente:
            estado_txt = f'<font color="{M.AVISO_BORDE}"><b>{estado_txt}</b></font>'
        filas.append([
            p(str(a.numero)), p(f"<b>{esc(a.nombre)}</b>"), p(esc(a.contenido.get("area") or "—")), p(estado_txt),
            p(f"N.º {a.version}<br/><font color='{M.GRIS}'>{M.fecha_local(a.fecha_version, False)}</font>"
              if a.version else f'<font color="{M.AVISO_BORDE}">Sin versión vigente</font>'),
            p(esc(cat.nombre(cat.BASES_POR_CODIGO, a.contenido.get("base_licitud")) or "Sin indicar")),
            p(nivel(rv.nivel) if rv else "—")])
    historia.append(M.tabla(filas, [ancho * w for w in (0.05, 0.27, 0.17, 0.13, 0.13, 0.15, 0.10)]))

    # ================================================================ 4. detalle por actividad
    historia.append(CondPageBreak(110 * mm))
    historia.append(p("3. Detalle por actividad", e.h2))
    historia.append(p("Los 11 campos mínimos del reglamento, las medidas de seguridad y el rol de la empresa. Los "
                      "sistemas, terceros, países y transferencias se toman del mapa de datos tal como estaban al "
                      "quedar vigente cada versión.", e.gris_chico))
    for a in acts:
        rv = riesgo_de.get(a.id)
        historia.append(CondPageBreak(70 * mm))
        historia.append(Spacer(1, 8))
        meta = [f"Estado: {esc(a.estado_nombre)}",
                (f"Versión vigente N.º {a.version} del {M.fecha_local(a.fecha_version, False)}" if a.version
                 else "Sin versión vigente")]
        if rv:
            meta.append(f"Riesgo {nivel(rv.nivel)} ({rv.puntaje} de 25)")
        bloque = [M.tabla([[p(f"{a.numero}. {esc(a.nombre)}", e.cabecera)]], [ancho], cebra=False,
                          extra=[("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]),
                  Spacer(1, 3), p(" · ".join(meta), e.chico)]
        if a.pendiente:
            bloque.append(p(f'<font color="{M.AVISO_BORDE}"><b>{esc(a.pendiente)}.</b></font>', e.chico))
        if a.faltantes:
            bloque.append(p(f'<font color="{M.COLOR_NIVEL["Crítico"]}">Datos obligatorios por completar: '
                            f'{esc(", ".join(a.faltantes))}.</font>', e.chico))
        desc = a.contenido.get("descripcion")
        area = a.contenido.get("area")
        if desc or area:
            bloque.append(p((f"<b>Área responsable:</b> {esc(area)}. " if area else "")
                            + (f"{esc(desc)}" if desc else ""), e.gris_chico))
        bloque.append(Spacer(1, 4))
        filas = [cab("Campo del registro", "Contenido")]
        for _, titulo, texto in I.campos_legibles(a, plazos_aparte=True):
            filas.append([p(f"<b>{esc(titulo)}</b>"), p(_marcar_sensibles(texto))])
        tabla_campos = M.tabla(filas, [ancho * 0.27, ancho * 0.73])
        historia.append(KeepTogether(bloque))
        historia.append(tabla_campos)
        plazos = a.contenido.get("plazos") or []
        if plazos:
            filas = [cab("Categoría de datos", "Plazo de conservación", "Fundamento")]
            for pl in plazos:
                sensible = cat_mapa.es_sensible(pl.get("categoria", ""))
                nombre = esc(cat_mapa.nombre_dato(pl.get("categoria", "")))
                filas.append([p(f'<font color="{M.SENSIBLE}"><b>{nombre}</b></font>' if sensible else nombre),
                              p(esc(I.texto_plazo(pl))), p(esc(pl.get("fundamento") or "—"))])
            historia.append(Spacer(1, 4))
            historia.append(M.tabla(filas, [ancho * w for w in (0.30, 0.35, 0.35)]))
        if a.huella_version:
            historia.append(p(f"Huella de la versión {a.version}: <b>{I.huella_legible(a.huella_version)}</b>",
                              e.gris_chico))

    # ================================================================ 5. matriz de riesgos
    historia.append(PageBreak())
    historia.append(p("4. Matriz de riesgos", e.h2))
    historia.append(p(esc(rg.METODOLOGIA), e.gris_chico))
    historia.append(Spacer(1, 8))
    celdas = rg.mapa_calor(list(inf.riesgos))
    lado_w, lado_h = 24 * mm, 12 * mm
    margen_izq, margen_inf = 30 * mm, 14 * mm
    dib = Drawing(margen_izq + 5 * lado_w + 4 * mm, margen_inf + 5 * lado_h + 8 * mm)
    for fila in range(5):              # fila 0 = probabilidad 5
        prob = 5 - fila
        y = margen_inf + (4 - fila) * lado_h
        dib.add(String(margen_izq - 4 * mm, y + lado_h / 2 - 3, f"{prob} · {rg.ETIQUETA_PROBABILIDAD[prob]}",
                       fontName="Helvetica", fontSize=7.5, fillColor=c(M.GRIS), textAnchor="end"))
        for col in range(5):
            imp = col + 1
            n_niv = rg.nivel_de(prob * imp)
            x0 = margen_izq + col * lado_w
            n = celdas[fila][col]
            dib.add(Rect(x0, y, lado_w, lado_h, fillColor=c(M.FONDO_NIVEL[n_niv]), strokeColor=colors.white,
                         strokeWidth=1.5))
            if n:
                dib.add(String(x0 + lado_w / 2, y + lado_h / 2 - 4, str(n), fontName="Helvetica-Bold", fontSize=12,
                               fillColor=c(M.COLOR_NIVEL[n_niv]), textAnchor="middle"))
    for col in range(5):
        imp = col + 1
        dib.add(String(margen_izq + col * lado_w + lado_w / 2, margen_inf - 9, f"{imp} · {rg.ETIQUETA_IMPACTO[imp]}",
                       fontName="Helvetica", fontSize=7.5, fillColor=c(M.GRIS), textAnchor="middle"))
    dib.add(String(margen_izq + 2.5 * lado_w, 2, "Impacto", fontName="Helvetica-Bold", fontSize=8.5,
                   fillColor=c(M.TINTA), textAnchor="middle"))
    dib.add(String(margen_izq - 4 * mm, margen_inf + 5 * lado_h + 3, "Probabilidad", fontName="Helvetica-Bold",
                   fontSize=8.5, fillColor=c(M.TINTA), textAnchor="end"))
    dib.hAlign = "CENTER"
    historia.append(dib)
    conteo = rg.conteo_niveles(list(inf.riesgos))
    historia.append(Spacer(1, 4))
    historia.append(p("Cada celda indica cuántas actividades tienen esa combinación. " + " · ".join(
        f'<font color="{M.COLOR_NIVEL[n]}"><b>{conteo[n]} {n.lower()}</b></font>' for n in reversed(rg.NIVELES)),
        e.chico))
    historia.append(Spacer(1, 8))
    filas = [cab("#", "Actividad", "Prob.", "Impacto", "Nivel", "Factores", "Tratamiento sugerido")]
    numero_de = {a.id: a.numero for a in acts}
    for rv in inf.riesgos:
        factores = "<br/>".join(f"• {esc(f.titulo)}" for f in rv.factores) or "Sin factores relevantes"
        trat = "<br/>".join(f"• {esc(t)}" for t in rv.tratamientos[:3]) or "Mantener los controles actuales."
        filas.append([p(str(numero_de.get(rv.actividad_id, ""))), p(f"<b>{esc(rv.nombre)}</b>"),
                      p(str(rv.probabilidad)), p(str(rv.impacto)), p(f"{nivel(rv.nivel)}<br/>{rv.puntaje}/25"),
                      p(factores), p(trat)])
    historia.append(M.tabla(filas, [ancho * w for w in (0.04, 0.18, 0.06, 0.08, 0.09, 0.24, 0.31)]))

    # HU-38: matriz de las actividades de mayor riesgo y evaluaciones de impacto recomendadas
    mayores = rg.matriz_mayor_riesgo(list(inf.riesgos))
    historia.append(Spacer(1, 10))
    historia.append(p(f"Actividades de mayor riesgo ({esc(rg.REFERENCIA_MATRIZ)})", e.h3))
    historia.append(p(esc(rg.METODOLOGIA_PIA), e.gris_chico))
    if mayores:
        filas = [cab("#", "Actividad", "Nivel", "Evaluación de impacto", "Por qué")]
        for rv in mayores:
            filas.append([p(str(numero_de.get(rv.actividad_id, ""))), p(f"<b>{esc(rv.nombre)}</b>"),
                          p(nivel(rv.nivel)), p("Recomendada" if rv.requiere_pia else "No requerida"),
                          p("<br/>".join(f"• {esc(m)}" for m in rv.motivos_pia) or "Riesgo alto o crítico.")])
        historia.append(M.tabla(filas, [ancho * w for w in (0.05, 0.27, 0.12, 0.16, 0.40)]))
    else:
        historia.append(p("Ninguna actividad del registro tiene un riesgo alto o crítico ni requiere una evaluación "
                          "de impacto.", e.chico))

    # ================================================================ 6. verificación
    historia.append(Spacer(1, 12))
    filas = [cab("#", "Actividad", "Versión", "Huella")]
    for a in acts:
        filas.append([p(str(a.numero)), p(esc(a.nombre)), p(f"N.º {a.version}" if a.version else "Sin versión vigente"),
                      p(I.huella_legible(a.huella_version) if a.huella_version else "—")])
    historia.append(KeepTogether([
        p("5. Verificación del informe", e.h2),
        p(f"Código <b>{esc(inf.codigo or 'vista previa')}</b> · versión del RAT <b>N.º {inf.version_rat or '—'}</b> · "
          f"huella del registro <b>{I.huella_legible(inf.huella)}</b>.", e.chico),
        p("La huella resume lo que afirma el registro (la versión y el contenido de cada actividad), no la fecha de "
          "emisión: dos informes con la misma huella dicen lo mismo. Quien reciba este documento puede pedir a la "
          "empresa que confirme el código en ComplianceIA (Registro de actividades › Informe › Verificar un código) y "
          "comparar la huella. El dígito final del código permite detectar un código mal transcrito.", e.gris_chico),
        Spacer(1, 4),
        M.tabla(filas, [ancho * w for w in (0.05, 0.47, 0.16, 0.32)]),
    ]))

    izquierda = (f"ComplianceIA | {inf.codigo or 'Vista previa'} | RAT versión {inf.version_rat or '—'} | "
                 f"{inf.empresa[:60]}")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"Registro de Actividades de Tratamiento · {inf.empresa}" + (" (borrador)" if inf.borrador else ""),
        author="ComplianceIA (Therion Labs)",
        subject="Registro de Actividades de Tratamiento (Ley N.º 21.719)",
        keywords=f"RAT, registro de actividades, {inf.codigo or 'vista previa'}, versión {inf.version_rat or '-'}",
    )
    doc.build(historia, canvasmaker=M.lienzo(A4, inf.aviso.pie, izquierda,
                                             marca_agua="BORRADOR" if inf.borrador else None))
    return buffer.getvalue()
