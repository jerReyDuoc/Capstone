"""Descarga y envío por correo de una emisión del informe RAT."""
from __future__ import annotations

import hashlib
import logging
from datetime import timezone

from app.application.informes import correo
from app.domain.ports.correo_port import Adjunto, CorreoFallidoError, CorreoNoDisponibleError
from app.application.rat import correo_rat
from app.application.rat import armado_informe_rat as I
from app.application.encuesta_publica.casos_uso.limites_encuesta import ventana_diaria
from app.application.fabricas import fabricas
from app.core.config import settings
from app.domain.models.documento_empresa import DocumentoEmpresa
from app.domain.models.rat_informe import RatInforme
from app.domain.ports.limitador_port import LimitadorNoDisponibleError
from app.domain.auditoria.acciones import Accion
from app.application.rat.casos_uso.generar_informe.comun import FORMATOS, InformeRatError

logger = logging.getLogger(__name__)


class DescargaEnvioInformeMixin:
    async def _emision(self, informe_id: int) -> RatInforme:
        fila = await self.repo.emision(informe_id)
        if fila is None or fila.empresa_id != self.empresa_id:        # lo ajeno no existe (404)
            raise InformeRatError(404, "INFORME_NO_ENCONTRADO", "No encontramos ese informe de tu empresa.")
        return fila

    async def _archivo(self, fila: RatInforme, formato: str) -> tuple[bytes, DocumentoEmpresa]:
        if formato not in FORMATOS:
            raise InformeRatError(422, "FORMATO_INVALIDO", "Elige PDF o Excel.")
        doc = await self._documento(fila.documento_pdf_id if formato == "pdf" else fila.documento_xlsx_id)
        if doc is None:
            raise InformeRatError(410, "ARCHIVO_ELIMINADO", "Ese archivo se eliminó de Mis documentos. Genera el informe "
                                                            "de nuevo para obtenerlo.")
        try:
            contenido = await self.storage.get(doc.storage_path)
        except FileNotFoundError:
            raise InformeRatError(410, "ARCHIVO_ELIMINADO", "El archivo ya no está disponible. Genera el informe de nuevo.")
        if hashlib.sha256(contenido).hexdigest() != doc.hash_contenido:
            logger.error("HU-36: el documento %s del informe %s no coincide con su hash", doc.id, fila.id)
            raise InformeRatError(500, "DOCUMENTO_DANADO", "El documento está dañado. Genera el informe de nuevo o "
                                                           "contacta a Therion Labs.")
        return contenido, doc

    async def descargar(self, informe_id: int, formato: str) -> tuple[bytes, str, str]:
        fila = await self._emision(informe_id)
        contenido, doc = await self._archivo(fila, formato)
        self.bitacora.registrar(
            accion=Accion.RAT_INFORME_DESCARGADO, entidad="rat_informe", entidad_id=fila.id, actor=self.actor,
            detalle={"formato": formato, "documento_id": doc.id, "version_rat": fila.version_rat,
                     "borrador": fila.borrador})
        await self.db.commit()
        return contenido, doc.nombre, doc.mime_type

    async def _informe_de(self, fila: RatInforme) -> I.InformeRat:
        """Lo mínimo para el cuerpo del correo (las cifras guardadas al emitir)."""
        marca = await self._marca(revision_id=fila.revision_id) if fila.revision_id else None
        return I.InformeRat(
            empresa=self.razon_social, rut=self.rut, rubro=None,
            generado=fila.fecha.replace(tzinfo=timezone.utc), actividades=(), resumen=fila.resumen or {},
            borrador=fila.borrador, motivos_borrador=tuple(fila.motivos_borrador or []), huella=fila.huella,
            riesgos=(), codigo=fila.codigo, version_rat=fila.version_rat, revision=marca, revision_aplica=True)

    async def enviar(self, informe_id: int, email: str | None, formatos: list[str]) -> dict:
        if settings.CORREO_MODO == "desactivado":
            raise InformeRatError(503, "CORREO_NO_DISPONIBLE", "El envío por correo no está habilitado. Descarga el informe.")
        formatos = [f for f in FORMATOS if f in set(formatos or FORMATOS)]
        if not formatos:
            raise InformeRatError(422, "FORMATO_INVALIDO", "Elige al menos un formato para adjuntar.")
        destino = (email or "").strip().lower() or self.email_usuario
        if not correo.EMAIL_VALIDO.match(destino or ""):
            raise InformeRatError(422, "EMAIL_INVALIDO", "Revisa el formato del correo (ejemplo: nombre@empresa.cl).")
        fila = await self._emision(informe_id)
        adjuntos = []
        for f in formatos:                    # 410 antes de gastar el cupo
            contenido, doc = await self._archivo(fila, f)
            adjuntos.append(Adjunto(doc.nombre, contenido, doc.mime_type))

        fecha, ventana, _ = ventana_diaria()
        clave = f"rat:correo:{self.empresa_id}:{fecha}"
        if self.limitador is None:
            raise InformeRatError(503, "LIMITADOR_NO_DISPONIBLE", "No pudimos enviar el correo ahora. Descarga el informe.")
        try:
            consumo = await self.limitador.consumir(clave, settings.RAT_CORREOS_DIA_EMPRESA, ventana)
        except LimitadorNoDisponibleError:
            raise InformeRatError(503, "LIMITADOR_NO_DISPONIBLE", "No pudimos enviar el correo ahora. Descarga el informe.")
        if not consumo.permitido:
            await self.limitador.devolver(clave)
            raise InformeRatError(429, "LIMITE_CORREOS", f"Ya enviaste el informe {settings.RAT_CORREOS_DIA_EMPRESA} "
                                                         "veces hoy. Descárgalo o vuelve a intentarlo mañana.",
                                  reintentar_en_s=consumo.reintentar_en_s)
        inf = await self._informe_de(fila)
        texto, html = correo_rat.cuerpo(inf, formatos)
        try:
            modo = await fabricas().correo.enviar(destino, correo_rat.asunto(inf), texto, html, adjuntos)
        except (CorreoFallidoError, CorreoNoDisponibleError) as e:
            await self.limitador.devolver(clave)
            logger.warning("[informe_rat] envío fallido empresa %s: %s", self.empresa_id, type(e).__name__)
            raise InformeRatError(502 if isinstance(e, CorreoFallidoError) else 503, "CORREO_FALLIDO",
                                  "No pudimos enviar el correo. Inténtalo de nuevo en unos minutos o descarga el informe.")
        self.bitacora.registrar(
            accion=Accion.RAT_INFORME_ENVIADO, entidad="rat_informe", entidad_id=fila.id, actor=self.actor,
            detalle={"formatos": formatos, "modo": modo, "destino_propio": destino == self.email_usuario,
                     "version_rat": fila.version_rat, "borrador": fila.borrador})
        await self.db.commit()
        logger.info("[informe_rat] informe %s enviado a %s (%s)", fila.id, correo.enmascarar(destino), modo)
        return {"enviado": True, "destino": correo.enmascarar(destino), "modo": modo, "formatos": formatos}
