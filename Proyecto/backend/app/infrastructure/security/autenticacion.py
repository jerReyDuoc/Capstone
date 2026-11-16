"""
Contraseñas (PBKDF2) y tokens bearer firmados de la API.

El token es un HMAC-SHA256 firmado con AUTH_SECRET (solo librería estándar):
    base64url(json {"sub": <id>, "rol": <rol>, "exp": <epoch>[, "sid": <sesión>]}) . base64url(firma)

HU-28: los logins con contraseña (admin y cliente) abren una SESIÓN en la BD
(sesion_usuario) y el token lleva su `sid`. Cerrar sesión (POST /api/auth/logout) o
restablecer la contraseña la cierra y el token deja de servir aunque no haya vencido.
Un token de admin o cliente SIN sid solo puede salir de la CLI de pruebas
(app/cli/emitir_token.py) o ser anterior a HU-28: sigue valiendo hasta su `exp`.

Los roles y el `Actor` viven en app/domain/auth/actor.py; la dependencia FastAPI que
exige el token en cada petición, en app/api/dependencias/autenticacion.py.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings
from app.domain.auth.actor import Actor, Rol


class TokenInvalidoError(Exception):
    pass


# ---------------------------------------------------------------- contraseñas
_PBKDF2_ITERACIONES = 600_000


def hash_password(password: str, iteraciones: int = _PBKDF2_ITERACIONES) -> str:
    """Formato: pbkdf2_sha256$<iteraciones>$<sal b64>$<hash b64>"""
    sal = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sal, iteraciones)
    return f"pbkdf2_sha256${iteraciones}${_b64(sal)}${_b64(dk)}"


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        algoritmo, iteraciones, sal, esperado = almacenado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _b64_decode(sal), int(iteraciones))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64(dk), esperado)


# Hash señuelo: se verifica contra él cuando el email no existe, para que la
# respuesta tarde lo mismo y no revele qué correos están registrados.
_HASH_SENUELO: str | None = None


def verificar_password_senuelo(password: str) -> None:
    global _HASH_SENUELO
    if _HASH_SENUELO is None:
        _HASH_SENUELO = hash_password(secrets.token_urlsafe(16))
    verificar_password(password, _HASH_SENUELO)


# ---------------------------------------------------------------- tokens
def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _b64_decode(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _firmar(cuerpo: str, secreto: str) -> str:
    return _b64(hmac.new(secreto.encode("utf-8"), cuerpo.encode("ascii"), hashlib.sha256).digest())


def emitir_token(usuario_id: int, rol: str, ttl_min: int | None = None, secreto: str | None = None,
                 sid: str | None = None) -> str:
    secreto = secreto or settings.AUTH_SECRET
    if not secreto:
        raise RuntimeError("AUTH_SECRET no está configurado.")
    if rol not in Rol.valores():
        raise ValueError(f"Rol inválido. Debe ser uno de: {', '.join(Rol.valores())}")
    ttl = ttl_min if ttl_min is not None else settings.AUTH_TOKEN_TTL_MIN
    payload = {"sub": int(usuario_id), "rol": rol, "exp": int(time.time()) + ttl * 60}
    if sid:
        payload["sid"] = sid
    cuerpo = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{cuerpo}.{_firmar(cuerpo, secreto)}"


def verificar_token(token: str, secreto: str) -> Actor:
    try:
        cuerpo, firma = token.split(".", 1)
    except ValueError:
        raise TokenInvalidoError("Formato de token inválido")
    if not hmac.compare_digest(firma, _firmar(cuerpo, secreto)):
        raise TokenInvalidoError("Firma de token inválida")
    try:
        payload = json.loads(_b64_decode(cuerpo))
        sub, rol, exp = int(payload["sub"]), str(payload["rol"]), int(payload["exp"])
        sid = payload.get("sid")
        if sid is not None and (not isinstance(sid, str) or not 16 <= len(sid) <= 64):
            raise ValueError("sid")
    except (ValueError, KeyError, TypeError):
        raise TokenInvalidoError("Contenido de token inválido")
    if exp < time.time():
        raise TokenInvalidoError("Token expirado")
    if rol not in Rol.valores():
        raise TokenInvalidoError("Rol desconocido")
    return Actor(id=sub, rol=rol, sid=sid)


class CredencialesPBKDF2:
    """Adaptador de `CredencialesPort`: delega en las funciones de este módulo."""

    def hash_password(self, password: str, iteraciones: int = _PBKDF2_ITERACIONES) -> str:
        return hash_password(password, iteraciones)

    def verificar_password(self, password: str, almacenado: str) -> bool:
        return verificar_password(password, almacenado)

    def verificar_password_senuelo(self, password: str) -> None:
        verificar_password_senuelo(password)

    def emitir_token(self, usuario_id: int, rol: str, ttl_min: int | None = None, secreto: str | None = None,
                     sid: str | None = None) -> str:
        return emitir_token(usuario_id, rol, ttl_min=ttl_min, secreto=secreto, sid=sid)
