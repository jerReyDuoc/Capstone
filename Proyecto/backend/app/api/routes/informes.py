"""
Informes de una evaluación completada.

  GET  /api/evaluaciones/{id}/plan-formativo   HU-12: plan de estudio por dimensión normativa
  GET  /api/evaluaciones/{id}/informe/pdf      PDF descargable (mismos filtros que el panel:
                                               ?severidad=Crítica,Alta&dominio=…&estado=…&q=…)
  POST /api/evaluaciones/{id}/informe/enviar   el mismo PDF por correo

Todas exigen que la evaluación tenga resumen (se completó o se cerró). El alcance es el
de las demás rutas de evaluaciones (app/core/alcance.py): el encuestado solo ve la suya.

El correo lleva un PDF que genera el servidor con los datos de la BD: no se aceptan
archivos del cliente, así la API no sirve para mandar contenido arbitrario a terceros.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.application.informes.analisis import (
    ETIQUETA_MADUREZ,
    FiltrosBrechas,
    construir_brechas,
    construir_plan,
    contar_por_severidad,
    filtrar_brechas,
    nivel_madurez,
    parsear_filtros,
    plan_a_dict,
)
from app.application.informes.carga import DatosEvaluacion, SinResultadosError, cargar_evaluacion
from app.application.informes.pdf_informe import DatosInforme, PdfNoDisponibleError, generar_pdf, nombre_archivo
from app.application.use_cases.limites_encuesta import ventana_diaria
from app.core.alcance import alcance_evaluacion
from app.core.autenticacion import Actor
from app.core.cliente import huella, ip_cliente
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evaluaciones", tags=["informes (HU-11 / HU-12)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _error(status: int, codigo: str, mensaje: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"codigo": codigo, "mensaje": mensaje, **extra})


async def _datos(db: AsyncSession, evaluacion_id: int) -> DatosEvaluacion:
    try:
        return await cargar_evaluacion(db, evaluacion_id)
    except SinResultadosError as e:
        raise _error(404, "SIN_RESULTADOS", str(e))


def _informe(datos: DatosEvaluacion, filtros: FiltrosBrechas) -> DatosInforme:
    puntajes = {d.nombre: d.puntaje for d in datos.dominios if d.puntaje is not None}
    brechas = construir_brechas(datos.respuestas, puntajes)
    return DatosInforme(
        evaluacion_id=datos.evaluacion_id, rubro=datos.rubro, puntaje_general=datos.puntaje_general,
        controles_evaluados=datos.controles_evaluados, en_revision=datos.en_revision,
        comparativa=datos.comparativa, brechas_total=len(brechas),
        brechas=filtrar_brechas(brechas, filtros), filtros=filtros,
        plan=construir_plan(brechas, datos.dominios, datos.rutas),
        generado=datetime.now(timezone.utc),
    )


def _pdf(informe: DatosInforme) -> bytes:
    try:
        return generar_pdf(informe)
    except PdfNoDisponibleError as e:
        raise _error(503, "PDF_NO_DISPONIBLE", str(e))


# ---------------------------------------------------------------------------- HU-12
@router.get("/{evaluacion_id}/plan-formativo")
async def plan_formativo(evaluacion_id: int, db: AsyncSession = Depends(get_db),
                         _actor: Actor | None = Depends(alcance_evaluacion)):
    """
    HU-12 · Plan de estudio recomendado según las brechas de la evaluación.

    - **Mapeo automático**: cada brecha (no cumplida o parcial) activa la ruta que el
      catálogo le asocia (`catalogo_brechas.ruta_formativa_id`).
    - **Nivel por dimensión** (Inicial / Intermedio / Avanzado) según el puntaje del
      dominio, con su objetivo. La ruta de ese nivel entra siempre como base.
    - **Agrupado por dimensión normativa** (dominio de la ruta).
    """
    datos = await _datos(db, evaluacion_id)
    puntajes = {d.nombre: d.puntaje for d in datos.dominios if d.puntaje is not None}
    plan = construir_plan(construir_brechas(datos.respuestas, puntajes), datos.dominios, datos.rutas)
    return JSONResponse({"evaluacion_id": evaluacion_id, **plan_a_dict(plan)}, headers=_SIN_CACHE)


# ---------------------------------------------------------------------------- PDF
@router.get("/{evaluacion_id}/informe/pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def descargar_informe(
    evaluacion_id: int,
    severidad: str | None = Query(None, max_length=80),
    dominio: str | None = Query(None, max_length=80),
    estado: str | None = Query(None, max_length=30),
    q: str | None = Query(None, max_length=80),
    db: AsyncSession = Depends(get_db),
    _actor: Actor | None = Depends(alcance_evaluacion),
):
    """Informe en PDF para descargar directo (sin el diálogo de impresión del navegador)."""
    informe = _informe(await _datos(db, evaluacion_id), parsear_filtros(severidad, dominio, estado, q))
    contenido = _pdf(informe)
    return Response(
        content=contenido, media_type="application/pdf",
        headers={
            **_SIN_CACHE,
            "Content-Disposition": f'attachment; filename="{nombre_archivo(evaluacion_id, informe.generado)}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------------------------- correo
class EnviarInformeRequest(BaseModel):
    # Encuestado: vacío = el correo que registró. Equipo interno: obligatorio.
    email: str | None = Field(None, max_length=100)
    # true = además guardarlo como su correo (HU-19: retomar / recibir informes)
    recordar: bool = False
    severidad: str | None = Field(None, max_length=80)
    dominio: str | None = Field(None, max_length=80)
    estado: str | None = Field(None, max_length=30)
    q: str | None = Field(None, max_length=80)


@router.post("/{evaluacion_id}/informe/enviar")
async def enviar_informe(
    evaluacion_id: int,
    payload: EnviarInformeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Actor | None = Depends(alcance_evaluacion),
    limitador: Limitador = Depends(obtener_limitador),
):
    """Envía el informe en PDF por correo, como respaldo por si se pierde el archivo descargado."""
    if settings.CORREO_MODO == "desactivado":
        raise _error(503, "CORREO_NO_DISPONIBLE", "El envío por correo no está habilitado. Descarga el PDF.")

    evaluacion = await db.get(Evaluacion, evaluacion_id)
    usuario = (await db.get(UsuarioTemporal, evaluacion.usuario_temporal_id)
               if evaluacion and evaluacion.usuario_temporal_id else None)
    destino = (payload.email or "").strip().lower() or None
    if destino is None and actor is not None and actor.es_encuestado and usuario is not None:
        destino = usuario.email
    if not destino:
        raise _error(422, "EMAIL_REQUERIDO", "Escribe el correo al que quieres recibir el informe.")
    if not correo.EMAIL_VALIDO.match(destino):
        raise _error(422, "EMAIL_INVALIDO", "Revisa el formato del correo (ejemplo: nombre@empresa.cl).")

    datos = await _datos(db, evaluacion_id)  # 404 si aún no hay resultados (antes de gastar cupo)

    fecha, ventana, _ = ventana_diaria()
    claves = [
        (f"inf:eval:{evaluacion_id}:{fecha}", settings.INFORME_CORREOS_DIA_EVALUACION),
        (f"inf:ip:{huella(ip_cliente(request))}:{fecha}", settings.INFORME_CORREOS_DIA_IP),
    ]
    consumidas: list[str] = []
    try:
        for clave, limite in claves:
            consumo = await limitador.consumir(clave, limite, ventana)
            consumidas.append(clave)
            if not consumo.permitido:
                for c in consumidas:
                    await limitador.devolver(c)
                raise _error(429, "LIMITE_CORREOS",
                             f"Ya enviaste el informe {limite} veces hoy. Descárgalo o vuelve a intentarlo mañana.",
                             reintentarEnS=consumo.reintentar_en_s)
    except LimitadorNoDisponibleError:
        raise _error(503, "LIMITADOR_NO_DISPONIBLE", "No pudimos enviar el correo ahora. Descarga el PDF.")

    try:
        informe = _informe(datos, parsear_filtros(payload.severidad, payload.dominio, payload.estado, payload.q))
        pdf = _pdf(informe)
        conteo = contar_por_severidad(construir_brechas(datos.respuestas))  # del listado completo
        texto, html = correo.cuerpo_informe(
            evaluacion_id, datos.puntaje_general, ETIQUETA_MADUREZ[nivel_madurez(datos.puntaje_general)],
            informe.brechas_total, conteo["Crítica"], informe.plan.modulos, informe.plan.horas,
        )
        modo = await correo.enviar(
            destino, f"Tu informe de diagnóstico · Evaluación #{evaluacion_id}", texto, html,
            [correo.Adjunto(nombre_archivo(evaluacion_id, informe.generado), pdf)],
        )
    except (correo.CorreoFallidoError, correo.CorreoNoDisponibleError, HTTPException) as e:
        for c in consumidas:
            await limitador.devolver(c)
        if isinstance(e, HTTPException):
            raise
        logger.warning("[informe] envío fallido evaluación %s: %s", evaluacion_id, e)
        raise _error(502 if isinstance(e, correo.CorreoFallidoError) else 503, "CORREO_FALLIDO",
                     "No pudimos enviar el correo. Inténtalo de nuevo en unos minutos o descarga el PDF.")

    if payload.recordar and actor is not None and actor.es_encuestado and usuario is not None:
        usuario.email = destino
        await db.commit()

    logger.info("[informe] evaluación %s enviada a %s (%s)", evaluacion_id, correo.enmascarar(destino), modo)
    return JSONResponse(
        {"enviado": True, "destino": correo.enmascarar(destino), "modo": modo},
        headers=_SIN_CACHE,
    )
