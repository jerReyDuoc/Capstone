"""
Dependencias FastAPI de autenticación y roles (punto ÚNICO de identidad de la API).

Cómo se obtiene el token (app/api/routes/auth.py):
  - Invitado:   POST /api/auth/titular     {usuario_temporal_id, email}
  - Encuestado: POST /api/auth/encuestado  {evaluacion_id, clave}
  - Admin:      POST /api/auth/login       {email, password}
  - Cliente:    POST /api/auth/cliente     {email, password}  (HU-27, tras activar la cuenta)
  - Auditor:    POST /api/auth/auditor     {email, password}  (HU-09, cuenta creada por un admin)

En cada petición se comprueba además en BD que el usuario siga habilitado
(admin activo / titular no anonimizado / evaluación con clave vigente / cliente activo con
contrato vigente), así desactivar a alguien corta su acceso
sin esperar a que expire el token.

Roles y Actor: app/domain/auth/actor.py. Firma y verificación del token:
app/infrastructure/security/autenticacion.py.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.domain.auth.actor import Actor, Rol
from app.infrastructure.security.autenticacion import TokenInvalidoError, verificar_token

_NO_AUTENTICADO = {"WWW-Authenticate": "Bearer"}

# Esquema de seguridad: lee el header Authorization y hace que Swagger (/docs)
# muestre el botón "Authorize". auto_error=False -> los errores los damos nosotros.
_bearer = HTTPBearer(
    auto_error=False,
    description="Token de /api/auth/login, /api/auth/titular, /api/auth/encuestado, /api/auth/cliente "
                "o /api/auth/auditor "
                "(sin la palabra Bearer)",
)


def _no_autorizado(codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"codigo": codigo, "mensaje": mensaje}, headers=_NO_AUTENTICADO)


async def _sigue_habilitado(actor: Actor, db: AsyncSession) -> bool:
    # imports locales: evitan ciclos (los modelos importan app.core.database)
    if actor.sid is not None:
        # HU-28: sesión cerrada (logout, cambio de contraseña) o vencida -> token sin efecto
        from app.application.use_cases.sesiones import sesion_vigente
        if not await sesion_vigente(db, actor):
            return False
    if actor.es_admin:
        from app.domain.models.usuario_admin import UsuarioAdmin
        admin = await db.get(UsuarioAdmin, actor.id)
        return bool(admin and admin.activo)
    if actor.es_encuestado:
        from app.domain.models.evaluacion import Evaluacion
        evaluacion = await db.get(Evaluacion, actor.id)
        return bool(evaluacion and evaluacion.clave_acceso_hash)
    if actor.es_cliente:
        # HU-30: el contrato ya no decide si el token sirve. Sin contrato vigente el cliente
        # conserva lo gratuito, sus documentos durante el plazo de gracia y sus derechos
        # ARCOP; el servicio pagado lo cortan las guardas de app/api/dependencias/servicio_pagado.py.
        from app.domain.models.usuario_definitivo import UsuarioDefinitivo
        usuario = await db.get(UsuarioDefinitivo, actor.id)
        return bool(usuario and usuario.activo)
    if actor.es_auditor:
        # HU-09: cuenta activa y no vencida (desactivarla o que venza corta el acceso al instante)
        from datetime import datetime, timezone
        from app.domain.models.auditoria_externa import UsuarioAuditor
        auditor = await db.get(UsuarioAuditor, actor.id)
        return bool(auditor and auditor.vigente(datetime.now(timezone.utc).replace(tzinfo=None)))
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
