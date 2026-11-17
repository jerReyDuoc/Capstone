"""Guardado de documentos generados por el sistema y archivado del informe PDF de una evaluación."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes.analisis_informe import parsear_filtros
from app.application.informes.carga import SinResultadosError, cargar_evaluacion
from app.application.informes.datos_informe import DatosInforme
from app.application.ports.generador_documentos_port import PdfNoDisponibleError
from app.application.fabricas import fabricas
from app.domain.auth.actor import Actor
from app.core.config import settings
from app.domain.models.documento_empresa import TIPO_INFORME, TIPOS_DOCUMENTO, DocumentoEmpresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.auditoria.acciones import Accion
from app.application.empresa.casos_uso.documentos_empresa.comun import (
    NOMBRE_SEGURO, DocumentoError, _ahora, _storage_documentos,
)

logger = logging.getLogger(__name__)


async def guardar_documento(
    db: AsyncSession, *, empresa_id: int, tipo: str, nombre: str, contenido: bytes, mime_type: str,
    evaluacion_id: int | None = None, actor: Actor | None = None, storage=None,
) -> DocumentoEmpresa:
    """
    Guarda un archivo generado por el sistema en "Mis documentos" (cifrado en reposo) y deja
    el registro en la bitácora. NO hace commit: lo hace quien llama, con su acción de negocio.
    Si el flush falla, el archivo recién escrito se borra.
    """
    if tipo not in TIPOS_DOCUMENTO:
        raise ValueError(f"Tipo de documento desconocido: {tipo}")
    if not NOMBRE_SEGURO.match(nombre):
        raise ValueError("El nombre del documento solo admite letras, números, '.', '_' y '-'.")
    storage = storage or _storage_documentos()
    ruta = await storage.save(contenido, nombre)
    try:
        doc = DocumentoEmpresa(
            empresa_id=empresa_id, evaluacion_id=evaluacion_id, tipo=tipo, nombre=nombre,
            storage_path=ruta, mime_type=mime_type, tamano_bytes=len(contenido),
            hash_contenido=hashlib.sha256(contenido).hexdigest(), fecha_creacion=_ahora(),
            creado_por_usuario_id=actor.id if actor is not None and actor.es_cliente else None,
        )
        await fabricas().documentos_empresa(db).agregar_documento(doc)
    except Exception:
        await storage.delete(ruta)
        raise
    fabricas().bitacora(db).registrar(
        accion=Accion.DOCUMENTO_GENERADO, entidad="documento_empresa", entidad_id=doc.id,
        actor=actor, actor_rol=None if actor else "sistema",
        detalle={"empresa_id": empresa_id, "tipo": tipo, "evaluacion_id": evaluacion_id,
                 "tamano_bytes": len(contenido)},
    )
    return doc


def _datos_informe(datos) -> DatosInforme:
    """El informe completo (sin filtros), igual al que se descarga desde el panel (HU-21)."""
    from app.application.informes.informe_evaluacion import construir_informe

    return construir_informe(datos, parsear_filtros(None, None, None, None), datetime.now(timezone.utc))


async def archivar_informe(db: AsyncSession, evaluacion: Evaluacion, actor: Actor | None) -> DocumentoEmpresa:
    """Genera el informe PDF de una evaluación COMPLETADA de la empresa y lo guarda (sin commit)."""
    if evaluacion.empresa_id is None:
        raise DocumentoError(404, "EVALUACION_NO_ENCONTRADA", "Evaluación no encontrada.")
    if not evaluacion.esta_cerrada:
        raise DocumentoError(409, "EVALUACION_NO_COMPLETADA",
                             "El informe se guarda cuando la evaluación está completada.")
    ya = await fabricas().documentos_empresa(db).contar_informes_de_evaluacion(evaluacion.id, TIPO_INFORME)
    if ya >= settings.DOCUMENTOS_INFORMES_POR_EVALUACION:
        raise DocumentoError(
            409, "LIMITE_INFORMES",
            f"Ya guardaste {ya} informes de esta evaluación. Elimina uno en Mis documentos para guardar otro.",
        )
    try:
        datos = await cargar_evaluacion(db, evaluacion.id)
    except SinResultadosError as e:
        raise DocumentoError(409, "SIN_RESULTADOS", str(e))
    informe = _datos_informe(datos)
    try:
        pdf = fabricas().documentos.pdf_informe(informe)
    except PdfNoDisponibleError as e:
        raise DocumentoError(503, "PDF_NO_DISPONIBLE", str(e))
    nombre = f"informe_evaluacion-{evaluacion.id}_{informe.generado:%Y-%m-%d_%H%M%S}.pdf"
    return await guardar_documento(
        db, empresa_id=evaluacion.empresa_id, tipo=TIPO_INFORME, nombre=nombre, contenido=pdf,
        mime_type="application/pdf", evaluacion_id=evaluacion.id, actor=actor,
    )


async def tras_completar(db: AsyncSession, evaluacion_id: int, actor: Actor | None) -> int | None:
    """
    POST /completar de una evaluación de empresa (HU-29): deja el registro en la bitácora y,
    si DOCUMENTOS_ARCHIVAR_AL_COMPLETAR, archiva su informe PDF. Nunca rompe /completar: la
    evaluación ya quedó completada; si el informe falla, el usuario lo guarda a mano.
    Devuelve el id del documento archivado (o None).
    """
    evaluacion = await fabricas().documentos_empresa(db).obtener_evaluacion(evaluacion_id)
    if evaluacion is None or evaluacion.empresa_id is None:
        return None
    try:
        fabricas().bitacora(db).registrar(
            accion=Accion.EVALUACION_COMPLETADA_EMPRESA, entidad="evaluacion", entidad_id=evaluacion.id,
            actor=actor, detalle={"empresa_id": evaluacion.empresa_id, "origen": evaluacion.origen},
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.error("HU-29: no se pudo registrar el cierre de la evaluación %s (%s)", evaluacion_id, type(e).__name__)
    if not settings.DOCUMENTOS_ARCHIVAR_AL_COMPLETAR:
        return None
    try:
        evaluacion = await fabricas().documentos_empresa(db).obtener_evaluacion(evaluacion_id)
        documento = await archivar_informe(db, evaluacion, actor)
        await db.commit()
        return documento.id
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.error("HU-29: no se pudo archivar el informe de la evaluación %s (%s)", evaluacion_id, type(e).__name__)
        return None
