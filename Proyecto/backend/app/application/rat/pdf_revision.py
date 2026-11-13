"""
HU-40 · Informe de la revisión interna del registro (constancia) en PDF.

Se arma con el motor de informes de HU-21 (app/application/informes/motor_pdf.py), en A4 vertical:

  Portada         empresa, revisión, versión y huella del registro, quién revisó y cuándo, cifras de la revisión,
                  la conclusión, la declaración con espacio para firma y el alcance de la revisión.
  1. Resultado    por criterio: cuántos puntos cumplen, tienen advertencia o falla y cuántos se aceptaron.
  2. Actividades  cada actividad con sus puntos: resultado, detalle y decisión de quien revisó.
  3. Mapa         elementos y flujos del mapa de datos (resultado por criterio).
  4. Aceptados    los puntos aceptados con su justificación.
  5. Observaciones  lo observado, cuándo y cómo se cerró.
  6. Diferencias  qué cambió en el registro desde la revisión anterior.
  7. Verificación huella del registro y cómo comprobar el paquete de evidencia.

Mientras la revisión está en curso el documento lleva la marca de agua «EN CURSO»: no es una constancia.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime

from app.application.informes import motor_pdf as M
from app.application.informes.ficha import AvisoInforme
from app.application.rat import informe as I
from app.domain.rat import revision as R

esc = M.esc
PdfNoDisponibleError = M.PdfNoDisponibleError

AVISO_REVISION = AvisoInforme(
    version="2026-11-revision-v1",
    titulo="Alcance de la revisión",
    texto=(
        "Esta revisión la realiza la propia organización, en su función de auditoría interna, sobre el Registro de "
        "Actividades de Tratamiento y el mapa de datos que mantiene en ComplianceIA. La plataforma comprueba de forma "
        "automática que la información esté completa y sea coherente; la persona que revisa confirma que lo "
        "declarado corresponde a la realidad de la organización.",
        "La constancia vale para la versión del registro indicada (identificada por su huella). Si el registro "
        "cambia, la versión nueva debe revisarse otra vez. Este documento no es una auditoría externa, no certifica "
        "el cumplimiento de la Ley N.º 21.719 y no constituye asesoría legal.",
    ),
    pie="La revisión interna la hace la propia organización; la plataforma no certifica el cumplimiento (Ley N.º 21.719).",
)

COLOR_RESULTADO = {R.CUMPLE: M.VERDE, R.ADVERTENCIA: M.AVISO_BORDE, R.FALLA: M.ALERTA_BORDE, R.NO_APLICA: M.GRIS}
COLOR_REVISION = {R.VERIFICADO: M.VERDE, R.ACEPTADO: M.AVISO_BORDE, R.PENDIENTE: M.ALERTA_BORDE,
                  R.DESACTUALIZADO: M.ALERTA_BORDE, R.NO_APLICA: M.GRIS}
PRIORIDAD = {"alta": "Alta", "media": "Media", "baja": "Baja"}
# Encabezados cortos para las tablas del mapa (los títulos completos no caben en columnas angostas)
CORTO = {"ficha": "Ficha", "confirmado": "Confirmado", "en_registro": "En el registro", "contrato": "Contrato",
         "garantia": "Garantía", "cifrado": "Cifrado"}


@dataclass
class DatosConstancia:
    empresa: str
    rut: str | None
    numero: int
    estado: str                       # en_curso | revisada
    fecha_inicio: datetime
    generado: datetime
    lista: list[dict]                 # objetos consolidados (revision.consolidar)
    observaciones: list[dict]
    resumen: dict
    fecha_revision: datetime | None = None
    revisor: str | None = None
    cargo: str | None = None
    conclusion: str | None = None
    version_rat: int | None = None
    huella: str | None = None
    version_mapa: int | None = None
    informe_codigo: str | None = None
    proxima_revision: str | None = None
    plazo_meses: int | None = None
    diferencias: dict | None = None
    diferencias_desde: str | None = None
    notas: list[str] = field(default_factory=list)

    @property
    def revisada(self) -> bool:
        return self.estado == "revisada"


def nombre_archivo(d: DatosConstancia) -> str:
    fecha = M.fecha_local(d.fecha_revision or d.generado, con_hora=False)
    dd, mm, aaaa = fecha.split("-")
    v = f"_v{d.version_rat}" if d.version_rat else ""
    return f"revision_interna_{d.numero}{v}_{aaaa}-{mm}-{dd}{'' if d.revisada else '_en_curso'}.pdf"


def _fecha_iso(v) -> str:
    if not v:
        return "—"
    try:
        return M.fecha_local(datetime.fromisoformat(str(v)))
    except ValueError:
        return str(v)


def generar_pdf_revision(d: DatosConstancia) -> bytes:
    M.importar()
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    e = M.estilos()
    ancho = A4[0] - 30 * mm
    res = d.resumen or {}
    obs = res.get("observaciones") or {}

    def p(texto, estilo=None):
        return Paragraph(texto, estilo or e.chico)

    def cab(*titulos):
        return [p(esc(t), e.cabecera) for t in titulos]

    def color(texto: str, c: str, negrita: bool = True) -> str:
        t = esc(texto)
        return f'<font color="{c}">' + (f"<b>{t}</b>" if negrita else t) + "</font>"

    def resultado(i: dict) -> str:
        return color(R.TITULO_RESULTADO.get(i["resultado"], i["resultado"]), COLOR_RESULTADO.get(i["resultado"], M.GRIS))

    def revision(i: dict) -> str:
        if i["resultado"] == R.NO_APLICA:
            return color("—", M.GRIS, False)
        return color(R.TITULO_REVISION.get(i["revision"], i["revision"]), COLOR_REVISION.get(i["revision"], M.GRIS))

    historia: list = []
    # ================================================================ portada
    historia += [
        p("ComplianceIA de Therion Labs · Protección de datos personales", e.gris_chico), Spacer(1, 3),
        p("Informe de revisión interna del registro", e.h1), Spacer(1, 3),
        p(f"Revisión de <b>{esc(d.empresa)}</b> sobre su Registro de Actividades de Tratamiento y su mapa de datos: "
          "lista de verificación por actividad y por elemento del mapa (campos completos, base de licitud, plazos, "
          "transferencias con garantía y contratos), observaciones y su cierre.", e.gris), Spacer(1, 10)]
    if not d.revisada:
        historia += [M.caja_alerta("REVISIÓN EN CURSO: este documento todavía no es una constancia", [
            "La versión del registro aún no se marca como revisada. Sirve para hacer seguimiento del avance.",
            f"Puntos revisados: {res.get('revisados', 0)} de {res.get('puntos', 0)} · observaciones abiertas: "
            f"{obs.get('abiertas', 0)}."], ancho, e), Spacer(1, 8)]
    estado = color("Revisada", M.VERDE) if d.revisada else color("En curso", M.MARCA_AGUA)
    quien = esc(d.revisor) + (f'<font size=7>, {esc(d.cargo)}</font>' if d.cargo else "") if d.revisor else "—"
    celdas = [
        ("Empresa", esc(d.empresa)), ("RUT", esc(d.rut) if d.rut else "—"),
        ("Revisión interna", f"N.º {d.numero}"),
        ("Versión del registro", f"N.º {d.version_rat}" if d.version_rat else "Se fija al marcarla"),
        ("Estado", estado),
        ("Fecha de la revisión", (M.fecha_local(d.fecha_revision) + '<font size=7> (hora de Chile)</font>')
         if d.fecha_revision else f"Iniciada el {M.fecha_local(d.fecha_inicio, con_hora=False)}"),
        ("Revisó", quien),
        ("Huella del registro", I.huella_legible(d.huella) if d.huella else "—"),
        ("Próxima revisión", (f"{esc(d.proxima_revision)}" + (f'<font size=7> (cada {d.plazo_meses} meses)</font>'
                                                              if d.plazo_meses else "")) if d.proxima_revision else "—"),
    ]
    historia += [M.ficha(celdas, ancho, e), Spacer(1, 8)]
    por_tipo = res.get("por_tipo") or {}
    historia.append(M.indicadores([
        ("Puntos revisados", f"{res.get('revisados', 0)}/{res.get('puntos', 0)}", f"{res.get('porcentaje', 0)} %",
         M.VERDE if res.get("puntos") and res.get("revisados") == res.get("puntos") else None),
        ("Aceptados con justificación", str(res.get("aceptados", 0)), "fallas o advertencias asumidas",
         M.AVISO_BORDE if res.get("aceptados") else None),
        ("Observaciones", str(obs.get("total", 0)), f"{obs.get('cerradas', 0)} cerradas · {obs.get('abiertas', 0)} abiertas",
         M.ALERTA_BORDE if obs.get("abiertas") else None),
        ("Alcance", str(res.get("objetos", 0)), f"{por_tipo.get('actividad', 0)} actividades · "
         f"{por_tipo.get('elemento', 0)} elementos · {por_tipo.get('flujo', 0)} flujos", None),
    ], ancho, e))
    historia.append(Spacer(1, 8))
    if d.conclusion:
        historia += [p("Conclusión de quien revisó", e.h3), p(esc(d.conclusion), e.base), Spacer(1, 6)]
    if d.revisada:
        historia += [M._caja([
            p("Declaración", e.aviso_titulo), Spacer(1, 2),
            p(f"Quien firma declara haber revisado la versión N.º {d.version_rat} del Registro de Actividades de "
              f"Tratamiento de {esc(d.empresa)} y su mapa de datos con la lista de verificación de este informe, que "
              "las observaciones quedaron cerradas y que, a su leal saber, el registro es fiel a la realidad de la "
              "organización en la fecha indicada.", e.aviso_texto), Spacer(1, 18),
            p("_______________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;_______________", e.chico),
            p(f"{esc(d.revisor or '')}{(', ' + esc(d.cargo)) if d.cargo else ''}"
              "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Fecha", e.gris_chico),
        ], ancho, M.VERDE_SUAVE, M.VERDE), Spacer(1, 8)]
    historia.append(M.caja_aviso(AVISO_REVISION, ancho, e))
    for n in d.notas:
        historia += [Spacer(1, 4), p(esc(n), e.gris_chico)]

    # ================================================================ 1. resultado por criterio
    historia += [PageBreak(), p("1. Resultado por criterio", e.h2),
                 p("Cuántos puntos de la lista cumplen, tienen una advertencia o una falla según la comprobación "
                   "automática, y cuántos aceptó quien revisó con una justificación escrita.", e.gris_chico),
                 Spacer(1, 6)]
    for tipo, titulo, criterios in (("actividad", "Actividades del registro", R.CRITERIOS_ACTIVIDAD),
                                    ("elemento", "Elementos del mapa", R.CRITERIOS_ELEMENTO),
                                    ("flujo", "Flujos del mapa", R.CRITERIOS_FLUJO)):
        objs = [o for o in d.lista if o["tipo"] == tipo]
        if not objs:
            continue
        filas = [cab(titulo, "Cumple", "Advertencia", "Falla", "No aplica", "Aceptados")]
        for c in criterios:
            its = [i for o in objs for i in o["items"] if i["codigo"] == c.codigo]
            cuenta = {r: sum(1 for i in its if i["resultado"] == r) for r in R.RESULTADOS}
            filas.append([p(esc(c.titulo) + (' <font size=6 color="#5b6b64">(bloqueante)</font>' if c.bloqueante else "")),
                          p(color(str(cuenta[R.CUMPLE]), M.VERDE) if cuenta[R.CUMPLE] else "0"),
                          p(color(str(cuenta[R.ADVERTENCIA]), M.AVISO_BORDE) if cuenta[R.ADVERTENCIA] else "0"),
                          p(color(str(cuenta[R.FALLA]), M.ALERTA_BORDE) if cuenta[R.FALLA] else "0"),
                          p(str(cuenta[R.NO_APLICA])),
                          p(str(sum(1 for i in its if i["revision"] == R.ACEPTADO)))])
        historia += [M.tabla(filas, [ancho * w for w in (0.40, 0.12, 0.13, 0.11, 0.12, 0.12)]), Spacer(1, 8)]

    # ================================================================ 2. actividades
    acts = [o for o in d.lista if o["tipo"] == "actividad"]
    historia += [PageBreak(), p("2. Actividades del registro", e.h2),
                 p("Cada actividad con sus puntos de la lista de verificación. «Verificado»: quien revisó confirmó el "
                   "punto. «Aceptado»: lo asumió con la justificación del capítulo 4.", e.gris_chico), Spacer(1, 4)]
    for n, o in enumerate(acts, start=1):
        filas = [cab("Punto", "Resultado", "Detalle", "Revisión")]
        for i in o["items"]:
            filas.append([p(esc(i["titulo"])), p(resultado(i)), p(esc(i["detalle"])), p(revision(i))])
        historia.append(CondPageBreak(60 * mm))
        historia.append(KeepTogether([
            p(f"{n}. {esc(o['nombre'])}", e.h3),
            p(esc(o.get("subtitulo") or "") + f" · {o['revisados']} de {o['por_revisar']} puntos revisados", e.gris_chico),
            Spacer(1, 3), M.tabla(filas, [ancho * w for w in (0.24, 0.13, 0.43, 0.20)]), Spacer(1, 6)]))
    if not acts:
        historia.append(p("El registro no tiene actividades.", e.gris))

    # ================================================================ 3. mapa de datos
    historia += [PageBreak(), p("3. Mapa de datos", e.h2),
                 p("Los sistemas, bases de datos, terceros y flujos de los que se toma la información del registro.",
                   e.gris_chico), Spacer(1, 4)]
    for tipo, titulo, criterios in (("elemento", "Sistemas, bases de datos y terceros", R.CRITERIOS_ELEMENTO),
                                    ("flujo", "Flujos de datos", R.CRITERIOS_FLUJO)):
        objs = [o for o in d.lista if o["tipo"] == tipo]
        if not objs:
            continue
        filas = [cab(titulo, *[CORTO.get(c.codigo, c.titulo) for c in criterios], "Revisados")]
        for o in objs:
            por = {i["codigo"]: i for i in o["items"]}
            filas.append([p(f"<b>{esc(o['nombre'])}</b><br/><font size=6.5 color='#5b6b64'>{esc(o.get('subtitulo') or '')}</font>"),
                          *[p(resultado(por[c.codigo]) if c.codigo in por else "—") for c in criterios],
                          p(f"{o['revisados']}/{o['por_revisar']}")])
        n = len(criterios)
        ancho_crit = 0.58 / n
        historia += [p(titulo, e.h3), M.tabla(filas, [ancho * 0.30] + [ancho * ancho_crit] * n + [ancho * 0.12]),
                     Spacer(1, 8)]
    if not any(o["tipo"] in ("elemento", "flujo") for o in d.lista):
        historia.append(p("El mapa de datos no tiene elementos.", e.gris))

    # ================================================================ 4. aceptados con justificación
    aceptados = [(o, i) for o in d.lista for i in o["items"] if i["revision"] == R.ACEPTADO]
    historia += [CondPageBreak(50 * mm), p("4. Puntos aceptados con justificación", e.h2)]
    if aceptados:
        filas = [cab("Sobre", "Punto", "Resultado", "Justificación", "Fecha")]
        for o, i in aceptados:
            filas.append([p(esc(o["nombre"])), p(esc(i["titulo"])), p(resultado(i)), p(esc(i.get("nota") or "")),
                          p(_fecha_iso(i.get("fecha_revision")))])
        historia.append(M.tabla(filas, [ancho * w for w in (0.22, 0.18, 0.12, 0.34, 0.14)]))
    else:
        historia.append(p("No se aceptó ningún punto con justificación: todo lo revisado cumple o se confirmó.", e.gris))

    # ================================================================ 5. observaciones
    historia += [CondPageBreak(50 * mm), p("5. Observaciones", e.h2)]
    if d.observaciones:
        filas = [cab("N.º", "Sobre", "Prioridad", "Observación", "Apertura", "Cierre")]
        for x in d.observaciones:
            cierre = (f"{_fecha_iso(x.get('fecha_cierre'))}<br/>{esc(x.get('nota_cierre') or '')}"
                      + ("" if x.get("objeto_cambio") is None else
                         f"<br/><font size=6.5 color='#5b6b64'>{'El elemento se corrigió' if x['objeto_cambio'] else 'Cerrada sin cambios en el elemento'}</font>")
                      if x["estado"] == "cerrada" else color("Abierta", M.ALERTA_BORDE))
            filas.append([p(str(x["numero"])),
                          p(f"{esc(x['objeto_nombre'])}" + (f"<br/><font size=6.5 color='#5b6b64'>{esc(x['criterio_titulo'])}</font>"
                                                             if x.get("criterio_titulo") else "")),
                          p(PRIORIDAD.get(x["prioridad"], x["prioridad"])), p(esc(x["texto"])),
                          p(_fecha_iso(x["fecha_apertura"])), p(cierre)])
        historia.append(M.tabla(filas, [ancho * w for w in (0.06, 0.19, 0.09, 0.30, 0.13, 0.23)]))
    else:
        historia.append(p("No se registraron observaciones en esta revisión.", e.gris))

    # ================================================================ 6. diferencias
    historia += [CondPageBreak(50 * mm), p("6. Cambios desde la revisión anterior", e.h2)]
    dif = d.diferencias
    if dif is None:
        historia.append(p("Es la primera revisión interna del registro: no hay una versión anterior con qué comparar.",
                          e.gris))
    elif dif.get("sin_cambios"):
        historia.append(p(f"El registro no cambió respecto de {esc(d.diferencias_desde or 'la revisión anterior')}.", e.gris))
    else:
        t = dif["totales"]
        historia.append(p(f"Respecto de {esc(d.diferencias_desde or 'la revisión anterior')}: {t['agregadas']} actividad(es) "
                          f"nueva(s), {t['quitadas']} que ya no están, {t['cambiadas']} con cambios y {t['iguales']} "
                          "sin cambios.", e.chico))
        historia.append(Spacer(1, 4))
        filas = [cab("Actividad", "Qué cambió", "Antes", "Ahora")]
        for a in dif["agregadas"]:
            filas.append([p(esc(a["nombre"])), p(color("Nueva en el registro", M.VERDE)), p("—"),
                          p(f"Versión {a['version']}" if a.get("version") else "Sin versión vigente")])
        for a in dif["quitadas"]:
            filas.append([p(esc(a["nombre"])), p(color("Ya no está (archivada)", M.ALERTA_BORDE)),
                          p(f"Versión {a['version']}" if a.get("version") else "—"), p("—")])
        for a in dif["cambiadas"]:
            for c in a["campos"][:8] or [{"titulo": "Contenido", "antes": "—", "despues": "—"}]:
                filas.append([p(esc(a["nombre"])), p(esc(c["titulo"])), p(esc(_corto(c["antes"]))),
                              p(esc(_corto(c["despues"])))])
        historia.append(M.tabla(filas, [ancho * w for w in (0.22, 0.18, 0.30, 0.30)]))

    # ================================================================ 7. verificación
    historia += [CondPageBreak(40 * mm), p("7. Verificación", e.h2),
                 p(f"Huella del registro revisado: <b>{esc(d.huella or '—')}</b>"
                   + (f" · versión del mapa de datos N.º {d.version_mapa}" if d.version_mapa else "")
                   + (f" · informe del registro {esc(d.informe_codigo)}" if d.informe_codigo else "") + ".", e.chico),
                 p("La huella resume lo que afirma el registro: coincide con la que imprime el informe del registro de la "
                   "misma versión. El paquete de evidencia de esta revisión (ZIP) trae este informe, el del registro, la "
                   "lista de verificación, las observaciones y el historial de cambios, con el SHA-256 de cada archivo y "
                   "un script para comprobarlo sin depender de la plataforma.", e.gris_chico)]

    izquierda = (f"ComplianceIA | Revisión interna N.º {d.numero}"
                 + (f" | RAT versión {d.version_rat}" if d.version_rat else "") + f" | {d.empresa[:60]}")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"Revisión interna del registro · {d.empresa}" + ("" if d.revisada else " (en curso)"),
        author="ComplianceIA (Therion Labs)", subject="Revisión interna del Registro de Actividades de Tratamiento",
        keywords=f"revisión interna, RAT, versión {d.version_rat or '-'}")
    doc.build(historia, canvasmaker=M.lienzo(A4, AVISO_REVISION.pie, izquierda,
                                             marca_agua=None if d.revisada else "EN CURSO"))
    return buffer.getvalue()


def _corto(texto: str, maximo: int = 260) -> str:
    t = texto or "—"
    return t if len(t) <= maximo else t[: maximo - 1] + "…"
