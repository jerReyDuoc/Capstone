"""
HU-27 · Panel interno (HU-28): empresas cliente, usuario definitivo y migración.

Todas las rutas son solo de admin_therion (401 sin token, 403 con otro rol).

  Bandeja de solicitudes de contratación (HU-31 criterio 3; HU-28 la integra al panel)
    GET   /api/admin/contrataciones?estado=&page=&size=  incluye conteo_por_estado
    GET   /api/admin/contrataciones/{id}
    PATCH /api/admin/contrataciones/{id}                  {estado: contactada|contratada|descartada}

  Empresas cliente (HU-27)
    POST  /api/admin/empresas                             alta: empresa + usuario + migración + enlace
    GET   /api/admin/empresas
    GET   /api/admin/empresas/{id}
    POST  /api/admin/empresas/{id}/evaluaciones           asociar más evaluaciones autorizadas
    POST  /api/admin/empresas/{id}/usuario/activacion     reenviar el enlace (revoca el anterior)

  Contrato de la empresa (HU-30; cada cambio en la bitácora)
    POST  /api/admin/empresas/{id}/contrato/renovacion    {fecha_termino_contrato}
    POST  /api/admin/empresas/{id}/contrato/suspension    {motivo}
    POST  /api/admin/empresas/{id}/contrato/reactivacion  levanta la suspensión
    POST  /api/admin/empresas/{id}/contrato/terminacion   {motivo}; abre el plazo de gracia

  Evaluaciones (HU-28: el panel interno lista todas, con su empresa si fue migrada)
    GET   /api/admin/evaluaciones?estado=&origen=&empresa_id=&page=&size=

  Bitácora = audit_log (HU-09; el Auditor Externo usa /api/auditoria/*)
    GET   /api/admin/bitacora?entidad=&entidad_id=&accion=&page=&size=
    GET   /api/admin/bitacora/verificacion                HU-18 + HU-09: cadena HMAC y hash por lote

El admin nunca ve ni define la contraseña del cliente, ni recibe el token de activación:
el enlace solo va al correo del usuario definitivo.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.cuentas.casos_uso.activacion_cuenta import ResultadoCorreo
from app.application.contratacion.casos_uso.contratacion_empresa import (
    ContratacionError, DatosEmpresa, DatosUsuario, EmpresasClienteUseCase, SolicitudesContratacionUseCase,
)
from app.application.evaluacion.casos_uso.migrar_evaluacion import EvaluacionMigrada, MigracionError
from app.application.contratacion.casos_uso.gestionar_contrato import ContratoError, GestionarContratoUseCase, contrato_dict
from app.api.dependencias.alcance import solo_admin
from app.domain.auth.actor import Actor
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.empresa import Empresa
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.domain.models.usuario_definitivo import UsuarioDefinitivo
from app.domain.auditoria.acciones import categoria
from app.application.administracion.casos_uso.panel_clientes import PanelClientesError, PanelClientesUseCase
from app.infrastructure.repositories.panel_clientes_repository import PanelClientesRepository
from app.api.schemas.admin_clientes_esquemas import (
    CambiarEstadoRequest,
    AltaEmpresaRequest,
    AsociarRequest,
    RenovacionRequest,
    MotivoContratoRequest,
)

router = APIRouter(prefix="/api/admin", tags=["admin · empresas cliente (HU-27)"])


def _error(e: ContratacionError | MigracionError | ContratoError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e), **e.extra})


# ------------------------------------------------------------------ serialización
async def _datos_evaluacion(db: AsyncSession, evaluacion_id: int) -> dict:
    datos = await PanelClientesUseCase(db, PanelClientesRepository(db)).datos_evaluacion(evaluacion_id)
    if datos is None:
        return {"id": evaluacion_id}
    ev, puntaje = datos.evaluacion, datos.puntaje
    return {
        "id": ev.id, "origen": ev.origen, "estado_progreso": ev.estado_progreso,
        "fecha_inicio": ev.fecha_inicio, "completada": ev.esta_cerrada,
        "rubro_id": datos.rubro_id, "rubro": datos.rubro,
        "puntaje_general": round(puntaje, 1) if puntaje is not None else None,
        "empresa_id": ev.empresa_id, "fecha_migracion": ev.fecha_migracion,
    }


async def _solicitud(db: AsyncSession, s: SolicitudContratacion) -> dict:
    return {
        "id": s.id, "estado": s.estado,
        "contacto": {"nombre": s.nombre_contacto, "cargo": s.cargo_contacto, "email": s.email_contacto,
                     "telefono": s.telefono_contacto},
        "razon_social_declarada": s.razon_social_declarada,
        # HU-31 criterio 2: los dos consentimientos, cada uno con su versión y fecha
        "consentimientos": {
            "contacto": {"aceptado": s.consentimiento_contacto_version is not None,
                         "version": s.consentimiento_contacto_version,
                         "fecha": s.fecha_consentimiento_contacto},
            "migracion": {"aceptado": bool(s.autoriza_migracion), "version": s.consentimiento_version,
                          "fecha": s.fecha_autorizacion},
        },
        # Campos de HU-27 (se mantienen por compatibilidad con el alta de empresa)
        "autoriza_migracion": s.autoriza_migracion, "consentimiento_version": s.consentimiento_version,
        "fecha_autorizacion": s.fecha_autorizacion, "fecha_creacion": s.fecha_creacion,
        "fecha_actualizacion": s.fecha_actualizacion, "fecha_migracion": s.fecha_migracion,
        "empresa_id": s.empresa_id,
        "evaluacion": await _datos_evaluacion(db, s.evaluacion_id),
    }


def _empresa(e: Empresa) -> dict:
    return {
        "id": e.id, "razon_social": e.razon_social, "rut": e.rut, "rubro_id": e.rubro_id,
        "fecha_inicio_contrato": e.fecha_inicio_contrato, "fecha_termino_contrato": e.fecha_termino_contrato,
        "contrato_vigente": e.contrato_vigente(settings.CONTRATO_GRACIA_DIAS), "fecha_creacion": e.fecha_creacion,
        "contrato": contrato_dict(e),  # HU-30: estado, situación y plazo de gracia
    }


def _usuario(u: UsuarioDefinitivo | None) -> dict | None:
    if u is None:
        return None
    return {  # nunca el hash ni tokens
        "id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol, "estado": u.estado,
        "fecha_creacion": u.fecha_creacion, "fecha_activacion": u.fecha_activacion, "ultimo_acceso": u.ultimo_acceso,
    }


def _correo(r: ResultadoCorreo | None) -> dict | None:
    if r is None:
        return None
    mensaje = (
        "Enlace de activación enviado al correo del usuario." if r.enviado and r.modo == "smtp" else
        "Enlace guardado como .eml en STORAGE_DIR/correos (CORREO_MODO=archivo, solo desarrollo)."
        if r.enviado else
        "No se pudo enviar el enlace de activación: reenvíalo cuando el correo esté disponible."
    )
    return {"enviado": r.enviado, "modo": r.modo, "motivo": r.motivo, "mensaje": mensaje}


def _migradas(migradas: list[EvaluacionMigrada]) -> list[dict]:
    return [m.como_dict() for m in migradas]


# ------------------------------------------------------------------ bandeja de solicitudes (HU-31)
@router.get("/contrataciones")
async def listar_contrataciones(
    estado: str | None = Query(None, description="nueva | contactada | contratada | migrada | descartada"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    uc = SolicitudesContratacionUseCase(db)
    try:
        filas, total = await uc.listar(estado, page, size)
    except ContratacionError as e:
        raise _error(e)
    return {"items": [await _solicitud(db, s) for s in filas], "total": total, "page": page, "size": size,
            "conteo_por_estado": await uc.conteo_por_estado()}


@router.get("/contrataciones/{solicitud_id}")
async def obtener_contratacion(solicitud_id: int, _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        s = await SolicitudesContratacionUseCase(db).obtener(solicitud_id)
    except ContratacionError as e:
        raise _error(e)
    return await _solicitud(db, s)


@router.patch("/contrataciones/{solicitud_id}")
async def cambiar_estado_contratacion(
    solicitud_id: int, payload: CambiarEstadoRequest,
    actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db),
):
    """Cambia el estado en la bandeja: contactada, contratada (habilita HU-27) o descartada."""
    try:
        s = await SolicitudesContratacionUseCase(db).cambiar_estado(actor, solicitud_id, payload.estado)
    except ContratacionError as e:
        raise _error(e)
    return await _solicitud(db, s)


# ------------------------------------------------------------------ empresas (HU-27)
@router.post("/empresas", status_code=201)
async def alta_empresa(payload: AltaEmpresaRequest, actor: Actor = Depends(solo_admin),
                       db: AsyncSession = Depends(get_db)):
    """
    Crea la empresa y su usuario definitivo (rol cliente), migra en la misma transacción
    las evaluaciones de las solicitudes indicadas y envía el enlace de activación.
    """
    e, u = payload.empresa, payload.usuario
    try:
        r = await EmpresasClienteUseCase(db).crear(
            actor,
            DatosEmpresa(razon_social=e.razon_social, rut=e.rut, rubro_id=e.rubro_id,
                         fecha_inicio_contrato=e.fecha_inicio_contrato,
                         fecha_termino_contrato=e.fecha_termino_contrato),
            DatosUsuario(nombre=u.nombre, email=u.email),
            payload.solicitudes_ids,
        )
    except (ContratacionError, MigracionError) as err:
        raise _error(err)
    return {
        "empresa": _empresa(r.empresa), "usuario": _usuario(r.usuario),
        "evaluaciones_migradas": _migradas(r.migradas), "activacion": _correo(r.correo),
    }


@router.get("/empresas")
async def listar_empresas(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                          _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    filas, total = await EmpresasClienteUseCase(db).listar(page, size)
    return {
        "items": [{**_empresa(e), "usuario": _usuario(u), "evaluaciones": n} for e, u, n in filas],
        "total": total, "page": page, "size": size,
    }


@router.get("/empresas/{empresa_id}")
async def detalle_empresa(empresa_id: int, _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        e, u, evaluaciones = await EmpresasClienteUseCase(db).detalle(empresa_id)
    except ContratacionError as err:
        raise _error(err)
    return {**_empresa(e), "usuario": _usuario(u),
            "evaluaciones": [await _datos_evaluacion(db, ev.id) for ev in evaluaciones]}


@router.post("/empresas/{empresa_id}/evaluaciones")
async def asociar_evaluaciones(empresa_id: int, payload: AsociarRequest,
                               actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        migradas = await EmpresasClienteUseCase(db).asociar_evaluaciones(actor, empresa_id, payload.solicitudes_ids)
    except (ContratacionError, MigracionError) as err:
        raise _error(err)
    return {"empresa_id": empresa_id, "evaluaciones_migradas": _migradas(migradas)}


@router.post("/empresas/{empresa_id}/usuario/activacion")
async def reenviar_activacion(empresa_id: int, actor: Actor = Depends(solo_admin),
                              db: AsyncSession = Depends(get_db)):
    try:
        r = await EmpresasClienteUseCase(db).reenviar_activacion(actor, empresa_id)
    except ContratacionError as err:
        raise _error(err)
    return {"empresa_id": empresa_id, "activacion": _correo(r)}


# ------------------------------------------------------------------ contrato (HU-30)
async def _contrato(empresa_id: int, operacion) -> dict:
    try:
        e = await operacion
    except ContratoError as err:
        raise _error(err)
    return _empresa(e)


@router.post("/empresas/{empresa_id}/contrato/renovacion")
async def renovar_contrato(empresa_id: int, payload: RenovacionRequest,
                           actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Nueva fecha de término; deja el contrato activo (también levanta una suspensión o una terminación en gracia)."""
    return await _contrato(empresa_id, GestionarContratoUseCase(db).renovar(
        actor, empresa_id, payload.fecha_termino_contrato))


@router.post("/empresas/{empresa_id}/contrato/suspension")
async def suspender_contrato(empresa_id: int, payload: MotivoContratoRequest,
                             actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Corta el servicio pagado sin terminar el contrato."""
    return await _contrato(empresa_id, GestionarContratoUseCase(db).suspender(actor, empresa_id, payload.motivo))


@router.post("/empresas/{empresa_id}/contrato/reactivacion")
async def reactivar_contrato(empresa_id: int, actor: Actor = Depends(solo_admin),
                             db: AsyncSession = Depends(get_db)):
    """Levanta la suspensión (las fechas no cambian)."""
    return await _contrato(empresa_id, GestionarContratoUseCase(db).reactivar(actor, empresa_id))


@router.post("/empresas/{empresa_id}/contrato/terminacion")
async def terminar_contrato(empresa_id: int, payload: MotivoContratoRequest,
                            actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Termina el contrato; el usuario puede descargar sus documentos durante el plazo de gracia."""
    return await _contrato(empresa_id, GestionarContratoUseCase(db).terminar(actor, empresa_id, payload.motivo))


# ------------------------------------------------------------------ evaluaciones (HU-28)
@router.get("/empresas/{empresa_id}/formacion")
async def formacion_empresa(empresa_id: int, evaluacion_id: int | None = Query(None, ge=1),
                            _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """HU-26: avance formativo de la empresa (lo mismo que ve el cliente en su panel)."""
    from app.application.empresa.casos_uso.formacion_empresa import FormacionError

    try:
        return await PanelClientesUseCase(db, PanelClientesRepository(db)).formacion_empresa(
            empresa_id, evaluacion_id)
    except PanelClientesError as e:
        raise HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": e.mensaje})
    except FormacionError as e:
        raise HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje})


@router.get("/evaluaciones")
async def listar_evaluaciones_admin(
    estado: str | None = Query(None, max_length=20, description="en_progreso | completada | ..."),
    origen: str | None = Query(None, max_length=20, description="publica | invitacion"),
    empresa_id: int | None = Query(None, ge=1),
    incluir_prueba: bool = Query(False, description="Incluir las marcadas como de prueba"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    HU-28 criterio 2: evaluaciones del panel interno, con su rubro, puntaje general y la
    empresa a la que se migraron (si ya contrató). Sin datos de contacto del encuestado.
    """
    pagina = await PanelClientesUseCase(db, PanelClientesRepository(db)).listar_evaluaciones(
        estado=estado, origen=origen, empresa_id=empresa_id, incluir_prueba=incluir_prueba, page=page, size=size)
    return {
        "items": [{
            "id": d.evaluacion.id, "origen": d.evaluacion.origen, "estado_progreso": d.evaluacion.estado_progreso,
            "completada": d.evaluacion.esta_cerrada, "fecha_inicio": d.evaluacion.fecha_inicio,
            "es_prueba": d.evaluacion.es_prueba,
            "rubro": d.rubro, "puntaje_general": round(d.puntaje, 1) if d.puntaje is not None else None,
            "empresa": ({"id": d.evaluacion.empresa_id, "razon_social": d.empresa_razon_social}
                        if d.evaluacion.empresa_id else None),
            "fecha_migracion": d.evaluacion.fecha_migracion,
        } for d in pagina.filas],
        "total": pagina.total, "page": page, "size": size,
        "conteo_por_estado": {str(k or "sin_estado"): v for k, v in pagina.conteo_por_estado.items()},
    }


# ------------------------------------------------------------------ bitácora (HU-09 base)
@router.get("/bitacora")
async def bitacora(
    entidad: str | None = Query(None, max_length=40),
    entidad_id: int | None = Query(None),
    accion: str | None = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    filas, total = await PanelClientesUseCase(db, PanelClientesRepository(db)).listar_bitacora(
        entidad=entidad, entidad_id=entidad_id, accion=accion, page=page, size=size)
    return {
        "items": [{"id": f.id, "fecha": f.fecha, "actor_rol": f.actor_rol, "actor_id": f.actor_id,
                   "ip": f.ip, "accion": f.accion, "categoria": categoria(f.accion),
                   "entidad": f.entidad, "entidad_id": f.entidad_id,
                   "resultado": f.resultado, "detalle": f.detalle, "hash": f.hash} for f in filas],
        "total": total, "page": page, "size": size,
    }


@router.get("/bitacora/verificacion")
async def verificar_bitacora(
    actor: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    HU-18: verifica la cadena de hashes de la bitácora (registro inmutable). `integra=false`
    trae la primera fila alterada, borrada o intercalada. Guarda el `ancla` (último id y hash)
    fuera del sistema para detectar también un borrado de las últimas filas.
    HU-09: además verifica cada lote sellado (`lotes`, `filas`, `ancla_lote`).
    """
    r = await PanelClientesUseCase(db, PanelClientesRepository(db)).verificar_bitacora(actor)
    # Mismas claves que HU-18 (integra, total, verificadas, primera_falla, ancla) + las de HU-09
    return {**r["cadena"], "integra": r["integra"], "lotes": r["lotes"], "filas": r["filas"],
            "ancla_lote": r["ancla"], "metodo": r["metodo"], "fecha_verificacion": r["fecha_verificacion"]}
