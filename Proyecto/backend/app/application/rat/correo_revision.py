"""HU-40 · Correos de la revisión interna: la constancia (con o sin el paquete de evidencia) y el recordatorio
de la revisión periódica. Sin datos personales de terceros: cifras, versiones y fechas."""
from __future__ import annotations

from html import escape

from app.application.informes import motor_pdf as M
from app.application.rat.pdf_revision import DatosConstancia


def _marco(titulo: str, cuerpo_html: str, color: str = "#0b7a5a") -> str:
    return f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#14201b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;border-top:4px solid {color}">
<tr><td style="padding:28px 28px 8px">
<p style="margin:0 0 4px;font-size:12px;color:#5b6b64">ComplianceIA · Protección de datos</p>
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">{titulo}</h1>
</td></tr>
{cuerpo_html}
<tr><td style="padding:20px 28px 28px;font-size:12px;line-height:1.5;color:#5b6b64">
La revisión interna la hace la propia organización; la plataforma no certifica el cumplimiento (Ley N.º 21.719).
Este correo se generó automáticamente; no es necesario responderlo.
</td></tr></table>
</td></tr></table></body></html>"""


def _celda(titulo: str, cifra, pie: str) -> str:
    return (f'<td style="padding:14px;font-size:12px;color:#5b6b64;vertical-align:top">{titulo}<br>'
            f'<span style="font-size:22px;font-weight:bold;color:#14201b">{cifra}</span><br>{pie}</td>')


def asunto_constancia(d: DatosConstancia) -> str:
    if d.revisada:
        return (f"Revisión interna del registro · versión {d.version_rat} revisada el "
                f"{M.fecha_local(d.fecha_revision, con_hora=False)}")
    return f"Revisión interna del registro N.º {d.numero} · avance (en curso)"


def cuerpo_constancia(d: DatosConstancia, con_paquete: bool, codigo_paquete: str | None) -> tuple[str, str]:
    r = d.resumen or {}
    obs = r.get("observaciones") or {}
    adjuntos = "el informe de la revisión (PDF)" + (" y el paquete de evidencia (ZIP)" if con_paquete else "")
    if d.revisada:
        estado = (f"Versión N.º {d.version_rat} del registro revisada el {M.fecha_local(d.fecha_revision)} por "
                  f"{d.revisor}{', ' + d.cargo if d.cargo else ''}.")
    else:
        estado = "La revisión sigue en curso: este informe muestra el avance y todavía no es una constancia."
    texto = (
        "Hola,\n\n"
        f"Te enviamos {adjuntos} de la revisión interna N.º {d.numero} del registro de actividades de {d.empresa}.\n\n"
        f"{estado}\n"
        f"Puntos revisados: {r.get('revisados', 0)} de {r.get('puntos', 0)} · aceptados con justificación: "
        f"{r.get('aceptados', 0)}\n"
        f"Observaciones: {obs.get('total', 0)} ({obs.get('cerradas', 0)} cerradas, {obs.get('abiertas', 0)} abiertas)\n"
        + (f"Huella del registro: {(d.huella or '')[:16].upper()}\n" if d.huella else "")
        + (f"Código del paquete: {codigo_paquete} (verifícalo con el script que trae o en la plataforma)\n"
           if codigo_paquete else "")
        + (f"Próxima revisión: {d.proxima_revision}\n" if d.proxima_revision else "")
        + "\nComplianceIA\n")
    color = "#0b7a5a" if d.revisada else "#8a6200"
    html = _marco(f"Revisión interna del registro de {escape(d.empresa)}", f"""
<tr><td style="padding:0 28px 8px">
<p style="margin:0 0 14px;font-size:15px;line-height:1.5">Adjuntamos <b>{escape(adjuntos)}</b>.</p>
<p style="margin:0 0 16px;padding:10px 14px;border-left:3px solid {color};background:{'#e3f4ee' if d.revisada else '#f6f4ee'};font-size:13px;line-height:1.5;color:{color}"><b>{escape(estado)}</b></p>
</td></tr>
<tr><td style="padding:0 28px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e3f4ee;border-radius:8px"><tr>
{_celda("Puntos revisados", f"{r.get('revisados', 0)}/{r.get('puntos', 0)}", f"{r.get('porcentaje', 0)} %")}
{_celda("Aceptados", r.get('aceptados', 0), "con justificación")}
{_celda("Observaciones", obs.get('total', 0), f"{obs.get('cerradas', 0)} cerradas")}
</tr></table>
</td></tr>
<tr><td style="padding:18px 28px 0;font-size:13px;line-height:1.6">
{f"<b>Versión del registro:</b> N.º {d.version_rat}<br>" if d.version_rat else ""}
{f"<b>Huella del registro:</b> {escape((d.huella or '')[:16].upper())}<br>" if d.huella else ""}
{f"<b>Código del paquete:</b> {escape(codigo_paquete)}<br>" if codigo_paquete else ""}
{f"<b>Próxima revisión:</b> {escape(d.proxima_revision)}" if d.proxima_revision else ""}
</td></tr>""", color)
    return texto, html


TITULO_ESTADO = {"por_vencer": "vence pronto", "vencida": "está vencida"}


def asunto_recordatorio(estado: str, empresa: str) -> str:
    return f"Recordatorio: la revisión interna del registro de {empresa} {TITULO_ESTADO.get(estado, 'está pendiente')}"


def cuerpo_recordatorio(empresa: str, estado: dict, plazo_meses: int, ultima: str | None, url: str | None) -> tuple[str, str]:
    vence = estado.get("vence")
    try:
        d, m, a = vence[8:10], vence[5:7], vence[0:4]
        vence_txt = f"{d}-{m}-{a}"
    except (TypeError, IndexError):
        vence_txt = "—"
    if estado["estado"] == "vencida":
        frase = f"La revisión periódica del registro venció el {vence_txt}."
    else:
        frase = f"La revisión periódica del registro vence el {vence_txt} (en {estado.get('dias')} día(s))."
    base = (f"La última revisión fue el {ultima}." if ultima else
            "El registro todavía no tiene una revisión interna registrada.")
    texto = (
        "Hola,\n\n"
        f"{frase} {base}\n\n"
        f"Tu empresa definió revisar el registro de actividades cada {plazo_meses} meses para verificar que sigue "
        "siendo fiel antes de presentarlo, certificarlo o informarlo al directorio.\n\n"
        "Entra a ComplianceIA › Registro de actividades › Revisión interna, recorre la lista de verificación, cierra "
        "las observaciones y marca la versión como revisada.\n"
        + (f"\n{url}\n" if url else "")
        + "\nPuedes cambiar el plazo o desactivar este recordatorio en la misma página.\n\nComplianceIA\n")
    color = "#b4233f" if estado["estado"] == "vencida" else "#8a6200"
    boton = (f'<p style="margin:18px 0 0"><a href="{escape(url)}" style="display:inline-block;padding:10px 18px;'
             f'background:#0b7a5a;color:#ffffff;border-radius:8px;text-decoration:none;font-weight:bold">Ir a la revisión '
             f'interna</a></p>' if url else "")
    html = _marco("Es momento de revisar tu registro de actividades", f"""
<tr><td style="padding:0 28px 8px;font-size:15px;line-height:1.55">
<p style="margin:0 0 14px;padding:10px 14px;border-left:3px solid {color};background:#f6f4ee;color:{color}"><b>{escape(frase)}</b></p>
<p style="margin:0 0 12px">{escape(base)} Tu empresa definió revisarlo cada <b>{plazo_meses} meses</b> para verificar que sigue siendo fiel antes de presentarlo, certificarlo o informarlo al directorio.</p>
<p style="margin:0">Recorre la lista de verificación, cierra las observaciones y marca la versión como revisada.</p>
{boton}
<p style="margin:16px 0 0;font-size:12px;color:#5b6b64">Puedes cambiar el plazo o desactivar este recordatorio en la misma página.</p>
</td></tr>""", color)
    return texto, html
