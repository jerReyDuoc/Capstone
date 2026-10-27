"""
HU-28 criterio 2: espacio de la empresa del usuario definitivo (rol cliente).

    GET /api/cliente/empresa   su empresa, su contrato y las evaluaciones migradas a ella

Es la puerta de entrada del cliente después de iniciar sesión. El detalle de cada
evaluación (resultados, brechas, plan formativo, informe PDF) se lee con las rutas de
siempre de /api/evaluaciones, que ya limitan al cliente a lo migrado a su empresa
(app/core/alcance.py). HU-29 completa este espacio (cursos y tutor IA).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.database import get_db
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.usuario_definitivo import UsuarioDefinitivo

router = APIRouter(prefix="/api/cliente", tags=["cliente · espacio de la empresa (HU-28)"])

solo_cliente = requerir_rol(Rol.CLIENTE)


@router.get("/empresa")
async def mi_empresa(actor: Actor = Depends(solo_cliente), db: AsyncSession = Depends(get_db)):
    usuario = await db.get(UsuarioDefinitivo, actor.id)
    empresa = await db.get(Empresa, usuario.empresa_id) if usuario else None
    if usuario is None or empresa is None:  # obtener_actor ya lo comprobó; defensa en profundidad
        raise HTTPException(status_code=404, detail={"codigo": "NO_ENCONTRADO", "mensaje": "Empresa no encontrada."})
    rubro = await db.scalar(select(Rubro.nombre_rubro).where(Rubro.id == empresa.rubro_id))

    puntaje = (
        select(Resumen.evaluacion_id, func.avg(Resumen.puntaje_obtenido).label("puntaje"))
        .group_by(Resumen.evaluacion_id).subquery()
    )
    filas = (await db.execute(
        select(Evaluacion, puntaje.c.puntaje)
        .outerjoin(puntaje, puntaje.c.evaluacion_id == Evaluacion.id)
        .where(Evaluacion.empresa_id == empresa.id)
        .order_by(Evaluacion.fecha_migracion.desc(), Evaluacion.id.desc())
    )).all()
    return {
        "usuario": {"nombre": usuario.nombre, "email": usuario.email},
        "empresa": {
            "id": empresa.id, "razon_social": empresa.razon_social, "rut": empresa.rut, "rubro": rubro,
            "fecha_inicio_contrato": empresa.fecha_inicio_contrato,
            "fecha_termino_contrato": empresa.fecha_termino_contrato,
            "contrato_vigente": empresa.contrato_vigente(),
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
