"""
Correcciones 05-11 · Rubros desde el panel interno (solo admin_therion).

El rubro clasifica a cada organización (lo elige quien hace el autodiagnóstico y queda en la
empresa cliente) y define con quién se compara en el sector (HU-10). Hasta ahora solo se
cargaba con las migraciones; el admin lo gestiona en "Matriz normativa → Rubros".

    GET   /api/admin/rubros              rubros con cuántas evaluaciones y empresas los usan
    POST  /api/admin/rubros              {nombre}        agrega un rubro
    PATCH /api/admin/rubros/{rubro_id}   {nombre}        corrige el nombre

No hay borrado: un rubro ya usado por evaluaciones, empresas o el benchmark del sector debe
conservarse para que esas comparaciones sigan siendo explicables. Cada cambio queda en el
audit log (HU-09). El rubro no forma parte de la matriz versionada (HU-24): un rubro nuevo
aparece de inmediato en /api/rubros (la landing lo muestra al refrescar su caché).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencias.alcance import solo_admin
from app.api.schemas.admin_rubros_esquemas import RubroRequest
from app.application.administracion.casos_uso.mantenedor_rubros import MantenedorRubrosUseCase, RubroError
from app.core.database import get_db
from app.domain.auth.actor import Actor
from app.infrastructure.repositories.rubros_repository import RubrosRepository

router = APIRouter(prefix="/api/admin/rubros", tags=["admin · rubros"])


def _uc(db: AsyncSession) -> MantenedorRubrosUseCase:
    return MantenedorRubrosUseCase(db, RubrosRepository(db))


def _error(e: RubroError) -> HTTPException:
    return HTTPException(e.status_code, {"codigo": e.codigo, "mensaje": e.mensaje})


@router.get("")
async def listar(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    filas = await _uc(db).listar()
    return {"items": [{"id": r.id, "nombre": r.nombre, "evaluaciones": r.evaluaciones, "empresas": r.empresas}
                      for r in filas]}


@router.post("", status_code=201)
async def crear(cuerpo: RubroRequest, actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        r = await _uc(db).crear(actor, cuerpo.nombre)
    except RubroError as e:
        raise _error(e)
    return {"id": r.id, "nombre": r.nombre, "evaluaciones": 0, "empresas": 0}


@router.patch("/{rubro_id}")
async def renombrar(rubro_id: int, cuerpo: RubroRequest, actor: Actor = Depends(solo_admin),
                    db: AsyncSession = Depends(get_db)):
    try:
        id_, nombre = await _uc(db).renombrar(actor, rubro_id, cuerpo.nombre)
    except RubroError as e:
        raise _error(e)
    return {"id": id_, "nombre": nombre}
