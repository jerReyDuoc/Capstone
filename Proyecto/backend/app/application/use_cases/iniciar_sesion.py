"""
Emisión de tokens de acceso (ver app/core/autenticacion.py).

  - Admin:   email + contraseña contra usuarios_admin (hash PBKDF2).
  - Titular: usuario_temporal_id + email de la invitación; la invitación no debe
             estar expirada ni el usuario anonimizado.
  - Encuestado anónimo (encuesta pública): evaluacion_id + clave de acceso de la
             evaluación (ver clave_acceso_encuestado.py).
  - Cliente (HU-27): email + contraseña del usuario definitivo, que la definió con su
             enlace de activación. Exige cuenta activa y contrato de la empresa vigente.

Los errores son deliberadamente genéricos ("credenciales inválidas") para no
revelar si un email o id existe.

HU-28 (admin y cliente, los dos logins con contraseña):
  - Abren una sesión revocable (sesiones.py): el token lleva su sid.
  - Intentos FALLIDOS limitados por cuenta y por IP (ProteccionLogin). La cuenta se
    identifica por la huella del correo escrito, exista o no: bloquear solo los correos
    que existen revelaría cuáles existen. Entrar bien reinicia el contador de la cuenta.
  - Cada intento queda en la bitácora: exitoso, fallido (con su motivo) o bloqueado.
    Nunca el correo escrito ni la contraseña; solo el id de la cuenta si existe.
"""
import asyncio
import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import (
    Rol, emitir_token, verificar_password, verificar_password_senuelo,
)
from app.core.cliente import huella
from app.core.config import settings
from app.application.use_cases.clave_acceso_encuestado import verificar_clave
from app.application.use_cases.sesiones import abrir_sesion
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.usuario_admin import UsuarioAdmin
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.cache.limitador import Limitador
from app.infrastructure.repositories.bitacora_repository import ROL_ANONIMO, Accion, BitacoraRepository

logger = logging.getLogger("seguridad")


class CredencialesInvalidasError(Exception):
    pass


class ContratoNoVigenteError(Exception):
    """Ya no se lanza desde HU-30 (el cliente entra sin contrato vigente); se conserva por compatibilidad."""


class DemasiadosIntentosError(Exception):
    """HU-28: la cuenta o la IP superaron los intentos fallidos permitidos."""

    def __init__(self, reintentar_en_s: int):
        super().__init__(
            "Demasiados intentos fallidos. Por seguridad, espera unos minutos antes de volver a intentarlo."
        )
        self.reintentar_en_s = max(1, int(reintentar_en_s))


class ProteccionLogin:
    """
    HU-28 criterio 3: límite de intentos FALLIDOS de inicio de sesión.

    Ventana fija de LOGIN_VENTANA_FALLOS_MIN: con LOGIN_MAX_FALLOS_CUENTA fallos sobre el
    mismo correo, o LOGIN_MAX_FALLOS_IP desde la misma IP, se rechaza (429) hasta que la
    ventana termine, aunque la contraseña sea correcta. Las claves llevan huellas HMAC:
    ni el correo ni la IP quedan en claro en Redis.

    Si Redis no responde, el limitador lanza LimitadorNoDisponibleError y la ruta responde
    503 (falla "cerrado", como los demás límites del sistema).
    """

    def __init__(self, limitador: Limitador | None, tipo: str, email: str, ip: str | None):
        self.limitador = limitador
        self.ventana_s = settings.LOGIN_VENTANA_FALLOS_MIN * 60
        self.clave_cuenta = f"login:{tipo}:em:{huella(email)}"
        self.reglas = [(self.clave_cuenta, settings.LOGIN_MAX_FALLOS_CUENTA)]
        if ip:
            self.reglas.append((f"login:{tipo}:ip:{huella(ip)}", settings.LOGIN_MAX_FALLOS_IP))

    async def verificar(self) -> None:
        if self.limitador is None:
            return
        esperas = [await self.limitador.restante_s(clave) for clave, maximo in self.reglas
                   if await self.limitador.usados(clave) >= maximo]
        if esperas:
            raise DemasiadosIntentosError(max(esperas) or self.ventana_s)

    async def registrar_fallo(self) -> bool:
        """Cuenta el fallo. True si con él la cuenta o la IP quedaron bloqueadas."""
        if self.limitador is None:
            return False
        bloqueada = False
        for clave, maximo in self.reglas:
            consumo = await self.limitador.consumir(clave, maximo, self.ventana_s)
            bloqueada = bloqueada or consumo.usados >= maximo
        return bloqueada

    async def registrar_exito(self) -> None:
        if self.limitador is not None:
            await self.limitador.reiniciar(self.clave_cuenta)


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def _respuesta(usuario_id: int, rol: Rol, token: str | None = None, **extra) -> dict:
    return {
        "access_token": token or emitir_token(usuario_id, rol.value),
        "token_type": "bearer",
        "rol": rol.value,
        "usuario_id": usuario_id,
        "expira_en_min": settings.AUTH_TOKEN_TTL_MIN,
        **extra,
    }


class IniciarSesionUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------ HU-28: comunes
    def _auditar_intento(self, tipo: str, entidad: str, entidad_id: int | None, motivo: str,
                         accion: str = Accion.LOGIN_FALLIDO, **extra) -> None:
        BitacoraRepository(self.db).registrar(
            accion=accion, entidad=entidad, entidad_id=entidad_id, actor_rol=ROL_ANONIMO,
            resultado=RESULTADO_RECHAZADO, detalle={"tipo": tipo, "motivo": motivo, **extra},
        )

    async def _bloqueo_previo(self, proteccion: ProteccionLogin, tipo: str, entidad: str) -> None:
        try:
            await proteccion.verificar()
        except DemasiadosIntentosError:
            self._auditar_intento(tipo, entidad, None, "demasiados_intentos", accion=Accion.LOGIN_BLOQUEADO)
            await self.db.commit()
            logger.warning("Inicio de sesión de %s bloqueado por intentos fallidos", tipo)
            raise

    async def _fallo(self, proteccion: ProteccionLogin, tipo: str, entidad: str, entidad_id: int | None) -> None:
        bloqueada = await proteccion.registrar_fallo()
        self._auditar_intento(tipo, entidad, entidad_id, "credenciales", bloqueo_activado=bloqueada)
        await self.db.commit()
        logger.warning("Login de %s fallido", tipo)
        raise CredencialesInvalidasError("Credenciales inválidas.")

    async def admin(self, email: str, password: str, limitador: Limitador | None = None,
                    ip: str | None = None) -> dict:
        email = _normalizar_email(email)
        proteccion = ProteccionLogin(limitador, "admin", email, ip)
        await self._bloqueo_previo(proteccion, "admin", "usuarios_admin")
        result = await self.db.execute(
            select(UsuarioAdmin).where(func.lower(UsuarioAdmin.email) == email)
        )
        admin = result.scalar_one_or_none()
        if admin is None:
            await asyncio.to_thread(verificar_password_senuelo, password or "")
            ok = False
        else:
            # PBKDF2 de 600.000 iteraciones: fuera del event loop
            ok = await asyncio.to_thread(verificar_password, password or "", admin.password_hash) and admin.activo
        if not ok:
            await self._fallo(proteccion, "admin", "usuarios_admin", admin.id if admin else None)
        await proteccion.registrar_exito()
        ahora = _ahora()
        token, sesion = await abrir_sesion(self.db, Rol.ADMIN_THERION.value, admin.id, ahora)
        admin.ultimo_acceso = ahora
        BitacoraRepository(self.db).registrar(
            accion=Accion.ADMIN_LOGIN, entidad="usuarios_admin", entidad_id=admin.id,
            actor_rol=Rol.ADMIN_THERION.value, actor_id=admin.id, detalle={"sesion_id": sesion.id}, fecha=ahora,
        )
        await self.db.commit()
        return _respuesta(admin.id, Rol.ADMIN_THERION, token)

    async def titular(self, usuario_temporal_id: int, email: str) -> dict:
        usuario = await self.db.get(UsuarioTemporal, usuario_temporal_id)
        valido = (
            usuario is not None
            and usuario.fecha_anonimizacion is None
            and usuario.email is not None
            and usuario.email.strip().lower() == _normalizar_email(email)
            and (usuario.fecha_expiracion is None or usuario.fecha_expiracion >= date.today())
        )
        if valido:
            # HU-19: el usuario anónimo de la encuesta pública entra solo con su clave
            # (POST /api/auth/encuestado); su email opcional no lo convierte en "referente".
            publica = await self.db.scalar(
                select(Evaluacion.id).where(
                    Evaluacion.usuario_temporal_id == usuario.id,
                    Evaluacion.origen == ORIGEN_PUBLICA,
                ).limit(1)
            )
            valido = publica is None
        if not valido:
            raise CredencialesInvalidasError(
                "Credenciales inválidas o invitación expirada."
            )
        return _respuesta(usuario.id, Rol.REFERENTE)

    async def encuestado(self, evaluacion_id: int, clave: str) -> dict:
        evaluacion = await self.db.get(Evaluacion, evaluacion_id)
        almacenado = evaluacion.clave_acceso_hash if evaluacion else None
        if almacenado is None:
            verificar_password_senuelo(clave or "")  # mismo tiempo de respuesta
            ok = False
        else:
            ok = verificar_clave(clave, almacenado)
        if not ok:
            logger.warning("Acceso de encuestado fallido (evaluacion=%s)", evaluacion_id)
            raise CredencialesInvalidasError("Credenciales inválidas.")
        return _respuesta(evaluacion.id, Rol.ENCUESTADO)

    async def cliente(self, email: str, password: str, limitador: Limitador | None = None,
                      ip: str | None = None) -> dict:
        """HU-27/HU-28: login del usuario definitivo (rol cliente)."""
        from app.domain.models.empresa import Empresa
        from app.domain.models.usuario_definitivo import UsuarioDefinitivo

        email = _normalizar_email(email)
        proteccion = ProteccionLogin(limitador, "cliente", email, ip)
        await self._bloqueo_previo(proteccion, "cliente", "usuario_definitivo")
        usuario = await self.db.scalar(
            select(UsuarioDefinitivo).where(func.lower(UsuarioDefinitivo.email) == email)
        )
        if usuario is None or not usuario.password_hash:
            # Mismo tiempo de respuesta exista o no (y aunque aún no active su cuenta)
            await asyncio.to_thread(verificar_password_senuelo, password or "")
            ok = False
        else:
            ok = await asyncio.to_thread(verificar_password, password or "", usuario.password_hash) and usuario.activo
        if not ok:
            await self._fallo(proteccion, "cliente", "usuario_definitivo", usuario.id if usuario else None)
        await proteccion.registrar_exito()
        # HU-30: sin contrato vigente el cliente SÍ entra (conserva lo gratuito, sus documentos
        # en el plazo de gracia y sus derechos ARCOP); el servicio pagado responde 403
        # CONTRATO_NO_VIGENTE. La respuesta trae la situación para que el frontend la muestre.
        empresa = await self.db.get(Empresa, usuario.empresa_id)
        vigencia = empresa.vigencia() if empresa else None
        ahora = _ahora()
        token, sesion = await abrir_sesion(self.db, Rol.CLIENTE.value, usuario.id, ahora)
        usuario.ultimo_acceso = ahora
        BitacoraRepository(self.db).registrar(
            accion=Accion.CLIENTE_LOGIN, entidad="usuario_definitivo", entidad_id=usuario.id,
            actor_rol=Rol.CLIENTE.value, actor_id=usuario.id,
            detalle={"empresa_id": usuario.empresa_id, "sesion_id": sesion.id,
                     "situacion_contrato": vigencia.situacion.value if vigencia else None}, fecha=ahora,
        )
        await self.db.commit()
        return _respuesta(usuario.id, Rol.CLIENTE, token, empresa_id=usuario.empresa_id,
                          contrato=vigencia.como_dict() if vigencia else None)
