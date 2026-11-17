"""Emisión del informe RAT: listado de emisiones, reutilización, límites y guardado de PDF y XLSX."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as dtime

from app.application.ports.generador_documentos_port import MIME_XLSX, PdfNoDisponibleError, XlsxNoDisponibleError
from app.application.rat import armado_informe_rat as I
from app.application.informes.formato import ZONA
from app.application.empresa.casos_uso.documentos_empresa import guardar_documento
from app.application.fabricas import fabricas
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.documento_empresa import TIPO_RAT_PDF, TIPO_RAT_XLSX, DocumentoEmpresa
from app.domain.models.rat_informe import RatInforme
from app.domain.auditoria.acciones import Accion
from app.application.rat.casos_uso.generar_informe.comun import (
    MAX_HISTORIAL, InformeRatError, _ahora, _fecha_txt, _iso, _naive,
)

logger = logging.getLogger(__name__)


class EmisionInformeMixin:
    async def _ultima(self) -> RatInforme | None:
        return await self.repo.ultima_emision(self.empresa_id)

    async def _documento(self, doc_id: int | None) -> DocumentoEmpresa | None:
        if not doc_id:
            return None
        doc = await self.repo.documento(doc_id)
        return doc if doc is not None and doc.empresa_id == self.empresa_id else None

    async def _vista_emision(self, r: RatInforme) -> dict:
        pdf, xlsx = await self._documento(r.documento_pdf_id), await self._documento(r.documento_xlsx_id)

        def doc(d: DocumentoEmpresa | None) -> dict | None:
            return {"id": d.id, "nombre": d.nombre, "tamano_bytes": d.tamano_bytes} if d else None

        marca = await self._marca(revision_id=r.revision_id) if getattr(r, "revision_id", None) else None
        return {
            "id": r.id, "codigo": r.codigo, "version_rat": r.version_rat, "fecha": _iso(r.fecha),
            "revision": I.marca_dict(marca),
            "borrador": r.borrador, "motivos_borrador": list(r.motivos_borrador or []), "actividades": r.actividades,
            "huella": r.huella, "huella_legible": I.huella_legible(r.huella), "resumen": r.resumen or {},
            "aviso_version": r.aviso_version, "documentos": {"pdf": doc(pdf), "xlsx": doc(xlsx)},
        }

    async def listar(self) -> dict:
        inf = await self.armar()
        filas = await self.repo.emisiones_recientes(self.empresa_id, MAX_HISTORIAL)
        emisiones = [await self._vista_emision(r) for r in filas]
        ultima = filas[0] if filas else None
        al_dia = bool(ultima and ultima.huella == inf.huella and ultima.borrador == inf.borrador
                      and ultima.revision_id == (inf.revision.id if inf.revision else None))
        return {
            "previa": {**I.resumen_publico(inf), "puede_emitir": bool(inf.actividades),
                       "version_siguiente": (ultima.version_rat + (0 if ultima.huella == inf.huella else 1)) if ultima else 1},
            "al_dia": al_dia,
            "ultima": emisiones[0] if emisiones else None,
            "emisiones": emisiones,
            "limites": {"emisiones_dia": settings.RAT_INFORMES_DIA_EMPRESA, "correos_dia": settings.RAT_CORREOS_DIA_EMPRESA},
            "correo_habilitado": settings.CORREO_MODO != "desactivado",
        }

    async def _rechazar(self, motivo: str, error: InformeRatError, **detalle) -> InformeRatError:
        await self.db.rollback()
        self.bitacora.registrar(accion=Accion.RAT_INFORME_GENERADO, entidad="rat_informe", entidad_id=None,
                                actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": motivo, **detalle})
        await self.db.commit()
        return error

    @property
    def storage(self):
        if self._storage is None:
            self._storage = fabricas().storage_documentos()
        return self._storage

    async def emitir(self, forzar: bool = False) -> dict:
        generado = _ahora()
        # Serializa las emisiones de la empresa (la versión del RAT es un correlativo)
        await self.repo.bloquear_empresa(self.empresa_id)
        inf = await self.armar(generado)
        if not inf.actividades:
            raise await self._rechazar("registro_vacio", InformeRatError(
                409, "RAT_VACIO", "Tu registro aún no tiene actividades. Registra al menos una para generar el informe."))
        ultima = await self._ultima()
        revision_id = inf.revision.id if inf.revision else None
        if (ultima is not None and not forzar and ultima.huella == inf.huella and ultima.borrador == inf.borrador
                and ultima.revision_id == revision_id):
            vista = await self._vista_emision(ultima)
            if vista["documentos"]["pdf"] and vista["documentos"]["xlsx"]:
                # El texto se arma ANTES del rollback: después, `ultima` queda expirada y leer su fecha
                # obligaría a SQLAlchemy a recargarla fuera del contexto async (error 500)
                mensaje = (f"Tu registro no cambió desde la emisión del {_fecha_txt(ultima.fecha)}: "
                           "usamos ese mismo informe.")
                await self.db.rollback()        # libera el bloqueo de la empresa
                return {"informe": vista, "reutilizado": True, "mensaje": mensaje}
        inicio_dia = datetime.combine(generado.astimezone(ZONA).date(), dtime.min, tzinfo=ZONA)
        hoy = await self.repo.contar_emisiones_desde(self.empresa_id, _naive(inicio_dia))
        if hoy >= settings.RAT_INFORMES_DIA_EMPRESA:
            raise await self._rechazar("limite_diario", InformeRatError(
                429, "LIMITE_INFORMES", f"Ya generaste {hoy} informes hoy. Descarga uno de los anteriores o vuelve a "
                                        "intentarlo mañana."))
        version = (ultima.version_rat + (0 if ultima.huella == inf.huella else 1)) if ultima else 1
        fila = RatInforme(
            empresa_id=self.empresa_id, codigo=None, version_rat=version, huella=inf.huella, borrador=inf.borrador,
            motivos_borrador=list(inf.motivos_borrador), actividades=len(inf.actividades), resumen=inf.resumen,
            versiones=[{"id": a.id, "version": a.version, "huella": a.huella_version} for a in inf.actividades],
            aviso_version=inf.aviso.version, fecha=_naive(generado), usuario_definitivo_id=self.usuario_id,
            revision_id=revision_id)
        self.repo.agregar(fila)
        await self.db.flush()
        fila.codigo = I.codigo(fila.id, generado.astimezone(ZONA).year)
        inf = inf.con_emision(fila.codigo, version)

        try:
            pdf, xlsx = await asyncio.gather(asyncio.to_thread(fabricas().documentos.pdf_rat, inf),
                                             asyncio.to_thread(fabricas().documentos.xlsx_rat, inf))
        except (PdfNoDisponibleError, XlsxNoDisponibleError) as e:
            await self.db.rollback()
            raise InformeRatError(503, "INFORME_NO_DISPONIBLE", str(e))
        guardados: list[str] = []
        try:
            doc_pdf = await guardar_documento(
                self.db, empresa_id=self.empresa_id, tipo=TIPO_RAT_PDF, nombre=I.nombre_archivo(inf, "pdf"),
                contenido=pdf, mime_type="application/pdf", actor=self.actor, storage=self.storage)
            guardados.append(doc_pdf.storage_path)
            doc_xlsx = await guardar_documento(
                self.db, empresa_id=self.empresa_id, tipo=TIPO_RAT_XLSX, nombre=I.nombre_archivo(inf, "xlsx"),
                contenido=xlsx, mime_type=MIME_XLSX, actor=self.actor, storage=self.storage)
            guardados.append(doc_xlsx.storage_path)
            fila.documento_pdf_id, fila.documento_xlsx_id = doc_pdf.id, doc_xlsx.id
            self.bitacora.registrar(
                accion=Accion.RAT_INFORME_GENERADO, entidad="rat_informe", entidad_id=fila.id, actor=self.actor,
                detalle={"version_rat": version, "borrador": inf.borrador, "actividades": len(inf.actividades),
                         "huella": inf.huella[:16], "forzado": forzar, "documentos": [doc_pdf.id, doc_xlsx.id],
                         "revision_id": revision_id})
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            for ruta in guardados:            # sin la fila, el archivo cifrado no sirve: se borra
                try:
                    await self.storage.delete(ruta)
                except Exception:  # noqa: BLE001
                    logger.error("HU-36: no se pudo borrar un archivo del informe que no se guardó")
            raise
        await self.db.refresh(fila)
        return {"informe": await self._vista_emision(fila), "reutilizado": False,
                "mensaje": ("Generamos el informe como borrador: hay actividades que no están vigentes."
                            if inf.borrador else f"Generamos el informe oficial de la versión {version} de tu registro.")}
