"""
HU-27 criterio 3: enlace de activación de un solo uso y con vencimiento.

  - El administrador NUNCA define ni ve la contraseña del cliente, y el sistema nunca
    la envía por correo: el usuario definitivo recibe un enlace y la define él mismo.
  - Token: 32 bytes aleatorios (secrets.token_urlsafe). En la BD solo queda su SHA-256
    (un token de alta entropía no necesita un hash lento y así se puede buscar por él).
  - Vence a las ACTIVACION_TTL_HORAS; se usa una sola vez (fecha_uso, marcada con un
    UPDATE condicional para que dos clics simultáneos no activen dos veces); emitir uno
    nuevo revoca los anteriores sin usar.
  - El enlace lleva el token en el fragmento (#token=...): el navegador no lo envía al
    servidor web, no queda en logs de acceso, en el historial del proxy ni en el Referer.
  - Todo queda en la bitácora (emitido, correo enviado o fallido, usado, rechazado).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.core.autenticacion import Actor, hash_password
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.empresa import Empresa
from app.domain.models.usuario_definitivo import (
    EstadoUsuarioDefinitivo, TokenActivacion, UsuarioDefinitivo,
)
from app.infrastructure.repositories.bitacora_repository import ROL_ANONIMO, Accion, BitacoraRepository

logger = logging.getLogger("seguridad")

_LARGO_TOKEN_MAX = 128
_FORMATO_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
CONTRASENA_MAX = 128


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def generar_token() -> tuple[str, str]:
    """(token en claro para el correo, SHA-256 para la BD)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def url_activacion(token: str) -> str:
    return f"{settings.ACTIVACION_URL_BASE.rstrip('#')}#token={token}"


def validar_contrasena(password: str, email: str = "", nombre: str = "") -> list[str]:
    """Reglas de la contraseña del usuario definitivo. Lista vacía = cumple."""
    problemas: list[str] = []
    pw = password or ""
    minimo = settings.CLIENTE_PASSWORD_MIN
    if len(pw) < minimo:
        problemas.append(f"Debe tener al menos {minimo} caracteres.")
    if len(pw) > CONTRASENA_MAX:
        problemas.append(f"Debe tener como máximo {CONTRASENA_MAX} caracteres.")
    if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", pw) or not re.search(r"\d", pw):
        problemas.append("Debe combinar letras y números.")
    if pw and pw.strip() != pw:
        problemas.append("No puede empezar ni terminar con espacios.")
    bajo = pw.lower()
    local = (email or "").split("@")[0].lower()
    if len(local) >= 4 and local in bajo:
        problemas.append("No puede contener tu correo.")
    for parte in re.split(r"\s+", (nombre or "").lower()):
        if len(parte) >= 4 and parte in bajo:
            problemas.append("No puede contener tu nombre.")
            break
    if len(set(bajo)) < 5 and len(bajo) >= minimo:
        problemas.append("Es demasiado repetitiva.")
    return problemas


class ActivacionError(Exception):
    def __init__(self, mensaje: str, codigo: str, status_code: int, **extra):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code
        self.extra = extra


@dataclass(frozen=True)
class ResultadoCorreo:
    enviado: bool
    modo: str | None = None
    motivo: str | None = None


async def emitir_token(db: AsyncSession, usuario: UsuarioDefinitivo, actor: Actor | None,
                       ahora: datetime | None = None) -> str:
    """
    Revoca los enlaces vigentes del usuario y crea uno nuevo. NO hace commit (va en la
    transacción del alta o del reenvío). Devuelve el token en claro, para el correo.
    """
    ahora = ahora or _ahora()
    if settings.APP_ENV == "production" and not settings.ACTIVACION_URL_BASE.startswith("https://"):
        # Antes de escribir: el alta se revierte entera y nunca sale un enlace por http
        raise RuntimeError("ACTIVACION_URL_BASE debe usar https:// con APP_ENV=production (HU-27).")
    await db.execute(
        update(TokenActivacion)
        .where(TokenActivacion.usuario_definitivo_id == usuario.id,
               TokenActivacion.fecha_uso.is_(None), TokenActivacion.fecha_revocacion.is_(None))
        .values(fecha_revocacion=ahora)
        .execution_options(synchronize_session=False)
    )
    token, digest = generar_token()
    fila = TokenActivacion(
        usuario_definitivo_id=usuario.id,
        token_hash=digest,
        fecha_creacion=ahora,
        fecha_expiracion=ahora + timedelta(hours=settings.ACTIVACION_TTL_HORAS),
        creado_por_admin_id=actor.id if actor and actor.es_admin else None,
    )
    db.add(fila)
    await db.flush()
    BitacoraRepository(db).registrar(
        accion=Accion.ACTIVACION_EMITIDA, entidad="usuario_definitivo", entidad_id=usuario.id, actor=actor,
        detalle={"token_activacion_id": fila.id, "vence_horas": settings.ACTIVACION_TTL_HORAS},
        fecha=ahora,
    )
    return token


def cuerpo_activacion(nombre: str, razon_social: str, url: str, horas: int) -> tuple[str, str]:
    """(texto, html) del correo de activación. Nunca incluye una contraseña."""
    from html import escape

    texto = (
        f"Hola {nombre},\n\n"
        f"Therion Labs habilitó el acceso de {razon_social} al servicio de ComplianceIA "
        "(cursos y tutor IA), con el historial de su autodiagnóstico.\n\n"
        "Para activar tu cuenta y definir tu contraseña, abre este enlace:\n"
        f"{url}\n\n"
        f"El enlace sirve una sola vez y vence en {horas} horas. Si vence, pide uno nuevo a Therion Labs.\n"
        "Nunca te enviaremos una contraseña por correo ni te la pediremos.\n\n"
        "Si no esperabas este mensaje, ignóralo.\n"
        "ComplianceIA · Therion Labs\n"
    )
    n, r, u = escape(nombre), escape(razon_social), escape(url, quote=True)
    html = f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#14201b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;border-top:4px solid #0b7a5a">
<tr><td style="padding:28px">
<p style="margin:0 0 4px;font-size:12px;color:#5b6b64">ComplianceIA · Therion Labs</p>
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">Activa tu cuenta</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.5">Hola {n}: habilitamos el acceso de <b>{r}</b> al servicio de ComplianceIA, con el historial de su autodiagnóstico.</p>
<p style="margin:0 0 20px"><a href="{u}" style="display:inline-block;background:#0b7a5a;color:#ffffff;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:bold">Definir mi contraseña</a></p>
<p style="margin:0 0 8px;font-size:13px;line-height:1.5;color:#3d4b45">El enlace sirve una sola vez y vence en {horas} horas. Si vence, pide uno nuevo a Therion Labs.</p>
<p style="margin:0;font-size:12px;line-height:1.5;color:#5b6b64">Nunca te enviaremos una contraseña por correo ni te la pediremos. Si no esperabas este mensaje, ignóralo.</p>
</td></tr></table>
</td></tr></table></body></html>"""
    return texto, html


async def enviar_correo_activacion(db: AsyncSession, usuario: UsuarioDefinitivo, empresa: Empresa,
                                   token: str, actor: Actor | None) -> ResultadoCorreo:
    """Envía el enlace (DESPUÉS del commit del alta) y registra el resultado en la bitácora."""
    texto, html = cuerpo_activacion(usuario.nombre, empresa.razon_social, url_activacion(token),
                                    settings.ACTIVACION_TTL_HORAS)
    try:
        modo = await correo.enviar(usuario.email, "Activa tu cuenta de ComplianceIA", texto, html, [])
        resultado = ResultadoCorreo(enviado=True, modo=modo)
    except correo.CorreoNoDisponibleError:
        resultado = ResultadoCorreo(enviado=False, motivo="CORREO_NO_DISPONIBLE")
    except (correo.CorreoFallidoError, ValueError) as e:
        logger.warning("No se pudo enviar el enlace de activación (%s)", type(e).__name__)
        resultado = ResultadoCorreo(enviado=False, motivo="CORREO_FALLIDO")
    BitacoraRepository(db).registrar(
        accion=Accion.ACTIVACION_CORREO, entidad="usuario_definitivo", entidad_id=usuario.id, actor=actor,
        resultado="ok" if resultado.enviado else RESULTADO_RECHAZADO,
        detalle={"modo": resultado.modo, "motivo": resultado.motivo},
    )
    await db.commit()
    return resultado


class ActivarCuentaUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitacora = BitacoraRepository(db)

    async def _buscar(self, token: str) -> tuple[TokenActivacion | None, UsuarioDefinitivo | None]:
        if not token or len(token) > _LARGO_TOKEN_MAX or not _FORMATO_TOKEN.match(token):
            return None, None
        fila = await self.db.scalar(select(TokenActivacion).where(TokenActivacion.token_hash == hash_token(token)))
        if fila is None:
            return None, None
        return fila, await self.db.get(UsuarioDefinitivo, fila.usuario_definitivo_id)

    def _motivo_invalido(self, fila: TokenActivacion | None, usuario: UsuarioDefinitivo | None,
                         ahora: datetime) -> str | None:
        if fila is None or usuario is None:
            return "inexistente"
        if fila.fecha_uso is not None:
            return "usado"
        if fila.fecha_revocacion is not None:
            return "revocado"
        if fila.fecha_expiracion <= ahora:
            return "vencido"
        if usuario.estado != EstadoUsuarioDefinitivo.PENDIENTE_ACTIVACION.value:
            return "usuario_no_pendiente"
        return None

    async def _rechazar(self, fila: TokenActivacion | None, motivo: str) -> ActivacionError:
        self.bitacora.registrar(
            accion=Accion.ACTIVACION_RECHAZADA, entidad="usuario_definitivo",
            entidad_id=fila.usuario_definitivo_id if fila else None, actor_rol=ROL_ANONIMO,
            resultado=RESULTADO_RECHAZADO,
            detalle={"motivo": motivo, "token_activacion_id": fila.id if fila else None},
        )
        await self.db.commit()
        logger.warning("Activación rechazada (%s)", motivo)
        if motivo == "vencido":
            return ActivacionError("El enlace venció. Pide uno nuevo a Therion Labs.", "ENLACE_VENCIDO", 410)
        # usado / revocado / inexistente: mismo mensaje (no revela si existió)
        return ActivacionError(
            "El enlace no es válido o ya se usó. Si aún no activas tu cuenta, pide uno nuevo a Therion Labs.",
            "ENLACE_INVALIDO", 400,
        )

    async def verificar(self, token: str) -> dict:
        """Comprueba el enlace sin consumirlo (para mostrar el formulario)."""
        ahora = _ahora()
        fila, usuario = await self._buscar(token)
        motivo = self._motivo_invalido(fila, usuario, ahora)
        if motivo:
            raise await self._rechazar(fila, motivo)
        empresa = await self.db.get(Empresa, usuario.empresa_id)
        return {
            "valido": True,
            "email": correo.enmascarar(usuario.email),
            "empresa": empresa.razon_social if empresa else None,
            "expira": fila.fecha_expiracion.replace(tzinfo=timezone.utc).isoformat(),
            "password_min": settings.CLIENTE_PASSWORD_MIN,
        }

    async def activar(self, token: str, password: str) -> dict:
        ahora = _ahora()
        fila, usuario = await self._buscar(token)
        motivo = self._motivo_invalido(fila, usuario, ahora)
        if motivo:
            raise await self._rechazar(fila, motivo)

        problemas = validar_contrasena(password, usuario.email, usuario.nombre)
        if problemas:  # no consume el enlace: puede corregir y reintentar
            raise ActivacionError("La contraseña no cumple los requisitos.", "CONTRASENA_DEBIL", 422,
                                  problemas=problemas)

        # PBKDF2 de 600.000 iteraciones (~0,5 s de CPU): fuera del event loop
        nuevo_hash = await asyncio.to_thread(hash_password, password)

        # Un solo uso, también ante dos peticiones simultáneas: solo una cambia la fila
        marcado = (await self.db.execute(
            update(TokenActivacion)
            .where(TokenActivacion.id == fila.id, TokenActivacion.fecha_uso.is_(None),
                   TokenActivacion.fecha_revocacion.is_(None))
            .values(fecha_uso=ahora)
            .execution_options(synchronize_session=False)
        )).rowcount
        if marcado != 1:
            await self.db.rollback()
            raise await self._rechazar(fila, "usado")

        usuario.password_hash = nuevo_hash
        usuario.estado = EstadoUsuarioDefinitivo.ACTIVO.value
        usuario.fecha_activacion = ahora
        self.bitacora.registrar(
            accion=Accion.ACTIVACION_USADA, entidad="usuario_definitivo", entidad_id=usuario.id,
            actor_rol="cliente", actor_id=usuario.id, detalle={"token_activacion_id": fila.id}, fecha=ahora,
        )
        await self.db.commit()
        return {"activado": True, "mensaje": "Tu cuenta quedó activa. Ya puedes iniciar sesión."}
