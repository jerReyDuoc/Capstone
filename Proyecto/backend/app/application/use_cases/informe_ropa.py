"""
HU-37 · Informe RoPA desde el registro de actividades de tratamiento.

Como Usuario Definitivo (cliente), quiero generar el informe RoPA desde el mismo registro, para responder a
clientes, matrices o socios que piden ese formato sin rehacer el trabajo.

  C1  Se genera desde el RAT vigente sin ingresar los datos de nuevo: lee las actividades igual que el
      informe del registro (InformeRatCasos._fuentes) y traduce cada campo a los del RoPA
      (app/application/ropa/informe.py). Solo entran las actividades con versión vigente.
  C2  Dos partes según el rol marcado en cada actividad: como responsable y como encargado (agrupado por
      la organización por cuenta de la cual se actúa). Se puede generar solo una.
  C3  En español. Los datos que el RoPA pide y el registro no tiene (contacto de la empresa, delegado de
      protección de datos y contacto de cada organización mandante) se piden antes de generar y quedan
      guardados en ropa_datos para la próxima vez (app/domain/ropa/datos.py). Sin ellos no se emite (422).
  C4  PDF y XLSX con fecha, versión, código y aviso legal; quedan en "Mis documentos" (documento_empresa)
      y cada guardado de datos, emisión y descarga queda en el audit_log (sin los datos de contacto).

Si nada cambió desde la última emisión (misma huella) y sus archivos siguen en "Mis documentos", se
reutiliza esa emisión; con `forzar` se emite una nueva. Solo con contrato vigente.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, time as dtime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes.motor_pdf import ZONA, PdfNoDisponibleError
from app.application.rat import informe as I
from app.application.ropa import informe as R
from app.application.use_cases.documentos_empresa import guardar_documento
from app.application.use_cases.informe_rat import InformeRatCasos
from app.core.config import settings
from app.domain.mapa_datos.modelo import ErrorValidacion
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.documento_empresa import TIPO_ROPA_PDF, TIPO_ROPA_XLSX, DocumentoEmpresa
from app.domain.models.empresa import Empresa
from app.domain.models.ropa import RopaDatos, RopaInforme
from app.domain.ropa import datos as D
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

FORMATOS = ("pdf", "xlsx")
MAX_HISTORIAL = 50


class InformeRopaError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _naive(d: datetime) -> datetime:
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _fecha_txt(d: datetime | None) -> str:
    if d is None:
        return "—"
    return d.replace(tzinfo=timezone.utc).astimezone(ZONA).strftime("%d-%m-%Y a las %H:%M")


class InformeRopaCasos:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, storage=None):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.usuario_id: int = cliente.usuario.id
        self.bitacora = BitacoraRepository(db)
        self._storage = storage
        self._rat = InformeRatCasos(db, cliente)

    @property
    def storage(self):
        if self._storage is None:
            from app.infrastructure.llm.factory import crear_storage_documentos
            self._storage = crear_storage_documentos()
        return self._storage

    # ================================================================ lectura
    async def _fila_datos(self) -> RopaDatos | None:
        return (await self.db.execute(
            select(RopaDatos).where(RopaDatos.empresa_id == self.empresa_id))).scalar_one_or_none()

    async def _datos(self) -> dict:
        fila = await self._fila_datos()
        return D.completar(fila.como_dict() if fila else None)

    async def _registro(self, generado: datetime | None = None) -> I.InformeRat:
        return await self._rat.armar(generado)

    async def _ultima(self) -> RopaInforme | None:
        return (await self.db.execute(
            select(RopaInforme).where(RopaInforme.empresa_id == self.empresa_id)
            .order_by(RopaInforme.id.desc()).limit(1))).scalar_one_or_none()

    async def _documento(self, doc_id: int | None) -> DocumentoEmpresa | None:
        if not doc_id:
            return None
        doc = await self.db.get(DocumentoEmpresa, doc_id)
        return doc if doc is not None and doc.empresa_id == self.empresa_id else None

    async def _vista_emision(self, r: RopaInforme) -> dict:
        pdf, xlsx = await self._documento(r.documento_pdf_id), await self._documento(r.documento_xlsx_id)

        def doc(d: DocumentoEmpresa | None) -> dict | None:
            return {"id": d.id, "nombre": d.nombre, "tamano_bytes": d.tamano_bytes} if d else None

        return {
            "id": r.id, "codigo": r.codigo, "version": r.version, "fecha": _iso(r.fecha), "partes": list(r.partes or []),
            "actividades": r.actividades, "resumen": r.resumen or {}, "aviso_version": r.aviso_version,
            "documentos": {"pdf": doc(pdf), "xlsx": doc(xlsx)},
        }

    def _vista_datos(self, datos: dict, mandantes: dict[str, str]) -> dict:
        """Los datos guardados, con los mandantes de las actividades vigentes primero (y su nombre del registro)."""
        lista = []
        for clave, nombre in mandantes.items():
            m = datos["mandantes"].get(clave) or {}
            lista.append({"clave": clave, "nombre": nombre, "direccion": m.get("direccion"), "correo": m.get("correo"),
                          "dpo": m.get("dpo")})
        return {**{k: datos.get(k) for k in D.CAMPOS_EMPRESA}, "mandantes": lista}

    async def listar(self, partes: list[str] | None = None) -> dict:
        inf_rat = await self._registro()
        datos = await self._datos()
        inf = R.armar(inf_rat, datos, partes)
        mandantes = R.mandantes(inf_rat)
        faltan = D.faltantes(datos, inf.partes, mandantes)
        filas = list((await self.db.execute(
            select(RopaInforme).where(RopaInforme.empresa_id == self.empresa_id)
            .order_by(RopaInforme.id.desc()).limit(MAX_HISTORIAL))).scalars().all())
        ultima = filas[0] if filas else None
        al_dia = bool(ultima and ultima.huella == inf.huella)
        return {
            "empresa": {"razon_social": inf.empresa, "rut": inf.rut},
            "previa": R.previa_publica(inf),
            "datos": self._vista_datos(datos, mandantes),
            "faltantes": faltan,
            "faltantes_texto": D.texto_faltantes(faltan, mandantes),
            "puede_emitir": bool(inf.partes) and not faltan,
            "al_dia": al_dia,
            "version_siguiente": (ultima.version + (0 if al_dia else 1)) if ultima else 1,
            "emisiones": [await self._vista_emision(r) for r in filas],
        }

    # ================================================================ datos que faltan (C3)
    async def guardar_datos(self, entrada: dict) -> dict:
        inf_rat = await self._registro()
        mandantes = R.mandantes(inf_rat)
        fila = await self._fila_datos()
        antes = D.completar(fila.como_dict() if fila else None)
        try:
            nuevo = D.normalizar(entrada, antes, mandantes)
        except ErrorValidacion as e:
            await self.db.rollback()
            raise InformeRopaError(422, "DATOS_INVALIDOS", e.mensaje, campo=e.campo)
        cambiados = D.campos_cambiados(antes, nuevo)
        if cambiados:
            if fila is None:
                fila = RopaDatos(empresa_id=self.empresa_id)
                self.db.add(fila)
            fila.guardar(nuevo)
            fila.fecha_actualizacion = _naive(_ahora())
            fila.actualizado_por_usuario_id = self.usuario_id
            await self.db.flush()
            # Solo los nombres de los campos y conteos: nunca direcciones ni correos
            self.bitacora.registrar(
                accion=Accion.ROPA_DATOS_ACTUALIZADOS, entidad="ropa_datos", entidad_id=fila.id, actor=self.actor,
                detalle={"campos": cambiados, "organizaciones": len(nuevo["mandantes"])})
            await self.db.commit()
        else:
            await self.db.rollback()
        faltan = D.faltantes(nuevo, R.partes_disponibles(inf_rat), mandantes)
        return {"datos": self._vista_datos(nuevo, mandantes), "faltantes": faltan,
                "faltantes_texto": D.texto_faltantes(faltan, mandantes), "guardado": bool(cambiados)}

    # ================================================================ emisión (C1, C2, C4)
    async def _rechazar(self, motivo: str, error: InformeRopaError, **detalle) -> InformeRopaError:
        await self.db.rollback()
        self.bitacora.registrar(accion=Accion.ROPA_INFORME_GENERADO, entidad="ropa_informe", entidad_id=None,
                                actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": motivo, **detalle})
        await self.db.commit()
        return error

    async def emitir(self, partes: list[str] | None = None, forzar: bool = False) -> dict:
        generado = _ahora()
        # Serializa las emisiones de la empresa (la versión es un correlativo)
        await self.db.execute(select(Empresa.id).where(Empresa.id == self.empresa_id).with_for_update())
        inf_rat = await self._registro(generado)
        datos = await self._datos()
        inf = R.armar(inf_rat, datos, partes, generado)
        if not inf.partes:
            raise await self._rechazar("sin_actividades_vigentes", InformeRopaError(
                409, "ROPA_SIN_ACTIVIDADES", "No hay actividades vigentes para el informe. Deja vigente al menos una "
                                             "actividad del registro."), partes=list(partes or []))
        mandantes = R.mandantes(inf_rat)
        faltan = D.faltantes(datos, inf.partes, mandantes)
        if faltan:
            raise await self._rechazar("datos_incompletos", InformeRopaError(
                422, "ROPA_DATOS_INCOMPLETOS", D.texto_faltantes(faltan, mandantes), faltantes=faltan),
                faltantes=[f["campo"] for f in faltan])
        ultima = await self._ultima()
        if ultima is not None and not forzar and ultima.huella == inf.huella:
            vista = await self._vista_emision(ultima)
            if vista["documentos"]["pdf"] and vista["documentos"]["xlsx"]:
                # El texto se arma ANTES del rollback (después `ultima` queda expirada)
                mensaje = f"Nada cambió desde el informe del {_fecha_txt(ultima.fecha)}: usamos ese mismo informe."
                await self.db.rollback()
                return {"informe": vista, "reutilizado": True, "mensaje": mensaje}
        inicio_dia = datetime.combine(generado.astimezone(ZONA).date(), dtime.min, tzinfo=ZONA)
        hoy = (await self.db.execute(
            select(func.count()).select_from(RopaInforme)
            .where(RopaInforme.empresa_id == self.empresa_id, RopaInforme.fecha >= _naive(inicio_dia)))).scalar() or 0
        if hoy >= settings.RAT_INFORMES_DIA_EMPRESA:
            raise await self._rechazar("limite_diario", InformeRopaError(
                429, "LIMITE_INFORMES", f"Ya generaste {hoy} informes RoPA hoy. Descarga uno de los anteriores o vuelve "
                                        "a intentarlo mañana."))
        version = (ultima.version + (0 if ultima.huella == inf.huella else 1)) if ultima else 1
        fila = RopaInforme(
            empresa_id=self.empresa_id, codigo=None, version=version, huella=inf.huella, partes=list(inf.partes),
            actividades=len(inf.actividades), resumen=inf.resumen,
            versiones=[{"id": a.id, "version": a.version, "huella": a.huella_version} for a in inf.actividades],
            aviso_version=inf.aviso.version, fecha=_naive(generado), usuario_definitivo_id=self.usuario_id)
        self.db.add(fila)
        await self.db.flush()
        fila.codigo = R.codigo(fila.id, generado.astimezone(ZONA).year)
        inf = inf.con_emision(fila.codigo, version)

        from app.application.ropa.pdf_ropa import generar_pdf_ropa
        from app.application.ropa.xlsx_ropa import MIME_XLSX, XlsxNoDisponibleError, generar_xlsx_ropa

        try:
            pdf, xlsx = await asyncio.gather(asyncio.to_thread(generar_pdf_ropa, inf),
                                             asyncio.to_thread(generar_xlsx_ropa, inf))
        except (PdfNoDisponibleError, XlsxNoDisponibleError) as e:
            await self.db.rollback()
            raise InformeRopaError(503, "INFORME_NO_DISPONIBLE", str(e))
        guardados: list[str] = []
        try:
            doc_pdf = await guardar_documento(
                self.db, empresa_id=self.empresa_id, tipo=TIPO_ROPA_PDF, nombre=R.nombre_archivo(inf, "pdf"),
                contenido=pdf, mime_type="application/pdf", actor=self.actor, storage=self.storage)
            guardados.append(doc_pdf.storage_path)
            doc_xlsx = await guardar_documento(
                self.db, empresa_id=self.empresa_id, tipo=TIPO_ROPA_XLSX, nombre=R.nombre_archivo(inf, "xlsx"),
                contenido=xlsx, mime_type=MIME_XLSX, actor=self.actor, storage=self.storage)
            guardados.append(doc_xlsx.storage_path)
            fila.documento_pdf_id, fila.documento_xlsx_id = doc_pdf.id, doc_xlsx.id
            self.bitacora.registrar(
                accion=Accion.ROPA_INFORME_GENERADO, entidad="ropa_informe", entidad_id=fila.id, actor=self.actor,
                detalle={"version": version, "partes": list(inf.partes), "actividades": len(inf.actividades),
                         "organizaciones": inf.resumen["organizaciones"], "huella": inf.huella[:16], "forzado": forzar,
                         "documentos": [doc_pdf.id, doc_xlsx.id]})
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            for ruta in guardados:            # sin la fila, el archivo cifrado no sirve: se borra
                try:
                    await self.storage.delete(ruta)
                except Exception:  # noqa: BLE001
                    logger.error("HU-37: no se pudo borrar un archivo del informe RoPA que no se guardó")
            raise
        await self.db.refresh(fila)
        return {"informe": await self._vista_emision(fila), "reutilizado": False,
                "mensaje": f"Generamos el informe RoPA N.º {version}. Quedó guardado en Mis documentos."}

    # ================================================================ descarga
    async def descargar(self, informe_id: int, formato: str) -> tuple[bytes, str, str]:
        if formato not in FORMATOS:
            raise InformeRopaError(422, "FORMATO_INVALIDO", "Elige PDF o Excel.")
        fila = await self.db.get(RopaInforme, informe_id)
        if fila is None or fila.empresa_id != self.empresa_id:        # lo ajeno no existe (404)
            raise InformeRopaError(404, "INFORME_NO_ENCONTRADO", "No encontramos ese informe RoPA de tu empresa.")
        doc = await self._documento(fila.documento_pdf_id if formato == "pdf" else fila.documento_xlsx_id)
        if doc is None:
            raise InformeRopaError(410, "ARCHIVO_ELIMINADO", "Ese archivo se eliminó de Mis documentos. Genera el "
                                                             "informe de nuevo para obtenerlo.")
        try:
            contenido = await self.storage.get(doc.storage_path)
        except FileNotFoundError:
            raise InformeRopaError(410, "ARCHIVO_ELIMINADO", "El archivo ya no está disponible. Genera el informe de nuevo.")
        if hashlib.sha256(contenido).hexdigest() != doc.hash_contenido:
            logger.error("HU-37: el documento %s del informe RoPA %s no coincide con su hash", doc.id, fila.id)
            raise InformeRopaError(500, "DOCUMENTO_DANADO", "El documento está dañado. Genera el informe de nuevo o "
                                                            "contacta a Therion Labs.")
        self.bitacora.registrar(
            accion=Accion.ROPA_INFORME_DESCARGADO, entidad="ropa_informe", entidad_id=fila.id, actor=self.actor,
            detalle={"formato": formato, "documento_id": doc.id, "version": fila.version})
        await self.db.commit()
        return contenido, doc.nombre, doc.mime_type
