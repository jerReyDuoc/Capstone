"""
Envío del informe por correo, solo con la biblioteca estándar (smtplib + email).

CORREO_MODO:
  smtp        envía por SMTP_HOST (STARTTLS en 587 o SSL en 465).
  archivo     guarda el mensaje completo (.eml, con el PDF adjunto) en
              STORAGE_DIR/correos para probar sin servidor de correo. Ábrelo con
              Outlook/Thunderbird o haz doble clic en Windows.
  desactivado lanza CorreoNoDisponibleError (el endpoint responde 503).

smtplib es bloqueante: se ejecuta en un hilo para no frenar el event loop.
"""
from __future__ import annotations

import asyncio
import re
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from app.core.config import settings

EMAIL_VALIDO = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$")


class CorreoNoDisponibleError(Exception):
    pass


class CorreoFallidoError(Exception):
    pass


@dataclass(frozen=True)
class Adjunto:
    nombre: str
    contenido: bytes
    tipo: str = "application/pdf"


def enmascarar(email: str) -> str:
    """jason.sanchez@empresa.cl -> j***z@empresa.cl (para mensajes y logs)."""
    local, _, dominio = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}***@{dominio}"
    return f"{local[0]}***{local[-1]}@{dominio}"


def construir_mensaje(destino: str, asunto: str, texto: str, html: str | None,
                      adjuntos: list[Adjunto]) -> EmailMessage:
    if not EMAIL_VALIDO.match(destino):
        raise ValueError("Correo de destino inválido")
    msg = EmailMessage()
    msg["From"] = settings.CORREO_REMITENTE
    msg["To"] = destino
    msg["Subject"] = asunto
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="complianceia.cl")
    msg["Auto-Submitted"] = "auto-generated"  # RFC 3834: no responder automáticamente
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
    for a in adjuntos:
        maintype, _, subtype = a.tipo.partition("/")
        msg.add_attachment(a.contenido, maintype=maintype, subtype=subtype, filename=a.nombre)
    return msg


def _enviar_smtp(msg: EmailMessage) -> None:
    contexto = ssl.create_default_context()
    try:
        if settings.SMTP_SSL:
            servidor = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=contexto,
                                        timeout=settings.SMTP_TIMEOUT_S)
        else:
            servidor = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_S)
        with servidor:
            if not settings.SMTP_SSL and settings.SMTP_STARTTLS:
                servidor.starttls(context=contexto)
            if settings.SMTP_USUARIO:
                servidor.login(settings.SMTP_USUARIO, settings.SMTP_PASSWORD or "")
            servidor.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise CorreoFallidoError(f"El servidor de correo rechazó el envío ({type(e).__name__})") from e


def _guardar_archivo(msg: EmailMessage) -> Path:
    carpeta = Path(settings.STORAGE_DIR) / "correos"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{uuid.uuid4().hex}.eml"
    ruta.write_bytes(bytes(msg))
    return ruta


async def enviar(destino: str, asunto: str, texto: str, html: str | None, adjuntos: list[Adjunto]) -> str:
    """Envía (o guarda) el mensaje. Devuelve el modo usado: "smtp" o "archivo"."""
    modo = settings.CORREO_MODO
    if modo == "desactivado":
        raise CorreoNoDisponibleError("El envío por correo no está habilitado en este entorno.")
    msg = construir_mensaje(destino, asunto, texto, html, adjuntos)
    if modo == "smtp":
        await asyncio.to_thread(_enviar_smtp, msg)
    else:
        await asyncio.to_thread(_guardar_archivo, msg)
    return modo


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
