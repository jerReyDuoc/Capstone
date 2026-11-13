"""
HU-40 · Revisión interna del registro (modo de auditoría interna del cliente).

Como Usuario Definitivo (cliente), en su función de auditoría interna, quiero revisar el mapa, el RAT y los
informes en un modo de auditoría interna y dejar constancia de esa revisión, para verificar que el registro
es fiel y está al día antes de presentarlo, certificarlo o informarlo al directorio.

  C1  El MISMO usuario definitivo entra al modo de revisión (sin rol ni cuenta adicional) y recorre la lista de
      verificación por actividad y por elemento del mapa (app/domain/rat/revision.py).
  C2  Deja observaciones por actividad, elemento o flujo (o del registro en general) y las cierra al corregir.
      Con observaciones abiertas la versión no se puede marcar revisada.
  C3  Marca la versión del RAT como revisada con fecha y nombre: la marca aparece en el informe del registro
      (InformeRatCasos.armar busca la revisión con la misma huella) y queda en el audit_log.
  C4  Ve las diferencias entre versiones y exporta un paquete de evidencia (informe, historial, lista de
      verificación y observaciones) verificable con hash, como el ZIP del Auditor Externo (HU-09).
  C5  Recordatorio de revisión periódica con plazo configurable (12 meses por defecto): aviso en la página y
      correo diario del worker (enviar_recordatorios) cuando vence o está por vencer.

La revisión lee el registro como lo afirmaría el informe (la versión vigente de cada actividad) y el mapa de
datos actual. Cada elemento revisado guarda su huella: si cambia después, su verificación queda
desactualizada. Solo con contrato vigente. Cada acción queda en el audit_log en la misma transacción.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.application.informes.motor_pdf import ZONA, PdfNoDisponibleError, fecha_local
from app.application.rat import correo_revision as CR
from app.application.rat import informe as I
from app.application.rat import paquete_revision as P
from app.application.rat.pdf_revision import DatosConstancia
from app.application.use_cases.informe_rat import InformeRatCasos, InformeRatError
from app.application.use_cases.limites_encuesta import ventana_diaria
from app.core.config import settings
from app.domain.mapa_datos.modelo import contiene_contacto
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADO_RECHAZADO, BitacoraAuditoria
from app.domain.models.empresa import Empresa
from app.domain.models.rat import RatActividad, RatActividadVersion
from app.domain.models.rat_informe import RatInforme
from app.domain.models.rat_revision import (ABIERTA, CERRADA, EN_CURSO, PRIORIDADES, REVISADA, RatObservacion,
                                            RatPaqueteEvidencia, RatRevision, RatRevisionConfig)
from app.domain.rat import revision as R
from app.infrastructure.cache.limitador import LimitadorNoDisponibleError
from app.infrastructure.repositories.bitacora_repository import ROL_SISTEMA, Accion, BitacoraRepository

logger = logging.getLogger(__name__)

CLAVE_REGISTRO = "registro:0"
LARGO_OBSERVACION = (5, 1000)
LARGO_CIERRE = (5, 1000)
LARGO_CONCLUSION = 1500
MAX_HISTORIAL_AUDITORIA = 5000
_SOLO_TEXTO = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .,\-()/]+$")
_PREFIJOS_HISTORIAL = ("rat.", "mapa_datos.", "revision_rat.", "ropa.")


class RevisionError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _texto(valor: str | None) -> str | None:
    return " ".join((valor or "").split()) or None


def _hoy_chile(v: datetime | None = None) -> date:
    """Fecha en Chile de un instante (las fechas de la BD son UTC sin zona); sin argumento, hoy."""
    v = v or datetime.now(timezone.utc)
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.astimezone(ZONA).date()


def _fecha_txt(d: date | datetime | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return fecha_local(d, con_hora=False)
    return f"{d:%d-%m-%Y}"


@dataclass
class Contexto:
    inf: I.InformeRat
    version_mapa: int
    objetos: list[R.Objeto]
    por_clave: dict[str, R.Objeto]


def observacion_vista(o: RatObservacion, por_clave: dict[str, R.Objeto] | None = None) -> dict:
    criterios = R.CRITERIOS.get(o.objeto_tipo, {})
    actual = (por_clave or {}).get(o.objeto_clave)
    return {
        "id": o.id, "numero": o.numero, "revision_id": o.revision_id, "objeto_tipo": o.objeto_tipo,
        "objeto_id": o.objeto_id, "objeto_clave": o.objeto_clave, "objeto_nombre": o.objeto_nombre,
        "objeto_existe": o.objeto_tipo == "registro" or actual is not None,
        "criterio": o.criterio, "criterio_titulo": criterios[o.criterio].titulo if o.criterio in criterios else None,
        "prioridad": o.prioridad, "texto": o.texto, "estado": o.estado,
        "fecha_apertura": _iso(o.fecha_apertura), "fecha_cierre": _iso(o.fecha_cierre), "nota_cierre": o.nota_cierre,
        "objeto_cambio": o.objeto_cambio, "reaperturas": o.reaperturas,
        # Mientras está abierta: ¿ya cambió el elemento desde que se observó? (pista de que se corrigió)
        "cambio_desde_apertura": (actual.huella != o.huella_apertura) if (actual and o.huella_apertura
                                                                          and o.estado == ABIERTA) else None,
    }


def _sin_preguntas(objs: list[dict]) -> list[dict]:
    """La pregunta de cada criterio va una sola vez en el catálogo (no repetida en cada punto)."""
    return [{**o, "items": [{k: v for k, v in i.items() if k != "pregunta"} for i in o["items"]]} for o in objs]


def catalogo_criterios() -> dict:
    return {tipo: [{"codigo": c.codigo, "titulo": c.titulo, "pregunta": c.pregunta, "bloqueante": c.bloqueante}
                   for c in lista]
            for tipo, lista in (("actividad", R.CRITERIOS_ACTIVIDAD), ("elemento", R.CRITERIOS_ELEMENTO),
                                ("flujo", R.CRITERIOS_FLUJO))}


class RevisionInternaCasos:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, limitador=None, storage=None):
        self.db = db
        self.cliente = cliente
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.razon_social: str = cliente.empresa.razon_social
        self.rut: str | None = getattr(cliente.empresa, "rut", None)
        self.usuario_id: int = cliente.usuario.id
        self.nombre_usuario: str = getattr(cliente.usuario, "nombre", "") or ""
        self.email_usuario: str = cliente.usuario.email
        self.limitador = limitador
        self.bitacora = BitacoraRepository(db)
        self.informes = InformeRatCasos(db, cliente, limitador, storage)

    # ================================================================ lectura
    async def _contexto(self) -> Contexto:
        from app.application.use_cases.registro_actividades import RegistroActividadesCasos

        inf = await self.informes.armar()
        version_mapa, elementos, flujos = await RegistroActividadesCasos(self.db, self.cliente)._mapa()
        objs = R.objetos(list(inf.actividades), elementos, flujos)
        return Contexto(inf, version_mapa, objs, {o.clave: o for o in objs})

    async def _en_curso(self, bloquear: bool = False) -> RatRevision | None:
        q = select(RatRevision).where(RatRevision.empresa_id == self.empresa_id, RatRevision.estado == EN_CURSO)
        if bloquear:
            q = q.with_for_update()
        return (await self.db.execute(q)).scalar_one_or_none()

    async def _revision(self, revision_id: int) -> RatRevision:
        r = await self.db.get(RatRevision, revision_id)
        if r is None or r.empresa_id != self.empresa_id:          # lo ajeno no existe (404)
            raise RevisionError(404, "REVISION_NO_ENCONTRADA", "No encontramos esa revisión de tu registro.")
        return r

    async def _revisadas(self, limite: int = 50) -> list[RatRevision]:
        return list((await self.db.execute(
            select(RatRevision).where(RatRevision.empresa_id == self.empresa_id, RatRevision.estado == REVISADA)
            .order_by(RatRevision.fecha_revision.desc(), RatRevision.id.desc()).limit(limite))).scalars().all())

    async def _observaciones(self, revision_id: int | None = None) -> list[RatObservacion]:
        q = select(RatObservacion).where(RatObservacion.empresa_id == self.empresa_id)
        if revision_id is not None:
            q = q.where(RatObservacion.revision_id == revision_id)
        return list((await self.db.execute(q.order_by(RatObservacion.numero))).scalars().all())

    async def _abiertas(self) -> int:
        return (await self.db.execute(select(func.count()).select_from(RatObservacion).where(
            RatObservacion.empresa_id == self.empresa_id, RatObservacion.estado == ABIERTA))).scalar() or 0

    async def _config(self) -> RatRevisionConfig | None:
        return await self.db.get(RatRevisionConfig, self.empresa_id)

    @staticmethod
    def _config_vista(c: RatRevisionConfig | None) -> dict:
        return {"plazo_meses": c.plazo_meses if c else settings.REVISION_RAT_PLAZO_MESES,
                "aviso_dias": c.aviso_dias if c else settings.REVISION_RAT_AVISO_DIAS,
                "recordatorio_correo": c.recordatorio_correo if c else True,
                "ultimo_recordatorio": _iso(c.ultimo_recordatorio) if c else None,
                "personalizada": c is not None}

    async def _primera_vigencia(self) -> date | None:
        f = (await self.db.execute(select(func.min(RatActividadVersion.fecha)).where(
            RatActividadVersion.empresa_id == self.empresa_id))).scalar()
        return _hoy_chile(f) if f else None

    async def _periodicidad(self, ultima: RatRevision | None, cfg: dict) -> dict:
        est = R.periodicidad(_hoy_chile(), _hoy_chile(ultima.fecha_revision) if ultima else None,
                             await self._primera_vigencia(), cfg["plazo_meses"], cfg["aviso_dias"])
        return {**est, **cfg, "ultima_revision": _iso(ultima.fecha_revision) if ultima else None}

    def _vista_revision(self, r: RatRevision, contar: dict | None = None) -> dict:
        return {
            "id": r.id, "numero": r.numero, "estado": r.estado, "fecha_inicio": _iso(r.fecha_inicio),
            "fecha_revision": _iso(r.fecha_revision), "revisor": r.revisor_nombre, "cargo": r.revisor_cargo,
            "conclusion": r.conclusion, "version_rat": r.version_rat, "huella": r.huella,
            "huella_legible": I.huella_legible(r.huella) if r.huella else None, "version_mapa": r.version_mapa,
            "resumen": contar if contar is not None else {k: v for k, v in (r.resumen or {}).items() if k != "versiones"},
            "informe_id": r.informe_id,
        }

    async def estado(self) -> dict:
        """Todo lo que muestra el modo de revisión: lista consolidada, observaciones, requisitos y periodicidad."""
        ctx = await self._contexto()
        en_curso = await self._en_curso()
        revisadas = await self._revisadas()
        ultima = revisadas[0] if revisadas else None
        observaciones = await self._observaciones(en_curso.id) if en_curso else []
        abiertas_previas = [o for o in await self._observaciones() if o.estado == ABIERTA
                            and (en_curso is None or o.revision_id != en_curso.id)]
        consolidados = R.consolidar(ctx.objetos, en_curso.verificaciones if en_curso else {})
        obs_vistas = [observacion_vista(o, ctx.por_clave) for o in [*observaciones, *abiertas_previas]]
        resumen = R.resumen(consolidados, obs_vistas)
        abiertas = sum(1 for o in obs_vistas if o["estado"] == ABIERTA)
        req = R.requisitos(consolidados, abiertas, len(ctx.inf.actividades))
        cfg = self._config_vista(await self._config())
        marca = ctx.inf.revision
        return {
            "revision": self._vista_revision(en_curso, resumen) if en_curso else None,
            "registro": {
                "huella": ctx.inf.huella, "huella_legible": I.huella_legible(ctx.inf.huella),
                "borrador": ctx.inf.borrador, "motivos_borrador": list(ctx.inf.motivos_borrador),
                "actividades": len(ctx.inf.actividades), "version_mapa": ctx.version_mapa,
                "version_siguiente": await self._version_para(ctx.inf.huella),
                # ¿La versión actual ya tiene constancia? ¿Cambió desde la última revisada?
                "revisada": I.marca_dict(marca),
                "cambio_desde_ultima": bool(ultima and ultima.huella != ctx.inf.huella),
            },
            "objetos": _sin_preguntas(consolidados),
            "observaciones": obs_vistas,
            "resumen": resumen,
            "requisitos": req,
            "criterios": catalogo_criterios(),
            "periodicidad": await self._periodicidad(ultima, cfg),
            "revisadas": [self._vista_revision(r) for r in revisadas],
            "ultima": self._vista_revision(ultima) if ultima else None,
            "versiones": await self._versiones_disponibles(),
            "limites": {"paquetes_dia": settings.REVISION_RAT_PAQUETES_DIA,
                        "correos_dia": settings.REVISION_RAT_CORREOS_DIA,
                        "paquete_correo_mb": settings.REVISION_RAT_PAQUETE_CORREO_MB,
                        "paquete_verificar_mb": settings.REVISION_RAT_PAQUETE_VERIFICAR_MB},
            "correo_habilitado": settings.CORREO_MODO != "desactivado",
            "revisor_sugerido": self.nombre_usuario,
        }

    async def _version_para(self, huella: str) -> int:
        ultima = (await self.db.execute(select(RatInforme).where(RatInforme.empresa_id == self.empresa_id)
                                        .order_by(RatInforme.id.desc()).limit(1))).scalar_one_or_none()
        if ultima is None:
            return 1
        return ultima.version_rat + (0 if ultima.huella == huella else 1)

    # ================================================================ rechazos (quedan en el audit_log)
    async def _rechazar(self, motivo: str, error: RevisionError, **detalle) -> RevisionError:
        await self.db.rollback()
        self.bitacora.registrar(accion=Accion.REVISION_RAT_MARCA_RECHAZADA, entidad="rat_revision", entidad_id=None,
                                actor=self.actor, resultado=RESULTADO_RECHAZADO, detalle={"motivo": motivo, **detalle})
        await self.db.commit()
        return error

    # ================================================================ iniciar (C1)
    async def _iniciar(self) -> RatRevision:
        # Serializa con la empresa: una sola revisión en curso (además del índice único parcial)
        await self.db.execute(select(Empresa.id).where(Empresa.id == self.empresa_id).with_for_update())
        actual = await self._en_curso(bloquear=True)
        if actual is not None:
            return actual
        numero = ((await self.db.execute(select(func.max(RatRevision.numero)).where(
            RatRevision.empresa_id == self.empresa_id))).scalar() or 0) + 1
        r = RatRevision(empresa_id=self.empresa_id, numero=numero, estado=EN_CURSO, fecha_inicio=_ahora(),
                        iniciada_por_id=self.usuario_id, verificaciones={}, resumen={}, lista=[])
        self.db.add(r)
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
        numero = ((await self.db.execute(select(func.max(RatObservacion.numero)).where(
            RatObservacion.empresa_id == self.empresa_id))).scalar() or 0) + 1
        o = RatObservacion(empresa_id=self.empresa_id, revision_id=r.id, numero=numero, objeto_tipo=tipo,
                           objeto_id=obj_id, objeto_clave=clave, objeto_nombre=nombre, criterio=criterio or None,
                           prioridad=prioridad, texto=texto, estado=ABIERTA, fecha_apertura=_ahora(),
                           abierta_por_id=self.usuario_id, huella_apertura=huella, reaperturas=0)
        self.db.add(o)
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
        o = (await self.db.execute(select(RatObservacion).where(
            RatObservacion.id == observacion_id, RatObservacion.empresa_id == self.empresa_id).with_for_update())
        ).scalar_one_or_none()
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
        rev = await self.db.get(RatRevision, o.revision_id)
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
        await self.db.execute(select(Empresa.id).where(Empresa.id == self.empresa_id).with_for_update())
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
            fila = await self.db.get(RatRevision, revision_id)
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

    # ================================================================ historial de revisiones
    async def detalle(self, revision_id: int) -> dict:
        r = await self._revision(revision_id)
        if r.estado == EN_CURSO:
            return await self.estado()
        obs = await self._observaciones(r.id)
        return {"revision": self._vista_revision(r), "objetos": r.lista or [],
                "observaciones": [observacion_vista(o) for o in obs], "criterios": catalogo_criterios()}

    # ================================================================ diferencias entre versiones (C4)
    async def _versiones_disponibles(self) -> list[dict]:
        filas = list((await self.db.execute(select(RatInforme).where(RatInforme.empresa_id == self.empresa_id)
                                            .order_by(RatInforme.id.desc()).limit(200))).scalars().all())
        revisadas = {(r.version_rat, r.huella): r for r in (await self._revisadas(200))}
        por_version: dict[int, dict] = {}
        for f in filas:                                     # la emisión más reciente de cada versión
            if f.version_rat in por_version:
                continue
            rv = revisadas.get((f.version_rat, f.huella))
            por_version[f.version_rat] = {
                "version": f.version_rat, "fecha": _iso(f.fecha), "borrador": f.borrador, "codigo": f.codigo,
                "actividades": f.actividades, "revisada": bool(rv),
                "revision": {"numero": rv.numero, "fecha": _iso(rv.fecha_revision)} if rv else None}
        for (v, _h), rv in revisadas.items():                # una revisada sin emisión (si el informe no se emitió)
            por_version.setdefault(v, {"version": v, "fecha": _iso(rv.fecha_revision), "borrador": False,
                                       "codigo": None, "actividades": len((rv.resumen or {}).get("versiones") or []),
                                       "revisada": True, "revision": {"numero": rv.numero,
                                                                      "fecha": _iso(rv.fecha_revision)}})
        return [por_version[k] for k in sorted(por_version, reverse=True)]

    async def _entradas_de(self, lista: list[dict]) -> dict[int, R.EntradaComparacion]:
        """[{id, version, huella}] → entradas legibles (desde la versión inmutable de cada actividad)."""
        ids = [x["id"] for x in lista if x.get("version")]
        filas: dict[tuple[int, int], RatActividadVersion] = {}
        if ids:
            for v in (await self.db.execute(select(RatActividadVersion).where(
                    RatActividadVersion.actividad_id.in_(ids),
                    RatActividadVersion.empresa_id == self.empresa_id))).scalars():
                filas[(v.actividad_id, v.numero)] = v
        nombres = dict((await self.db.execute(select(RatActividad.id, RatActividad.nombre).where(
            RatActividad.empresa_id == self.empresa_id))).all())
        salida: dict[int, R.EntradaComparacion] = {}
        fuentes = []
        for x in lista:
            v = filas.get((x["id"], x.get("version"))) if x.get("version") else None
            if v is None:
                salida[x["id"]] = R.EntradaComparacion(x["id"], nombres.get(x["id"], f"Actividad {x['id']}"), None,
                                                       x.get("huella"))
                continue
            fuentes.append(I.FuenteActividad(
                id=x["id"], nombre=nombres.get(x["id"], ""), estado="vigente", version_vigente=v.numero,
                fecha_vigencia=v.fecha, fecha_actualizacion=v.fecha, instantanea=v.contenido, huella_version=v.huella,
                fecha_version=v.fecha))
        if fuentes:
            for a in I.armar(fuentes, datetime.now(timezone.utc), self.razon_social).actividades:
                salida[a.id] = self._entrada(a)
        return salida

    @staticmethod
    def _entrada(a: I.ActividadInforme) -> R.EntradaComparacion:
        return R.EntradaComparacion(a.id, a.nombre, a.version, a.huella_version,
                                    {c: (t, txt) for c, t, txt in I.campos_legibles(a)})

    async def _lista_version(self, version: int) -> list[dict] | None:
        rv = (await self.db.execute(select(RatRevision).where(
            RatRevision.empresa_id == self.empresa_id, RatRevision.estado == REVISADA,
            RatRevision.version_rat == version).order_by(RatRevision.id.desc()).limit(1))).scalar_one_or_none()
        if rv is not None and (rv.resumen or {}).get("versiones"):
            return list(rv.resumen["versiones"])
        f = (await self.db.execute(select(RatInforme).where(
            RatInforme.empresa_id == self.empresa_id, RatInforme.version_rat == version)
            .order_by(RatInforme.id.desc()).limit(1))).scalar_one_or_none()
        return list(f.versiones or []) if f is not None else None

    async def diferencias(self, desde: int | None, hasta: int | None) -> dict:
        """Compara dos versiones del registro (hasta=None: el registro actual). Sin `desde`: la última revisada."""
        if desde is None:
            ultima = (await self._revisadas(1))
            if not ultima:
                raise RevisionError(404, "SIN_VERSION_ANTERIOR", "Aún no hay una versión revisada con qué comparar: elige "
                                                                 "una versión del registro.")
            desde = ultima[0].version_rat
        antes_lista = await self._lista_version(desde)
        if antes_lista is None:
            raise RevisionError(404, "VERSION_NO_ENCONTRADA", f"No encontramos la versión {desde} del registro.")
        antes = await self._entradas_de(antes_lista)
        if hasta is None:
            inf = await self.informes.armar()
            despues = {a.id: self._entrada(a) for a in inf.actividades}
            etiqueta = "el registro actual"
        else:
            lista = await self._lista_version(hasta)
            if lista is None:
                raise RevisionError(404, "VERSION_NO_ENCONTRADA", f"No encontramos la versión {hasta} del registro.")
            despues = await self._entradas_de(lista)
            etiqueta = f"la versión {hasta}"
        return {"desde": desde, "hasta": hasta, "etiqueta": f"De la versión {desde} a {etiqueta}",
                **R.comparar(antes, despues)}

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
        anterior = (await self.db.execute(select(RatRevision).where(
            RatRevision.empresa_id == self.empresa_id, RatRevision.estado == REVISADA,
            RatRevision.numero < r.numero).order_by(RatRevision.numero.desc()).limit(1))).scalar_one_or_none()
        diferencias, desde = None, None
        if anterior is not None and (anterior.resumen or {}).get("versiones"):
            antes = await self._entradas_de(anterior.resumen["versiones"])
            if r.estado == REVISADA:
                despues = await self._entradas_de(resumen.get("versiones") or [])
            else:
                despues = {a.id: self._entrada(a) for a in (await self.informes.armar()).actividades}
            diferencias = R.comparar(antes, despues)
            desde = f"la revisión N.º {anterior.numero} (versión {anterior.version_rat})"
        informe = await self.db.get(RatInforme, r.informe_id) if r.informe_id else None
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

        from app.application.rat.pdf_revision import generar_pdf_revision
        try:
            return await asyncio.to_thread(generar_pdf_revision, d)
        except PdfNoDisponibleError as e:
            raise RevisionError(503, "PDF_NO_DISPONIBLE", str(e))

    async def constancia(self, revision_id: int) -> tuple[bytes, str]:
        from app.application.rat.pdf_revision import nombre_archivo

        r = await self._revision(revision_id)
        d = await self._datos_constancia(r)
        contenido = await self._pdf(d)
        self.bitacora.registrar(accion=Accion.REVISION_RAT_CONSTANCIA_DESCARGADA, entidad="rat_revision",
                                entidad_id=r.id, actor=self.actor, detalle={"numero": r.numero, "estado": r.estado})
        await self.db.commit()
        return contenido, nombre_archivo(d)

    # ================================================================ paquete de evidencia (C4)
    async def _auditoria(self, hasta: datetime | None) -> list[dict]:
        cond_cliente = (BitacoraAuditoria.actor_rol == self.actor.rol) & (BitacoraAuditoria.actor_id == self.actor.id) \
            & or_(*[BitacoraAuditoria.accion.like(f"{p}%") for p in _PREFIJOS_HISTORIAL])
        cond_sistema = (BitacoraAuditoria.entidad == "rat_revision_config") & \
            (BitacoraAuditoria.entidad_id == self.empresa_id)
        q = select(BitacoraAuditoria).where(or_(cond_cliente, cond_sistema))
        if hasta is not None:
            q = q.where(BitacoraAuditoria.fecha <= hasta)
        filas = list((await self.db.execute(q.order_by(BitacoraAuditoria.id.desc())
                                            .limit(MAX_HISTORIAL_AUDITORIA))).scalars().all())
        return [{"id": f.id, "fecha": f.fecha.isoformat(timespec="microseconds") if f.fecha else None,
                 "actor_rol": f.actor_rol, "accion": f.accion, "entidad": f.entidad, "entidad_id": f.entidad_id,
                 "resultado": f.resultado, "detalle": f.detalle, "hash_anterior": f.hash_anterior, "hash": f.hash}
                for f in reversed(filas)]

    async def _versiones_paquete(self, lista: list[dict]) -> list[dict]:
        ids = [x["id"] for x in lista if x.get("version")]
        if not ids:
            return []
        por = {(v.actividad_id, v.numero): v for v in (await self.db.execute(select(RatActividadVersion).where(
            RatActividadVersion.actividad_id.in_(ids), RatActividadVersion.empresa_id == self.empresa_id))).scalars()}
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
        hoy = (await self.db.execute(select(func.count()).select_from(RatPaqueteEvidencia).where(
            RatPaqueteEvidencia.empresa_id == self.empresa_id,
            RatPaqueteEvidencia.fecha >= inicio.astimezone(timezone.utc).replace(tzinfo=None)))).scalar() or 0
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
        emision = await self.db.get(RatInforme, r.informe_id) if r.informe_id else None
        if emision is None and d.huella:
            emision = (await self.db.execute(select(RatInforme).where(
                RatInforme.empresa_id == self.empresa_id, RatInforme.huella == d.huella)
                .order_by(RatInforme.id.desc()).limit(1))).scalar_one_or_none()
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
                     for f in (await self.db.execute(select(RatInforme).where(
                         RatInforme.empresa_id == self.empresa_id, RatInforme.huella == d.huella)
                         .order_by(RatInforme.id))).scalars()] if d.huella else []

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
        fila = (await self.db.execute(select(RatPaqueteEvidencia).where(
            RatPaqueteEvidencia.sha256 == sha, RatPaqueteEvidencia.empresa_id == self.empresa_id))).scalar_one_or_none()
        por_codigo = None
        if fila is None and resultado.manifiesto and resultado.manifiesto.get("codigo"):
            leido = P.leer_codigo(str(resultado.manifiesto["codigo"]))
            if leido is not None:
                por_codigo = await self.db.get(RatPaqueteEvidencia, leido[1])
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
        revision = await self.db.get(RatRevision, ref.revision_id) if ref is not None else None
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
            from app.application.rat.pdf_revision import nombre_archivo

            d = await self._datos_constancia(r)
            adjuntos = [correo.Adjunto(nombre_archivo(d), await self._pdf(d), "application/pdf")]
            codigo_paquete = None
            if con_paquete:
                zip_, nombre, codigo_paquete, _ = await self.paquete(revision_id)
                if len(zip_) > settings.REVISION_RAT_PAQUETE_CORREO_MB * 1024 * 1024:
                    raise RevisionError(413, "PAQUETE_GRANDE", "El paquete es muy grande para el correo: descárgalo y "
                                                               "compártelo por otro medio.")
                adjuntos.append(correo.Adjunto(nombre, zip_, "application/zip"))
            texto, html = CR.cuerpo_constancia(d, con_paquete, codigo_paquete)
            modo = await correo.enviar(destino, CR.asunto_constancia(d), texto, html, adjuntos)
        except (correo.CorreoFallidoError, correo.CorreoNoDisponibleError) as e:
            await self.limitador.devolver(clave)
            raise RevisionError(502 if isinstance(e, correo.CorreoFallidoError) else 503, "CORREO_FALLIDO",
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

    # ================================================================ revisión periódica (C5)
    async def configurar(self, plazo_meses: int, aviso_dias: int, recordatorio_correo: bool) -> dict:
        if not 1 <= int(plazo_meses) <= 36:
            raise RevisionError(422, "PLAZO_INVALIDO", "El plazo entre revisiones va de 1 a 36 meses.", campo="plazo_meses")
        if not 0 <= int(aviso_dias) <= 90:
            raise RevisionError(422, "AVISO_INVALIDO", "El aviso previo va de 0 a 90 días.", campo="aviso_dias")
        c = await self._config()
        antes = self._config_vista(c)
        if c is None:
            c = RatRevisionConfig(empresa_id=self.empresa_id, fecha_actualizacion=_ahora())
            self.db.add(c)
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


# ====================================================================== resumen para otras pantallas
async def resumen_periodicidad(db: AsyncSession, empresa_id: int) -> dict:
    """Estado de la revisión periódica (consultas livianas): lo muestra la lista del registro (criterio 5)."""
    ultima = (await db.execute(select(RatRevision).where(
        RatRevision.empresa_id == empresa_id, RatRevision.estado == REVISADA)
        .order_by(RatRevision.fecha_revision.desc()).limit(1))).scalar_one_or_none()
    en_curso = (await db.execute(select(RatRevision.numero).where(
        RatRevision.empresa_id == empresa_id, RatRevision.estado == EN_CURSO))).scalar_one_or_none()
    primera = (await db.execute(select(func.min(RatActividadVersion.fecha)).where(
        RatActividadVersion.empresa_id == empresa_id))).scalar()
    cfg = await db.get(RatRevisionConfig, empresa_id)
    plazo = cfg.plazo_meses if cfg else settings.REVISION_RAT_PLAZO_MESES
    aviso = cfg.aviso_dias if cfg else settings.REVISION_RAT_AVISO_DIAS
    est = R.periodicidad(_hoy_chile(), _hoy_chile(ultima.fecha_revision) if ultima else None,
                         _hoy_chile(primera) if primera else None, plazo, aviso)
    return {**est, "plazo_meses": plazo, "en_curso": en_curso,
            "ultima": {"fecha": _iso(ultima.fecha_revision), "version_rat": ultima.version_rat,
                       "numero": ultima.numero} if ultima else None}


# ====================================================================== recordatorio diario (worker)
async def enviar_recordatorios(db: AsyncSession, ahora: datetime | None = None) -> dict:
    """
    C5: para cada empresa con contrato vigente y registro con versiones vigentes, si la revisión periódica vence
    pronto o está vencida, envía UN recordatorio por etapa (y lo repite cada REVISION_RAT_REPETIR_DIAS mientras
    siga vencida). Queda en el audit_log como acción del sistema. Un fallo en una empresa no frena a las demás.
    """
    from app.domain.models.usuario_definitivo import UsuarioDefinitivo

    ahora = ahora or datetime.now(timezone.utc)
    hoy = ahora.astimezone(ZONA).date()
    if settings.CORREO_MODO == "desactivado":
        return {"revisadas": 0, "enviados": 0, "motivo": "correo_desactivado"}
    primeras = dict((await db.execute(select(RatActividadVersion.empresa_id, func.min(RatActividadVersion.fecha))
                                      .group_by(RatActividadVersion.empresa_id))).all())
    ultimas = dict((await db.execute(select(RatRevision.empresa_id, func.max(RatRevision.fecha_revision))
                                     .where(RatRevision.estado == REVISADA).group_by(RatRevision.empresa_id))).all())
    enviados, fallidos, revisadas = 0, 0, 0
    for empresa_id in sorted(primeras):
        empresa = await db.get(Empresa, empresa_id)
        if empresa is None or not empresa.contrato_vigente(hoy):
            continue
        usuario = (await db.execute(select(UsuarioDefinitivo).where(
            UsuarioDefinitivo.empresa_id == empresa_id))).scalar_one_or_none()
        if usuario is None or not usuario.activo:
            continue
        revisadas += 1
        cfg = await db.get(RatRevisionConfig, empresa_id)
        plazo = cfg.plazo_meses if cfg else settings.REVISION_RAT_PLAZO_MESES
        aviso = cfg.aviso_dias if cfg else settings.REVISION_RAT_AVISO_DIAS
        if cfg is not None and not cfg.recordatorio_correo:
            continue
        ultima = ultimas.get(empresa_id)
        est = R.periodicidad(hoy, _hoy_chile(ultima) if ultima else None, _hoy_chile(primeras[empresa_id]), plazo, aviso)
        etapa = R.toca_recordar(est, _hoy_chile(cfg.ultimo_recordatorio) if cfg and cfg.ultimo_recordatorio else None,
                                cfg.etapa_recordatorio if cfg else None, hoy, settings.REVISION_RAT_REPETIR_DIAS)
        if etapa is None:
            continue
        texto, html = CR.cuerpo_recordatorio(empresa.razon_social, est, plazo, _fecha_txt(ultima),
                                             settings.REVISION_RAT_URL)
        try:
            modo = await correo.enviar(usuario.email, CR.asunto_recordatorio(est["estado"], empresa.razon_social),
                                       texto, html, [])
        except (correo.CorreoFallidoError, correo.CorreoNoDisponibleError, ValueError) as e:
            fallidos += 1
            logger.warning("[revision_rat] recordatorio fallido empresa %s: %s", empresa_id, type(e).__name__)
            continue
        if cfg is None:
            cfg = RatRevisionConfig(empresa_id=empresa_id, plazo_meses=plazo, aviso_dias=aviso, recordatorio_correo=True,
                                    fecha_actualizacion=_ahora())
            db.add(cfg)
        # Con la fecha de esta corrida (no la del reloj): así la repetición cada N días se cuenta bien
        cfg.ultimo_recordatorio = ahora.astimezone(timezone.utc).replace(tzinfo=None)
        cfg.etapa_recordatorio = etapa
        BitacoraRepository(db).registrar(
            accion=Accion.REVISION_RAT_RECORDATORIO, entidad="rat_revision_config", entidad_id=empresa_id,
            actor_rol=ROL_SISTEMA, detalle={"estado": est["estado"], "vence": est["vence"], "dias": est["dias"],
                                            "plazo_meses": plazo, "modo": modo})
        await db.commit()
        enviados += 1
    return {"revisadas": revisadas, "enviados": enviados, "fallidos": fallidos}
