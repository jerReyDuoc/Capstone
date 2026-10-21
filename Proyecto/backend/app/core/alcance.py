"""
Alcance de las rutas de evaluaciones (HU-19 criterio 2 y primera parte de HU-20).

Regla: quien entra por la encuesta pública solo ve y modifica SU evaluación.

  | Quién                        | Evaluación pública         | Evaluación por invitación          |
  |------------------------------|----------------------------|------------------------------------|
  | admin_therion                | todas                      | todas                              |
  | encuestado (sub = eval id)   | solo la suya (otra -> 404) | ninguna (404)                      |
  | referente (sub = usuario id) | ninguna (404)              | solo las suyas (otra -> 404)       |
  | sin token                    | 401                        | permitido mientras                 |
  |                              |                            | EXIGIR_TOKEN_EVALUACIONES=false    |

Se responde 404 (no 403) a lo ajeno para no confirmar que el id existe; los ids son
correlativos y un 403 permitiría enumerarlos.

Las evaluaciones por invitación siguen abiertas sin token para no romper el panel
HU-13 ni las pruebas mientras HU-20 no agregue el login del referente; el interruptor
EXIGIR_TOKEN_EVALUACIONES las cierra.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, Rol, obtener_actor
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
        detail={"codigo": "NO_AUTENTICADO", "mensaje": "Esta evaluación requiere la sesión de su encuestado."},
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


async def verificar_alcance(db: AsyncSession, actor: Actor | None, evaluacion_id: int) -> None:
    if actor is not None and actor.es_admin:
        return
    fila = (
        await db.execute(
            select(Evaluacion.origen, Evaluacion.usuario_temporal_id).where(Evaluacion.id == evaluacion_id)
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
    origen, usuario_temporal_id = fila

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
    elif actor is not None and not actor.es_admin:
        raise _NO_ENCONTRADA
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
    elif actor is not None and not actor.es_admin:
        raise _NO_ENCONTRADA
    return actor
