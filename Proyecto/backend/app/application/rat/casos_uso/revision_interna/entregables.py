"""Revisión interna: constancia (PDF), paquete de evidencia, verificación del paquete y envío por correo."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, time as dtime, timezone

from app.application.fabricas import fabricas
from app.application.informes import correo
from app.application.informes.formato import ZONA
from app.application.ports.generador_documentos_port import PdfNoDisponibleError
from app.application.rat import correo_revision as CR
from app.application.rat import paquete_revision as P
from app.application.rat.constancia_revision import DatosConstancia, nombre_archivo
from app.application.rat.casos_uso.revision_interna.comun import (
    MAX_HISTORIAL_AUDITORIA, _PREFIJOS_HISTORIAL, RevisionError, _ahora, _fecha_txt, _hoy_chile, _iso,
    observacion_vista,
)
from app.application.rat.casos_uso.generar_informe import InformeRatError
from app.application.use_cases.limites_encuesta import ventana_diaria
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO
from app.domain.models.rat_revision import REVISADA, RatPaqueteEvidencia, RatRevision
from app.domain.ports.correo_port import Adjunto, CorreoFallidoError, CorreoNoDisponibleError
from app.domain.ports.limitador_port import LimitadorNoDisponibleError
from app.domain.rat import revision as R


class EntregablesMixin:
    """Depende de los atributos que fija RevisionInternaCasos.__init__ (db, repo, informes, bitacora, ...)."""

    # ================================================================ constancia (PDF)
    async def _datos_constancia(self, r: RatRevision) -> DatosConstancia:
        cfg = self._config_vista(await self._config())
        if r.estado == REVISADA:
            lista, resumen = list(r.lista or []), dict(r.resumen or {})
            observaciones = [observacion_vista(o) for o in await self._observaciones(r.id)]
            proxima = R.sumar_meses(_hoy_chile(r.fecha_revision), cfg["plazo_meses"])
            huella, version = r.huella, r.version_rat
        else:
            ctx = await self._contexto()
            lista = R.consolidar(ctx.objetos, r.verificaciones)
            observaciones = [observacion_vista(o, ctx.por_clave) for o in await self._observaciones(r.id)]
            resumen = R.resumen(lista, observaciones)
            proxima, huella, version = None, ctx.inf.huella, None
        anterior = await self.repo.revisada_anterior(self.empresa_id, r.numero)
        diferencias, desde = None, None
        if anterior is not None and (anterior.resumen or {}).get("versiones"):
            antes = await self._entradas_de(anterior.resumen["versiones"])
            if r.estado == REVISADA:
                despues = await self._entradas_de(resumen.get("versiones") or [])
            else:
                despues = {a.id: self._entrada(a) for a in (await self.informes.armar()).actividades}
            diferencias = R.comparar(antes, despues)
            desde = f"la revisión N.º {anterior.numero} (versión {anterior.version_rat})"
        informe = await self.repo.informe(r.informe_id) if r.informe_id else None
        return DatosConstancia(
            empresa=self.razon_social, rut=self.rut, numero=r.numero, estado=r.estado, fecha_inicio=r.fecha_inicio,
            generado=_ahora(), lista=lista, observaciones=observaciones, resumen=resumen,
            fecha_revision=r.fecha_revision, revisor=r.revisor_nombre, cargo=r.revisor_cargo, conclusion=r.conclusion,
            version_rat=version, huella=huella, version_mapa=r.version_mapa,
            informe_codigo=informe.codigo if informe is not None and informe.empresa_id == self.empresa_id else None,
            proxima_revision=_fecha_txt(proxima), plazo_meses=cfg["plazo_meses"] if proxima else None,
            diferencias=diferencias, diferencias_desde=desde)

    async def _pdf(self, d: DatosConstancia) -> bytes:
        import asyncio

        try:
            return await asyncio.to_thread(fabricas().documentos.pdf_revision_interna, d)
        except PdfNoDisponibleError as e:
            raise RevisionError(503, "PDF_NO_DISPONIBLE", str(e))

    async def constancia(self, revision_id: int) -> tuple[bytes, str]:
        r = await self._revision(revision_id)
        d = await self._datos_constancia(r)
        contenido = await self._pdf(d)
        self.bitacora.registrar(accion=Accion.REVISION_RAT_CONSTANCIA_DESCARGADA, entidad="rat_revision",
                                entidad_id=r.id, actor=self.actor, detalle={"numero": r.numero, "estado": r.estado})
        await self.db.commit()
        return contenido, nombre_archivo(d)

    # ================================================================ paquete de evidencia (C4)
    async def _auditoria(self, hasta: datetime | None) -> list[dict]:
        filas = await self.repo.historial_auditoria(
            actor_rol=self.actor.rol, actor_id=self.actor.id, empresa_id=self.empresa_id,
            prefijos=_PREFIJOS_HISTORIAL, hasta=hasta, limite=MAX_HISTORIAL_AUDITORIA)
        return [{"id": f.id, "fecha": f.fecha.isoformat(timespec="microseconds") if f.fecha else None,
                 "actor_rol": f.actor_rol, "accion": f.accion, "entidad": f.entidad, "entidad_id": f.entidad_id,
                 "resultado": f.resultado, "detalle": f.detalle, "hash_anterior": f.hash_anterior, "hash": f.hash}
                for f in reversed(filas)]

    async def _versiones_paquete(self, lista: list[dict]) -> list[dict]:
        ids = [x["id"] for x in lista if x.get("version")]
        if not ids:
            return []
        por = await self.repo.versiones_de_actividades(self.empresa_id, ids)
        salida = []
        for x in sorted(lista, key=lambda y: y["id"]):
            v = por.get((x["id"], x.get("version")))
            if v is not None:
                salida.append({"actividad_id": x["id"], "numero": v.numero, "estado": x.get("estado") or "vigente",
                               "huella": v.huella, "fecha": _iso(v.fecha), "contenido": v.contenido})
        return salida

    async def paquete(self, revision_id: int) -> tuple[bytes, str, str, str]:
        """(zip, nombre de archivo, código, sha256)."""
        import asyncio

        r = await self._revision(revision_id)
        ahora_tz = datetime.now(timezone.utc)
        inicio = datetime.combine(ahora_tz.astimezone(ZONA).date(), dtime.min, tzinfo=ZONA)
        hoy = await self.repo.paquetes_desde(self.empresa_id, inicio.astimezone(timezone.utc).replace(tzinfo=None))
        if hoy >= settings.REVISION_RAT_PAQUETES_DIA:
            raise RevisionError(429, "LIMITE_PAQUETES", f"Ya exportaste {hoy} paquetes hoy. Usa uno de los anteriores o "
                                                        "vuelve a intentarlo mañana.")
        d = await self._datos_constancia(r)
        constancia = await self._pdf(d)
        notas: list[str] = []
        if r.estado != REVISADA:
            notas.append("La revisión está en curso: este paquete muestra su avance y no es una constancia.")
        # El informe del registro de esa versión (el emitido con la marca o el último con la misma huella)
        informe_archivos: dict[str, bytes] = {}
        emision = await self.repo.informe(r.informe_id) if r.informe_id else None
        if emision is None and d.huella:
            emision = await self.repo.ultimo_informe_con_huella(self.empresa_id, d.huella)
        if emision is not None and emision.empresa_id == self.empresa_id:
            for formato in ("pdf", "xlsx"):
                try:
                    contenido, doc = await self.informes._archivo(emision, formato)
                    informe_archivos[doc.nombre] = contenido
                except InformeRatError as e:
                    notas.append(f"El informe del registro en {formato.upper()} no se incluyó: {e.mensaje}")
        else:
            notas.append("No hay un informe del registro emitido para esta versión: genéralo y vuelve a exportar el "
                         "paquete para incluirlo.")
        versiones_lista = (d.resumen or {}).get("versiones") or (
            [{"id": a.id, "version": a.version, "huella": a.huella_version, "estado": a.estado}
             for a in (await self.informes.armar()).actividades] if r.estado != REVISADA else [])
        emisiones = [{"codigo": f.codigo, "version_rat": f.version_rat, "fecha": _iso(f.fecha), "borrador": f.borrador,
                      "huella": f.huella, "revision_id": f.revision_id, "actividades": f.actividades}
                     for f in (await self.repo.informes_con_huella(self.empresa_id, d.huella))] if d.huella else []

        # La huella del registro solo se puede recalcular si todas las actividades tienen versión vigente
        recalculable = bool(versiones_lista) and all(x.get("version") for x in versiones_lista)
        if not recalculable:
            notas.append("Hay actividades sin versión vigente: el script verifica los archivos, pero no puede recalcular "
                         "la huella del registro.")
        fila = RatPaqueteEvidencia(empresa_id=self.empresa_id, revision_id=r.id, codigo=None,
                                   sha256=secrets.token_hex(32), huella_manifiesto="0" * 64, archivos=0,
                                   tamano_bytes=0, fecha=ahora_tz.replace(tzinfo=None),
                                   usuario_definitivo_id=self.usuario_id)
        self.db.add(fila)
        await self.db.flush()
        codigo = P.codigo(fila.id, ahora_tz.astimezone(ZONA).year)
        datos = P.DatosPaquete(
            codigo=codigo, empresa=self.razon_social, generado=ahora_tz.replace(tzinfo=None).isoformat(timespec="seconds"),
            revision={"numero": r.numero, "estado": r.estado, "version_rat": r.version_rat, "huella": d.huella,
                      "fecha_inicio": _iso(r.fecha_inicio), "fecha_revision": _iso(r.fecha_revision),
                      "revisor": r.revisor_nombre, "cargo": r.revisor_cargo, "conclusion": r.conclusion,
                      "version_mapa": r.version_mapa, "resumen": {k: v for k, v in (d.resumen or {}).items()
                                                                   if k != "versiones"}},
            lista=d.lista, observaciones=d.observaciones, versiones=await self._versiones_paquete(versiones_lista),
            auditoria=await self._auditoria(r.fecha_revision), emisiones=emisiones, diferencias=d.diferencias,
            constancia_pdf=constancia, informe=informe_archivos, notas=notas, huella_recalculable=recalculable)
        archivos = await asyncio.to_thread(P.archivos, datos)
        contenido = await asyncio.to_thread(P.comprimir, archivos)
        sha = hashlib.sha256(contenido).hexdigest()
        fila.codigo, fila.sha256, fila.huella_manifiesto = codigo, sha, P.huella_manifiesto(archivos)
        fila.archivos, fila.tamano_bytes = len(archivos), len(contenido)
        self.bitacora.registrar(
            accion=Accion.REVISION_RAT_PAQUETE_EXPORTADO, entidad="rat_paquete_evidencia", entidad_id=fila.id,
            actor=self.actor, detalle={"codigo": codigo, "revision_id": r.id, "estado": r.estado,
                                       "sha256_zip": sha, "archivos": len(archivos), "version_rat": r.version_rat})
        await self.db.commit()
        nombre = f"paquete_revision_{r.numero}_{codigo}.zip"
        return contenido, nombre, codigo, sha

    async def verificar_paquete(self, contenido: bytes) -> dict:
        maximo = settings.REVISION_RAT_PAQUETE_VERIFICAR_MB * 1024 * 1024
        if not contenido or len(contenido) > maximo:
            raise RevisionError(413 if contenido else 422, "ARCHIVO_INVALIDO",
                                f"Sube el ZIP del paquete (hasta {settings.REVISION_RAT_PAQUETE_VERIFICAR_MB} MB).")
        sha = hashlib.sha256(contenido).hexdigest()
        resultado = P.verificar_zip(contenido)
        fila = await self.repo.paquete_por_sha256(sha, self.empresa_id)
        por_codigo = None
        if fila is None and resultado.manifiesto and resultado.manifiesto.get("codigo"):
            leido = P.leer_codigo(str(resultado.manifiesto["codigo"]))
            if leido is not None:
                por_codigo = await self.repo.paquete(leido[1])
                if por_codigo is not None and por_codigo.empresa_id != self.empresa_id:
                    por_codigo = None
        registrado = fila is not None
        if registrado and resultado.integro:
            mensaje = "El paquete es auténtico: es exactamente el que exportaste y ningún archivo cambió."
        elif por_codigo is not None:
            mensaje = ("El código corresponde a un paquete de tu empresa, pero el ZIP no es idéntico al exportado: "
                       "fue modificado o recomprimido.")
        elif resultado.error:
            mensaje = resultado.error
        elif resultado.integro:
            mensaje = ("Los archivos coinciden con su manifiesto, pero la plataforma no tiene registrado este paquete "
                       "para tu empresa.")
        else:
            mensaje = "El paquete NO es íntegro: hay archivos modificados, que faltan o que sobran."
        ref = fila or por_codigo
        revision = await self.repo.revision(ref.revision_id) if ref is not None else None
        self.bitacora.registrar(
            accion=Accion.REVISION_RAT_PAQUETE_VERIFICADO, entidad="rat_paquete_evidencia",
            entidad_id=ref.id if ref else None, actor=self.actor,
            resultado=RESULTADO_OK if registrado and resultado.integro else RESULTADO_RECHAZADO,
            detalle={"registrado": registrado, "integro": resultado.integro, "alterados": len(resultado.alterados)})
        await self.db.commit()
        return {
            "valido": registrado and resultado.integro, "registrado": registrado, "integro": resultado.integro,
            "sha256": sha, "alterados": resultado.alterados, "faltantes": resultado.faltantes,
            "sobrantes": resultado.sobrantes, "mensaje": mensaje,
            "paquete": {"codigo": ref.codigo, "fecha": _iso(ref.fecha), "archivos": ref.archivos,
                        "revision": {"numero": revision.numero, "estado": revision.estado,
                                     "version_rat": revision.version_rat} if revision else None} if ref else None,
        }

    # ================================================================ envío por correo
    async def enviar(self, revision_id: int, email: str | None, con_paquete: bool) -> dict:
        if settings.CORREO_MODO == "desactivado":
            raise RevisionError(503, "CORREO_NO_DISPONIBLE", "El envío por correo no está habilitado. Descarga el informe.")
        destino = (email or "").strip().lower() or self.email_usuario
        if not correo.EMAIL_VALIDO.match(destino or ""):
            raise RevisionError(422, "EMAIL_INVALIDO", "Revisa el formato del correo (ejemplo: nombre@empresa.cl).")
        r = await self._revision(revision_id)
        if self.limitador is None:
            raise RevisionError(503, "LIMITADOR_NO_DISPONIBLE", "No pudimos enviar el correo ahora. Descarga el informe.")
        fecha, ventana, _ = ventana_diaria()
        clave = f"revision_rat:correo:{self.empresa_id}:{fecha}"
        try:
            consumo = await self.limitador.consumir(clave, settings.REVISION_RAT_CORREOS_DIA, ventana)
        except LimitadorNoDisponibleError:
            raise RevisionError(503, "LIMITADOR_NO_DISPONIBLE", "No pudimos enviar el correo ahora. Descarga el informe.")
        if not consumo.permitido:
            await self.limitador.devolver(clave)
            raise RevisionError(429, "LIMITE_CORREOS", f"Ya enviaste {settings.REVISION_RAT_CORREOS_DIA} correos de la "
                                                       "revisión hoy. Descarga el informe o vuelve a intentarlo mañana.",
                                reintentar_en_s=consumo.reintentar_en_s)
        try:
            d = await self._datos_constancia(r)
            adjuntos = [Adjunto(nombre_archivo(d), await self._pdf(d), "application/pdf")]
            codigo_paquete = None
            if con_paquete:
                zip_, nombre, codigo_paquete, _ = await self.paquete(revision_id)
                if len(zip_) > settings.REVISION_RAT_PAQUETE_CORREO_MB * 1024 * 1024:
                    raise RevisionError(413, "PAQUETE_GRANDE", "El paquete es muy grande para el correo: descárgalo y "
                                                               "compártelo por otro medio.")
                adjuntos.append(Adjunto(nombre, zip_, "application/zip"))
            texto, html = CR.cuerpo_constancia(d, con_paquete, codigo_paquete)
            modo = await fabricas().correo.enviar(destino, CR.asunto_constancia(d), texto, html, adjuntos)
        except (CorreoFallidoError, CorreoNoDisponibleError) as e:
            await self.limitador.devolver(clave)
            raise RevisionError(502 if isinstance(e, CorreoFallidoError) else 503, "CORREO_FALLIDO",
                                "No pudimos enviar el correo. Inténtalo de nuevo en unos minutos o descarga el informe.")
        except RevisionError:
            await self.limitador.devolver(clave)
            raise
        self.bitacora.registrar(accion=Accion.REVISION_RAT_ENVIADA, entidad="rat_revision", entidad_id=r.id,
                                actor=self.actor, detalle={"modo": modo, "con_paquete": con_paquete,
                                                           "destino_propio": destino == self.email_usuario,
                                                           "estado": r.estado})
        await self.db.commit()
        return {"enviado": True, "destino": correo.enmascarar(destino), "modo": modo, "con_paquete": con_paquete}
