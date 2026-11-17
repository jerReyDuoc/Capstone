"""
Puerto de generación de documentos (PDF y XLSX de informes, borradores y constancias).

Vive en application (no en domain) porque recibe los DTO de aplicación de cada informe. Las excepciones
son únicas: cada adaptador lanza la suya cuando falta la librería de dibujo (las rutas responden 503).
"""
from __future__ import annotations

from typing import Protocol

from app.application.formacion.datos_constancia import DatosConstancia
from app.application.informes.datos_informe import DatosInforme
from app.application.mapa_datos.informe_mapa import DatosInformeMapa
from app.application.rat.constancia_revision import DatosConstancia as DatosConstanciaRevision
from app.application.rat.armado_informe_rat import InformeRat
from app.application.ropa.armado_informe_ropa import InformeRopa

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class DocumentoNoDisponibleError(Exception):
    """Falta la librería que dibuja el documento: solo fallan las descargas de ese formato (503)."""


class PdfNoDisponibleError(DocumentoNoDisponibleError):
    pass


class XlsxNoDisponibleError(DocumentoNoDisponibleError):
    pass


class GeneradorDocumentosPort(Protocol):
    def pdf_informe(self, d: DatosInforme) -> bytes: ...

    def pdf_borrador(self, markdown: str, *, titulo: str, pie: str, marca_agua: str | None = None) -> bytes: ...

    def pdf_constancia_formacion(self, d: DatosConstancia) -> bytes: ...

    def pdf_mapa_datos(self, d: DatosInformeMapa) -> bytes: ...

    def pdf_rat(self, inf: InformeRat) -> bytes: ...

    def pdf_revision_interna(self, d: DatosConstanciaRevision) -> bytes: ...

    def pdf_ropa(self, inf: InformeRopa) -> bytes: ...

    def xlsx_rat(self, inf: InformeRat) -> bytes: ...

    def xlsx_ropa(self, inf: InformeRopa) -> bytes: ...
