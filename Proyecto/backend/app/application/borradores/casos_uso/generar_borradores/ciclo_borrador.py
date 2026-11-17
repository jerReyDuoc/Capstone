"""Revisión, edición, descarga, consolidación y descarte del borrador (C3)."""
from __future__ import annotations

from datetime import timezone

from app.application.borradores import generador_markdown as generador
from app.application.ports.generador_documentos_port import PdfNoDisponibleError
from app.application.borradores.plantillas_borrador import plantilla as obtener_plantilla
from app.application.fabricas import fabricas
from app.core.config import settings
from app.domain.models.borrador_modelo import BorradorDocumento, EstadoBorrador
from app.domain.models.documento_empresa import TIPO_BORRADOR
from app.domain.auditoria.acciones import Accion
from app.application.borradores.casos_uso.generar_borradores.comun import (
    ZONA,
    MAX_PENDIENTES_LISTA,
    MIME_MD,
    MIME_PDF,
    BorradorError,
    _ahora,
    borrador_a_dict,
)

class RevisionMixin:
    """Revisión, edición, descarga, consolidación y descarte del borrador (C3)."""

    # ------------------------------------------------------------------ revisión y edición (C3)
    def _editable(self, b: BorradorDocumento, version: int | None) -> None:
        if not b.editable:
            raise BorradorError(409, "BORRADOR_CONSOLIDADO",
                                "Este borrador ya está consolidado: es de solo lectura. Genera uno nuevo para cambiarlo.")
        if version is not None and version != b.version:
            raise BorradorError(409, "VERSION_DESACTUALIZADA",
                                "El borrador cambió desde que lo abriste (otra pestaña u otra persona). Recárgalo "
                                "para no perder cambios.", version_actual=b.version)

    async def editar(self, borrador_id: int, contenido: str | None, version: int | None) -> dict:
        b = await self._borrador(borrador_id)
        self._editable(b, version)
        texto = (contenido or "").replace("\r\n", "\n").strip()
        if not texto:
            raise BorradorError(422, "CONTENIDO_VACIO", "El borrador no puede quedar vacío.")
        if len(texto) > settings.BORRADORES_MAX_CHARS_CONTENIDO:
            raise BorradorError(422, "CONTENIDO_DEMASIADO_LARGO",
                                f"El borrador supera los {settings.BORRADORES_MAX_CHARS_CONTENIDO} caracteres.",
                                max_caracteres=settings.BORRADORES_MAX_CHARS_CONTENIDO)
        texto += "\n"
        if texto == b.contenido:
            return {"borrador": borrador_a_dict(b, con_contenido=True)}
        b.contenido = texto
        b.version = (b.version or 1) + 1
        b.fecha_actualizacion = _ahora()
        self.bitacora.registrar(
            accion=Accion.BORRADOR_EDITADO, entidad="borrador_documento", entidad_id=b.id, actor=self.cliente.actor,
            detalle={"tipo": b.tipo, "version": b.version, "largo": len(texto),
                     "pendientes": len(generador.pendientes(texto))},
        )
        await self.db.commit()
        return {"borrador": borrador_a_dict(b, con_contenido=True)}

    def _plantilla(self, b: BorradorDocumento):
        return obtener_plantilla(b.tipo)

    def _pdf(self, b: BorradorDocumento, consolidado: bool) -> bytes:
        fecha = (b.fecha_consolidacion or _ahora()).replace(tzinfo=timezone.utc).astimezone(ZONA)
        pie = (f"{self.empresa.razon_social} · Versión consolidada el {fecha:%d-%m-%Y}" if consolidado
               else f"{self.empresa.razon_social} · Borrador en revisión (versión {b.version})")
        try:
            return fabricas().documentos.pdf_borrador(b.contenido, titulo=b.titulo, pie=pie,
                                                      marca_agua=None if consolidado else "BORRADOR")
        except PdfNoDisponibleError as e:
            raise BorradorError(503, "PDF_NO_DISPONIBLE", str(e))

    async def descargar(self, borrador_id: int, formato: str) -> tuple[bytes, str, str]:
        b = await self._borrador(borrador_id)
        formato = (formato or "").lower()
        if formato not in ("md", "pdf"):
            raise BorradorError(422, "FORMATO_INVALIDO", "El formato debe ser md o pdf.")
        consolidado = not b.editable
        base = f"{self._plantilla(b).nombre_corto}_{'consolidado' if consolidado else 'borrador'}-{b.id}_v{b.version}"
        if formato == "md":
            contenido, nombre, mime = b.contenido.encode("utf-8"), f"{base}.md", MIME_MD
        else:
            contenido, nombre, mime = self._pdf(b, consolidado), f"{base}.pdf", MIME_PDF
        self.bitacora.registrar(
            accion=Accion.BORRADOR_DESCARGADO, entidad="borrador_documento", entidad_id=b.id, actor=self.cliente.actor,
            detalle={"tipo": b.tipo, "formato": formato, "version": b.version, "estado": b.estado},
        )
        await self.db.commit()
        return contenido, nombre, mime

    # ------------------------------------------------------------------ consolidar (C3)
    async def consolidar(self, borrador_id: int, version: int | None, confirmar_pendientes: bool = False) -> dict:
        from app.application.empresa.casos_uso.documentos_empresa import _doc_dict, guardar_documento

        b = await self._borrador(borrador_id)
        self._editable(b, version)
        pend = generador.pendientes(b.contenido)
        if pend and not confirmar_pendientes:
            raise BorradorError(409, "CAMPOS_PENDIENTES",
                                f"El borrador tiene {len(pend)} campos por completar. Complétalos o confirma que "
                                "quieres consolidarlo así.", pendientes=pend[:MAX_PENDIENTES_LISTA], total=len(pend))
        ahora = _ahora()
        b.fecha_consolidacion = ahora
        pdf = self._pdf(b, consolidado=True)
        local = ahora.replace(tzinfo=timezone.utc).astimezone(ZONA)
        nombre = f"{self._plantilla(b).nombre_corto}_{local:%Y-%m-%d}_{b.id}.pdf"
        try:
            doc = await guardar_documento(
                self.db, empresa_id=self.empresa.id, tipo=TIPO_BORRADOR, nombre=nombre, contenido=pdf,
                mime_type=MIME_PDF, evaluacion_id=b.evaluacion_id, actor=self.cliente.actor,
            )
        except Exception:
            await self.db.rollback()
            raise
        b.estado = EstadoBorrador.CONSOLIDADO.value
        b.documento_id = doc.id
        b.fecha_actualizacion = ahora
        self.bitacora.registrar(
            accion=Accion.BORRADOR_CONSOLIDADO, entidad="borrador_documento", entidad_id=b.id, actor=self.cliente.actor,
            detalle={"tipo": b.tipo, "version": b.version, "documento_id": doc.id, "pendientes": len(pend),
                     "confirmo_pendientes": bool(pend), "evaluacion_id": b.evaluacion_id},
        )
        await self.db.commit()
        return {"borrador": borrador_a_dict(b, con_contenido=True), "documento": _doc_dict(doc)}

    async def descartar(self, borrador_id: int) -> None:
        b = await self._borrador(borrador_id)
        detalle = {"tipo": b.tipo, "estado": b.estado, "version": b.version, "documento_id": b.documento_id}
        await self.repo.eliminar(b)
        self.bitacora.registrar(
            accion=Accion.BORRADOR_DESCARTADO, entidad="borrador_documento", entidad_id=borrador_id,
            actor=self.cliente.actor, detalle=detalle,
        )
        await self.db.commit()
