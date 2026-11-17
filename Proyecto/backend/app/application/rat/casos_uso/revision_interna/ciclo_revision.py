"""Revisión interna: iniciar, verificar puntos, observaciones, marcar la versión revisada y revisión periódica."""
from __future__ import annotations

import logging

from app.application.informes.formato import fecha_local
from app.application.rat.casos_uso.revision_interna.comun import (
    CLAVE_REGISTRO, LARGO_CIERRE, LARGO_CONCLUSION, LARGO_OBSERVACION, _SOLO_TEXTO, RevisionError, _ahora, _sin_preguntas,
    _texto, observacion_vista,
)
from app.application.rat.casos_uso.generar_informe import InformeRatError
from app.domain.auditoria.acciones import Accion
from app.domain.mapa_datos.modelo_mapa import contiene_contacto
from app.domain.models.rat_revision import (
    ABIERTA, CERRADA, EN_CURSO, PRIORIDADES, REVISADA, RatObservacion, RatRevision, ConfiguracionRevisionRat,
)
from app.domain.rat import lista_verificacion as R

logger = logging.getLogger(__name__)


class RevisionMixin:
    """Depende de los atributos que fija RevisionInternaCasos.__init__ (db, repo, informes, bitacora, ...)."""

    # ================================================================ iniciar (C1)
    async def _iniciar(self) -> RatRevision:
        # Serializa con la empresa: una sola revisión en curso (además del índice único parcial)
        await self.repo.bloquear_empresa(self.empresa_id)
        actual = await self._en_curso(bloquear=True)
        if actual is not None:
            return actual
        numero = await self.repo.max_numero_revision(self.empresa_id) + 1
        r = RatRevision(empresa_id=self.empresa_id, numero=numero, estado=EN_CURSO, fecha_inicio=_ahora(),
                        iniciada_por_id=self.usuario_id, verificaciones={}, resumen={}, lista=[])
        self.repo.agregar(r)
        await self.db.flush()
        self.bitacora.registrar(accion=Accion.REVISION_RAT_INICIADA, entidad="rat_revision", entidad_id=r.id,
                                actor=self.actor, detalle={"numero": numero})
        return r

    async def iniciar(self) -> dict:
        existia = await self._en_curso() is not None
        await self._iniciar()
        await self.db.commit()
        return {**await self.estado(), "mensaje": "Ya tenías una revisión en curso: continúa donde quedaste." if existia
                else "Comenzó la revisión interna. Recorre la lista de verificación de cada actividad y elemento."}

    # ================================================================ verificar puntos (C1)
    async def verificar(self, clave: str, criterios: list[str] | None, decision: str, nota: str | None) -> dict:
        ctx = await self._contexto()
        objeto = ctx.por_clave.get(clave)
        if objeto is None:
            raise RevisionError(404, "OBJETO_NO_ENCONTRADO", "Ese elemento ya no está en el registro o en el mapa. "
                                                             "Actualiza la página.")
        if nota and contiene_contacto(nota):
            raise RevisionError(422, "DATOS_DE_CONTACTO", "La justificación describe el registro, no a personas: "
                                                          "quita correos, RUT o teléfonos.", campo="nota")
        r = await self._iniciar()
        r = await self._en_curso(bloquear=True) or r
        try:
            nuevas, cambiados = R.aplicar_verificacion(r.verificaciones, objeto, criterios, decision, nota, _ahora())
        except R.ErrorRevision as e:
            await self.db.rollback()
            raise RevisionError(422, e.codigo, e.mensaje)
        r.verificaciones = nuevas
        self.bitacora.registrar(accion=Accion.REVISION_RAT_VERIFICACION, entidad="rat_revision", entidad_id=r.id,
                                actor=self.actor, detalle={"objeto": clave, "criterios": cambiados,
                                                           "decision": decision, "huella": objeto.huella[:16]})
        await self.db.commit()
        consolidado = R.consolidar([objeto], nuevas)[0]
        return {"objeto": _sin_preguntas([consolidado])[0],
                "mensaje": {"verificado": "Quedó verificado.", "aceptado": "Quedó aceptado con tu justificación.",
                            "pendiente": "Quedó pendiente otra vez."}[decision]}

    # ================================================================ observaciones (C2)
    async def crear_observacion(self, clave: str, criterio: str | None, prioridad: str, texto: str) -> dict:
        texto = _texto(texto)
        if not texto or not LARGO_OBSERVACION[0] <= len(texto) <= LARGO_OBSERVACION[1]:
            raise RevisionError(422, "TEXTO_INVALIDO", f"Describe la observación en {LARGO_OBSERVACION[0]} a "
                                                       f"{LARGO_OBSERVACION[1]} caracteres.", campo="texto")
        if contiene_contacto(texto):
            raise RevisionError(422, "DATOS_DE_CONTACTO", "La observación describe el registro, no a personas: quita "
                                                          "correos, RUT o teléfonos.", campo="texto")
        if prioridad not in PRIORIDADES:
            raise RevisionError(422, "PRIORIDAD_INVALIDA", "Elige la prioridad: alta, media o baja.", campo="prioridad")
        ctx = await self._contexto()
        if clave == CLAVE_REGISTRO:
            tipo, obj_id, nombre, huella = "registro", None, "Registro completo", ctx.inf.huella
            if criterio:
                raise RevisionError(422, "CRITERIO_INVALIDO", "Una observación del registro completo no lleva criterio.")
        else:
            objeto = ctx.por_clave.get(clave)
            if objeto is None:
                raise RevisionError(404, "OBJETO_NO_ENCONTRADO", "Ese elemento ya no está en el registro o en el mapa.")
            if criterio and criterio not in R.CRITERIOS[objeto.tipo]:
                raise RevisionError(422, "CRITERIO_INVALIDO", "Ese punto no existe para este elemento.", campo="criterio")
            tipo, obj_id, nombre, huella = objeto.tipo, objeto.id, objeto.nombre[:200], objeto.huella
        r = await self._iniciar()
        numero = await self.repo.max_numero_observacion(self.empresa_id) + 1
        o = RatObservacion(empresa_id=self.empresa_id, revision_id=r.id, numero=numero, objeto_tipo=tipo,
                           objeto_id=obj_id, objeto_clave=clave, objeto_nombre=nombre, criterio=criterio or None,
                           prioridad=prioridad, texto=texto, estado=ABIERTA, fecha_apertura=_ahora(),
                           abierta_por_id=self.usuario_id, huella_apertura=huella, reaperturas=0)
        self.repo.agregar(o)
        await self.db.flush()
        self.bitacora.registrar(accion=Accion.REVISION_RAT_OBSERVACION_CREADA, entidad="rat_observacion",
                                entidad_id=o.id, actor=self.actor,
                                detalle={"revision_id": r.id, "numero": numero, "objeto": clave, "criterio": criterio,
                                         "prioridad": prioridad})
        await self.db.commit()
        return {"observacion": observacion_vista(o, ctx.por_clave),
                "mensaje": f"Registraste la observación N.º {numero}. Mientras esté abierta no se puede marcar la "
                           "versión como revisada."}

    async def _observacion(self, observacion_id: int) -> RatObservacion:
        o = await self.repo.observacion_bloqueada(observacion_id, self.empresa_id)
        if o is None:
            raise RevisionError(404, "OBSERVACION_NO_ENCONTRADA", "No encontramos esa observación.")
        return o

    async def cerrar_observacion(self, observacion_id: int, nota: str) -> dict:
        nota = _texto(nota)
        if not nota or not LARGO_CIERRE[0] <= len(nota) <= LARGO_CIERRE[1]:
            raise RevisionError(422, "NOTA_INVALIDA", "Cuenta qué se corrigió o por qué se cierra "
                                                      f"({LARGO_CIERRE[0]} a {LARGO_CIERRE[1]} caracteres).", campo="nota")
        if contiene_contacto(nota):
            raise RevisionError(422, "DATOS_DE_CONTACTO", "Quita correos, RUT o teléfonos de la nota.", campo="nota")
        ctx = await self._contexto()
        o = await self._observacion(observacion_id)
        if o.estado == CERRADA:
            await self.db.rollback()
            raise RevisionError(409, "OBSERVACION_CERRADA", "Esa observación ya estaba cerrada.")
        actual = ctx.inf.huella if o.objeto_tipo == "registro" else (
            ctx.por_clave[o.objeto_clave].huella if o.objeto_clave in ctx.por_clave else None)
        o.estado, o.fecha_cierre, o.cerrada_por_id, o.nota_cierre = CERRADA, _ahora(), self.usuario_id, nota
        o.huella_cierre = actual
        o.objeto_cambio = (actual != o.huella_apertura) if o.huella_apertura else None
        self.bitacora.registrar(accion=Accion.REVISION_RAT_OBSERVACION_CERRADA, entidad="rat_observacion",
                                entidad_id=o.id, actor=self.actor,
                                detalle={"numero": o.numero, "objeto": o.objeto_clave, "objeto_cambio": o.objeto_cambio,
                                         "objeto_eliminado": actual is None})
        await self.db.commit()
        return {"observacion": observacion_vista(o, ctx.por_clave),
                "mensaje": "Cerraste la observación." + ("" if o.objeto_cambio or o.objeto_tipo == "registro" else
                                                         " El elemento no cambió desde que la abriste: quedó anotado.")}

    async def reabrir_observacion(self, observacion_id: int) -> dict:
        ctx = await self._contexto()
        o = await self._observacion(observacion_id)
        if o.estado == ABIERTA:
            await self.db.rollback()
            raise RevisionError(409, "OBSERVACION_ABIERTA", "Esa observación ya está abierta.")
        rev = await self.repo.revision(o.revision_id)
        if rev is not None and rev.estado == REVISADA:
            await self.db.rollback()
            raise RevisionError(409, "REVISION_CERRADA", "Esa observación es parte de una revisión ya marcada: "
                                                         "si el problema volvió, registra una nueva.")
        o.estado, o.fecha_cierre, o.cerrada_por_id, o.nota_cierre = ABIERTA, None, None, None
        o.huella_cierre, o.objeto_cambio, o.reaperturas = None, None, (o.reaperturas or 0) + 1
        self.bitacora.registrar(accion=Accion.REVISION_RAT_OBSERVACION_REABIERTA, entidad="rat_observacion",
                                entidad_id=o.id, actor=self.actor,
                                detalle={"numero": o.numero, "reaperturas": o.reaperturas})
        await self.db.commit()
        return {"observacion": observacion_vista(o, ctx.por_clave), "mensaje": "Volviste a abrir la observación."}

    # ================================================================ marcar la versión revisada (C3)
    @staticmethod
    def _validar_persona(valor: str | None, campo: str, obligatorio: bool) -> str | None:
        v = _texto(valor)
        if not v:
            if obligatorio:
                raise RevisionError(422, "NOMBRE_REQUERIDO", "Escribe el nombre de quien revisa: aparece en la "
                                                             "constancia y en el informe.", campo=campo)
            return None
        if not 2 <= len(v) <= 120 or not _SOLO_TEXTO.match(v) or contiene_contacto(v):
            raise RevisionError(422, "NOMBRE_INVALIDO" if campo == "revisor_nombre" else "CARGO_INVALIDO",
                                "Usa solo letras (2 a 120 caracteres), sin correos ni números.", campo=campo)
        return v

    async def marcar(self, revisor_nombre: str, revisor_cargo: str | None, conclusion: str | None,
                     huella_vista: str | None, confirmo: bool) -> dict:
        if not confirmo:
            raise RevisionError(422, "CONFIRMACION_REQUERIDA", "Confirma que revisaste el registro y que es fiel.")
        nombre = self._validar_persona(revisor_nombre, "revisor_nombre", True)
        cargo = self._validar_persona(revisor_cargo, "revisor_cargo", False)
        conclusion = _texto(conclusion)
        if conclusion and (len(conclusion) > LARGO_CONCLUSION or contiene_contacto(conclusion)):
            raise RevisionError(422, "CONCLUSION_INVALIDA", f"La conclusión admite hasta {LARGO_CONCLUSION} caracteres y "
                                                            "no lleva datos de contacto.", campo="conclusion")
        await self.repo.bloquear_empresa(self.empresa_id)
        r = await self._en_curso(bloquear=True)
        if r is None:
            raise await self._rechazar("sin_revision", RevisionError(
                409, "SIN_REVISION", "Primero comienza la revisión y recorre la lista de verificación."))
        ctx = await self._contexto()
        consolidados = R.consolidar(ctx.objetos, r.verificaciones)
        observaciones = [observacion_vista(o, ctx.por_clave) for o in await self._observaciones()
                         if o.revision_id == r.id or o.estado == ABIERTA]
        abiertas = sum(1 for o in observaciones if o["estado"] == ABIERTA)
        req = R.requisitos(consolidados, abiertas, len(ctx.inf.actividades), huella_vista, ctx.inf.huella)
        if not req["puede_marcar"] or ctx.inf.borrador:
            faltan = req["faltan"] or [{"codigo": "BORRADOR", "texto": "Hay actividades que no están vigentes."}]
            raise await self._rechazar("requisitos", RevisionError(
                409, "REVISION_INCOMPLETA", "Todavía no se puede marcar la versión como revisada: "
                + " ".join(f["texto"] for f in faltan), faltan=faltan),
                faltan=[f["codigo"] for f in faltan])
        ahora = _ahora()
        version = await self._version_para(ctx.inf.huella)
        resumen = R.resumen(consolidados, [o for o in observaciones if o["revision_id"] == r.id])
        resumen["versiones"] = [{"id": a.id, "version": a.version, "huella": a.huella_version, "estado": a.estado}
                                for a in ctx.inf.actividades]
        r.estado, r.fecha_revision, r.revisado_por_id = REVISADA, ahora, self.usuario_id
        r.revisor_nombre, r.revisor_cargo, r.conclusion = nombre, cargo, conclusion
        r.version_rat, r.huella, r.version_mapa = version, ctx.inf.huella, ctx.version_mapa
        r.resumen = resumen
        r.lista = [{**o, "items": [{k: v for k, v in i.items() if k != "pregunta"} for i in o["items"]]}
                   for o in consolidados]
        self.bitacora.registrar(
            accion=Accion.REVISION_RAT_VERSION_REVISADA, entidad="rat_revision", entidad_id=r.id, actor=self.actor,
            detalle={"numero": r.numero, "version_rat": version, "huella": ctx.inf.huella[:16],
                     "puntos": resumen["puntos"], "aceptados": resumen["aceptados"],
                     "observaciones_cerradas": resumen["observaciones"]["cerradas"], "objetos": resumen["objetos"],
                     "con_conclusion": bool(conclusion)})
        await self.db.commit()
        revision_id = r.id
        # El informe del registro de esta versión, ya con la marca (si falla, se puede emitir después)
        informe, aviso = None, None
        try:
            emision = await self.informes.emitir()
            informe = emision["informe"]
            fila = await self.repo.revision(revision_id)
            if fila is not None and fila.informe_id is None and informe.get("revision"):
                fila.informe_id = informe["id"]
                await self.db.commit()
        except Exception as e:  # noqa: BLE001 - la revisión ya quedó marcada: el informe se puede emitir después
            await self.db.rollback()
            aviso = getattr(e, "mensaje", None) if isinstance(e, InformeRatError) else None
            logger.warning("HU-40: la revisión %s quedó marcada pero el informe no se emitió (%s)", revision_id, aviso)
        fila = await self._revision(revision_id)
        return {"revision": self._vista_revision(fila), "informe": informe,
                "mensaje": f"La versión N.º {version} del registro quedó revisada el "
                           f"{fecha_local(ahora, con_hora=False)}. "
                           + ("El informe del registro ya lleva la marca." if informe else
                              "Genera el informe del registro para que lleve la marca."
                              + (f" ({aviso})" if aviso else ""))}

    # ================================================================ revisión periódica (C5)
    async def configurar(self, plazo_meses: int, aviso_dias: int, recordatorio_correo: bool) -> dict:
        if not 1 <= int(plazo_meses) <= 36:
            raise RevisionError(422, "PLAZO_INVALIDO", "El plazo entre revisiones va de 1 a 36 meses.", campo="plazo_meses")
        if not 0 <= int(aviso_dias) <= 90:
            raise RevisionError(422, "AVISO_INVALIDO", "El aviso previo va de 0 a 90 días.", campo="aviso_dias")
        c = await self._config()
        antes = self._config_vista(c)
        if c is None:
            c = ConfiguracionRevisionRat(empresa_id=self.empresa_id, fecha_actualizacion=_ahora())
            self.repo.agregar(c)
        c.plazo_meses, c.aviso_dias, c.recordatorio_correo = int(plazo_meses), int(aviso_dias), bool(recordatorio_correo)
        c.fecha_actualizacion = _ahora()
        if antes["plazo_meses"] != c.plazo_meses or antes["aviso_dias"] != c.aviso_dias:
            c.etapa_recordatorio = None             # con otro plazo, el próximo recordatorio se recalcula
        self.bitacora.registrar(accion=Accion.REVISION_RAT_CONFIGURACION, entidad="rat_revision_config",
                                entidad_id=self.empresa_id, actor=self.actor,
                                detalle={"plazo_meses": c.plazo_meses, "aviso_dias": c.aviso_dias,
                                         "recordatorio_correo": c.recordatorio_correo,
                                         "antes": {k: antes[k] for k in ("plazo_meses", "aviso_dias", "recordatorio_correo")}})
        await self.db.commit()
        revisadas = await self._revisadas(1)
        return {"periodicidad": await self._periodicidad(revisadas[0] if revisadas else None, self._config_vista(c)),
                "mensaje": f"Guardamos el plazo: revisarás el registro cada {c.plazo_meses} meses."}
