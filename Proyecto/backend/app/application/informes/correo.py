"""
Piezas puras del correo del informe (A-14): validación y enmascarado de destinos y cuerpo del mensaje.

El envío (smtplib + email) vive en app/infrastructure/correo/smtp.py, tras CorreoPort
(app/domain/ports/correo_port.py); los casos de uso lo piden con `fabricas().correo`.
"""
from __future__ import annotations

import re

EMAIL_VALIDO = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$")


def enmascarar(email: str) -> str:
    """jason.sanchez@empresa.cl -> j***z@empresa.cl (para mensajes y logs)."""
    local, _, dominio = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}***@{dominio}"
    return f"{local[0]}***{local[-1]}@{dominio}"


def cuerpo_informe(evaluacion_id: int, puntaje: float, nivel: str, brechas: int, criticas: int,
                   modulos: int, horas: int) -> tuple[str, str]:
    """(texto plano, html) del correo. Sin datos personales: solo resultados de la organización."""
    p = f"{puntaje:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    texto = (
        "Hola,\n\n"
        f"Te enviamos el informe de tu evaluación #{evaluacion_id} de gobernanza de IA y protección de datos.\n\n"
        f"Puntaje general: {p} / 100 ({nivel})\n"
        f"Brechas detectadas: {brechas} ({criticas} críticas)\n"
        f"Plan formativo recomendado: {modulos} módulos, {horas} horas\n\n"
        "El informe completo va adjunto en PDF. Guárdalo: incluye el listado priorizado de brechas "
        "y el plan de capacitación por dimensión.\n\n"
        "Este correo se generó automáticamente; no es necesario responderlo.\n"
        "ComplianceIA\n"
    )
    html = f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#14201b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;border-top:4px solid #0b7a5a">
<tr><td style="padding:28px 28px 8px">
<p style="margin:0 0 4px;font-size:12px;color:#5b6b64">ComplianceIA</p>
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">Tu informe de diagnóstico está listo</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.5">Adjuntamos el informe de la evaluación <b>#{evaluacion_id}</b>. Guárdalo: incluye el listado priorizado de brechas y el plan de capacitación por dimensión.</p>
</td></tr>
<tr><td style="padding:0 28px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e3f4ee;border-radius:8px">
<tr>
<td style="padding:14px;font-size:12px;color:#5b6b64">Puntaje general<br><span style="font-size:22px;font-weight:bold;color:#14201b">{p}</span> / 100<br>{nivel}</td>
<td style="padding:14px;font-size:12px;color:#5b6b64">Brechas<br><span style="font-size:22px;font-weight:bold;color:#14201b">{brechas}</span><br>{criticas} críticas</td>
<td style="padding:14px;font-size:12px;color:#5b6b64">Plan formativo<br><span style="font-size:22px;font-weight:bold;color:#14201b">{modulos}</span> módulos<br>{horas} horas</td>
</tr></table>
</td></tr>
<tr><td style="padding:20px 28px 28px;font-size:12px;line-height:1.5;color:#5b6b64">
Este correo se generó automáticamente; no es necesario responderlo. El informe es una autoevaluación orientativa y no constituye asesoría legal.
</td></tr></table>
</td></tr></table></body></html>"""
    return texto, html
