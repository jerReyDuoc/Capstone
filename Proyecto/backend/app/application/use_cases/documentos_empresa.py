"""
HU-29 criterio 3 · "Mis documentos" de la empresa cliente.

Reúne en un solo lugar lo que la empresa tiene guardado en la plataforma:

  informes      informes PDF archivados (documento_empresa, tipo informe_pdf). Se archivan al
                completar una reevaluación (DOCUMENTOS_ARCHIVAR_AL_COMPLETAR) o cuando el
                usuario lo pide desde "Mis evaluaciones". Son una foto del informe al generarlo.
  borradores    borradores de cumplimiento de HU-16 (documento_empresa, tipo borrador). HU-16
                los guarda con guardar_documento() y aparecen aquí sin cambiar nada más.
  evidencias    las de sus evaluaciones (cuestionario y remediación). Tras la validación en el
                disco solo queda su texto ANONIMIZADO (HU-06): eso es lo que se descarga.
  constancias   las de los módulos formativos completados (HU-26).

Cada descarga y cada eliminación queda en la bitácora de auditoría (HU-09) con el tipo y
los ids, nunca con el contenido ni el nombre que subió el usuario.

Qué borra "eliminar":
  informe / borrador   la fila y el archivo cifrado.
  evidencia            el archivo y lo que se extrajo de él (datos_extraidos). Se conservan los
                       metadatos de la validación (clasificación, estados, puntajes) para que
                       el historial de madurez siga explicable: borrar un archivo no cambia
                       ningún puntaje (HU-26: el puntaje solo cambia con evidencia NUEVA).
  constancia           anula su código (ya no se descarga ni se puede verificar). El módulo
                       sigue completado: el avance formativo de la empresa no se pierde.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes.analisis import construir_brechas, construir_plan, filtrar_brechas, parsear_filtros
from app.application.informes.carga import SinResultadosError, cargar_evaluacion
from app.application.informes.pdf_informe import DatosInforme, PdfNoDisponibleError, generar_pdf
from app.core.autenticacion import Actor
from app.core.config import settings
from app.domain.models.documento_empresa import TIPO_BORRADOR, TIPO_INFORME, TIPOS_DOCUMENTO, DocumentoEmpresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.formacion import AvanceFormativo
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.ruta_formativa import RutaFormativa
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

# Nombre de descarga de un documento: lo arma el sistema y pasa tal cual por el BFF
NOMBRE_SEGURO = re.compile(r"^[A-Za-z0-9_.-]{1,150}$")
_EN_PROCESO = (EstadoValidacion.PENDING.value, EstadoValidacion.PROCESSING.value)
_EXTENSIONES = {"application/pdf": ".pdf", "text/plain": ".txt",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}


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
    from app.infrastructure.llm.factory import crear_storage_documentos
    return crear_storage_documentos()


def _storage_evidencias():
    from app.infrastructure.llm.factory import crear_storage_evidencias
    return crear_storage_evidencias()


# ------------------------------------------------------------------ guardar (informes y HU-16)
async def guardar_documento(
    db: AsyncSession, *, empresa_id: int, tipo: str, nombre: str, contenido: bytes, mime_type: str,
    evaluacion_id: int | None = None, actor: Actor | None = None, storage=None,
) -> DocumentoEmpresa:
    """
    Guarda un archivo generado por el sistema en "Mis documentos" (cifrado en reposo) y deja
    el registro en la bitácora. NO hace commit: lo hace quien llama, con su acción de negocio.
    Si el flush falla, el archivo recién escrito se borra.
    """
    if tipo not in TIPOS_DOCUMENTO:
        raise ValueError(f"Tipo de documento desconocido: {tipo}")
    if not NOMBRE_SEGURO.match(nombre):
        raise ValueError("El nombre del documento solo admite letras, números, '.', '_' y '-'.")
    storage = storage or _storage_documentos()
    ruta = await storage.save(contenido, nombre)
    try:
        doc = DocumentoEmpresa(
            empresa_id=empresa_id, evaluacion_id=evaluacion_id, tipo=tipo, nombre=nombre,
            storage_path=ruta, mime_type=mime_type, tamano_bytes=len(contenido),
            hash_contenido=hashlib.sha256(contenido).hexdigest(), fecha_creacion=_ahora(),
            creado_por_usuario_id=actor.id if actor is not None and actor.es_cliente else None,
        )
        db.add(doc)
        await db.flush()
    except Exception:
        await storage.delete(ruta)
        raise
    BitacoraRepository(db).registrar(
        accion=Accion.DOCUMENTO_GENERADO, entidad="documento_empresa", entidad_id=doc.id,
        actor=actor, actor_rol=None if actor else "sistema",
        detalle={"empresa_id": empresa_id, "tipo": tipo, "evaluacion_id": evaluacion_id,
                 "tamano_bytes": len(contenido)},
    )
    return doc


def _datos_informe(datos) -> DatosInforme:
    """El informe completo (sin filtros), igual al que se descarga desde el panel."""
    filtros = parsear_filtros(None, None, None, None)
    puntajes = {d.nombre: d.puntaje for d in datos.dominios if d.puntaje is not None}
    brechas = construir_brechas(datos.respuestas, puntajes)
    return DatosInforme(
        evaluacion_id=datos.evaluacion_id, rubro=datos.rubro, puntaje_general=datos.puntaje_general,
        controles_evaluados=datos.controles_evaluados, en_revision=datos.en_revision,
        comparativa=datos.comparativa, brechas_total=len(brechas),
        brechas=filtrar_brechas(brechas, filtros), filtros=filtros,
        plan=construir_plan(brechas, datos.dominios, datos.rutas),
        generado=datetime.now(timezone.utc),
    )


async def archivar_informe(db: AsyncSession, evaluacion: Evaluacion, actor: Actor | None) -> DocumentoEmpresa:
    """Genera el informe PDF de una evaluación COMPLETADA de la empresa y lo guarda (sin commit)."""
    if evaluacion.empresa_id is None:
        raise DocumentoError(404, "EVALUACION_NO_ENCONTRADA", "Evaluación no encontrada.")
    if not evaluacion.esta_cerrada:
        raise DocumentoError(409, "EVALUACION_NO_COMPLETADA",
                             "El informe se guarda cuando la evaluación está completada.")
    ya = await db.scalar(
        select(func.count()).select_from(DocumentoEmpresa).where(
            DocumentoEmpresa.evaluacion_id == evaluacion.id, DocumentoEmpresa.tipo == TIPO_INFORME)
    ) or 0
    if ya >= settings.DOCUMENTOS_INFORMES_POR_EVALUACION:
        raise DocumentoError(
            409, "LIMITE_INFORMES",
            f"Ya guardaste {ya} informes de esta evaluación. Elimina uno en Mis documentos para guardar otro.",
        )
    try:
        datos = await cargar_evaluacion(db, evaluacion.id)
    except SinResultadosError as e:
        raise DocumentoError(409, "SIN_RESULTADOS", str(e))
    informe = _datos_informe(datos)
    try:
        pdf = generar_pdf(informe)
    except PdfNoDisponibleError as e:
        raise DocumentoError(503, "PDF_NO_DISPONIBLE", str(e))
    nombre = f"informe_evaluacion-{evaluacion.id}_{informe.generado:%Y-%m-%d_%H%M%S}.pdf"
    return await guardar_documento(
        db, empresa_id=evaluacion.empresa_id, tipo=TIPO_INFORME, nombre=nombre, contenido=pdf,
        mime_type="application/pdf", evaluacion_id=evaluacion.id, actor=actor,
    )


async def tras_completar(db: AsyncSession, evaluacion_id: int, actor: Actor | None) -> int | None:
    """
    POST /completar de una evaluación de empresa (HU-29): deja el registro en la bitácora y,
    si DOCUMENTOS_ARCHIVAR_AL_COMPLETAR, archiva su informe PDF. Nunca rompe /completar: la
    evaluación ya quedó completada; si el informe falla, el usuario lo guarda a mano.
    Devuelve el id del documento archivado (o None).
    """
    evaluacion = await db.get(Evaluacion, evaluacion_id)
    if evaluacion is None or evaluacion.empresa_id is None:
        return None
    try:
        BitacoraRepository(db).registrar(
            accion=Accion.EVALUACION_COMPLETADA_EMPRESA, entidad="evaluacion", entidad_id=evaluacion.id,
            actor=actor, detalle={"empresa_id": evaluacion.empresa_id, "origen": evaluacion.origen},
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.error("HU-29: no se pudo registrar el cierre de la evaluación %s (%s)", evaluacion_id, type(e).__name__)
    if not settings.DOCUMENTOS_ARCHIVAR_AL_COMPLETAR:
        return None
    try:
        evaluacion = await db.get(Evaluacion, evaluacion_id)
        documento = await archivar_informe(db, evaluacion, actor)
        await db.commit()
        return documento.id
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.error("HU-29: no se pudo archivar el informe de la evaluación %s (%s)", evaluacion_id, type(e).__name__)
        return None


# ------------------------------------------------------------------ "Mis documentos"
def _doc_dict(d: DocumentoEmpresa) -> dict:
    return {
        "id": d.id, "tipo": d.tipo, "nombre": d.nombre, "evaluacion_id": d.evaluacion_id,
        "mime_type": d.mime_type, "tamano_bytes": d.tamano_bytes, "fecha_creacion": d.fecha_creacion,
        "descarga": f"/api/cliente/documentos/{d.id}/descarga",
    }


class DocumentosEmpresa:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (empresa_con_documentos)."""

    def __init__(self, db: AsyncSession, cliente, storage_documentos=None, storage_evidencias=None):
        self.db = db
        self.cliente = cliente
        self.empresa = cliente.empresa
        self.bitacora = BitacoraRepository(db)
        self._storage_documentos = storage_documentos
        self._storage_evidencias = storage_evidencias

    @property
    def storage_documentos(self):
        if self._storage_documentos is None:
            self._storage_documentos = _storage_documentos()
        return self._storage_documentos

    @property
    def storage_evidencias(self):
        if self._storage_evidencias is None:
            self._storage_evidencias = _storage_evidencias()
        return self._storage_evidencias

    # ---------------------------------------------------------------- listado
    async def listar(self) -> dict:
        documentos = (await self.db.execute(
            select(DocumentoEmpresa).where(DocumentoEmpresa.empresa_id == self.empresa.id)
            .order_by(DocumentoEmpresa.fecha_creacion.desc(), DocumentoEmpresa.id.desc())
        )).scalars().all()

        evidencias = (await self.db.execute(
            select(Evidencia, Respuesta.evaluacion_id, MatrizControl.codigo_control)
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .join(Evaluacion, Respuesta.evaluacion_id == Evaluacion.id)
            .outerjoin(MatrizControl, Respuesta.matriz_controles_id_control == MatrizControl.id_control)
            .where(Evaluacion.empresa_id == self.empresa.id, Evidencia.fecha_eliminacion.is_(None))
            .order_by(Evidencia.id_evidencia.desc())
        )).all()

        constancias = (await self.db.execute(
            select(AvanceFormativo, RutaFormativa.nombre)
            .join(RutaFormativa, RutaFormativa.id == AvanceFormativo.ruta_formativa_id)
            .where(AvanceFormativo.empresa_id == self.empresa.id, AvanceFormativo.codigo_constancia.is_not(None))
            .order_by(AvanceFormativo.fecha_completado.desc())
        )).all()

        return {
            "empresa": {"id": self.empresa.id, "razon_social": self.empresa.razon_social},
            "informes": [_doc_dict(d) for d in documentos if d.tipo == TIPO_INFORME],
            # HU-16: los borradores se guardan con guardar_documento(tipo="borrador")
            "borradores": [_doc_dict(d) for d in documentos if d.tipo == TIPO_BORRADOR],
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
            "documentos_disponibles_hasta": self.empresa.vigencia().como_dict()["documentos_disponibles_hasta"],
        }

    # ---------------------------------------------------------------- informes y borradores
    async def _documento(self, documento_id: int) -> DocumentoEmpresa:
        doc = await self.db.get(DocumentoEmpresa, documento_id)
        if doc is None or doc.empresa_id != self.empresa.id:  # lo ajeno no existe (404, no 403)
            raise _no_encontrado()
        return doc

    async def archivar_informe(self, evaluacion_id: int) -> dict:
        evaluacion = await self.db.get(Evaluacion, evaluacion_id)
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
        await self.db.delete(doc)
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

    # ---------------------------------------------------------------- evidencias
    async def _evidencia(self, evidencia_id: int) -> tuple[Evidencia, int]:
        fila = (await self.db.execute(
            select(Evidencia, Evaluacion.id)
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .join(Evaluacion, Respuesta.evaluacion_id == Evaluacion.id)
            .where(Evidencia.id_evidencia == evidencia_id, Evaluacion.empresa_id == self.empresa.id)
        )).first()
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
        a = await self.db.scalar(
            select(AvanceFormativo).where(
                AvanceFormativo.empresa_id == self.empresa.id, AvanceFormativo.ruta_formativa_id == ruta_id)
        )
        if a is None or not a.codigo_constancia:
            raise _no_encontrado("Constancia")
        a.codigo_constancia = None
        a.fecha_eliminacion_constancia = _ahora()
        self.bitacora.registrar(
            accion=Accion.DOCUMENTO_ELIMINADO, entidad="avance_formativo", entidad_id=a.id,
            actor=self.cliente.actor, detalle={"tipo": "constancia", "ruta_id": ruta_id},
        )
        await self.db.commit()
