"""
Espacio de la empresa del usuario definitivo (rol cliente).

    GET /api/cliente/empresa    HU-28: su empresa, su contrato y las evaluaciones migradas.
                                HU-30: es parte del servicio pagado (403 CONTRATO_NO_VIGENTE
                                sin contrato vigente).
    GET /api/cliente/contrato   HU-30: situación del contrato y qué puede hacer el usuario.
                                Responde SIEMPRE (también sin contrato vigente): es lo que
                                muestra el frontend cuando el servicio está cortado, con los
                                documentos que aún puede descargar y el acceso a ARCOP.

El detalle de cada evaluación (resultados, brechas, plan formativo, informe PDF) se lee con
las rutas de siempre de /api/evaluaciones, que limitan al cliente a lo migrado a su empresa
(app/core/alcance.py) y que, por ser funciones gratuitas, no dependen del contrato.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.gestionar_contrato import contrato_dict
from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.formacion import AvanceFormativo
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.usuario_definitivo import UsuarioDefinitivo

router = APIRouter(prefix="/api/cliente", tags=["cliente · espacio de la empresa (HU-28, HU-30)"])

solo_cliente = requerir_rol(Rol.CLIENTE)

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


async def _evaluaciones(db: AsyncSession, empresa_id: int):
    puntaje = (
        select(Resumen.evaluacion_id, func.avg(Resumen.puntaje_obtenido).label("puntaje"))
        .group_by(Resumen.evaluacion_id).subquery()
    )
    return (await db.execute(
        select(Evaluacion, puntaje.c.puntaje)
        .outerjoin(puntaje, puntaje.c.evaluacion_id == Evaluacion.id)
        .where(Evaluacion.empresa_id == empresa_id)
        .order_by(Evaluacion.fecha_migracion.desc(), Evaluacion.id.desc())
    )).all()


@router.get("/empresa")
async def mi_empresa(cliente: ClienteConServicio = Depends(empresa_con_servicio),
                     db: AsyncSession = Depends(get_db)):
    usuario, empresa = cliente.usuario, cliente.empresa
    rubro = await db.scalar(select(Rubro.nombre_rubro).where(Rubro.id == empresa.rubro_id))
    filas = await _evaluaciones(db, empresa.id)
    return {
        "usuario": {"nombre": usuario.nombre, "email": usuario.email},
        "empresa": {
            "id": empresa.id, "razon_social": empresa.razon_social, "rut": empresa.rut, "rubro": rubro,
            "fecha_inicio_contrato": empresa.fecha_inicio_contrato,
            "fecha_termino_contrato": empresa.fecha_termino_contrato,
            "contrato_vigente": empresa.contrato_vigente(),
            "contrato": contrato_dict(empresa),
        },
        "evaluaciones": [
            {
                "id": ev.id, "estado_progreso": ev.estado_progreso, "completada": ev.esta_cerrada,
                "fecha_inicio": ev.fecha_inicio, "fecha_migracion": ev.fecha_migracion,
                "puntaje_general": round(p, 1) if p is not None else None,
            }
            for ev, p in filas
        ],
    }


@router.get("/contrato")
async def mi_contrato(actor: Actor = Depends(solo_cliente), db: AsyncSession = Depends(get_db)):
    """
    HU-30: situación del contrato y lo que el usuario puede hacer según ella. Con el
    servicio cortado lista lo gratuito (informe PDF y plan formativo de sus evaluaciones)
    y, mientras dure el plazo de gracia, sus constancias para descargar.
    """
    usuario = await db.get(UsuarioDefinitivo, actor.id)
    empresa = await db.get(Empresa, usuario.empresa_id) if usuario else None
    if usuario is None or empresa is None:  # obtener_actor ya lo comprobó; defensa en profundidad
        raise HTTPException(status_code=404, detail={"codigo": "NO_ENCONTRADO", "mensaje": "Empresa no encontrada."})
    contrato = contrato_dict(empresa)

    constancias = []
    if contrato["documentos_disponibles"]:
        filas = (await db.execute(
            select(AvanceFormativo, RutaFormativa.nombre)
            .join(RutaFormativa, RutaFormativa.id == AvanceFormativo.ruta_formativa_id)
            .where(AvanceFormativo.empresa_id == empresa.id, AvanceFormativo.codigo_constancia.is_not(None))
            .order_by(AvanceFormativo.fecha_completado.desc())
        )).all()
        constancias = [{
            "ruta_id": a.ruta_formativa_id, "modulo": nombre or f"Ruta {a.ruta_formativa_id}",
            "fecha_completado": a.fecha_completado, "codigo": a.codigo_constancia,
            "url": f"/api/formacion/modulos/{a.ruta_formativa_id}/constancia",
        } for a, nombre in filas if a.completado]

    evaluaciones = [{
        "id": ev.id, "completada": ev.esta_cerrada,
        # Funciones gratuitas: disponibles con o sin contrato
        "informe_pdf": f"/api/evaluaciones/{ev.id}/informe/pdf",
        "plan_formativo": f"/api/evaluaciones/{ev.id}/plan-formativo",
    } for ev, _ in await _evaluaciones(db, empresa.id)]

    return JSONResponse(content=jsonable_encoder({
        "empresa": {"id": empresa.id, "razon_social": empresa.razon_social},
        "contrato": contrato,
        "documentos": {"constancias": constancias, "evaluaciones": evaluaciones},
        "arcop": {"disponible": True, "solicitudes": "/api/arcop/solicitudes"},
    }), headers=_SIN_CACHE)
