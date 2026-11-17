"""Asistente RAT: análisis de documentos de la empresa (C3)."""
from __future__ import annotations

import asyncio
import hashlib

from app.application.ai.anonimizador import AnonimizacionError
from app.application.fabricas import fabricas
from app.application.rat.asistente import documento
from app.application.rat.casos_uso.asistente_rat.comun import (
    AVISOS, ESTADO_DOCUMENTO_MENSAJE, MIN_CARACTERES_DOCUMENTO, MUESTRA_DENSIDAD, AsistenteError, _ahora,
    documento_a_dict,
)
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.models.asistente import AsistenteDocumento
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO


class DocumentosMixin:
    """Depende de los atributos que fija AsistenteRat.__init__ (db, repo, limitador, agente, ...)."""

    # ------------------------------------------------------------------ documentos (C3)
    async def analizar_documento(self, nombre: str | None, contenido: bytes, sesion_id: int | None = None) -> dict:
        from app.application.evidencias.archivos import (
            ArchivoNoAdmitidoError, detectar_tipo,
        )
        from app.domain.ports.extractor_texto_port import ArchivoIlegibleError

        maximo = settings.ASISTENTE_DOCUMENTO_MAX_MB * 1024 * 1024
        if not contenido:
            raise AsistenteError(422, "ARCHIVO_VACIO", "El archivo está vacío.")
        if len(contenido) > maximo:
            raise AsistenteError(413, "ARCHIVO_DEMASIADO_GRANDE",
                                 f"El archivo supera los {settings.ASISTENTE_DOCUMENTO_MAX_MB} MB.")
        try:
            tipo_archivo = detectar_tipo(nombre, contenido)
        except ArchivoNoAdmitidoError as e:
            raise AsistenteError(422, "TIPO_NO_ADMITIDO", str(e) or "Sube un PDF, un Word (.docx) o un texto (.txt).")
        if sesion_id is not None:
            await self._sesion(sesion_id)
        try:
            nombre_seguro = (await self.anonimizador.anonimizar_nombre_archivo(nombre) if self.anonimizador
                             else "documento")
        except AnonimizacionError:
            nombre_seguro = "documento"
        doc = AsistenteDocumento(
            empresa_id=self.empresa_id, sesion_id=sesion_id, usuario_definitivo_id=self.usuario_id,
            nombre_archivo=nombre_seguro[:255], tipo_archivo=tipo_archivo, tipo_documento="otro",
            huella_sha256=hashlib.sha256(contenido).hexdigest(), estado="listo", lineas_omitidas=0,
            entidades_anonimizadas=0, fecha=_ahora())

        info: dict | None = None
        try:
            texto = fabricas().extractor_texto.extraer_texto(contenido)
        except ArchivoIlegibleError:
            texto, doc.estado = "", "ilegible"
        del contenido   # el archivo no se guarda: solo su huella y sus metadatos
        if doc.estado == "listo" and len(texto.strip()) < MIN_CARACTERES_DOCUMENTO:
            doc.estado = "sin_texto"
        if doc.estado == "listo":
            doc.tipo_documento = documento.tipo_documento(texto)
            if await self._es_listado_de_personas(texto):
                doc.estado = "rechazado_pii"
        if doc.estado == "listo":
            pasajes, rag = documento.pasajes_relevantes(texto, settings.ASISTENTE_MAX_CHARS_DOCUMENTO_LLM)
            doc.pasajes_total, doc.pasajes_usados = rag.get("pasajes_total"), rag.get("pasajes_usados")
            self.db.add(doc)
            await self.db.flush()
            info = await self._proponer(respuesta="", documento_texto=pasajes, area="documento", pregunta=None,
                                        origen="documento", sesion_id=sesion_id, documento_id=doc.id,
                                        tipo_documento=doc.tipo_documento, cuota="doc", previos=[])
            await self._registrar_neutralizados(info["neutralizados"])
            doc.lineas_omitidas = sum(1 for n in info["neutralizados"] if n.get("campo") == "documento")
            doc.entidades_anonimizadas = info.get("entidades") or 0
            doc.traza_id = info.get("traza_id")
            if info["motivo_sin_ia"] and info["motivo_sin_ia"] != "sin_propuestas":
                doc.estado, doc.motivo_sin_ia = "sin_ia", info["motivo_sin_ia"]
        else:
            self.db.add(doc)
            await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.ASISTENTE_DOCUMENTO_ANALIZADO, entidad="asistente_documento", entidad_id=doc.id,
            actor=self.actor, resultado=RESULTADO_RECHAZADO if doc.estado in ESTADO_DOCUMENTO_MENSAJE else RESULTADO_OK,
            detalle={"tipo_archivo": doc.tipo_archivo, "tipo_documento": doc.tipo_documento, "estado": doc.estado,
                     "huella_archivo": doc.huella_sha256[:16], "propuestas": len(info["propuestas"]) if info else 0,
                     "lineas_omitidas": doc.lineas_omitidas, "pasajes_usados": doc.pasajes_usados,
                     "entidades_anonimizadas": doc.entidades_anonimizadas, "motivo_sin_ia": doc.motivo_sin_ia,
                     "traza_id": doc.traza_id})
        await self.db.commit()
        aviso = ESTADO_DOCUMENTO_MENSAJE.get(doc.estado) or (AVISOS.get(info["motivo_sin_ia"] or "") if info else None)
        if info and not info["propuestas"] and doc.estado == "listo":
            aviso = "Leímos el documento, pero no encontramos actividades nuevas que proponer."
        if doc.lineas_omitidas:
            aviso = ((aviso + " ") if aviso else "") + (
                f"Omitimos {doc.lineas_omitidas} línea{'s' if doc.lineas_omitidas != 1 else ''} del documento por "
                "seguridad.")
        return {**await self.estado(), "documento": documento_a_dict(doc),
                "nuevas": [p.id for p in (info["propuestas"] if info else [])], "aviso": aviso}

    async def _es_listado_de_personas(self, texto: str) -> bool:
        """Densidad de entidades personales con el mismo motor NER (fail-closed: si falla, no se envía)."""
        if self.anonimizador is None or not self.anonimizador.habilitado:
            return False
        muestra = texto[:MUESTRA_DENSIDAD]
        try:
            res = await asyncio.to_thread(self.anonimizador.sanitizer.sanitizar, muestra)
        except Exception:  # noqa: BLE001 - el gateway volvería a fallar: mejor no seguir
            return True
        return documento.parece_listado_de_personas(len(res.entidades), len(muestra),
                                                    settings.ASISTENTE_MAX_DENSIDAD_PII)
