"""
HU-37 criterios 1, 2 y 4 · PDF del informe RoPA.

Se arma en el servidor con el motor de informes de HU-21 (app/application/informes/motor_pdf.py), desde
InformeRopa (app/application/ropa/informe.py), en A4 vertical:

  Portada                   empresa, código, versión, fecha de emisión, partes incluidas y el aviso legal.
  1. Organización           contacto de la empresa y delegado de protección de datos.
  2. Como responsable       una ficha por actividad con los campos del RoPA (si hay actividades).
  3. Como encargado         por cada organización mandante: su contacto y una ficha por actividad.
  4. Transferencias         todas las transferencias internacionales de las actividades incluidas.

El aviso legal va completo en la portada y en una línea al pie de todas las páginas.
"""
from __future__ import annotations

import io

from app.application.informes import motor_pdf as M
from app.application.ropa import informe as R

PdfNoDisponibleError = M.PdfNoDisponibleError
esc = M.esc


def _marcar(texto: str) -> str:
    t = esc(texto)
    return (t.replace("(sensible)", f'<font color="{M.SENSIBLE}"><b>(sensible)</b></font>')
             .replace("(NNA)", f'<font color="{M.NNA}"><b>(NNA)</b></font>'))


def _lineas(lineas: list[str]) -> str:
    if len(lineas) == 1:
        return _marcar(lineas[0])
    return "<br/>".join(f"• {_marcar(x)}" for x in lineas)


def generar_pdf_ropa(inf: R.InformeRopa) -> bytes:
    M.importar()
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    e = M.estilos()
    ancho = A4[0] - 30 * mm
    r = inf.resumen

    def p(texto, estilo=None):
        return Paragraph(texto, estilo or e.chico)

    def cab(*titulos):
        return [p(esc(t), e.cabecera) for t in titulos]

    def ficha_actividad(a: R.ActividadRopa, campos: list[tuple[str, str, list[str]]]) -> list:
        meta = []
        if a.area:
            meta.append(f"Área: {esc(a.area)}")
        if a.version:
            meta.append(f"Versión vigente N.º {a.version} del {M.fecha_local(a.fecha_version, False)}")
        bloque = [
            M.tabla([[p(f"{a.numero}. {esc(a.nombre)}", e.cabecera)]], [ancho], cebra=False,
                    extra=[("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]),
            Spacer(1, 3),
        ]
        if meta:
            bloque.append(p(" · ".join(meta), e.gris_chico))
            bloque.append(Spacer(1, 3))
        filas = [cab("Campo", "Contenido")]
        for _, titulo, lineas in campos:
            filas.append([p(f"<b>{esc(titulo)}</b>"), p(_lineas(lineas))])
        return [CondPageBreak(60 * mm), Spacer(1, 6), KeepTogether(bloque), M.tabla(filas, [ancho * 0.30, ancho * 0.70])]

    historia: list = []
    secciones = ["Organización"] + [R.TITULO_PARTE[x] for x in inf.partes] + ["Transferencias internacionales"]

    # ================================================================ portada
    historia += [
        p("ComplianceIA de Therion Labs · Protección de datos personales", e.gris_chico),
        Spacer(1, 3),
        p(esc(R.TITULO), e.h1),
        Spacer(1, 3),
        p(f"Actividades en que <b>{esc(inf.empresa)}</b> trata datos personales, en formato RoPA: responsable y "
          "delegado, finalidades, categorías de titulares y de datos, destinatarios, transferencias "
          "internacionales, plazos de supresión y medidas de seguridad.", e.gris),
        Spacer(1, 10),
    ]
    incluye = []
    if "responsable" in inf.partes:
        incluye.append(f"Como responsable: {r['responsable']} actividad(es)")
    if "encargado" in inf.partes:
        incluye.append(f"Como encargado: {r['encargado']} actividad(es) de {r['organizaciones']} organización(es)")
    celdas = [
        ("Empresa", esc(inf.empresa)),
        ("RUT", esc(inf.rut) if inf.rut else "—"),
        ("Código", esc(inf.codigo) if inf.codigo else "Vista previa (sin código)"),
        ("Versión del informe", f"N.º {inf.version}" if inf.version else "—"),
        ("Emitido el", M.fecha_local(inf.generado) + '<font size=7> (hora de Chile)</font>'),
        ("Idioma", "Español"),
    ]
    historia += [M.ficha(celdas, ancho, e), Spacer(1, 6)]
    historia.append(p("<b>Incluye:</b> " + esc(" · ".join(incluye) or "Sin actividades vigentes") + ".", e.chico))
    historia.append(Spacer(1, 8))
    historia.append(M.caja_aviso(inf.aviso, ancho, e))
    historia.append(Spacer(1, 10))
    historia.append(p("Contenido", e.h3))
    for i, t in enumerate(secciones, start=1):
        historia.append(p(f"{i}. {esc(t)}", e.chico))

    # ================================================================ 1. organización
    historia.append(PageBreak())
    n = 1
    historia.append(p(f"{n}. Organización", e.h2))
    d = inf.datos
    filas = [cab("Dato", "Contenido"),
             [p("<b>Razón social</b>"), p(esc(inf.empresa))],
             [p("<b>RUT</b>"), p(esc(inf.rut or "—"))],
             [p("<b>Dirección</b>"), p(esc(d.get("direccion") or "Sin indicar"))],
             [p("<b>Correo de contacto</b>"), p(esc(d.get("correo") or "Sin indicar"))]]
    if d.get("telefono"):
        filas.append([p("<b>Teléfono</b>"), p(esc(d["telefono"]))])
    filas.append([p("<b>Delegado de protección de datos</b>"), p(esc(R.texto_delegado(inf)))])
    historia.append(M.tabla(filas, [ancho * 0.30, ancho * 0.70]))

    # ================================================================ 2. como responsable
    if "responsable" in inf.partes:
        n += 1
        historia.append(CondPageBreak(90 * mm))
        historia.append(p(f"{n}. {R.TITULO_PARTE['responsable']}", e.h2))
        historia.append(p("Actividades en que la empresa decide para qué y cómo se tratan los datos.", e.gris_chico))
        for a in inf.responsable:
            historia += ficha_actividad(a, R.campos_responsable(inf, a))

    # ================================================================ 3. como encargado
    if "encargado" in inf.partes:
        n += 1
        historia.append(CondPageBreak(90 * mm))
        historia.append(p(f"{n}. {R.TITULO_PARTE['encargado']}", e.h2))
        historia.append(p("Actividades que la empresa realiza por cuenta de otras organizaciones, agrupadas por "
                          "organización.", e.gris_chico))
        for g in inf.encargado:
            historia.append(CondPageBreak(70 * mm))
            historia.append(Spacer(1, 6))
            historia.append(p(f"Por cuenta de {esc(g.nombre)}", e.h3))
            filas = [cab("Organización", "Contacto"),
                     [p(f"<b>{esc(g.nombre)}</b>"), p("<br/>".join(esc(x) for x in R.texto_mandante(g)[1:]))]]
            historia.append(M.tabla(filas, [ancho * 0.30, ancho * 0.70]))
            for a in g.actividades:
                historia += ficha_actividad(a, R.campos_encargado(inf, g, a))

    # ================================================================ 4. transferencias
    n += 1
    historia.append(CondPageBreak(60 * mm))
    historia.append(Spacer(1, 6))
    historia.append(p(f"{n}. Transferencias internacionales", e.h2))
    trans = inf.transferencias
    if trans:
        filas = [cab("Actividad", "Rol", "Destino", "País", "Garantía")]
        for t in trans:
            garantia = esc(t["garantia"])
            if not t["con_garantia"]:
                garantia = f'<font color="{M.COLOR_NIVEL["Crítico"]}"><b>{garantia}</b></font>'
            filas.append([p(esc(t["actividad"])), p(R.NOMBRE_PARTE[t["rol"]]), p(esc(t["destino"])), p(esc(t["pais"])),
                          p(garantia)])
        historia.append(M.tabla(filas, [ancho * w for w in (0.26, 0.15, 0.24, 0.13, 0.22)]))
    else:
        historia.append(p("Los datos de las actividades incluidas no salen de Chile.", e.gris))

    izquierda = f"ComplianceIA | {inf.codigo or 'Vista previa'} | RoPA versión {inf.version or '—'} | {inf.empresa[:60]}"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"{R.TITULO} · {inf.empresa}", author="ComplianceIA (Therion Labs)", subject=R.TITULO,
        keywords=f"RoPA, registro de actividades, {inf.codigo or 'vista previa'}, versión {inf.version or '-'}",
    )
    doc.build(historia, canvasmaker=M.lienzo(A4, inf.aviso.pie, izquierda))
    return buffer.getvalue()
