"""
HU-28 criterio 1: recuperación de contraseña del administrador y del usuario definitivo.

  1. POST /api/auth/recuperacion {tipo, email}: si el correo es de una cuenta ACTIVA del
     tipo indicado, se emite un enlace de un solo uso que vence en RECUPERACION_TTL_MIN y
     se envía por correo. La respuesta es SIEMPRE la misma (202) exista o no la cuenta, y
     el correo sale en segundo plano, después de responder, para que el tiempo de
     respuesta tampoco lo revele.
  2. POST /api/auth/recuperacion/verificar {token}: comprueba el enlace sin consumirlo.
  3. POST /api/auth/recuperacion/restablecer {token, password}: define la contraseña nueva
     con las reglas de HU-27, marca el enlace como usado (UPDATE condicional: dos clics
     simultáneos no lo usan dos veces), cierra TODAS las sesiones abiertas de la cuenta,
     reinicia su contador de intentos fallidos y avisa por correo que la contraseña cambió.

Igual que la activación (HU-27): el token va en el fragmento de la URL (#token=...), en la
BD solo queda su SHA-256, pedir uno nuevo revoca los anteriores y todo queda en la
bitácora sin correos, nombres ni tokens.

Solo para cuentas que ya tienen contraseña: un usuario definitivo que aún no activa su
cuenta usa su enlace de activación (o pide uno nuevo a Therion Labs).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.domain.ports.correo_port import CorreoNoDisponibleError
from app.application.cuentas.casos_uso.activacion_cuenta import (
    ActivacionError, generar_token, hash_token, validar_contrasena,
)
from app.application.cuentas.casos_uso.sesiones import cerrar_todas
from app.domain.auth.actor import Rol
from app.application.seguridad.huella import huella
from app.application.fabricas import fabricas
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.sesion_modelo import MotivoCierre, TokenRecuperacion
from app.domain.ports.limitador_port import Limitador
from app.domain.auditoria.acciones import ROL_ANONIMO, Accion

logger = logging.getLogger("seguridad")

_FORMATO_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")

# tipo de la API -> (rol de la sesión, entidad de la bitácora)
TIPOS = {
    "cliente": (Rol.CLIENTE.value, "usuario_definitivo"),
    "admin": (Rol.ADMIN_THERION.value, "usuarios_admin"),
}
_TIPO_DE_ROL = {rol: tipo for tipo, (rol, _) in TIPOS.items()}

MENSAJE_SOLICITUD = (
    "Si el correo corresponde a una cuenta activa, te enviamos un enlace para restablecer tu "
    "contraseña. Revisa tu bandeja de entrada (y la carpeta de spam)."
)


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def url_recuperacion(token: str) -> str:
    return f"{settings.RECUPERACION_URL_BASE.rstrip('#')}#token={token}"


@dataclass(frozen=True)
class CorreoPendiente:
    """Lo que necesita la tarea en segundo plano para enviar el correo (después de responder)."""
    destino: str
    asunto: str
    texto: str
    html: str


def _marco_html(titulo: str, cuerpo: str) -> str:
    return f"""<!doctype html><html lang="es"><body style="margin:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#14201b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;border-top:4px solid #0b7a5a">
<tr><td style="padding:28px">
<p style="margin:0 0 4px;font-size:12px;color:#5b6b64">ComplianceIA · Therion Labs</p>
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">{titulo}</h1>
{cuerpo}
</td></tr></table>
</td></tr></table></body></html>"""


def cuerpo_recuperacion(url: str, minutos: int) -> tuple[str, str]:
    """(texto, html) del correo con el enlace. No lleva el nombre: el enlace basta."""
    from html import escape

    texto = (
        "Hola:\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta de ComplianceIA.\n\n"
        "Para definir una contraseña nueva, abre este enlace:\n"
        f"{url}\n\n"
        f"El enlace sirve una sola vez y vence en {minutos} minutos.\n"
        "Si no fuiste tú, ignora este mensaje: tu contraseña actual sigue funcionando.\n"
        "Nunca te pediremos tu contraseña por correo.\n\n"
        "ComplianceIA · Therion Labs\n"
    )
    u = escape(url, quote=True)
    html = _marco_html("Restablece tu contraseña", f"""
<p style="margin:0 0 16px;font-size:15px;line-height:1.5">Recibimos una solicitud para restablecer la contraseña de tu cuenta de ComplianceIA.</p>
<p style="margin:0 0 20px"><a href="{u}" style="display:inline-block;background:#0b7a5a;color:#ffffff;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:bold">Definir una contraseña nueva</a></p>
<p style="margin:0 0 8px;font-size:13px;line-height:1.5;color:#3d4b45">El enlace sirve una sola vez y vence en {minutos} minutos.</p>
<p style="margin:0;font-size:12px;line-height:1.5;color:#5b6b64">Si no fuiste tú, ignora este mensaje: tu contraseña actual sigue funcionando. Nunca te pediremos tu contraseña por correo.</p>""")
    return texto, html


def cuerpo_aviso_cambio() -> tuple[str, str]:
    texto = (
        "Hola:\n\n"
        "La contraseña de tu cuenta de ComplianceIA se acaba de cambiar y cerramos todas las "
        "sesiones abiertas.\n\n"
        "Si no fuiste tú, escríbenos de inmediato a Therion Labs.\n\n"
        "ComplianceIA · Therion Labs\n"
    )
    html = _marco_html("Tu contraseña cambió", """
<p style="margin:0 0 12px;font-size:15px;line-height:1.5">La contraseña de tu cuenta de ComplianceIA se acaba de cambiar y cerramos todas las sesiones abiertas.</p>
<p style="margin:0;font-size:13px;line-height:1.5;color:#3d4b45">Si no fuiste tú, escríbenos de inmediato a Therion Labs.</p>""")
    return texto, html


async def enviar_en_segundo_plano(pendiente: CorreoPendiente) -> None:
    """Tarea de fondo (BackgroundTasks). No toca la BD: el pedido ya quedó en la bitácora."""
    try:
        await fabricas().correo.enviar(pendiente.destino, pendiente.asunto, pendiente.texto, pendiente.html, [])
    except CorreoNoDisponibleError:
        logger.warning("Recuperación de contraseña: el correo no está habilitado (CORREO_MODO)")
    except Exception as e:  # noqa: BLE001  (nunca debe romper la respuesta ya enviada)
        logger.warning("No se pudo enviar un correo de recuperación (%s)", type(e).__name__)


class RecuperacionContrasenaUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitacora = fabricas().bitacora(db)

    async def _cuenta(self, rol: str, *, email: str | None = None, cuenta_id: int | None = None):
        cuentas = fabricas().cuentas(self.db)
        if cuenta_id is not None:
            return await cuentas.cuenta_con_contrasena_por_id(rol, cuenta_id)
        return await cuentas.cuenta_con_contrasena_por_email(rol, email)

    @staticmethod
    def _activa(cuenta) -> bool:
        # admin: activo; cliente: estado 'activo' y con contraseña (ver UsuarioDefinitivo.activo)
        return bool(cuenta is not None and cuenta.activo and cuenta.password_hash)

    # ------------------------------------------------------------ 1. solicitar
    async def solicitar(self, tipo: str, email: str, limitador: Limitador | None) -> CorreoPendiente | None:
        """
        Devuelve el correo a enviar, o None si no corresponde enviar nada. Quien llama responde
        lo mismo en ambos casos. Hace commit (la bitácora registra el pedido).
        """
        rol, entidad = TIPOS[tipo]
        email = (email or "").strip().lower()
        ahora = _ahora()

        # Correos por cuenta y hora: pasado el límite no se envía nada (y se responde igual)
        if limitador is not None:
            consumo = await limitador.consumir(f"rec:{tipo}:em:{huella(email)}",
                                               settings.RECUPERACION_CORREOS_CUENTA_HORA, 3600)
            if not consumo.permitido:
                self._registrar_pedido(tipo, entidad, None, "limite_por_cuenta", ahora)
                await self.db.commit()
                return None

        cuenta = await self._cuenta(rol, email=email) if email else None
        if not self._activa(cuenta):
            self._registrar_pedido(tipo, entidad, cuenta.id if cuenta else None, "sin_cuenta_activa", ahora)
            await self.db.commit()
            return None

        tokens = fabricas().tokens_cuenta(self.db)
        await tokens.revocar_recuperaciones_vigentes(rol, cuenta.id, ahora)
        token, digest = generar_token()
        fila = TokenRecuperacion(
            actor_rol=rol, actor_id=cuenta.id, token_hash=digest, fecha_creacion=ahora,
            fecha_expiracion=ahora + timedelta(minutes=settings.RECUPERACION_TTL_MIN),
        )
        await tokens.agregar_recuperacion(fila)
        self.bitacora.registrar(
            accion=Accion.RECUPERACION_SOLICITADA, entidad=entidad, entidad_id=cuenta.id, actor_rol=ROL_ANONIMO,
            detalle={"tipo": tipo, "token_recuperacion_id": fila.id, "vence_min": settings.RECUPERACION_TTL_MIN},
            fecha=ahora,
        )
        await self.db.commit()
        texto, html = cuerpo_recuperacion(url_recuperacion(token), settings.RECUPERACION_TTL_MIN)
        return CorreoPendiente(cuenta.email, "Restablece tu contraseña de ComplianceIA", texto, html)

    def _registrar_pedido(self, tipo: str, entidad: str, entidad_id: int | None, motivo: str,
                          ahora: datetime) -> None:
        self.bitacora.registrar(
            accion=Accion.RECUPERACION_SOLICITADA, entidad=entidad, entidad_id=entidad_id, actor_rol=ROL_ANONIMO,
            resultado=RESULTADO_RECHAZADO, detalle={"tipo": tipo, "motivo": motivo}, fecha=ahora,
        )

    # ------------------------------------------------------------ 2 y 3. usar el enlace
    async def _buscar(self, token: str) -> tuple[TokenRecuperacion | None, object | None]:
        if not token or not _FORMATO_TOKEN.match(token):
            return None, None
        fila = await fabricas().tokens_cuenta(self.db).recuperacion_por_hash(hash_token(token))
        if fila is None:
            return None, None
        return fila, await self._cuenta(fila.actor_rol, cuenta_id=fila.actor_id)

    def _motivo_invalido(self, fila: TokenRecuperacion | None, cuenta, ahora: datetime) -> str | None:
        if fila is None or cuenta is None:
            return "inexistente"
        if fila.fecha_uso is not None:
            return "usado"
        if fila.fecha_revocacion is not None:
            return "revocado"
        if fila.fecha_expiracion <= ahora:
            return "vencido"
        if not self._activa(cuenta):
            return "cuenta_no_activa"
        return None

    async def _rechazar(self, fila: TokenRecuperacion | None, motivo: str) -> ActivacionError:
        entidad = TIPOS[_TIPO_DE_ROL[fila.actor_rol]][1] if fila else "token_recuperacion"
        self.bitacora.registrar(
            accion=Accion.RECUPERACION_RECHAZADA, entidad=entidad, entidad_id=fila.actor_id if fila else None,
            actor_rol=ROL_ANONIMO, resultado=RESULTADO_RECHAZADO,
            detalle={"motivo": motivo, "token_recuperacion_id": fila.id if fila else None},
        )
        await self.db.commit()
        logger.warning("Recuperación de contraseña rechazada (%s)", motivo)
        if motivo == "vencido":
            return ActivacionError("El enlace venció. Pide uno nuevo desde «¿Olvidaste tu contraseña?».",
                                   "ENLACE_VENCIDO", 410)
        return ActivacionError(
            "El enlace no es válido o ya se usó. Pide uno nuevo desde «¿Olvidaste tu contraseña?».",
            "ENLACE_INVALIDO", 400,
        )

    async def verificar(self, token: str) -> dict:
        ahora = _ahora()
        fila, cuenta = await self._buscar(token)
        motivo = self._motivo_invalido(fila, cuenta, ahora)
        if motivo:
            raise await self._rechazar(fila, motivo)
        return {
            "valido": True,
            "tipo": _TIPO_DE_ROL[fila.actor_rol],
            "email": correo.enmascarar(cuenta.email),
            "expira": fila.fecha_expiracion.replace(tzinfo=timezone.utc).isoformat(),
            "password_min": settings.CLIENTE_PASSWORD_MIN,
        }

    async def restablecer(self, token: str, password: str,
                          limitador: Limitador | None) -> tuple[dict, CorreoPendiente]:
        ahora = _ahora()
        fila, cuenta = await self._buscar(token)
        motivo = self._motivo_invalido(fila, cuenta, ahora)
        if motivo:
            raise await self._rechazar(fila, motivo)

        nombre = getattr(cuenta, "nombre", "") or ""
        problemas = validar_contrasena(password, cuenta.email, nombre)
        if problemas:  # no consume el enlace: puede corregir y reintentar
            raise ActivacionError("La contraseña no cumple los requisitos.", "CONTRASENA_DEBIL", 422,
                                  problemas=problemas)

        nuevo_hash = await asyncio.to_thread(fabricas().credenciales.hash_password, password)
        tokens = fabricas().tokens_cuenta(self.db)
        marcado = await tokens.marcar_recuperacion_usada(fila.id, ahora)
        if marcado != 1:
            await self.db.rollback()
            raise await self._rechazar(fila, "usado")

        # Los demás enlaces vigentes de la cuenta dejan de servir
        await tokens.revocar_otras_recuperaciones(fila.actor_rol, fila.actor_id, fila.id, ahora)
        cuenta.password_hash = nuevo_hash
        cerradas = await cerrar_todas(self.db, fila.actor_rol, fila.actor_id, MotivoCierre.CAMBIO_CONTRASENA, ahora)
        tipo = _TIPO_DE_ROL[fila.actor_rol]
        self.bitacora.registrar(
            accion=Accion.RECUPERACION_USADA, entidad=TIPOS[tipo][1], entidad_id=fila.actor_id,
            actor_rol=fila.actor_rol, actor_id=fila.actor_id,
            detalle={"token_recuperacion_id": fila.id, "sesiones_cerradas": cerradas}, fecha=ahora,
        )
        await self.db.commit()
        if limitador is not None:
            # Quien recuperó su contraseña puede entrar de inmediato aunque antes la bloqueara
            await limitador.reiniciar(f"login:{tipo}:em:{huella(cuenta.email.strip().lower())}")
        texto, html = cuerpo_aviso_cambio()
        aviso = CorreoPendiente(cuenta.email, "Tu contraseña de ComplianceIA cambió", texto, html)
        return {"restablecido": True, "tipo": tipo,
                "mensaje": "Tu contraseña quedó actualizada. Ya puedes iniciar sesión."}, aviso
