"""Listado consolidado de "Mis documentos" (informes, borradores, registro, evidencias y constancias)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.core.config import settings
from app.domain.models.documento_empresa import TIPO_BORRADOR, TIPO_INFORME, TIPOS_RAT, TIPOS_ROPA
from app.application.empresa.casos_uso.documentos_empresa.comun import _EN_PROCESO, _doc_dict


async def _emisiones_rat(db: AsyncSession, empresa_id: int) -> dict[int, dict]:
    """HU-36: código, versión y estado de la emisión de cada documento del RAT (por id de documento)."""
    filas = await fabricas().documentos_empresa(db).informes_rat(empresa_id)
    salida: dict[int, dict] = {}
    for r in filas:
        datos = {"rat": {"informe_id": r.id, "codigo": r.codigo, "version_rat": r.version_rat,
                         "borrador": r.borrador, "actividades": r.actividades}}
        for doc_id in (r.documento_pdf_id, r.documento_xlsx_id):
            if doc_id:
                salida[doc_id] = datos
    return salida


async def _emisiones_ropa(db: AsyncSession, empresa_id: int) -> dict[int, dict]:
    """HU-37: código, versión y partes de la emisión de cada documento del informe RoPA (por id de documento)."""
    filas = await fabricas().documentos_empresa(db).informes_ropa(empresa_id)
    salida: dict[int, dict] = {}
    for r in filas:
        datos = {"ropa": {"informe_id": r.id, "codigo": r.codigo, "version": r.version,
                          "partes": list(r.partes or []), "actividades": r.actividades}}
        for doc_id in (r.documento_pdf_id, r.documento_xlsx_id):
            if doc_id:
                salida[doc_id] = datos
    return salida


class ListadoDocumentosMixin:
    # ---------------------------------------------------------------- listado
    async def listar(self) -> dict:
        documentos = await self.repo.documentos_de_empresa(self.empresa.id)

        evidencias = await self.repo.evidencias_de_empresa(self.empresa.id)  # HU-38: sin las del registro

        emisiones = await _emisiones_rat(self.db, self.empresa.id) if any(
            d.tipo in TIPOS_RAT for d in documentos) else {}
        if any(d.tipo in TIPOS_ROPA for d in documentos):          # HU-37
            emisiones.update(await _emisiones_ropa(self.db, self.empresa.id))

        constancias = await self.repo.avances_con_constancia(self.empresa.id)

        return {
            "empresa": {"id": self.empresa.id, "razon_social": self.empresa.razon_social},
            "informes": [_doc_dict(d) for d in documentos if d.tipo == TIPO_INFORME],
            # HU-16: los borradores se guardan con guardar_documento(tipo="borrador")
            "borradores": [_doc_dict(d) for d in documentos if d.tipo == TIPO_BORRADOR],
            # HU-36: informes del registro de actividades (PDF y XLSX), con su código verificable
            # HU-37: también los informes RoPA (PDF y XLSX), con su código y versión
            "registro_actividades": [_doc_dict(d, emisiones.get(d.id)) for d in documentos
                                     if d.tipo in TIPOS_RAT or d.tipo in TIPOS_ROPA],
            "evidencias": [{
                "id": e.id_evidencia, "nombre": e.nombre_archivo, "evaluacion_id": ev_id,
                "control": codigo, "origen": e.origen, "fecha_subida": e.fecha_subida,
                "estado_validacion": e.estado_validacion, "clasificacion": e.clasificacion_llm,
                "en_proceso": e.estado_validacion in _EN_PROCESO,
                "descarga": f"/api/cliente/documentos/evidencias/{e.id_evidencia}/descarga",
            } for e, ev_id, codigo in evidencias],
            "constancias": [{
                "ruta_id": a.ruta_formativa_id, "modulo": nombre or f"Ruta {a.ruta_formativa_id}",
                "fecha_completado": a.fecha_completado, "codigo": a.codigo_constancia,
                "descarga": f"/api/formacion/modulos/{a.ruta_formativa_id}/constancia",
            } for a, nombre in constancias if a.completado],
            "documentos_disponibles_hasta": self.empresa.vigencia(settings.CONTRATO_GRACIA_DIAS).como_dict()["documentos_disponibles_hasta"],
        }
