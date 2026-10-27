"""
Alcance de las rutas de evaluaciones (HU-19 criterio 2 y HU-20).

HU-20: las respuestas, evidencias y reportes de una organización solo los ven ella misma
(su encuestado o su referente) y los administradores de Therion Labs.

  | Quién                        | Evaluación pública         | Evaluación por invitación          |
  |------------------------------|----------------------------|------------------------------------|
  | admin_therion                | todas                      | todas                              |
  | encuestado (sub = eval id)   | solo la suya (otra -> 404) | ninguna (404)                      |
  | referente (sub = usuario id) | ninguna (404)              | solo las suyas (otra -> 404)       |
  | cliente (HU-27, sub = id del | solo las MIGRADAS a su     | solo las MIGRADAS a su empresa     |
  |   usuario definitivo)        | empresa (otra -> 404)      | (otra -> 404)                      |
  | sin token                    | 401                        | 401 (EXIGIR_TOKEN_EVALUACIONES,    |
  |                              |                            | true por defecto; false solo dev)  |

Se responde 404 (no 403) a lo ajeno para no confirmar que el id existe; los ids son
correlativos y un 403 permitiría enumerarlos. Sin token se responde 401 siempre, exista o
no la evaluación, por la misma razón.

Lo que es solo de Therion Labs (métricas de IA, eventos de seguridad, revisión humana,
marcar evaluaciones de prueba) usa `solo_admin`: 401 sin token y 403 con otro rol.
Catálogos, controles, la landing (encuesta pública) y el aviso legal siguen públicos.
La matriz completa de cada endpoint está en tests/test_hu20_autorizacion.py.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, Rol, obtener_actor, requerir_rol
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion

_bearer_opcional = HTTPBearer(auto_error=False)

_NO_ENCONTRADA = HTTPException(
    status_code=404,
    detail={"codigo": "EVALUACION_NO_ENCONTRADA", "mensaje": "Evaluación no encontrada"},
)


def _exige_token() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"codigo": "NO_AUTENTICADO",
                "mensaje": "Requiere la sesión del encuestado o de un administrador (Authorization: Bearer ...)."},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def actor_opcional(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer_opcional),
    db: AsyncSession = Depends(get_db),
) -> Actor | None:
    """None sin header Authorization; con header, el token DEBE ser válido (si no, 401)."""
    if credenciales is None or not credenciales.credentials:
        return None
    return await obtener_actor(credenciales, db)


async def actor_de_evaluaciones(actor: Actor | None = Depends(actor_opcional)) -> Actor | None:
    """
    Para rutas de evaluaciones sin id (listado, benchmark): exige token salvo que
    EXIGIR_TOKEN_EVALUACIONES=false (solo desarrollo). Devuelve el actor (o None) para
    que la ruta filtre lo que le corresponde ver.
    """
    if actor is None and settings.EXIGIR_TOKEN_EVALUACIONES:
        raise _exige_token()
    return actor


# HU-20: todo lo que es solo de Therion Labs (401 sin token, 403 con otro rol)
solo_admin = requerir_rol(Rol.ADMIN_THERION)


async def empresa_del_cliente(db: AsyncSession, actor: Actor) -> int | None:
    """HU-27: empresa del usuario definitivo del token (None si no es cliente)."""
    if not actor.es_cliente:
        return None
    from app.domain.models.usuario_definitivo import UsuarioDefinitivo

    return await db.scalar(select(UsuarioDefinitivo.empresa_id).where(UsuarioDefinitivo.id == actor.id))


async def verificar_alcance(db: AsyncSession, actor: Actor | None, evaluacion_id: int) -> None:
    if actor is not None and actor.es_admin:
        return
    fila = (
        await db.execute(
            select(Evaluacion.origen, Evaluacion.usuario_temporal_id, Evaluacion.empresa_id)
            .where(Evaluacion.id == evaluacion_id)
        )
    ).first()
    if fila is None:
        # Inexistente: un encuestado/referente recibe el mismo 404 que con una ajena;
        # sin token se deja seguir para que la ruta conserve su respuesta habitual.
        if actor is not None:
            raise _NO_ENCONTRADA
        if settings.EXIGIR_TOKEN_EVALUACIONES:
            raise _exige_token()
        return
    origen, usuario_temporal_id, empresa_id = fila

    if actor is not None and actor.es_cliente:
        # HU-27: el cliente solo ve lo que se migró a SU empresa (lo demás no existe para él).
        if empresa_id is None or empresa_id != await empresa_del_cliente(db, actor):
            raise _NO_ENCONTRADA
        return

    if actor is not None and actor.es_encuestado:
        if actor.id != evaluacion_id:
            raise _NO_ENCONTRADA
        return
    if actor is not None and actor.rol == Rol.REFERENTE.value:
        if origen == ORIGEN_PUBLICA or usuario_temporal_id != actor.id:
            raise _NO_ENCONTRADA
        return
    # sin token
    if origen == ORIGEN_PUBLICA or settings.EXIGIR_TOKEN_EVALUACIONES:
        raise _exige_token()


def _sin_evaluacion(actor: Actor | None) -> None:
    """Respuesta/evidencia inexistente: sin token 401 (no revela si existe), ajeno 404."""
    if actor is None:
        if settings.EXIGIR_TOKEN_EVALUACIONES:
            raise _exige_token()
        return
    if not actor.es_admin:
        raise _NO_ENCONTRADA


# ------------------------------------------------------------ dependencias por tipo de ruta
async def alcance_evaluacion(
    evaluacion_id: int,
    actor: Actor | None = Depends(actor_opcional),
    db: AsyncSession = Depends(get_db),
) -> Actor | None:
    await verificar_alcance(db, actor, evaluacion_id)
    return actor


async def alcance_respuesta(
    respuesta_id: int,
    actor: Actor | None = Depends(actor_opcional),
    db: AsyncSession = Depends(get_db),
) -> Actor | None:
    from app.domain.models.respuesta import Respuesta

    evaluacion_id = await db.scalar(select(Respuesta.evaluacion_id).where(Respuesta.id == respuesta_id))
    if evaluacion_id is not None:
        await verificar_alcance(db, actor, evaluacion_id)
    else:
        _sin_evaluacion(actor)
    return actor


async def alcance_evidencia(
    evidencia_id: int,
    actor: Actor | None = Depends(actor_opcional),
    db: AsyncSession = Depends(get_db),
) -> Actor | None:
    from app.domain.models.evidencia import Evidencia
    from app.domain.models.respuesta import Respuesta

    evaluacion_id = await db.scalar(
        select(Respuesta.evaluacion_id)
        .join(Evidencia, Evidencia.respuesta_id == Respuesta.id)
        .where(Evidencia.id_evidencia == evidencia_id)
    )
    if evaluacion_id is not None:
        await verificar_alcance(db, actor, evaluacion_id)
    else:
        _sin_evaluacion(actor)
    return actor
