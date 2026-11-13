"""HU-36 · Cuerpo del correo con el informe del registro adjunto (sin datos personales: solo cifras)."""
from __future__ import annotations

from html import escape

from app.application.informes import motor_pdf as M
from app.application.rat import informe as I


def asunto(inf: I.InformeRat) -> str:
    return (f"Registro de actividades de tratamiento · versión {inf.version_rat}"
            + (" (borrador)" if inf.borrador else "") + f" · {inf.codigo}")


def cuerpo(inf: I.InformeRat, formatos: list[str]) -> tuple[str, str]:
    """(texto plano, html)."""
    r = inf.resumen
    adjuntos = " y ".join({"pdf": "PDF", "xlsx": "Excel"}[f] for f in formatos)
    estado = ("BORRADOR: hay actividades que no están vigentes, así que no es apto para una presentación oficial."
              if inf.borrador else "Informe oficial: todas las actividades incluidas están vigentes.")
    texto = (
        "Hola,\n\n"
        f"Te enviamos el informe del Registro de Actividades de Tratamiento de {inf.empresa}.\n\n"
        f"Código verificable: {inf.codigo}\n"
        f"Versión del RAT: {inf.version_rat}\n"
        f"Emitido el: {M.fecha_local(inf.generado)} (hora de Chile)\n"
        f"{estado}\n\n"
        f"Actividades: {r['actividades']} · Con datos sensibles: {r['con_sensibles']}\n"
        f"Transferencias internacionales: {r['transferencias']} ({r['transferencias_sin_garantia']} sin garantía)\n"
        f"Decisiones automatizadas: {r['con_decisiones']} · Riesgo alto o crítico: {r['riesgos_altos']}\n"
        + (f"Revisión interna: {inf.revision.texto}.\n" if inf.revision else "") + "\n"
        f"Adjuntamos el informe en {adjuntos}. {inf.aviso.pie}\n\n"
        "Este correo se generó automáticamente; no es necesario responderlo.\nComplianceIA\n"
    )

    def celda(titulo: str, cifra, pie: str) -> str:
        return (f'<td style="padding:14px;font-size:12px;color:#5b6b64;vertical-align:top">{titulo}<br>'
                f'<span style="font-size:22px;font-weight:bold;color:#14201b">{cifra}</span><br>{pie}</td>')

    revision = (f"<br><b>Revisión interna:</b> {escape(inf.revision.texto)}" if inf.revision else "")
    color_estado = "#b4233f" if inf.borrador else "#0b7a5a"
    fondo_estado = "#fbecef" if inf.borrador else "#e3f4ee"
    html = f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#14201b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;border-top:4px solid #0b7a5a">
<tr><td style="padding:28px 28px 8px">
<p style="margin:0 0 4px;font-size:12px;color:#5b6b64">ComplianceIA · Protección de datos</p>
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">Registro de actividades de tratamiento de {escape(inf.empresa)}</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.5">Adjuntamos el informe en <b>{adjuntos}</b>, listo para presentarlo ante la Agencia de Protección de Datos Personales, el certificador de tu modelo de prevención o tu directorio.</p>
<p style="margin:0 0 16px;padding:10px 14px;border-left:3px solid {color_estado};background:{fondo_estado};font-size:13px;line-height:1.5;color:{color_estado}"><b>{escape(estado)}</b></p>
</td></tr>
<tr><td style="padding:0 28px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e3f4ee;border-radius:8px"><tr>
{celda("Actividades", r["actividades"], f"{r['por_estado']['vigente']} vigentes")}
{celda("Datos sensibles", r["con_sensibles"], "actividades")}
{celda("Transferencias", r["transferencias"], f"{r['transferencias_sin_garantia']} sin garantía")}
{celda("Riesgo alto o crítico", r["riesgos_altos"], "actividades")}
</tr></table>
</td></tr>
<tr><td style="padding:18px 28px 0;font-size:13px;line-height:1.6">
<b>Código verificable:</b> {escape(inf.codigo or "")}<br>
<b>Versión del RAT:</b> N.º {inf.version_rat}<br>
<b>Emitido el:</b> {M.fecha_local(inf.generado)} (hora de Chile)<br>
<b>Huella del registro:</b> {I.huella_legible(inf.huella)}{revision}
</td></tr>
<tr><td style="padding:20px 28px 28px;font-size:12px;line-height:1.5;color:#5b6b64">
{escape(inf.aviso.pie)} Este correo se generó automáticamente; no es necesario responderlo.
</td></tr></table>
</td></tr></table></body></html>"""
    return texto, html
