"""
HU-24 · Mantenedor de la matriz normativa con versionado (solo admin_therion).

Todas las rutas: 401 sin token y 403 con otro rol (app/core/alcance.py: solo_admin).
Cada cambio queda en el audit log (HU-09). Las que modifican el borrador aceptan
`revision` (la que devolvió la última lectura) y responden 409 BORRADOR_CAMBIADO si otro
administrador lo modificó entre medio.

  Estado y versiones
    GET   /api/admin/matriz                              vigente, borrador y etiqueta sugerida
    GET   /api/admin/matriz/versiones                    historial (publicadas y reemplazadas)
    GET   /api/admin/matriz/versiones/{version_id}       contenido, árbol y diferencias con la anterior

  Borrador
    POST  /api/admin/matriz/borrador                     {desde_version_id?}  crea la copia de trabajo
    GET   /api/admin/matriz/borrador                     contenido, árbol, cambios, errores
    GET   /api/admin/matriz/borrador/validacion          errores, advertencias y diferencias
    POST  /api/admin/matriz/borrador/descartar           {revision}
    POST  /api/admin/matriz/borrador/publicar            {etiqueta, nota_cambio, revision}

  CRUD del borrador ({entidad} = controles | brechas | rutas | preguntas-filtro)
    POST  /api/admin/matriz/borrador/{entidad}                         {datos, revision}
    PATCH /api/admin/matriz/borrador/{entidad}/{item_id}               {datos, revision}
    POST  /api/admin/matriz/borrador/{entidad}/{item_id}/retirar       {revision}
    POST  /api/admin/matriz/borrador/{entidad}/{item_id}/restaurar     {revision}
    PATCH /api/admin/matriz/borrador/controles/{item_id}/aplicabilidad {aplica_siempre, filtros, revision}

"Eliminar" un elemento ya publicado es RETIRARLO: deja de aplicarse en la versión nueva y
se conserva para las evaluaciones anteriores.
"""
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.mantenedor_matriz import MantenedorMatrizUseCase, MatrizError
from app.core.alcance import solo_admin
from app.core.autenticacion import Actor
from app.core.database import get_db

router = APIRouter(prefix="/api/admin/matriz", tags=["admin · matriz normativa (HU-24)"])


class Entidad(str, Enum):
    controles = "controles"
    brechas = "brechas"
    rutas = "rutas"
    preguntas_filtro = "preguntas-filtro"

    @property
    def clave(self) -> str:
        return self.value.replace("-", "_")


class CrearBorradorRequest(BaseModel):
    desde_version_id: int | None = Field(None, ge=1, description="Versión de origen (por defecto, la vigente)")


class RevisionRequest(BaseModel):
    revision: int | None = Field(None, ge=1)


class DatosRequest(RevisionRequest):
    datos: dict[str, Any] = Field(..., description="Campos del elemento (ver app/domain/matriz/contenido.py)")


class AplicabilidadRequest(RevisionRequest):
    aplica_siempre: bool = False
    filtros: list[int] = Field(default_factory=list, max_length=50)


class PublicarRequest(RevisionRequest):
    etiqueta: str = Field(..., max_length=30)
    nota_cambio: str = Field(..., max_length=1000)


def _error(e: MatrizError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e), **e.extra})


async def _correr(coro):
    try:
        return await coro
    except MatrizError as e:
        raise _error(e)


# ------------------------------------------------------------------ estado y versiones
@router.get("")
async def estado_matriz(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Versión vigente, borrador en edición (si hay) y la etiqueta sugerida para publicar."""
    return await _correr(MantenedorMatrizUseCase(db).estado())


@router.get("/versiones")
async def listar_versiones(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Historial: cada versión con su etiqueta, autor, fecha, nota y cuántas evaluaciones la usan."""
    return {"items": await _correr(MantenedorMatrizUseCase(db).versiones())}


@router.get("/versiones/{version_id}")
async def obtener_version(version_id: int, _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).version(version_id))


# ------------------------------------------------------------------ borrador
@router.post("/borrador", status_code=201)
async def crear_borrador(body: CrearBorradorRequest | None = None, actor: Actor = Depends(solo_admin),
                         db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).crear_borrador(actor, body.desde_version_id if body else None))


@router.get("/borrador")
async def obtener_borrador(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).borrador())


@router.get("/borrador/validacion")
async def revisar_borrador(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).revisar())


@router.post("/borrador/descartar")
async def descartar_borrador(body: RevisionRequest | None = None, actor: Actor = Depends(solo_admin),
                             db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).descartar(actor, body.revision if body else None))


@router.post("/borrador/publicar")
async def publicar_borrador(body: PublicarRequest, actor: Actor = Depends(solo_admin),
                            db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).publicar(actor, body.etiqueta, body.nota_cambio, body.revision))


# ------------------------------------------------------------------ CRUD del borrador
@router.patch("/borrador/controles/{item_id}/aplicabilidad")
async def fijar_aplicabilidad(item_id: int, body: AplicabilidadRequest, actor: Actor = Depends(solo_admin),
                              db: AsyncSession = Depends(get_db)):
    """Reglas del árbol para un control: aplica siempre y/o se suma con estas preguntas de filtro."""
    return await _correr(MantenedorMatrizUseCase(db).editar(
        actor, "aplicabilidad", "controles", item_id,
        {"aplica_siempre": body.aplica_siempre, "filtros": body.filtros}, body.revision,
    ))


@router.post("/borrador/{entidad}", status_code=201)
async def crear_elemento(entidad: Entidad, body: DatosRequest, actor: Actor = Depends(solo_admin),
                         db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).editar(actor, "crear", entidad.clave, None, body.datos,
                                                            body.revision))


@router.patch("/borrador/{entidad}/{item_id}")
async def actualizar_elemento(entidad: Entidad, item_id: int, body: DatosRequest, actor: Actor = Depends(solo_admin),
                              db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).editar(actor, "actualizar", entidad.clave, item_id, body.datos,
                                                            body.revision))


@router.post("/borrador/{entidad}/{item_id}/retirar")
async def retirar_elemento(entidad: Entidad, item_id: int, body: RevisionRequest | None = None,
                           actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Publicado: queda retirado en la versión nueva (se conserva para las anteriores). Nuevo: se quita."""
    return await _correr(MantenedorMatrizUseCase(db).editar(actor, "retirar", entidad.clave, item_id, None,
                                                            body.revision if body else None))


@router.post("/borrador/{entidad}/{item_id}/restaurar")
async def restaurar_elemento(entidad: Entidad, item_id: int, body: RevisionRequest | None = None,
                             actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    return await _correr(MantenedorMatrizUseCase(db).editar(actor, "restaurar", entidad.clave, item_id, None,
                                                            body.revision if body else None))
