"""Evidencias y constancias de "Mis documentos": descargar y eliminar."""
from __future__ import annotations

import logging

from app.domain.auditoria.acciones import Accion
from app.domain.models.evidencia import Evidencia
from app.application.empresa.casos_uso.documentos_empresa.comun import (
    _EN_PROCESO, _EXTENSIONES, DocumentoError, _ahora, _no_encontrado,
)

logger = logging.getLogger(__name__)


class AccionesEvidenciaMixin:
    async def _evidencia(self, evidencia_id: int) -> tuple[Evidencia, int]:
        fila = await self.repo.obtener_evidencia_de_empresa(evidencia_id, self.empresa.id)
        if fila is None or fila[0].eliminada:
            raise _no_encontrado("Evidencia")
        return fila[0], fila[1]

    @staticmethod
    def _en_proceso(e: Evidencia) -> DocumentoError | None:
        if e.estado_validacion in _EN_PROCESO:
            return DocumentoError(409, "EVIDENCIA_EN_PROCESO",
                                  "La evidencia aún se está validando. Inténtalo en unos minutos.")
        return None

    async def descargar_evidencia(self, evidencia_id: int) -> tuple[bytes, str, str]:
        e, evaluacion_id = await self._evidencia(evidencia_id)
        if (error := self._en_proceso(e)) is not None:
            raise error
        if not e.storage_path:
            raise DocumentoError(404, "ARCHIVO_NO_DISPONIBLE", "El archivo ya no está disponible.")
        storage = self.storage_evidencias
        try:
            crudo = await storage.interno.get(e.storage_path)
        except FileNotFoundError:
            raise DocumentoError(404, "ARCHIVO_NO_DISPONIBLE", "El archivo ya no está disponible.")
        cifrado = storage.cifrador.esta_cifrado(crudo)
        contenido = storage.cifrador.descifrar_bytes(crudo)
        if cifrado:
            # Aún es el archivo original (el motor de anonimización no estaba activo o falló)
            mime = e.mime_type or "application/octet-stream"
            nombre = f"evidencia-{e.id_evidencia}{_EXTENSIONES.get(mime, '')}"
        else:
            # HU-06: en el disco solo queda el texto anonimizado
            mime, nombre = "text/plain", f"evidencia-{e.id_evidencia}_anonimizada.txt"
        self.bitacora.registrar(
            accion=Accion.DOCUMENTO_DESCARGADO, entidad="evidencia", entidad_id=e.id_evidencia,
            actor=self.cliente.actor, detalle={"tipo": "evidencia", "evaluacion_id": evaluacion_id,
                                               "anonimizada": not cifrado},
        )
        await self.db.commit()
        return contenido, nombre, mime

    async def eliminar_evidencia(self, evidencia_id: int) -> None:
        e, evaluacion_id = await self._evidencia(evidencia_id)
        if (error := self._en_proceso(e)) is not None:
            raise error  # el worker la está procesando: borrarla ahora rompería su resultado
        ruta = e.storage_path
        e.storage_path = ""
        e.datos_extraidos = None
        e.fecha_eliminacion = _ahora()
        self.bitacora.registrar(
            accion=Accion.DOCUMENTO_ELIMINADO, entidad="evidencia", entidad_id=e.id_evidencia,
            actor=self.cliente.actor,
            detalle={"tipo": "evidencia", "evaluacion_id": evaluacion_id, "origen": e.origen,
                     "estado_validacion": e.estado_validacion},
        )
        await self.db.commit()
        if ruta:
            try:
                await self.storage_evidencias.delete(ruta)
            except Exception as ex:  # noqa: BLE001
                logger.error("HU-29: no se pudo borrar el archivo de la evidencia %s (%s)",
                             evidencia_id, type(ex).__name__)

    # ---------------------------------------------------------------- constancias
    async def eliminar_constancia(self, ruta_id: int) -> None:
        a = await self.repo.obtener_avance(self.empresa.id, ruta_id)
        if a is None or not a.codigo_constancia:
            raise _no_encontrado("Constancia")
        a.codigo_constancia = None
        a.fecha_eliminacion_constancia = _ahora()
        self.bitacora.registrar(
            accion=Accion.DOCUMENTO_ELIMINADO, entidad="avance_formativo", entidad_id=a.id,
            actor=self.cliente.actor, detalle={"tipo": "constancia", "ruta_id": ruta_id},
        )
        await self.db.commit()
