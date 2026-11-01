"""
HU-09 · Log inmutable para el Auditor Externo (Ley 21.719, art. 14 ter).

Auditor Externo (rol auditor_externo, token de POST /api/auth/auditor) y admin_therion:
  GET  /api/auditoria/registros?desde=&hasta=&categoria=&accion=&entidad=&entidad_id=&resultado=&actor_rol=&page=&size=
  GET  /api/auditoria/verificacion        integridad: cadena HMAC + hash por lote (criterio 3)
  GET  /api/auditoria/lotes               sellos de los lotes (para anotar el ancla)
  GET  /api/auditoria/exportacion?desde=&hasta=   ZIP con lotes completos + script de verificación
  GET  /api/auditoria/catalogo            acciones y categorías (modificacion, supresion...)

Solo admin_therion (cuentas de auditor):
  GET   /api/admin/auditores
  POST  /api/admin/auditores              {email, organizacion, password, dias_vigencia}
  PATCH /api/admin/auditores/{id}         {activo?, dias_vigencia?, password?}

Fechas en UTC (las del log lo son). `hasta` no se incluye. Sin token 401; con otro rol 403.
Cada consulta, verificación y exportación queda registrada en el propio log.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.auditoria_externa import (
    LEY, AuditoriaError, ConsultaAuditLog, ExportarAuditLog, GestionarAuditoresUseCase, auditor_dict,
)
from app.core.alcance import solo_admin
from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.database import get_db
from app.domain.models.bitacora_auditoria import RESULTADOS
from app.infrastructure.repositories.bitacora_repository import Categoria, acciones_conocidas, categoria

router = APIRouter(prefix="/api/auditoria", tags=["auditoría externa (HU-09)"])
router_admin = APIRouter(prefix="/api/admin/auditores", tags=["auditoría externa (HU-09)"])

auditor_o_admin = requerir_rol(Rol.AUDITOR_EXTERNO, Rol.ADMIN_THERION)


def _error(e: AuditoriaError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e)})


# ------------------------------------------------------------------ auditor externo
@router.get("/catalogo")
async def catalogo(_: Actor = Depends(auditor_o_admin)):
    """Acciones registradas y su categoría (para filtrar modificaciones y supresiones)."""
    return {
        "ley": LEY,
        "categorias": Categoria.valores(),
        "resultados": list(RESULTADOS),
        "acciones": [{"accion": a, "categoria": categoria(a)} for a in acciones_conocidas()],
        "campos_obligatorios": ["fecha", "actor_rol", "actor_id", "ip", "accion", "resultado"],
    }


@router.get("/registros")
async def registros(
    desde: datetime | None = Query(None, description="UTC, incluido (AAAA-MM-DD o ISO 8601)"),
    hasta: datetime | None = Query(None, description="UTC, NO incluido"),
    categoria: str | None = Query(None, max_length=20, description="modificacion, supresion, creacion, acceso, seguridad, auditoria"),
    accion: str | None = Query(None, max_length=60),
    entidad: str | None = Query(None, max_length=40),
    entidad_id: int | None = Query(None),
    resultado: str | None = Query(None, max_length=10),
    actor_rol: str | None = Query(None, max_length=20),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    actor: Actor = Depends(auditor_o_admin),
    db: AsyncSession = Depends(get_db),
):
    """Historial del audit_log con filtros. Cada registro trae fecha, actor, IP, acción, resultado y hash."""
    try:
        return await ConsultaAuditLog(db).registros(
            actor, desde=desde, hasta=hasta, categoria_=categoria, accion=accion, entidad=entidad,
            entidad_id=entidad_id, resultado=resultado, actor_rol=actor_rol, page=page, size=size)
    except AuditoriaError as e:
        raise _error(e)


@router.get("/verificacion")
async def verificacion(actor: Actor = Depends(auditor_o_admin), db: AsyncSession = Depends(get_db)):
    """
    Criterio 3: verifica el log completo por lotes. `integra=false` trae la primera fila
    alterada de la cadena y los lotes con falla (motivo: hash_lote_distinto, cantidad_distinta,
    cadena_de_sellos_rota, sello_alterado, firma_invalida, filas_fuera_de_lote...).
    Guarde el `ancla` (último lote y sello) fuera del sistema.
    """
    return await ConsultaAuditLog(db).verificar(actor)


@router.get("/lotes")
async def lotes(page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500),
                _: Actor = Depends(auditor_o_admin), db: AsyncSession = Depends(get_db)):
    return await ConsultaAuditLog(db).lotes(page, size)


@router.get("/exportacion", response_class=Response,
            responses={200: {"content": {"application/zip": {}}, "description": "ZIP de la exportación"},
                       404: {"description": "Sin registros en el rango"},
                       413: {"description": "Demasiados registros: acotar las fechas"}})
async def exportacion(
    desde: datetime | None = Query(None, description="UTC, incluido"),
    hasta: datetime | None = Query(None, description="UTC, NO incluido"),
    actor: Actor = Depends(auditor_o_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Exporta el log inmutable: lotes COMPLETOS que tocan el rango, con su sello, el resultado
    de la verificación y un script para recalcular los hashes sin depender del sistema.
    """
    try:
        exp = await ExportarAuditLog(db).generar(actor, desde, hasta)
    except AuditoriaError as e:
        raise _error(e)
    return Response(content=exp.contenido, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{exp.nombre}"',
        "X-Audit-Export-SHA256": exp.sha256,
        "X-Audit-Export-Lotes": f"{exp.lotes[0]}-{exp.lotes[1]}",
        "Cache-Control": "no-store",
    })


# ------------------------------------------------------------------ admin: cuentas de auditor
class CrearAuditorRequest(BaseModel):
    email: str = Field(..., max_length=100)
    organizacion: str = Field(..., max_length=120)
    password: str = Field(..., max_length=200)
    dias_vigencia: int = Field(30, ge=1, le=365)


class ActualizarAuditorRequest(BaseModel):
    activo: bool | None = None
    dias_vigencia: int | None = Field(None, ge=1, le=365)
    password: str | None = Field(None, max_length=200)


@router_admin.get("")
async def listar_auditores(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    return {"items": [auditor_dict(a) for a in await GestionarAuditoresUseCase(db).listar()]}


@router_admin.post("", status_code=201)
async def crear_auditor(payload: CrearAuditorRequest, admin: Actor = Depends(solo_admin),
                        db: AsyncSession = Depends(get_db)):
    """
    Crea la cuenta del Auditor Externo (solo lectura del audit_log, vence en `dias_vigencia`).
    Entregue la contraseña por un canal distinto al correo; no queda en el log.
    """
    try:
        a = await GestionarAuditoresUseCase(db).crear(admin, payload.email, payload.organizacion,
                                                      payload.password, payload.dias_vigencia)
    except AuditoriaError as e:
        raise _error(e)
    return auditor_dict(a)


@router_admin.patch("/{auditor_id}")
async def actualizar_auditor(auditor_id: int, payload: ActualizarAuditorRequest,
                             admin: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Extiende la vigencia, cambia la contraseña o desactiva (cierra sus sesiones al instante)."""
    try:
        a = await GestionarAuditoresUseCase(db).actualizar(
            admin, auditor_id, activo=payload.activo, dias_vigencia=payload.dias_vigencia, password=payload.password)
    except AuditoriaError as e:
        raise _error(e)
    return auditor_dict(a)
