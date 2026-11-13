"""
HU-36 · Informe del Registro de Actividades de Tratamiento (RAT) de la empresa cliente.

Como Usuario Definitivo (cliente), quiero descargar el informe RAT de mi empresa, para presentarlo ante
la Agencia de Protección de Datos, el certificador de mi modelo de prevención de infracciones o mi
directorio.

  C1  PDF armado en el servidor desde la versión vigente del RAT, con el motor de informes de HU-21:
      portada, resumen (actividades, datos sensibles, transferencias internacionales, decisiones
      automatizadas), detalle por actividad y matriz de riesgos (base de HU-38).
      → app/application/rat/informe.py (armado) y pdf_rat.py (PDF).
  C2  Fecha, versión del RAT, código verificable y el aviso legal (la plataforma apoya, no reemplaza la
      asesoría legal). → rat_informe (versión y código) y AVISO_RAT.
  C3  También en XLSX (xlsx_rat.py); ambos quedan en "Mis documentos" (documento_empresa, HU-29) y cada
      emisión, descarga, envío y verificación queda en el audit_log (HU-09).
  C4  Con actividades incompletas o en revisión, el informe sale como borrador con marca de agua y lo
      indica en la portada.

Emitir genera los dos formatos con el MISMO código. Si el registro no cambió desde la última emisión (misma
huella y mismo estado) y sus archivos siguen en "Mis documentos", se reutiliza esa emisión (no se llena
"Mis documentos" de copias iguales); con `forzar` se emite una nueva igual. Solo con contrato vigente.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, time as dtime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.application.informes.motor_pdf import ZONA, PdfNoDisponibleError
from app.application.rat import correo_rat
from app.application.rat import informe as I
from app.application.use_cases.documentos_empresa import guardar_documento
from app.application.use_cases.limites_encuesta import ventana_diaria
from app.core.config import settings
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.documento_empresa import TIPO_RAT_PDF, TIPO_RAT_XLSX, DocumentoEmpresa
from app.domain.models.empresa import Empresa
from app.domain.models.rat import RatActividad, RatActividadVersion
from app.domain.models.rat_informe import RatInforme
from app.domain.rat import analisis
from app.domain.rat import catalogo as cat
from app.infrastructure.cache.limitador import LimitadorNoDisponibleError
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

FORMATOS = ("pdf", "xlsx")
MAX_HISTORIAL = 50


class InformeRatError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _naive(d: datetime) -> datetime:
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


class InformeRatCasos:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, limitador=None, storage=None):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa = cliente.empresa
        self.empresa_id: int = cliente.empresa.id
        # Valores simples (no el objeto ORM): siguen disponibles después de un rollback
        self.razon_social: str = cliente.empresa.razon_social
        self.rut: str | None = getattr(cliente.empresa, "rut", None)
        self.rubro_id: int | None = getattr(cliente.empresa, "rubro_id", None)
        self.usuario_id: int = cliente.usuario.id
        self.email_usuario: str = cliente.usuario.email
        self.limitador = limitador
        self.bitacora = BitacoraRepository(db)
        self._storage = storage

    # ================================================================ lectura del registro
    async def _rubro(self) -> str | None:
        from app.domain.models.rubro import Rubro

        if self.rubro_id is None:
            return None
        return (await self.db.execute(select(Rubro.nombre_rubro).where(Rubro.id == self.rubro_id))).scalar_one_or_none()

    async def _mapa(self) -> tuple[list[Elemento], list[Flujo]]:
        from app.application.use_cases.registro_actividades import RegistroActividadesCasos

        _, els, fls = await RegistroActividadesCasos(self.db, self.cliente)._mapa()
        return els, fls

    async def _fuentes(self) -> tuple[list[I.FuenteActividad], int]:
        filas = list((await self.db.execute(
            select(RatActividad).where(RatActividad.empresa_id == self.empresa_id, RatActividad.estado != cat.ARCHIVADA)
            .order_by(RatActividad.nombre, RatActividad.id))).scalars().all())
        archivadas = (await self.db.execute(
            select(func.count()).select_from(RatActividad)
            .where(RatActividad.empresa_id == self.empresa_id, RatActividad.estado == cat.ARCHIVADA))).scalar() or 0
        con_vigente = [f.id for f in filas if f.version_vigente is not None]
        versiones: dict[tuple[int, int], RatActividadVersion] = {}
        if con_vigente:
            for v in (await self.db.execute(
                    select(RatActividadVersion).where(RatActividadVersion.actividad_id.in_(con_vigente)))).scalars():
                versiones[(v.actividad_id, v.numero)] = v
        # HU-38: el mapa se lee siempre (también para las vigentes): la matriz de riesgos necesita saber qué
        # sistemas con IA usa cada actividad, y la instantánea no guarda el subtipo de los elementos.
        els, fls = await self._mapa() if filas else ([], [])
        fuentes = []
        for f in filas:
            v = versiones.get((f.id, f.version_vigente)) if f.version_vigente is not None else None
            if v is not None:
                fuentes.append(I.FuenteActividad(
                    id=f.id, nombre=f.nombre, estado=f.estado, version_vigente=f.version_vigente,
                    fecha_vigencia=f.fecha_vigencia, fecha_actualizacion=f.fecha_actualizacion,
                    motivos_revision=tuple(f.motivos_revision or []), instantanea=v.contenido,
                    huella_version=v.huella, fecha_version=v.fecha,
                    sistemas_ia=tuple(analisis.sistemas_ia_en((v.contenido or {}).get("mapa") or {}, els))))
            else:
                deriv = analisis.derivados(f.contenido, els, fls)
                fuentes.append(I.FuenteActividad(
                    id=f.id, nombre=f.nombre, estado=f.estado, version_vigente=None,
                    fecha_vigencia=f.fecha_vigencia, fecha_actualizacion=f.fecha_actualizacion,
                    motivos_revision=tuple(f.motivos_revision or []), contenido=f.contenido, derivados=deriv,
                    completitud=analisis.completitud(f.contenido, deriv)))
        return fuentes, int(archivadas)

    async def armar(self, generado: datetime | None = None) -> I.InformeRat:
        fuentes, archivadas = await self._fuentes()
        return I.armar(fuentes, generado or _ahora(), self.razon_social, self.rut, await self._rubro(), archivadas)

    # ================================================================ emisiones
    async def _ultima(self) -> RatInforme | None:
        q = (select(RatInforme).where(RatInforme.empresa_id == self.empresa_id)
             .order_by(RatInforme.id.desc()).limit(1))
        return (await self.db.execute(q)).scalar_one_or_none()

    async def _documento(self, doc_id: int | None) -> DocumentoEmpresa | None:
        if not doc_id:
            return None
        doc = await self.db.get(DocumentoEmpresa, doc_id)
        return doc if doc is not None and doc.empresa_id == self.empresa_id else None

    async def _vista_emision(self, r: RatInforme) -> dict:
        pdf, xlsx = await self._documento(r.documento_pdf_id), await self._documento(r.documento_xlsx_id)

        def doc(d: DocumentoEmpresa | None) -> dict | None:
            return {"id": d.id, "nombre": d.nombre, "tamano_bytes": d.tamano_bytes} if d else None

        return {
            "id": r.id, "codigo": r.codigo, "version_rat": r.version_rat, "fecha": _iso(r.fecha),
            "borrador": r.borrador, "motivos_borrador": list(r.motivos_borrador or []), "actividades": r.actividades,
            "huella": r.huella, "huella_legible": I.huella_legible(r.huella), "resumen": r.resumen or {},
            "aviso_version": r.aviso_version, "documentos": {"pdf": doc(pdf), "xlsx": doc(xlsx)},
        }

    async def listar(self) -> dict:
        inf = await self.armar()
        filas = list((await self.db.execute(
            select(RatInforme).where(RatInforme.empresa_id == self.empresa_id)
            .order_by(RatInforme.id.desc()).limit(MAX_HISTORIAL))).scalars().all())
        emisiones = [await self._vista_emision(r) for r in filas]
        ultima = filas[0] if filas else None
        al_dia = bool(ultima and ultima.huella == inf.huella and ultima.borrador == inf.borrador)
        return {
            "previa": {**I.resumen_publico(inf), "puede_emitir": bool(inf.actividades),
                       "version_siguiente": (ultima.version_rat + (0 if al_dia else 1)) if ultima else 1},
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
            from app.infrastructure.llm.factory import crear_storage_documentos
            self._storage = crear_storage_documentos()
        return self._storage

    async def emitir(self, forzar: bool = False) -> dict:
        generado = _ahora()
        # Serializa las emisiones de la empresa (la versión del RAT es un correlativo)
        await self.db.execute(select(Empresa.id).where(Empresa.id == self.empresa_id).with_for_update())
        inf = await self.armar(generado)
        if not inf.actividades:
            raise await self._rechazar("registro_vacio", InformeRatError(
                409, "RAT_VACIO", "Tu registro aún no tiene actividades. Registra al menos una para generar el informe."))
        ultima = await self._ultima()
        if ultima is not None and not forzar and ultima.huella == inf.huella and ultima.borrador == inf.borrador:
            vista = await self._vista_emision(ultima)
            if vista["documentos"]["pdf"] and vista["documentos"]["xlsx"]:
                # El texto se arma ANTES del rollback: después, `ultima` queda expirada y leer su fecha
                # obligaría a SQLAlchemy a recargarla fuera del contexto async (error 500)
                mensaje = (f"Tu registro no cambió desde la emisión del {_fecha_txt(ultima.fecha)}: "
                           "usamos ese mismo informe.")
                await self.db.rollback()        # libera el bloqueo de la empresa
                return {"informe": vista, "reutilizado": True, "mensaje": mensaje}
        inicio_dia = datetime.combine(generado.astimezone(ZONA).date(), dtime.min, tzinfo=ZONA)
        hoy = (await self.db.execute(
            select(func.count()).select_from(RatInforme)
            .where(RatInforme.empresa_id == self.empresa_id, RatInforme.fecha >= _naive(inicio_dia)))).scalar() or 0
        if hoy >= settings.RAT_INFORMES_DIA_EMPRESA:
            raise await self._rechazar("limite_diario", InformeRatError(
                429, "LIMITE_INFORMES", f"Ya generaste {hoy} informes hoy. Descarga uno de los anteriores o vuelve a "
                                        "intentarlo mañana."))
        version = (ultima.version_rat + (0 if ultima.huella == inf.huella else 1)) if ultima else 1
        fila = RatInforme(
            empresa_id=self.empresa_id, codigo=None, version_rat=version, huella=inf.huella, borrador=inf.borrador,
            motivos_borrador=list(inf.motivos_borrador), actividades=len(inf.actividades), resumen=inf.resumen,
            versiones=[{"id": a.id, "version": a.version, "huella": a.huella_version} for a in inf.actividades],
            aviso_version=inf.aviso.version, fecha=_naive(generado), usuario_definitivo_id=self.usuario_id)
        self.db.add(fila)
        await self.db.flush()
        fila.codigo = I.codigo(fila.id, generado.astimezone(ZONA).year)
        inf = inf.con_emision(fila.codigo, version)

        from app.application.rat.pdf_rat import generar_pdf_rat, nombre_archivo
        from app.application.rat.xlsx_rat import MIME_XLSX, XlsxNoDisponibleError, generar_xlsx_rat

        try:
            pdf, xlsx = await asyncio.gather(asyncio.to_thread(generar_pdf_rat, inf),
                                             asyncio.to_thread(generar_xlsx_rat, inf))
        except (PdfNoDisponibleError, XlsxNoDisponibleError) as e:
            await self.db.rollback()
            raise InformeRatError(503, "INFORME_NO_DISPONIBLE", str(e))
        guardados: list[str] = []
        try:
            doc_pdf = await guardar_documento(
                self.db, empresa_id=self.empresa_id, tipo=TIPO_RAT_PDF, nombre=nombre_archivo(inf, "pdf"),
                contenido=pdf, mime_type="application/pdf", actor=self.actor, storage=self.storage)
            guardados.append(doc_pdf.storage_path)
            doc_xlsx = await guardar_documento(
                self.db, empresa_id=self.empresa_id, tipo=TIPO_RAT_XLSX, nombre=nombre_archivo(inf, "xlsx"),
                contenido=xlsx, mime_type=MIME_XLSX, actor=self.actor, storage=self.storage)
            guardados.append(doc_xlsx.storage_path)
            fila.documento_pdf_id, fila.documento_xlsx_id = doc_pdf.id, doc_xlsx.id
            self.bitacora.registrar(
                accion=Accion.RAT_INFORME_GENERADO, entidad="rat_informe", entidad_id=fila.id, actor=self.actor,
                detalle={"version_rat": version, "borrador": inf.borrador, "actividades": len(inf.actividades),
                         "huella": inf.huella[:16], "forzado": forzar, "documentos": [doc_pdf.id, doc_xlsx.id]})
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

    async def _emision(self, informe_id: int) -> RatInforme:
        fila = await self.db.get(RatInforme, informe_id)
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

    def _informe_de(self, fila: RatInforme) -> I.InformeRat:
        """Lo mínimo para el cuerpo del correo (las cifras guardadas al emitir)."""
        return I.InformeRat(
            empresa=self.razon_social, rut=self.rut, rubro=None,
            generado=fila.fecha.replace(tzinfo=timezone.utc), actividades=(), resumen=fila.resumen or {},
            borrador=fila.borrador, motivos_borrador=tuple(fila.motivos_borrador or []), huella=fila.huella,
            riesgos=(), codigo=fila.codigo, version_rat=fila.version_rat)

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
            adjuntos.append(correo.Adjunto(doc.nombre, contenido, doc.mime_type))

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
        inf = self._informe_de(fila)
        texto, html = correo_rat.cuerpo(inf, formatos)
        try:
            modo = await correo.enviar(destino, correo_rat.asunto(inf), texto, html, adjuntos)
        except (correo.CorreoFallidoError, correo.CorreoNoDisponibleError) as e:
            await self.limitador.devolver(clave)
            logger.warning("[informe_rat] envío fallido empresa %s: %s", self.empresa_id, type(e).__name__)
            raise InformeRatError(502 if isinstance(e, correo.CorreoFallidoError) else 503, "CORREO_FALLIDO",
                                  "No pudimos enviar el correo. Inténtalo de nuevo en unos minutos o descarga el informe.")
        self.bitacora.registrar(
            accion=Accion.RAT_INFORME_ENVIADO, entidad="rat_informe", entidad_id=fila.id, actor=self.actor,
            detalle={"formatos": formatos, "modo": modo, "destino_propio": destino == self.email_usuario,
                     "version_rat": fila.version_rat, "borrador": fila.borrador})
        await self.db.commit()
        logger.info("[informe_rat] informe %s enviado a %s (%s)", fila.id, correo.enmascarar(destino), modo)
        return {"enviado": True, "destino": correo.enmascarar(destino), "modo": modo, "formatos": formatos}

    async def verificar(self, codigo_txt: str) -> dict:
        leido = I.leer_codigo(codigo_txt)
        if leido is None:
            self.bitacora.registrar(accion=Accion.RAT_INFORME_VERIFICADO, entidad="rat_informe", entidad_id=None,
                                    actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": "codigo_invalido"})
            await self.db.commit()
            raise InformeRatError(422, "CODIGO_INVALIDO", "El código no es válido. Revisa que esté completo y bien "
                                                          "escrito: el último carácter es de control.")
        anio, emision_id = leido
        fila = await self.db.get(RatInforme, emision_id)
        if fila is None or fila.empresa_id != self.empresa_id or fila.codigo != I.codigo(emision_id, anio):
            self.bitacora.registrar(accion=Accion.RAT_INFORME_VERIFICADO, entidad="rat_informe", entidad_id=None,
                                    actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": "no_encontrado"})
            await self.db.commit()
            raise InformeRatError(404, "INFORME_NO_ENCONTRADO", "No encontramos un informe de tu empresa con ese código.")
        actual = await self.armar()
        vigente = actual.huella == fila.huella
        self.bitacora.registrar(accion=Accion.RAT_INFORME_VERIFICADO, entidad="rat_informe", entidad_id=fila.id,
                                actor=self.actor, detalle={"sigue_al_dia": vigente})
        await self.db.commit()
        return {
            "valido": True, "informe": await self._vista_emision(fila), "sigue_al_dia": vigente,
            "mensaje": ("El código es auténtico y el registro no ha cambiado desde esa emisión." if vigente else
                        "El código es auténtico, pero el registro cambió después de esa emisión: genera un informe "
                        "nuevo para presentar la versión actual."),
        }


def _fecha_txt(d: datetime | None) -> str:
    if d is None:
        return "—"
    return d.replace(tzinfo=timezone.utc).astimezone(ZONA).strftime("%d-%m-%Y a las %H:%M")
