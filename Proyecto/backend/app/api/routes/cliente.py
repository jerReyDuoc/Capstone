"""
Espacio de la empresa del usuario definitivo (rol cliente).

    GET /api/cliente/empresa    HU-28: su empresa, su contrato y las evaluaciones migradas.
                                HU-30: es parte del servicio pagado (403 CONTRATO_NO_VIGENTE
                                sin contrato vigente).
    GET /api/cliente/contrato   HU-30: situación del contrato y qué puede hacer el usuario.
                                Responde SIEMPRE (también sin contrato vigente): es lo que
                                muestra el frontend cuando el servicio está cortado, con los
                                documentos que aún puede descargar y el acceso a ARCOP.

HU-29 · "Mis evaluaciones" y "Mis documentos":

    GET    /api/cliente/evaluaciones                          historial (migradas y reevaluaciones):
                                                              fecha, estado, puntaje global, nivel y
                                                              evolución global y por dimensión.
                                                              Lectura gratuita (sin exigir contrato).
    POST   /api/cliente/evaluaciones                          inicia una reevaluación: pertenece a la
                                                              empresa, sin usuario temporal. Servicio
                                                              pagado (contrato vigente). 409 si ya hay
                                                              una en curso.
    GET    /api/cliente/documentos                            informes PDF, borradores (HU-16),
                                                              evidencias y constancias (HU-26)
    POST   /api/cliente/documentos/informes                   archiva el informe PDF de una evaluación
    GET    /api/cliente/documentos/{id}/descarga              informe o borrador
    DELETE /api/cliente/documentos/{id}
    GET    /api/cliente/documentos/evidencias/{id}/descarga   texto anonimizado de la evidencia
    DELETE /api/cliente/documentos/evidencias/{id}
    DELETE /api/cliente/documentos/constancias/{ruta_id}      (la descarga sigue en /api/formacion)

Los documentos usan empresa_con_documentos (HU-30): se descargan y eliminan con el contrato
vigente, suspendido o en plazo de gracia. Cada descarga y eliminación va a la bitácora (HU-09).

El detalle de cada evaluación (resultados, brechas, plan formativo, informe PDF) se lee con
las rutas de siempre de /api/evaluaciones, que limitan al cliente a las de su empresa
(app/api/dependencias/alcance.py) y que, por ser funciones gratuitas, no dependen del contrato. Las
mismas rutas del cuestionario (filtro, respuestas, evidencias, /completar) sirven para
responder la reevaluación con la sesión del cliente.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.espacio_empresa import EmpresaNoEncontradaError, EspacioEmpresa
from app.application.use_cases.documentos_empresa import DocumentoError, DocumentosEmpresa
from app.application.use_cases.gestionar_contrato import contrato_dict
from app.application.use_cases.historial_empresa import (
    IniciarReevaluacionUseCase,
    ReevaluacionError,
    historial_de_empresa,
)
from app.domain.auth.actor import Actor, Rol
from app.api.dependencias.autenticacion import requerir_rol
from app.core.config import settings
from app.core.database import get_db
from app.api.dependencias import servicio_pagado
from app.api.dependencias.servicio_pagado import ClienteConServicio, empresa_con_documentos, empresa_con_servicio
from app.api.schemas.cliente import ArchivarInformeRequest
from app.infrastructure.repositories.espacio_empresa_repository import EspacioEmpresaRepository

router = APIRouter(prefix="/api/cliente", tags=["cliente · espacio de la empresa (HU-28, HU-29, HU-30)"])

solo_cliente = requerir_rol(Rol.CLIENTE)

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _espacio(db: AsyncSession) -> EspacioEmpresa:
    return EspacioEmpresa(EspacioEmpresaRepository(db))


def _empresa_no_encontrada() -> HTTPException:
    return HTTPException(status_code=404, detail={"codigo": "NO_ENCONTRADO", "mensaje": "Empresa no encontrada."})


@router.get("/empresa")
async def mi_empresa(cliente: ClienteConServicio = Depends(empresa_con_servicio),
                     db: AsyncSession = Depends(get_db)):
    usuario, empresa = cliente.usuario, cliente.empresa
    espacio = _espacio(db)
    rubro = await espacio.nombre_rubro(empresa.rubro_id)
    filas = await espacio.evaluaciones(empresa.id)
    return {
        "usuario": {"nombre": usuario.nombre, "email": usuario.email},
        "empresa": {
            "id": empresa.id, "razon_social": empresa.razon_social, "rut": empresa.rut, "rubro": rubro,
            "fecha_inicio_contrato": empresa.fecha_inicio_contrato,
            "fecha_termino_contrato": empresa.fecha_termino_contrato,
            "contrato_vigente": empresa.contrato_vigente(settings.CONTRATO_GRACIA_DIAS),
            "contrato": contrato_dict(empresa),
        },
        "evaluaciones": [
            {
                "id": ev.id, "estado_progreso": ev.estado_progreso, "completada": ev.esta_cerrada,
                "origen": ev.origen, "fecha_completado": ev.fecha_completado,
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
    espacio = _espacio(db)
    try:
        empresa = await espacio.empresa_del_usuario(actor.id)
    except EmpresaNoEncontradaError:  # obtener_actor ya lo comprobó; defensa en profundidad
        raise _empresa_no_encontrada() from None
    contrato = contrato_dict(empresa)

    constancias = await espacio.constancias(empresa.id) if contrato["documentos_disponibles"] else []

    evaluaciones = [{
        "id": ev.id, "completada": ev.esta_cerrada,
        # Funciones gratuitas: disponibles con o sin contrato
        "informe_pdf": f"/api/evaluaciones/{ev.id}/informe/pdf",
        "plan_formativo": f"/api/evaluaciones/{ev.id}/plan-formativo",
    } for ev, _ in await espacio.evaluaciones(empresa.id)]

    return JSONResponse(content=jsonable_encoder({
        "empresa": {"id": empresa.id, "razon_social": empresa.razon_social},
        "contrato": contrato,
        "documentos": {"constancias": constancias, "evaluaciones": evaluaciones},
        "arcop": {"disponible": True, "solicitudes": "/api/arcop/solicitudes"},
    }), headers=_SIN_CACHE)


# ============================================================================ HU-29
@router.get("/evaluaciones")
async def mis_evaluaciones(actor: Actor = Depends(solo_cliente), db: AsyncSession = Depends(get_db)):
    """
    Criterio 1 · "Mis evaluaciones": todas las evaluaciones de la empresa, incluidas las
    migradas, con fecha, estado, puntaje global y nivel, y las series del gráfico de
    evolución (global y por dimensión; solo las completadas).

    Es lectura de resultados (gratuita): responde también sin contrato vigente, igual que
    /api/evaluaciones/{id}/resumen. `puede_reevaluar` dice si el usuario puede iniciar una
    reevaluación hoy (contrato vigente y ninguna en curso).
    """
    try:
        empresa = await _espacio(db).empresa_del_usuario(actor.id)
    except EmpresaNoEncontradaError:  # obtener_actor ya lo comprobó; defensa en profundidad
        raise _empresa_no_encontrada() from None
    historial = await historial_de_empresa(db, empresa.id)
    en_curso = historial["resumen"]["evaluacion_en_curso_id"]
    habilitado = servicio_pagado.servicio_habilitado(empresa)  # por módulo: las pruebas la reemplazan
    return JSONResponse(content=jsonable_encoder({
        "empresa": {"id": empresa.id, "razon_social": empresa.razon_social},
        **historial,
        "puede_reevaluar": habilitado and en_curso is None,
        "servicio_habilitado": habilitado,
    }), headers=_SIN_CACHE)


@router.post("/evaluaciones", status_code=201,
             responses={409: {"description": "EVALUACION_EN_CURSO (trae evaluacion_id para retomarla)"},
                        403: {"description": "CONTRATO_NO_VIGENTE"}})
async def iniciar_reevaluacion(cliente: ClienteConServicio = Depends(empresa_con_servicio),
                               db: AsyncSession = Depends(get_db)):
    """
    Criterio 2 · Inicia una reevaluación desde la cuenta. La evaluación pertenece a la
    empresa desde que nace (sin usuario temporal) y se responde con las mismas rutas del
    cuestionario (filtro F1–F7, respuestas, evidencias y /completar) usando la sesión del
    cliente. Para el benchmark solo cuenta la evaluación completada más reciente de la empresa.
    """
    try:
        ev = await IniciarReevaluacionUseCase(db).execute(cliente.actor, cliente.empresa)
    except ReevaluacionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detalle())
    return {"evaluacion_id": ev.id, "estado_progreso": ev.estado_progreso, "origen": ev.origen,
            "fecha_inicio": ev.fecha_inicio, "empresa_id": ev.empresa_id}


def _error_documento(e: DocumentoError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.detalle())


def _archivo(contenido: bytes, nombre: str, mime: str) -> Response:
    if mime.startswith("text/") and "charset" not in mime:
        mime = f"{mime}; charset=utf-8"
    return Response(content=contenido, media_type=mime, headers={
        **_SIN_CACHE,
        "Content-Disposition": f'attachment; filename="{nombre}"',
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/documentos")
async def mis_documentos(cliente: ClienteConServicio = Depends(empresa_con_documentos),
                         db: AsyncSession = Depends(get_db)):
    """Criterio 3 · "Mis documentos": informes PDF, borradores (HU-16), evidencias y constancias."""
    datos = await DocumentosEmpresa(db, cliente).listar()
    return JSONResponse(content=jsonable_encoder(datos), headers=_SIN_CACHE)


@router.post("/documentos/informes", status_code=201)
async def archivar_informe(payload: ArchivarInformeRequest,
                           cliente: ClienteConServicio = Depends(empresa_con_documentos),
                           db: AsyncSession = Depends(get_db)):
    """Guarda en "Mis documentos" el informe PDF de una evaluación completada de la empresa."""
    try:
        return await DocumentosEmpresa(db, cliente).archivar_informe(payload.evaluacion_id)
    except DocumentoError as e:
        raise _error_documento(e)


# Las rutas de evidencias y constancias van ANTES que /documentos/{documento_id}
@router.get("/documentos/evidencias/{evidencia_id}/descarga", response_class=Response)
async def descargar_evidencia(evidencia_id: int, cliente: ClienteConServicio = Depends(empresa_con_documentos),
                              db: AsyncSession = Depends(get_db)):
    """El archivo de la evidencia: tras la validación, solo su texto anonimizado (HU-06)."""
    try:
        return _archivo(*await DocumentosEmpresa(db, cliente).descargar_evidencia(evidencia_id))
    except DocumentoError as e:
        raise _error_documento(e)


@router.delete("/documentos/evidencias/{evidencia_id}", status_code=204, response_class=Response)
async def eliminar_evidencia(evidencia_id: int, cliente: ClienteConServicio = Depends(empresa_con_documentos),
                             db: AsyncSession = Depends(get_db)):
    """Borra el archivo; la clasificación y los puntajes que produjo se conservan."""
    try:
        await DocumentosEmpresa(db, cliente).eliminar_evidencia(evidencia_id)
    except DocumentoError as e:
        raise _error_documento(e)
    return Response(status_code=204, headers=_SIN_CACHE)


@router.delete("/documentos/constancias/{ruta_id}", status_code=204, response_class=Response)
async def eliminar_constancia(ruta_id: int, cliente: ClienteConServicio = Depends(empresa_con_documentos),
                              db: AsyncSession = Depends(get_db)):
    """Anula la constancia del módulo (el módulo sigue completado)."""
    try:
        await DocumentosEmpresa(db, cliente).eliminar_constancia(ruta_id)
    except DocumentoError as e:
        raise _error_documento(e)
    return Response(status_code=204, headers=_SIN_CACHE)


@router.get("/documentos/{documento_id}/descarga", response_class=Response)
async def descargar_documento(documento_id: int, cliente: ClienteConServicio = Depends(empresa_con_documentos),
                              db: AsyncSession = Depends(get_db)):
    try:
        return _archivo(*await DocumentosEmpresa(db, cliente).descargar_documento(documento_id))
    except DocumentoError as e:
        raise _error_documento(e)


@router.delete("/documentos/{documento_id}", status_code=204, response_class=Response)
async def eliminar_documento(documento_id: int, cliente: ClienteConServicio = Depends(empresa_con_documentos),
                             db: AsyncSession = Depends(get_db)):
    try:
        await DocumentosEmpresa(db, cliente).eliminar_documento(documento_id)
    except DocumentoError as e:
        raise _error_documento(e)
    return Response(status_code=204, headers=_SIN_CACHE)
