"""
HU-41 · Registro de tratamiento de la propia plataforma (solo admin_therion).

Como Administrador de Therion Labs, quiero generar el mapeo de datos y el RAT de la propia plataforma
ComplianceAI desde el inventario, auditar internamente el tratamiento que hace la plataforma y demostrarlo
con las mismas herramientas que vendemos.

  C1  Las actividades salen de app/core/catalogo_datos_personales.py con finalidad, base y plazo
      → app/application/plataforma/registro.py (generar).
  C2  Los plazos son el valor VIGENTE de cada ajuste (el de titulares, el del panel de retención si se fijó
      allí). tests/test_hu41_registro_plataforma.py falla si difieren o si aparece una tabla sin actividad.
  C3  Los proveedores activos figuran como encargados con país y garantía de la transferencia.
  C4  El RAT y el RoPA se generan con los mismos módulos del cliente (pdf_rat, xlsx_rat, pdf_ropa, xlsx_ropa).

Además, la revisión interna (app/application/plataforma/revision.py) y el PDF del mapa de la plataforma.

Emitir genera los dos formatos con el mismo código. Si el registro no cambió desde la última emisión del mismo
tipo (misma huella y mismo estado), se reutiliza esa emisión; con `forzar` se emite una nueva igual. Los archivos
quedan cifrados en STORAGE_DIR (no en "Mis documentos": no son de una empresa cliente). Cada emisión, descarga,
verificación y cambio de los datos de contacto queda en el audit_log, sin los datos de contacto.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, time as dtime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes.motor_pdf import ZONA, PdfNoDisponibleError, fecha_local
from app.application.plataforma import registro as R
from app.application.plataforma import revision as V
from app.application.rat import informe as I
from app.core.autenticacion import Actor
from app.core.config import settings
from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.mapa_datos.modelo import ErrorValidacion
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.plataforma import ID_REGISTRO, TIPO_RAT, TIPO_ROPA, TIPOS, PlataformaInforme, PlataformaRegistro
from app.domain.ropa import datos as D
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

FORMATOS = ("pdf", "xlsx")
MAX_HISTORIAL = 50
NOMBRE_TIPO = {TIPO_RAT: "Registro de actividades", TIPO_ROPA: "RoPA"}
MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class PrivacidadPlataformaError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _naive(d: datetime) -> datetime:
    return d.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.replace(tzinfo=timezone.utc).isoformat() if d else None


def _fecha_txt(d: datetime) -> str:
    return d.replace(tzinfo=timezone.utc).astimezone(ZONA).strftime("%d-%m-%Y a las %H:%M")


class PrivacidadPlataformaCasos:
    def __init__(self, db: AsyncSession, actor: Actor, storage=None, conf=None):
        self.db = db
        self.actor = actor
        self.conf = conf or settings
        self.bitacora = BitacoraRepository(db)
        self._storage = storage

    @property
    def storage(self):
        if self._storage is None:
            from app.infrastructure.llm.factory import crear_storage_documentos
            self._storage = crear_storage_documentos()
        return self._storage

    # ================================================================ lectura
    async def _plazo_titular(self) -> tuple[int | None, str]:
        from app.application.use_cases.configurar_retencion import plazo_titular_vigente
        from app.domain.models.configuracion_retencion import FUENTE_PANEL

        p = await plazo_titular_vigente(self.db)
        return p.dias, (R.FUENTE_PANEL if p.fuente == FUENTE_PANEL else R.FUENTE_ENTORNO)

    async def registro(self) -> R.RegistroPlataforma:
        return R.generar(self.conf, await self._plazo_titular())

    async def _ultima_retencion(self) -> dict | None:
        filas, _ = await self.bitacora.listar(accion=Accion.RETENCION_EJECUCION, page=1, size=20)
        for f in filas:
            detalle = f.detalle or {}
            if not detalle.get("simulacion"):
                return {"fecha": f.fecha, "resultado": f.resultado, "detalle": detalle}
        return None

    async def _fila_datos(self) -> PlataformaRegistro | None:
        return await self.db.get(PlataformaRegistro, ID_REGISTRO)

    async def _datos_ropa(self) -> dict:
        fila = await self._fila_datos()
        return D.completar(fila.como_dict() if fila else None)

    async def _ultima(self, tipo: str) -> PlataformaInforme | None:
        q = (select(PlataformaInforme).where(PlataformaInforme.tipo == tipo, PlataformaInforme.codigo.is_not(None))
             .order_by(PlataformaInforme.id.desc()).limit(1))
        return (await self.db.execute(q)).scalar_one_or_none()

    @staticmethod
    def _vista_emision(f: PlataformaInforme) -> dict:
        return {
            "id": f.id, "tipo": f.tipo, "tipo_nombre": NOMBRE_TIPO.get(f.tipo, f.tipo), "codigo": f.codigo,
            "version": f.version, "fecha": _iso(f.fecha), "oficial": f.oficial,
            "motivos_borrador": list(f.motivos_borrador or []), "actividades": f.actividades,
            "huella_legible": I.huella_legible(f.huella), "resumen": f.resumen or {}, "aviso_version": f.aviso_version,
            "archivos": {"pdf": {"nombre": f.nombre_pdf}, "xlsx": {"nombre": f.nombre_xlsx}},
        }

    def _version_registro(self, reg: R.RegistroPlataforma, ultima_rat: PlataformaInforme | None) -> int:
        if ultima_rat is None:
            return 1
        return ultima_rat.version + (0 if ultima_rat.huella == reg.huella else 1)

    async def resumen(self) -> dict:
        ahora = _ahora()
        reg = await self.registro()
        ultima_rat, ultima_ropa = await self._ultima(TIPO_RAT), await self._ultima(TIPO_ROPA)
        version = self._version_registro(reg, ultima_rat)
        inf = R.informe_rat(reg, version, ahora)
        datos = await self._datos_ropa()
        huella_ropa = R.huella_ropa(reg, datos)
        falt = D.faltantes(datos, ("responsable",), {})
        filas = list((await self.db.execute(
            select(PlataformaInforme).where(PlataformaInforme.codigo.is_not(None))
            .order_by(PlataformaInforme.id.desc()).limit(MAX_HISTORIAL))).scalars().all())
        provs = {p.clave: p for p in reg.proveedores}
        rat_al_dia = bool(ultima_rat and ultima_rat.huella == reg.huella and ultima_rat.oficial == reg.oficial)
        ropa_al_dia = bool(ultima_ropa and ultima_ropa.huella == huella_ropa)
        return {
            "organizacion": {"razon_social": reg.razon_social, "rut": reg.rut},
            "registro": {
                "huella": reg.huella, "huella_legible": I.huella_legible(reg.huella), "oficial": reg.oficial,
                "motivos_borrador": list(inf.motivos_borrador), "version_siguiente": version,
                "al_dia": rat_al_dia, "cambio_desde_ultima": bool(ultima_rat) and not rat_al_dia,
                "pais_alojamiento": reg.pais_alojamiento,
                "pais_alojamiento_nombre": cat_mapa.nombre_pais(reg.pais_alojamiento),
            },
            "resumen": inf.resumen,
            "actividades": [R.vista_actividad(a, provs) for a in reg.actividades],
            "mapa": R.vista_mapa(reg),
            "proveedores": [p.como_dict() for p in reg.proveedores],
            "ajustes": [a.como_dict() for a in reg.ajustes.values()],
            "revision": V.revisar(reg, self.conf, await self._ultima_retencion(), _naive(ahora)),
            "ropa": {"datos": {k: datos.get(k) for k in D.CAMPOS_EMPRESA}, "faltantes": falt,
                     "texto_faltantes": D.texto_faltantes(falt, {}), "puede_emitir": not falt,
                     "al_dia": ropa_al_dia, "cambio_desde_ultima": bool(ultima_ropa) and not ropa_al_dia,
                     "version_siguiente": (ultima_ropa.version + (0 if ropa_al_dia else 1)) if ultima_ropa else 1},
            "ultimas": {TIPO_RAT: self._vista_emision(ultima_rat) if ultima_rat else None,
                        TIPO_ROPA: self._vista_emision(ultima_ropa) if ultima_ropa else None},
            "emisiones": [self._vista_emision(f) for f in filas],
            "limites": {"informes_dia": self.conf.PLATAFORMA_INFORMES_DIA},
        }

    async def actividad(self, clave: str) -> dict:
        reg = await self.registro()
        provs = {p.clave: p for p in reg.proveedores}
        for a in reg.actividades:
            if a.clave == clave:
                return R.vista_actividad(a, provs)
        raise PrivacidadPlataformaError(404, "ACTIVIDAD_NO_ENCONTRADA", "No encontramos esa actividad del registro.")

    # ================================================================ datos del RoPA
    async def guardar_ropa_datos(self, entrada: dict) -> dict:
        if not isinstance(entrada, dict) or "mandantes" in entrada:
            raise PrivacidadPlataformaError(422, "DATO_INVALIDO", "Ese dato no es parte del RoPA de la plataforma.",
                                            campo="mandantes")
        fila = await self._fila_datos()
        antes = D.completar(fila.como_dict() if fila else None)
        try:
            nuevo = D.normalizar(entrada, antes, {})
        except ErrorValidacion as e:
            raise PrivacidadPlataformaError(422, "DATO_INVALIDO", e.mensaje, campo=e.campo)
        nuevo["mandantes"] = {}
        cambiados = D.campos_cambiados(antes, nuevo)
        if cambiados:
            if fila is None:
                fila = PlataformaRegistro(id=ID_REGISTRO, fecha_actualizacion=_naive(_ahora()))
                self.db.add(fila)
            fila.guardar(nuevo)
            fila.fecha_actualizacion = _naive(_ahora())
            fila.actualizado_por_admin_id = self.actor.id
            self.bitacora.registrar(accion=Accion.PLATAFORMA_ROPA_DATOS_ACTUALIZADOS, entidad="plataforma_registro",
                                    entidad_id=ID_REGISTRO, actor=self.actor, detalle={"campos": cambiados})
            await self.db.commit()
        falt = D.faltantes(nuevo, ("responsable",), {})
        return {"datos": {k: nuevo.get(k) for k in D.CAMPOS_EMPRESA}, "faltantes": falt,
                "texto_faltantes": D.texto_faltantes(falt, {}), "puede_emitir": not falt, "cambiados": cambiados}

    # ================================================================ emisiones
    async def _rechazar(self, motivo: str, error: PrivacidadPlataformaError, tipo: str) -> PrivacidadPlataformaError:
        await self.db.rollback()
        self.bitacora.registrar(accion=Accion.PLATAFORMA_INFORME_GENERADO, entidad="plataforma_informe",
                                entidad_id=None, actor=self.actor, resultado=RESULTADO_RECHAZADO,
                                detalle={"motivo": motivo, "tipo": tipo})
        await self.db.commit()
        return error

    async def emitir(self, tipo: str, forzar: bool = False) -> dict:
        if tipo not in TIPOS:
            raise PrivacidadPlataformaError(422, "TIPO_INVALIDO", "Elige el registro de actividades o el RoPA.")
        generado = _ahora()
        reg = await self.registro()
        ultima_rat = await self._ultima(TIPO_RAT)
        version_registro = self._version_registro(reg, ultima_rat)
        datos: dict | None = None
        if tipo == TIPO_ROPA:
            datos = await self._datos_ropa()
            falt = D.faltantes(datos, ("responsable",), {})
            if falt:
                raise await self._rechazar("datos_incompletos", PrivacidadPlataformaError(
                    409, "ROPA_DATOS_INCOMPLETOS", "Completa los datos de contacto de Therion Labs antes de generar el "
                    "RoPA.", faltantes=falt), tipo)
            huella, oficial = R.huella_ropa(reg, datos), True
        else:
            huella, oficial = reg.huella, reg.oficial
        ultima = ultima_rat if tipo == TIPO_RAT else await self._ultima(TIPO_ROPA)
        if ultima is not None and not forzar and ultima.huella == huella and ultima.oficial == oficial:
            mensaje = (f"El registro no cambió desde la emisión del {_fecha_txt(ultima.fecha)}: usamos ese mismo "
                       "informe.")
            return {"informe": self._vista_emision(ultima), "reutilizado": True, "mensaje": mensaje}

        inicio_dia = datetime.combine(generado.astimezone(ZONA).date(), dtime.min, tzinfo=ZONA)
        hoy = (await self.db.execute(
            select(func.count()).select_from(PlataformaInforme)
            .where(PlataformaInforme.fecha >= _naive(inicio_dia)))).scalar() or 0
        if hoy >= self.conf.PLATAFORMA_INFORMES_DIA:
            raise await self._rechazar("limite_diario", PrivacidadPlataformaError(
                429, "LIMITE_INFORMES", f"Ya se generaron {hoy} informes hoy. Descarga uno de los anteriores o vuelve "
                                        "a intentarlo mañana."), tipo)
        version = (ultima.version + (0 if ultima.huella == huella else 1)) if ultima else 1

        if tipo == TIPO_RAT:
            inf = R.informe_rat(reg, version, generado)
            motivos, aviso, actividades = list(inf.motivos_borrador), inf.aviso.version, len(inf.actividades)
            resumen = {k: inf.resumen.get(k) for k in ("actividades", "transferencias", "transferencias_sin_garantia",
                                                       "terceros", "terceros_sin_contrato", "riesgos_altos")}
        else:
            inf = R.informe_ropa(reg, datos, version_registro, generado)
            motivos, aviso, actividades = [], inf.aviso.version, len(inf.actividades)
            resumen = dict(inf.resumen)
        fila = PlataformaInforme(
            tipo=tipo, codigo=None, version=version, huella=huella, oficial=oficial, motivos_borrador=motivos,
            actividades=actividades, resumen=resumen, aviso_version=aviso, archivo_pdf="", archivo_xlsx="",
            hash_pdf="", hash_xlsx="", nombre_pdf="", nombre_xlsx="", fecha=_naive(generado),
            emitido_por_admin_id=self.actor.id)
        self.db.add(fila)
        await self.db.flush()
        prefijo = R.PREFIJO_RAT if tipo == TIPO_RAT else R.PREFIJO_ROPA
        codigo = R.codigo(prefijo, fila.id, generado.astimezone(ZONA).year)

        from app.application.rat.pdf_rat import generar_pdf_rat
        from app.application.rat.xlsx_rat import XlsxNoDisponibleError as XlsxRatNoDisponible, generar_xlsx_rat
        from app.application.ropa.pdf_ropa import generar_pdf_ropa
        from app.application.ropa.xlsx_ropa import XlsxNoDisponibleError as XlsxRopaNoDisponible, generar_xlsx_ropa

        inf = inf.con_emision(codigo, version)
        gen_pdf, gen_xlsx = ((generar_pdf_rat, generar_xlsx_rat) if tipo == TIPO_RAT
                             else (generar_pdf_ropa, generar_xlsx_ropa))
        try:
            pdf, xlsx = await asyncio.gather(asyncio.to_thread(gen_pdf, inf), asyncio.to_thread(gen_xlsx, inf))
        except (PdfNoDisponibleError, XlsxRatNoDisponible, XlsxRopaNoDisponible) as e:
            await self.db.rollback()
            raise PrivacidadPlataformaError(503, "INFORME_NO_DISPONIBLE", str(e))

        base = _nombre_base(tipo, version, generado, oficial)
        guardados: list[str] = []
        try:
            ruta_pdf = await self.storage.save(pdf, f"{base}.pdf")
            guardados.append(ruta_pdf)
            ruta_xlsx = await self.storage.save(xlsx, f"{base}.xlsx")
            guardados.append(ruta_xlsx)
            fila.codigo = codigo
            fila.archivo_pdf, fila.archivo_xlsx = ruta_pdf, ruta_xlsx
            fila.hash_pdf, fila.hash_xlsx = hashlib.sha256(pdf).hexdigest(), hashlib.sha256(xlsx).hexdigest()
            fila.nombre_pdf, fila.nombre_xlsx = f"{base}.pdf", f"{base}.xlsx"
            self.bitacora.registrar(
                accion=Accion.PLATAFORMA_INFORME_GENERADO, entidad="plataforma_informe", entidad_id=fila.id,
                actor=self.actor, detalle={"tipo": tipo, "version": version, "oficial": oficial,
                                           "actividades": actividades, "huella": huella[:16], "forzado": forzar})
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            for ruta in guardados:            # sin la fila, el archivo cifrado no sirve: se borra
                try:
                    await self.storage.delete(ruta)
                except Exception:  # noqa: BLE001
                    logger.error("HU-41: no se pudo borrar un archivo de un informe que no se guardó")
            raise
        await self.db.refresh(fila)
        if tipo == TIPO_ROPA:
            mensaje = f"Generamos el RoPA de la plataforma (versión {version})."
        elif oficial:
            mensaje = f"Generamos el registro oficial de la plataforma (versión {version})."
        else:
            mensaje = ("Generamos el registro como borrador: hay actividades con datos por definir. Los motivos "
                       "están en la portada.")
        return {"informe": self._vista_emision(fila), "reutilizado": False, "mensaje": mensaje}

    async def _emision(self, informe_id: int) -> PlataformaInforme:
        fila = await self.db.get(PlataformaInforme, informe_id)
        if fila is None or fila.codigo is None:
            raise PrivacidadPlataformaError(404, "INFORME_NO_ENCONTRADO", "No encontramos ese informe.")
        return fila

    async def descargar(self, informe_id: int, formato: str) -> tuple[bytes, str, str]:
        if formato not in FORMATOS:
            raise PrivacidadPlataformaError(422, "FORMATO_INVALIDO", "Elige PDF o Excel.")
        fila = await self._emision(informe_id)
        ruta, esperado, nombre = ((fila.archivo_pdf, fila.hash_pdf, fila.nombre_pdf) if formato == "pdf"
                                  else (fila.archivo_xlsx, fila.hash_xlsx, fila.nombre_xlsx))
        try:
            contenido = await self.storage.get(ruta)
        except FileNotFoundError:
            raise PrivacidadPlataformaError(410, "ARCHIVO_ELIMINADO", "El archivo ya no está disponible. Genera el "
                                                                      "informe de nuevo.")
        if hashlib.sha256(contenido).hexdigest() != esperado:
            logger.error("HU-41: el archivo %s del informe %s no coincide con su hash", formato, fila.id)
            raise PrivacidadPlataformaError(500, "DOCUMENTO_DANADO", "El archivo está dañado. Genera el informe de "
                                                                     "nuevo.")
        self.bitacora.registrar(accion=Accion.PLATAFORMA_INFORME_DESCARGADO, entidad="plataforma_informe",
                                entidad_id=fila.id, actor=self.actor,
                                detalle={"tipo": fila.tipo, "formato": formato, "version": fila.version})
        await self.db.commit()
        return contenido, nombre, MIME[formato]

    async def verificar(self, codigo_txt: str) -> dict:
        leido = R.leer_codigo(codigo_txt)
        fila = None
        if leido is not None:
            tipo, anio, emision_id = leido
            fila = await self.db.get(PlataformaInforme, emision_id)
            prefijo = R.PREFIJO_RAT if tipo == TIPO_RAT else R.PREFIJO_ROPA
            if fila is not None and (fila.tipo != tipo or fila.codigo != R.codigo(prefijo, emision_id, anio)):
                fila = None
        if fila is None:
            motivo = "codigo_invalido" if leido is None else "no_encontrado"
            self.bitacora.registrar(accion=Accion.PLATAFORMA_INFORME_VERIFICADO, entidad="plataforma_informe",
                                    entidad_id=None, actor=self.actor, resultado=RESULTADO_RECHAZADO,
                                    detalle={"motivo": motivo})
            await self.db.commit()
            if leido is None:
                raise PrivacidadPlataformaError(422, "CODIGO_INVALIDO", "El código no es válido. Revisa que esté "
                                                "completo: el último carácter es de control.")
            raise PrivacidadPlataformaError(404, "INFORME_NO_ENCONTRADO", "El código no corresponde a un informe de la "
                                                                          "plataforma.")
        reg = await self.registro()
        actual = reg.huella if fila.tipo == TIPO_RAT else R.huella_ropa(reg, await self._datos_ropa())
        al_dia = actual == fila.huella
        self.bitacora.registrar(accion=Accion.PLATAFORMA_INFORME_VERIFICADO, entidad="plataforma_informe",
                                entidad_id=fila.id, actor=self.actor, detalle={"sigue_al_dia": al_dia})
        await self.db.commit()
        return {"valido": True, "informe": self._vista_emision(fila), "sigue_al_dia": al_dia,
                "mensaje": ("El código es auténtico y el registro no ha cambiado desde esa emisión." if al_dia else
                            "El código es auténtico, pero el registro cambió después de esa emisión: genera uno nuevo "
                            "para presentar la versión actual.")}

    async def pdf_mapa(self) -> tuple[bytes, str]:
        from app.application.mapa_datos.pdf_mapa import DatosInformeMapa, PdfNoDisponibleError as MapaNoDisponible
        from app.application.mapa_datos.pdf_mapa import generar_pdf_mapa
        from app.domain.mapa_datos.analisis import FiltrosMapa

        generado = _ahora()
        reg = await self.registro()
        version = self._version_registro(reg, await self._ultima(TIPO_RAT))
        datos = DatosInformeMapa(razon_social=reg.razon_social, rubro=R.RUBRO_THERION, version=version,
                                 fecha_version=None, huella=reg.huella, elementos=list(reg.elementos),
                                 flujos=list(reg.flujos), filtros=FiltrosMapa(), generado=generado)
        try:
            pdf = await asyncio.to_thread(generar_pdf_mapa, datos)
        except (MapaNoDisponible, PdfNoDisponibleError) as e:
            raise PrivacidadPlataformaError(503, "INFORME_NO_DISPONIBLE", str(e))
        self.bitacora.registrar(accion=Accion.PLATAFORMA_MAPA_DESCARGADO, entidad="plataforma_registro",
                                entidad_id=ID_REGISTRO, actor=self.actor,
                                detalle={"version": version, "huella": reg.huella[:16]})
        await self.db.commit()
        dd, mm, aaaa = fecha_local(generado, con_hora=False).split("-")
        return pdf, f"mapa_datos_plataforma_v{version}_{aaaa}-{mm}-{dd}.pdf"


def _nombre_base(tipo: str, version: int, generado: datetime, oficial: bool) -> str:
    """registro_plataforma_v3_2026-11-13 (con _borrador si lo es). Solo [A-Za-z0-9_.-]."""
    dd, mm, aaaa = fecha_local(generado, con_hora=False).split("-")
    nombre = "registro_plataforma" if tipo == TIPO_RAT else "ropa_plataforma"
    return f"{nombre}_v{version}_{aaaa}-{mm}-{dd}{'' if oficial else '_borrador'}"
