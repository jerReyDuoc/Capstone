"""
Envío de correo, solo con la biblioteca estándar (smtplib + email). Implementa CorreoPort (A-14).

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
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from app.application.informes.correo import EMAIL_VALIDO
from app.core.config import settings
from app.domain.ports.correo_port import Adjunto, CorreoFallidoError, CorreoNoDisponibleError


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


class CorreoSmtp:
    """Implementa CorreoPort. Busca `enviar` del módulo al llamar (los tests lo reemplazan con monkeypatch)."""

    async def enviar(self, destino: str, asunto: str, texto: str, html: str | None,
                     adjuntos: list[Adjunto]) -> str:
        return await enviar(destino, asunto, texto, html, adjuntos)
