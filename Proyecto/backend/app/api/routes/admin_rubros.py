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
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alcance import solo_admin
from app.core.autenticacion import Actor
from app.core.database import get_db
from app.domain.models.empresa import Empresa
from app.domain.models.rubro import Rubro
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

router = APIRouter(prefix="/api/admin/rubros", tags=["admin · rubros"])

NOMBRE_MIN, NOMBRE_MAX = 2, 50
_ESPACIOS = re.compile(r"\s+")


class RubroRequest(BaseModel):
    nombre: str = Field(..., max_length=200)


def _normalizar(nombre: str) -> str:
    limpio = _ESPACIOS.sub(" ", nombre or "").strip()
    if len(limpio) < NOMBRE_MIN or not re.search(r"[^\W\d_]", limpio):
        raise HTTPException(422, {"codigo": "RUBRO_INVALIDO",
                                  "mensaje": f"Escribe un nombre de al menos {NOMBRE_MIN} letras."})
    if len(limpio) > NOMBRE_MAX:
        raise HTTPException(422, {"codigo": "RUBRO_INVALIDO",
                                  "mensaje": f"El nombre admite hasta {NOMBRE_MAX} caracteres."})
    return limpio


async def _duplicado(db: AsyncSession, nombre: str, excepto: int | None = None) -> bool:
    q = select(Rubro.id).where(func.lower(func.trim(Rubro.nombre_rubro)) == nombre.lower())
    if excepto is not None:
        q = q.where(Rubro.id != excepto)
    return (await db.scalar(q.limit(1))) is not None


@router.get("")
async def listar(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    evaluaciones = dict((await db.execute(
        select(UsuarioTemporal.rubro_id, func.count()).where(UsuarioTemporal.rubro_id.is_not(None))
        .group_by(UsuarioTemporal.rubro_id))).all())
    empresas = dict((await db.execute(
        select(Empresa.rubro_id, func.count()).group_by(Empresa.rubro_id))).all())
    filas = (await db.execute(select(Rubro).order_by(Rubro.id))).scalars().all()
    return {"items": [{
        "id": r.id, "nombre": (r.nombre_rubro or "").strip() or f"Rubro {r.id}",
        "evaluaciones": int(evaluaciones.get(r.id, 0)), "empresas": int(empresas.get(r.id, 0)),
    } for r in filas]}


@router.post("", status_code=201)
async def crear(cuerpo: RubroRequest, actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    nombre = _normalizar(cuerpo.nombre)
    if await _duplicado(db, nombre):
        raise HTTPException(409, {"codigo": "RUBRO_DUPLICADO", "mensaje": f"Ya existe el rubro «{nombre}»."})
    # Los rubros sembrados por la migración llevan id explícito y la secuencia de PostgreSQL
    # no avanzó con ellos: el id se calcula aquí (lo usa solo el admin, sin concurrencia real).
    for _ in range(3):
        nuevo_id = int(await db.scalar(select(func.coalesce(func.max(Rubro.id), 0))) or 0) + 1
        rubro = Rubro(id=nuevo_id, nombre_rubro=nombre)
        db.add(rubro)
        try:
            await db.flush()
            break
        except IntegrityError:
            await db.rollback()
    else:
        raise HTTPException(409, {"codigo": "RUBRO_CONFLICTO", "mensaje": "No pudimos guardar el rubro. Inténtalo de nuevo."})
    BitacoraRepository(db).registrar(accion=Accion.RUBRO_CREADO, entidad="rubro", entidad_id=rubro.id, actor=actor,
                                     detalle={"rubro": nombre})
    await db.commit()
    return {"id": rubro.id, "nombre": nombre, "evaluaciones": 0, "empresas": 0}


@router.patch("/{rubro_id}")
async def renombrar(rubro_id: int, cuerpo: RubroRequest, actor: Actor = Depends(solo_admin),
                    db: AsyncSession = Depends(get_db)):
    rubro = await db.get(Rubro, rubro_id)
    if rubro is None:
        raise HTTPException(404, {"codigo": "RUBRO_NO_ENCONTRADO", "mensaje": "El rubro no existe."})
    nombre = _normalizar(cuerpo.nombre)
    if await _duplicado(db, nombre, excepto=rubro_id):
        raise HTTPException(409, {"codigo": "RUBRO_DUPLICADO", "mensaje": f"Ya existe el rubro «{nombre}»."})
    antes = (rubro.nombre_rubro or "").strip()
    if antes != nombre:
        rubro.nombre_rubro = nombre
        BitacoraRepository(db).registrar(accion=Accion.RUBRO_RENOMBRADO, entidad="rubro", entidad_id=rubro.id,
                                         actor=actor, detalle={"antes": antes, "despues": nombre})
        await db.commit()
    return {"id": rubro.id, "nombre": nombre}
