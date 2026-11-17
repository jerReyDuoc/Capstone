"""Informes y borradores de "Mis documentos": archivar, descargar y eliminar."""
from __future__ import annotations

import hashlib
import logging

from app.application.empresa.casos_uso.documentos_empresa.comun import (
    DocumentoError, _doc_dict, _no_encontrado,
)
from app.application.empresa.casos_uso.documentos_empresa.guardado_documentos import archivar_informe
from app.domain.auditoria.acciones import Accion
from app.domain.models.documento_empresa import DocumentoEmpresa

logger = logging.getLogger(__name__)


class AccionesDocumentoMixin:
    async def _documento(self, documento_id: int) -> DocumentoEmpresa:
        doc = await self.repo.obtener_documento(documento_id)
        if doc is None or doc.empresa_id != self.empresa.id:  # lo ajeno no existe (404, no 403)
            raise _no_encontrado()
        return doc

    async def archivar_informe(self, evaluacion_id: int) -> dict:
        evaluacion = await self.repo.obtener_evaluacion(evaluacion_id)
        if evaluacion is None or evaluacion.empresa_id != self.empresa.id:
            raise DocumentoError(404, "EVALUACION_NO_ENCONTRADA", "Evaluación no encontrada.")
        doc = await archivar_informe(self.db, evaluacion, self.cliente.actor)
        await self.db.commit()
        return _doc_dict(doc)

    async def descargar_documento(self, documento_id: int) -> tuple[bytes, str, str]:
        doc = await self._documento(documento_id)
        try:
            contenido = await self.storage_documentos.get(doc.storage_path)
        except FileNotFoundError:
            raise DocumentoError(404, "ARCHIVO_NO_DISPONIBLE", "El archivo ya no está disponible.")
        if hashlib.sha256(contenido).hexdigest() != doc.hash_contenido:
            logger.error("HU-29: el documento %s no coincide con su hash", doc.id)
            raise DocumentoError(500, "DOCUMENTO_DANADO", "El documento está dañado. Contacta a Therion Labs.")
        self.bitacora.registrar(
            accion=Accion.DOCUMENTO_DESCARGADO, entidad="documento_empresa", entidad_id=doc.id,
            actor=self.cliente.actor, detalle={"tipo": doc.tipo, "evaluacion_id": doc.evaluacion_id},
        )
        await self.db.commit()
        return contenido, doc.nombre, doc.mime_type

    async def eliminar_documento(self, documento_id: int) -> None:
        doc = await self._documento(documento_id)
        ruta, detalle = doc.storage_path, {"tipo": doc.tipo, "evaluacion_id": doc.evaluacion_id,
                                           "documento_id": doc.id, "tamano_bytes": doc.tamano_bytes}
        await self.repo.eliminar_documento(doc)
        self.bitacora.registrar(
            accion=Accion.DOCUMENTO_ELIMINADO, entidad="documento_empresa", entidad_id=documento_id,
            actor=self.cliente.actor, detalle=detalle,
        )
        await self.db.commit()
        # El archivo se borra DESPUÉS del commit: si la transacción fallara, el documento seguiría
        # listado y descargable. Si el borrado del disco falla queda un archivo huérfano cifrado.
        try:
            await self.storage_documentos.delete(ruta)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-29: no se pudo borrar el archivo del documento %s (%s)", documento_id, type(e).__name__)
