"""
Autenticación y roles de la API (punto ÚNICO de identidad del backend).

Roles (referente y admin_therion son los mismos que usa el frontend):
  - referente      -> usuario temporal invitado (sub = usuario_temporal.id).
  - encuestado     -> encuestado anónimo de la encuesta pública (sub = evaluacion.id).
  - admin_therion  -> administrador (sub = usuarios_admin.id). Gestiona las solicitudes.
  - cliente        -> usuario definitivo de una empresa cliente (sub = usuario_definitivo.id).
                      HU-27: rol único del servicio pagado; ve las evaluaciones migradas
                      a su empresa. NO es titular ARCOP (no usa esas rutas).
referente y encuestado son TITULARES de sus datos en las solicitudes ARCOP.

Cómo se obtiene el token (app/api/routes/auth.py):
  - Invitado:   POST /api/auth/titular     {usuario_temporal_id, email}
  - Encuestado: POST /api/auth/encuestado  {evaluacion_id, clave}
  - Admin:      POST /api/auth/login       {email, password}
  - Cliente:    POST /api/auth/cliente     {email, password}  (HU-27, tras activar la cuenta)

El token es un HMAC-SHA256 firmado con AUTH_SECRET (solo librería estándar):
    base64url(json {"sub": <id>, "rol": <rol>, "exp": <epoch>}) . base64url(firma)

En cada petición se comprueba además en BD que el usuario siga habilitado
(admin activo / titular no anonimizado / evaluación con clave vigente / cliente activo con
contrato vigente), así desactivar a alguien corta su acceso
sin esperar a que expire el token.

Token de prueba sin pasar por el login (solo desarrollo):
    python -m app.core.autenticacion --usuario 1 --rol referente
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from enum import Enum

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db


class Rol(str, Enum):
    REFERENTE = "referente"
    ENCUESTADO = "encuestado"
    ADMIN_THERION = "admin_therion"
    CLIENTE = "cliente"  # HU-27

    @classmethod
    def valores(cls) -> list[str]:
        return [r.value for r in cls]


@dataclass(frozen=True)
class Actor:
    """
    Quién hace la petición. `id` es usuario_temporal.id (referente),
    evaluacion.id (encuestado), usuarios_admin.id (admin) o usuario_definitivo.id (cliente).
    """
    id: int
    rol: str

    @property
    def es_admin(self) -> bool:
        return self.rol == Rol.ADMIN_THERION.value

    @property
    def es_encuestado(self) -> bool:
        return self.rol == Rol.ENCUESTADO.value

    @property
    def es_cliente(self) -> bool:
        return self.rol == Rol.CLIENTE.value


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


def emitir_token(usuario_id: int, rol: str, ttl_min: int | None = None, secreto: str | None = None) -> str:
    secreto = secreto or settings.AUTH_SECRET
    if not secreto:
        raise RuntimeError("AUTH_SECRET no está configurado.")
    if rol not in Rol.valores():
        raise ValueError(f"Rol inválido. Debe ser uno de: {', '.join(Rol.valores())}")
    ttl = ttl_min if ttl_min is not None else settings.AUTH_TOKEN_TTL_MIN
    payload = {"sub": int(usuario_id), "rol": rol, "exp": int(time.time()) + ttl * 60}
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
    except (ValueError, KeyError, TypeError):
        raise TokenInvalidoError("Contenido de token inválido")
    if exp < time.time():
        raise TokenInvalidoError("Token expirado")
    if rol not in Rol.valores():
        raise TokenInvalidoError("Rol desconocido")
    return Actor(id=sub, rol=rol)


# ---------------------------------------------------------------- dependencias FastAPI
_NO_AUTENTICADO = {"WWW-Authenticate": "Bearer"}

# Esquema de seguridad: lee el header Authorization y hace que Swagger (/docs)
# muestre el botón "Authorize". auto_error=False -> los errores los damos nosotros.
_bearer = HTTPBearer(
    auto_error=False,
    description="Token de /api/auth/login, /api/auth/titular, /api/auth/encuestado o /api/auth/cliente "
                "(sin la palabra Bearer)",
)


def _no_autorizado(codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"codigo": codigo, "mensaje": mensaje}, headers=_NO_AUTENTICADO)


async def _sigue_habilitado(actor: Actor, db: AsyncSession) -> bool:
    # imports locales: evitan ciclos (los modelos importan app.core.database)
    if actor.es_admin:
        from app.domain.models.usuario_admin import UsuarioAdmin
        admin = await db.get(UsuarioAdmin, actor.id)
        return bool(admin and admin.activo)
    if actor.es_encuestado:
        from app.domain.models.evaluacion import Evaluacion
        evaluacion = await db.get(Evaluacion, actor.id)
        return bool(evaluacion and evaluacion.clave_acceso_hash)
    if actor.es_cliente:
        from app.domain.models.empresa import Empresa
        from app.domain.models.usuario_definitivo import UsuarioDefinitivo
        usuario = await db.get(UsuarioDefinitivo, actor.id)
        if not (usuario and usuario.activo):
            return False
        empresa = await db.get(Empresa, usuario.empresa_id)
        return bool(empresa and empresa.contrato_vigente())
    from app.domain.models.usuario_temporal import UsuarioTemporal
    usuario = await db.get(UsuarioTemporal, actor.id)
    return bool(usuario and usuario.fecha_anonimizacion is None)


async def obtener_actor(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    """Exige `Authorization: Bearer <token>` válido y un usuario aún habilitado."""
    if not settings.AUTH_SECRET:
        raise HTTPException(
            status_code=503,
            detail={"codigo": "AUTH_NO_CONFIGURADA", "mensaje": "AUTH_SECRET no está configurado en el servidor."},
        )
    if credenciales is None or not credenciales.credentials:
        raise _no_autorizado("NO_AUTENTICADO", "Falta el token (Authorization: Bearer ...).")
    try:
        actor = verificar_token(credenciales.credentials.strip(), settings.AUTH_SECRET)
    except TokenInvalidoError as e:
        raise _no_autorizado("TOKEN_INVALIDO", str(e))
    if not await _sigue_habilitado(actor, db):
        raise _no_autorizado("USUARIO_DESHABILITADO", "El usuario del token ya no está habilitado.")
    return actor


def requerir_rol(*roles: Rol):
    """Dependencia que además exige uno de los roles indicados (403 si no)."""
    permitidos = {r.value for r in roles}

    async def _dep(actor: Actor = Depends(obtener_actor)) -> Actor:
        if actor.rol not in permitidos:
            raise HTTPException(
                status_code=403,
                detail={
                    "codigo": "NO_AUTORIZADO",
                    "mensaje": f"Requiere rol: {', '.join(sorted(permitidos))}",
                },
            )
        return actor

    return _dep


if __name__ == "__main__":  # emisión de tokens de prueba
    import argparse

    p = argparse.ArgumentParser(description="Emite un token de acceso de prueba (solo desarrollo).")
    p.add_argument("--usuario", type=int, required=True,
                   help="usuario_temporal.id, evaluacion.id (encuestado), usuarios_admin.id "
                        "o usuario_definitivo.id (cliente)")
    p.add_argument("--rol", choices=Rol.valores(), required=True)
    p.add_argument("--ttl", type=int, default=None, help="minutos de validez")
    a = p.parse_args()
    print(emitir_token(a.usuario, a.rol, a.ttl))
