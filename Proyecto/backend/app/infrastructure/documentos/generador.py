"""Adaptador de GeneradorDocumentosPort: delega en las funciones generar_* (reportlab y openpyxl, import diferido)."""
from __future__ import annotations

from app.application.formacion.constancia import DatosConstancia
from app.application.informes.datos_informe import DatosInforme
from app.application.mapa_datos.informe_mapa import DatosInformeMapa
from app.application.rat.constancia_revision import DatosConstancia as DatosConstanciaRevision
from app.application.rat.informe_rat import InformeRat
from app.application.ropa.informe_ropa import InformeRopa


class GeneradorDocumentos:
    """Implementa GeneradorDocumentosPort."""

    def pdf_informe(self, d: DatosInforme) -> bytes:
        from app.infrastructure.documentos.pdf.informe_evaluacion import generar_pdf
        return generar_pdf(d)

    def pdf_borrador(self, markdown: str, *, titulo: str, pie: str, marca_agua: str | None = None) -> bytes:
        from app.infrastructure.documentos.pdf.borrador import generar_pdf_borrador
        return generar_pdf_borrador(markdown, titulo=titulo, pie=pie, marca_agua=marca_agua)

    def pdf_constancia_formacion(self, d: DatosConstancia) -> bytes:
        from app.infrastructure.documentos.pdf.constancia import generar_constancia
        return generar_constancia(d)

    def pdf_mapa_datos(self, d: DatosInformeMapa) -> bytes:
        from app.infrastructure.documentos.pdf.mapa_datos import generar_pdf_mapa
        return generar_pdf_mapa(d)

    def pdf_rat(self, inf: InformeRat) -> bytes:
        from app.infrastructure.documentos.pdf.rat import generar_pdf_rat
        return generar_pdf_rat(inf)

    def pdf_revision_interna(self, d: DatosConstanciaRevision) -> bytes:
        from app.infrastructure.documentos.pdf.revision_interna import generar_pdf_revision
        return generar_pdf_revision(d)

    def pdf_ropa(self, inf: InformeRopa) -> bytes:
        from app.infrastructure.documentos.pdf.ropa import generar_pdf_ropa
        return generar_pdf_ropa(inf)

    def xlsx_rat(self, inf: InformeRat) -> bytes:
        from app.infrastructure.documentos.xlsx.rat import generar_xlsx_rat
        return generar_xlsx_rat(inf)

    def xlsx_ropa(self, inf: InformeRopa) -> bytes:
        from app.infrastructure.documentos.xlsx.ropa import generar_xlsx_ropa
        return generar_xlsx_ropa(inf)
