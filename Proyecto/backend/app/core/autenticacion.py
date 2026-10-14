"""
Autenticación y roles de la API (punto ÚNICO de identidad del backend).

Hasta ahora el backend no autenticaba a nadie; el frontend ya trabaja con un
token "bearer" y dos roles (ver frontend/js/store.js):
  - referente      -> usuario de la plataforma (usuario_temporal). Es el TITULAR
                      de sus datos personales en las solicitudes ARCOP.
  - admin_therion  -> equipo Therion; gestiona y resuelve solicitudes.

Este módulo reutiliza esos mismos roles. El token es un HMAC-SHA256 firmado con
AUTH_SECRET (solo librería estándar, sin dependencias nuevas):

    base64url(json {"sub": <id>, "rol": <rol>, "exp": <epoch>}) . base64url(firma)

Cuando exista el login real (p. ej. POST /api/auth/login), basta con emitir el
token con `emitir_token()` o reemplazar `obtener_actor()`: las rutas solo
dependen de `Actor`, `obtener_actor` y `requerir_rol`.

Emitir un token de prueba (desarrollo):
    python -m app.core.autenticacion --usuario 1 --rol referente
    python -m app.core.autenticacion --usuario 1 --rol admin_therion
"""
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from enum import Enum

from fastapi import Depends, Header, HTTPException

from app.core.config import settings


class Rol(str, Enum):
    REFERENTE = "referente"
    ADMIN_THERION = "admin_therion"

    @classmethod
    def valores(cls) -> list[str]:
        return [r.value for r in cls]


@dataclass(frozen=True)
class Actor:
    """Quién hace la petición. `id` es usuario_temporal.id para el rol referente."""
    id: int
    rol: str

    @property
    def es_admin(self) -> bool:
        return self.rol == Rol.ADMIN_THERION.value


class TokenInvalidoError(Exception):
    pass


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


_NO_AUTENTICADO = {"WWW-Authenticate": "Bearer"}


async def obtener_actor(authorization: str | None = Header(None)) -> Actor:
    """Dependencia de FastAPI: exige `Authorization: Bearer <token>`."""
    if not settings.AUTH_SECRET:
        raise HTTPException(
            status_code=503,
            detail={"codigo": "AUTH_NO_CONFIGURADA", "mensaje": "AUTH_SECRET no está configurado en el servidor."},
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={"codigo": "NO_AUTENTICADO", "mensaje": "Falta el token (Authorization: Bearer ...)."},
            headers=_NO_AUTENTICADO,
        )
    try:
        return verificar_token(authorization[7:].strip(), settings.AUTH_SECRET)
    except TokenInvalidoError as e:
        raise HTTPException(
            status_code=401,
            detail={"codigo": "TOKEN_INVALIDO", "mensaje": str(e)},
            headers=_NO_AUTENTICADO,
        )


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

    p = argparse.ArgumentParser(description="Emite un token de acceso de prueba.")
    p.add_argument("--usuario", type=int, required=True, help="usuario_temporal.id (o id del admin)")
    p.add_argument("--rol", choices=Rol.valores(), required=True)
    p.add_argument("--ttl", type=int, default=None, help="minutos de validez")
    a = p.parse_args()
    print(emitir_token(a.usuario, a.rol, a.ttl))
