"""Constantes, errores y utilidades compartidas de "Mis documentos"."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.application.fabricas import fabricas
from app.domain.models.documento_empresa import DocumentoEmpresa
from app.domain.models.evidencia import EstadoValidacion

# Nombre de descarga de un documento: lo arma el sistema y pasa tal cual por el BFF
NOMBRE_SEGURO = re.compile(r"^[A-Za-z0-9_.-]{1,150}$")
_EN_PROCESO = (EstadoValidacion.PENDING.value, EstadoValidacion.PROCESSING.value)
_EXTENSIONES = {"application/pdf": ".pdf", "text/plain": ".txt",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx"}


class DocumentoError(Exception):
    def __init__(self, status_code: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.status_code, self.codigo = status_code, codigo

    def detalle(self) -> dict:
        return {"codigo": self.codigo, "mensaje": str(self)}


def _no_encontrado(que: str = "Documento") -> DocumentoError:
    return DocumentoError(404, "DOCUMENTO_NO_ENCONTRADO", f"{que} no encontrado.")


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _storage_documentos():
    return fabricas().storage_documentos()


def _storage_evidencias():
    return fabricas().storage_evidencias()



def _doc_dict(d: DocumentoEmpresa, extra: dict | None = None) -> dict:
    return {
        "id": d.id, "tipo": d.tipo, "nombre": d.nombre, "evaluacion_id": d.evaluacion_id,
        "mime_type": d.mime_type, "tamano_bytes": d.tamano_bytes, "fecha_creacion": d.fecha_creacion,
        "descarga": f"/api/cliente/documentos/{d.id}/descarga",
        **(extra or {}),
    }
