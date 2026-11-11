"""
HU-34 · Mapa de datos personales del cliente (base del RAT y del RoPA).

Como Usuario Definitivo (cliente), quiero mapear los sistemas, bases de datos y flujos donde mi
empresa trata datos personales, para saber qué datos tengo, de quién, dónde están y con quién los
comparto, y usarlo como base del RAT y del RoPA.

  C1  Sistemas y bases de datos (nombre, tipo, proveedor, país de alojamiento y responsable
      interno), terceros y los flujos entre ellos; las transferencias internacionales se
      calculan con el país de cada extremo (app/domain/mapa_datos/analisis.py).
  C2  Cada elemento y flujo lleva categorías de datos (sensibles marcadas) y de titulares (con
      NNA) del catálogo común con el RAT (app/domain/catalogo_tratamiento.py).
  C3  La vista navegable y sus filtros viven en el panel; aquí se entregan el mapa completo, sus
      hallazgos y el informe PDF con los mismos filtros (además de su envío por correo).
  C4  Se inicia desde una plantilla por rubro (app/application/mapa_datos/plantillas.py) o desde
      las respuestas de la evaluación (app/application/mapa_datos/sugerencias.py).
  C5  Cada cambio crea una versión con la instantánea completa (mapa_datos_version, inalterable)
      y queda en el audit_log (HU-09) en la MISMA transacción. Solo con contrato vigente (la ruta
      usa empresa_con_servicio, HU-30).

Concurrencia: toda edición manda la versión que vio el usuario. Si otra pestaña guardó antes,
responde 409 MAPA_DESACTUALIZADO (nada se pisa). La fila del mapa se bloquea (SELECT … FOR
UPDATE) mientras se aplica el cambio.

Nota: los datos de la empresa y del usuario se copian a variables simples al construir el caso
de uso, porque un rollback expira los objetos de la sesión y en modo asíncrono no se pueden
recargar de forma implícita.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.mapa_datos import plantillas as mod_plantillas
from app.application.mapa_datos import sugerencias as mod_sugerencias
from app.core.config import settings
from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos import analisis, versiones
from app.domain.mapa_datos.modelo import (
    CAMPOS_ELEMENTO, CAMPOS_FLUJO, Elemento, ErrorValidacion, Flujo, normalizar_elemento, normalizar_flujo,
)
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.mapa_datos import MapaDatos, MapaDatosVersion, MapaElemento, MapaFlujo
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

MAX_CAMBIOS_GUARDADOS = 500        # diferencias que se guardan por versión (el resto se cuenta)
TAMANO_PAGINA_VERSIONES = 30


class MapaDatosError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def elemento_de_fila(r: MapaElemento) -> Elemento:
    return Elemento(
        id=r.id, tipo=r.tipo, nombre=r.nombre, subtipo=r.subtipo, descripcion=r.descripcion, proveedor=r.proveedor,
        pais=r.pais, responsable=r.responsable, categorias_datos=list(r.categorias_datos or []),
        categorias_titulares=list(r.categorias_titulares or []), nna_declarado=bool(r.nna_declarado),
        rol_tercero=r.rol_tercero, contrato_firmado=r.contrato_firmado, origen=r.origen, clave=r.clave,
        pendiente_revision=bool(r.pendiente_revision),
    )


def flujo_de_fila(r: MapaFlujo) -> Flujo:
    return Flujo(
        id=r.id, origen_id=r.origen_id, destino_id=r.destino_id, finalidad=r.finalidad,
        categorias_datos=list(r.categorias_datos or []), categorias_titulares=list(r.categorias_titulares or []),
        nna_declarado=bool(r.nna_declarado), frecuencia=r.frecuencia, medio=r.medio, cifrado=r.cifrado,
        garantia=r.garantia, origen=r.origen, clave=r.clave, pendiente_revision=bool(r.pendiente_revision),
    )


class MapaDatosCasos:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente, limitador=None):
        self.db = db
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.razon_social: str = cliente.empresa.razon_social
        self.rubro_id: int | None = cliente.empresa.rubro_id
        self.usuario_id: int = cliente.usuario.id
        self.email_usuario: str = cliente.usuario.email
        self.limitador = limitador
        self.bitacora = BitacoraRepository(db)

    # ================================================================ lectura
    async def _mapa(self, bloquear: bool = False) -> MapaDatos | None:
        q = select(MapaDatos).where(MapaDatos.empresa_id == self.empresa_id)
        if bloquear:
            q = q.with_for_update()
        return (await self.db.execute(q)).scalar_one_or_none()

    async def _filas(self, mapa_id: int) -> tuple[list[MapaElemento], list[MapaFlujo]]:
        el = (await self.db.execute(
            select(MapaElemento).where(MapaElemento.mapa_id == mapa_id).order_by(MapaElemento.id))).scalars().all()
        fl = (await self.db.execute(
            select(MapaFlujo).where(MapaFlujo.mapa_id == mapa_id).order_by(MapaFlujo.id))).scalars().all()
        return list(el), list(fl)

    async def rubro(self) -> str | None:
        from app.domain.models.rubro import Rubro

        if self.rubro_id is None:
            return None
        return (await self.db.execute(select(Rubro.nombre_rubro).where(Rubro.id == self.rubro_id))).scalar_one_or_none()

    def _armar_vista(self, mapa: MapaDatos | None, el_filas: list[MapaElemento], fl_filas: list[MapaFlujo]) -> dict:
        els = [elemento_de_fila(r) for r in el_filas]
        fls = [flujo_de_fila(r) for r in fl_filas]
        por_id = {e.id: e for e in els}
        fechas_e = {r.id: (r.fecha_creacion, r.fecha_actualizacion) for r in el_filas}
        fechas_f = {r.id: (r.fecha_creacion, r.fecha_actualizacion) for r in fl_filas}
        hall = analisis.hallazgos(els, fls)
        return {
            "mapa": {
                "version": mapa.version if mapa else 0,
                "fecha_actualizacion": _iso(mapa.fecha_actualizacion) if mapa and mapa.version else None,
                "iniciado": bool(els),
                "plantilla_inicial": mapa.plantilla_inicial if mapa else None,
            },
            "elementos": [
                {**e.como_dict(), "incluye_nna": e.incluye_nna,
                 "fecha_creacion": _iso(fechas_e[e.id][0]), "fecha_actualizacion": _iso(fechas_e[e.id][1]),
                 "derivados": analisis.derivados_elemento(e, fls)}
                for e in els
            ],
            "flujos": [
                {**f.como_dict(), "incluye_nna": f.incluye_nna,
                 "fecha_creacion": _iso(fechas_f[f.id][0]), "fecha_actualizacion": _iso(fechas_f[f.id][1]),
                 "derivados": analisis.derivados_flujo(f, por_id).como_dict()}
                for f in fls
            ],
            "resumen": analisis.resumen(els, fls),
            "hallazgos": [h.como_dict() for h in hall],
            "conteo_hallazgos": analisis.contar_hallazgos(hall),
            "completitud": analisis.completitud(els, fls),
            "limites": {"max_elementos": settings.MAPA_MAX_ELEMENTOS, "max_flujos": settings.MAPA_MAX_FLUJOS},
            "catalogo_version": cat.VERSION_CATALOGO,
        }

    async def vista(self) -> dict:
        mapa = await self._mapa()
        el, fl = await self._filas(mapa.id) if mapa else ([], [])
        return self._armar_vista(mapa, el, fl)

    async def dominio(self) -> tuple[MapaDatos | None, list[Elemento], list[Flujo]]:
        mapa = await self._mapa()
        el, fl = await self._filas(mapa.id) if mapa else ([], [])
        return mapa, [elemento_de_fila(r) for r in el], [flujo_de_fila(r) for r in fl]

    # ================================================================ ciclo de un cambio
    def _invalido(self, e: ErrorValidacion) -> MapaDatosError:
        return MapaDatosError(422, "DATOS_INVALIDOS", e.mensaje, campo=e.campo)

    async def _rechazar(self, codigo: str, version_actual: int, mapa_id: int | None) -> None:
        """Deja el intento rechazado en el audit_log (en su propia transacción) antes de responder."""
        await self.db.rollback()
        self.bitacora.registrar(
            accion=Accion.MAPA_CAMBIO_RECHAZADO, entidad="mapa_datos", entidad_id=mapa_id, actor=self.actor,
            resultado=RESULTADO_RECHAZADO, detalle={"motivo": codigo, "version_actual": version_actual})
        await self.db.commit()

    async def _iniciar(self, version: int) -> tuple[MapaDatos, list[MapaElemento], list[MapaFlujo], dict]:
        """Bloquea el mapa, verifica la versión y devuelve el estado de partida (instantánea)."""
        mapa = await self._mapa(bloquear=True)
        actual = mapa.version if mapa else 0
        if version != actual:
            await self._rechazar("version_desactualizada", actual, mapa.id if mapa else None)
            raise MapaDatosError(
                409, "MAPA_DESACTUALIZADO",
                "El mapa cambió desde que lo abriste (quizás en otra pestaña). Actualiza la página para ver la "
                "última versión y vuelve a intentarlo.", version_actual=actual)
        if mapa is None:
            ahora = _ahora()
            mapa = MapaDatos(empresa_id=self.empresa_id, version=0, sugerencias_descartadas=[],
                             usuario_definitivo_id=self.usuario_id, fecha_creacion=ahora, fecha_actualizacion=ahora)
            self.db.add(mapa)
            try:
                await self.db.flush()
            except IntegrityError:            # otra petición creó el mapa al mismo tiempo
                await self.db.rollback()
                raise MapaDatosError(409, "MAPA_DESACTUALIZADO",
                                     "El mapa se acaba de crear en otra pestaña. Actualiza la página.", version_actual=1)
        el, fl = await self._filas(mapa.id)
        antes = versiones.instantanea([elemento_de_fila(r) for r in el], [flujo_de_fila(r) for r in fl])
        return mapa, el, fl, antes

    async def _guardar(self, mapa: MapaDatos, accion_version: str, accion_audit: str, antes: dict,
                       detalle: dict, resumen: str | None = None) -> dict:
        await self.db.flush()
        el, fl = await self._filas(mapa.id)
        despues = versiones.instantanea([elemento_de_fila(r) for r in el], [flujo_de_fila(r) for r in fl])
        cambios = versiones.diferencias(antes, despues)
        if not cambios:
            await self.db.rollback()
            datos = await self.vista()
            return {**datos, "cambio": None}
        mapa.version += 1
        mapa.fecha_actualizacion = _ahora()
        mapa.usuario_definitivo_id = self.usuario_id
        texto = (resumen or versiones.describir(cambios))[:300]
        self.db.add(MapaDatosVersion(
            mapa_id=mapa.id, empresa_id=self.empresa_id, numero=mapa.version, fecha=mapa.fecha_actualizacion,
            usuario_definitivo_id=self.usuario_id, accion=accion_version, resumen=texto,
            cambios=cambios[:MAX_CAMBIOS_GUARDADOS], contenido=despues, huella=versiones.huella(despues),
            elementos=len(el), flujos=len(fl),
        ))
        self.bitacora.registrar(
            accion=accion_audit, entidad="mapa_datos", entidad_id=mapa.id, actor=self.actor,
            detalle={"version": mapa.version, "cambios": len(cambios), "elementos_total": len(el),
                     "flujos_total": len(fl), **detalle})
        await self.db.commit()
        return {**self._armar_vista(mapa, el, fl), "cambio": {"version": mapa.version, "resumen": texto}}

    # ================================================================ elementos (C1, C2)
    @staticmethod
    def _buscar(filas, id_: int, codigo: str, mensaje: str):
        fila = next((r for r in filas if r.id == id_), None)
        if fila is None:                  # lo de otra empresa no existe (404, no 403)
            raise MapaDatosError(404, codigo, mensaje)
        return fila

    @staticmethod
    def _nombre_libre(filas: list[MapaElemento], nombre: str, tipo: str, excepto: int | None = None) -> None:
        clave = nombre.casefold()
        if any(r.nombre.casefold() == clave and r.tipo == tipo and r.id != excepto for r in filas):
            raise MapaDatosError(409, "NOMBRE_DUPLICADO",
                                 f"Ya hay un elemento de este tipo llamado «{nombre}». Usa otro nombre o edita el existente.",
                                 campo="nombre")

    def _nuevo_elemento(self, mapa_id: int, campos: dict, **extra) -> MapaElemento:
        ahora = _ahora()
        base = {"subtipo": None, "descripcion": None, "proveedor": None, "pais": None, "responsable": None,
                "categorias_datos": [], "categorias_titulares": [], "nna_declarado": False, "rol_tercero": None,
                "contrato_firmado": None, "pendiente_revision": False, "origen": "manual", "clave": None}
        base.update(campos)
        base.update(extra)
        if base["tipo"] != "tercero":
            base["rol_tercero"] = base["contrato_firmado"] = None
        return MapaElemento(mapa_id=mapa_id, fecha_creacion=ahora, fecha_actualizacion=ahora, **base)

    async def crear_elemento(self, datos: dict, version: int) -> dict:
        try:
            campos = normalizar_elemento(datos)
        except ErrorValidacion as e:
            raise self._invalido(e)
        mapa, el, _fl, antes = await self._iniciar(version)
        if len(el) >= settings.MAPA_MAX_ELEMENTOS:
            raise MapaDatosError(422, "LIMITE_ELEMENTOS",
                                 f"El mapa admite hasta {settings.MAPA_MAX_ELEMENTOS} elementos.")
        self._nombre_libre(el, campos["nombre"], campos["tipo"])
        fila = self._nuevo_elemento(mapa.id, campos)
        self.db.add(fila)
        await self.db.flush()
        return await self._guardar(mapa, "elemento_creado", Accion.MAPA_ELEMENTO_CREADO, antes,
                                   {"elemento_id": fila.id, "tipo": fila.tipo})

    async def editar_elemento(self, elemento_id: int, datos: dict, version: int) -> dict:
        mapa, el, _fl, antes = await self._iniciar(version)
        fila = self._buscar(el, elemento_id, "ELEMENTO_NO_ENCONTRADO", "No encontramos ese elemento en tu mapa.")
        try:
            cambios = normalizar_elemento(datos, elemento_de_fila(fila))
        except ErrorValidacion as e:
            raise self._invalido(e)
        if "nombre" in cambios or "tipo" in cambios:
            self._nombre_libre(el, cambios.get("nombre", fila.nombre), cambios.get("tipo", fila.tipo), fila.id)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)
        # Editarlo es revisarlo: lo que venía de una plantilla o sugerencia queda confirmado
        if cambios and "pendiente_revision" not in datos and fila.pendiente_revision:
            fila.pendiente_revision = False
            cambios["pendiente_revision"] = False
        if cambios:
            fila.fecha_actualizacion = _ahora()
        return await self._guardar(mapa, "elemento_editado", Accion.MAPA_ELEMENTO_EDITADO, antes,
                                   {"elemento_id": fila.id, "tipo": fila.tipo, "campos": sorted(cambios)})

    async def eliminar_elemento(self, elemento_id: int, version: int) -> dict:
        mapa, el, fl, antes = await self._iniciar(version)
        fila = self._buscar(el, elemento_id, "ELEMENTO_NO_ENCONTRADO", "No encontramos ese elemento en tu mapa.")
        sus_flujos = [f.id for f in fl if elemento_id in (f.origen_id, f.destino_id)]
        if sus_flujos:
            await self.db.execute(delete(MapaFlujo).where(MapaFlujo.id.in_(sus_flujos))
                                  .execution_options(synchronize_session="fetch"))
        tipo = fila.tipo
        await self.db.delete(fila)
        return await self._guardar(mapa, "elemento_eliminado", Accion.MAPA_ELEMENTO_ELIMINADO, antes,
                                   {"elemento_id": elemento_id, "tipo": tipo, "flujos_eliminados": len(sus_flujos)})

    # ================================================================ flujos (C1, C2)
    @staticmethod
    def _flujo_libre(fl: list[MapaFlujo], origen: int, destino: int, finalidad: str | None, excepto: int | None = None):
        clave = (finalidad or "").casefold()
        if any(f.origen_id == origen and f.destino_id == destino and (f.finalidad or "").casefold() == clave
               and f.id != excepto for f in fl):
            raise MapaDatosError(409, "FLUJO_DUPLICADO",
                                 "Ya existe un flujo entre esos elementos con la misma finalidad. Edita el existente o "
                                 "describe una finalidad distinta.", campo="finalidad")

    async def crear_flujo(self, datos: dict, version: int) -> dict:
        try:
            campos = normalizar_flujo(datos)
        except ErrorValidacion as e:
            raise self._invalido(e)
        mapa, el, fl, antes = await self._iniciar(version)
        if len(fl) >= settings.MAPA_MAX_FLUJOS:
            raise MapaDatosError(422, "LIMITE_FLUJOS", f"El mapa admite hasta {settings.MAPA_MAX_FLUJOS} flujos.")
        ids = {r.id for r in el}
        for campo in ("origen_id", "destino_id"):
            if campos[campo] not in ids:
                raise MapaDatosError(422, "DATOS_INVALIDOS", "El origen o el destino ya no está en el mapa.", campo=campo)
        self._flujo_libre(fl, campos["origen_id"], campos["destino_id"], campos.get("finalidad"))
        ahora = _ahora()
        base = {"finalidad": None, "categorias_datos": [], "categorias_titulares": [], "nna_declarado": False,
                "frecuencia": None, "medio": None, "cifrado": None, "garantia": None, "pendiente_revision": False}
        base.update(campos)
        fila = MapaFlujo(mapa_id=mapa.id, origen="manual", clave=None, fecha_creacion=ahora, fecha_actualizacion=ahora,
                         **base)
        self.db.add(fila)
        await self.db.flush()
        return await self._guardar(mapa, "flujo_creado", Accion.MAPA_FLUJO_CREADO, antes, {"flujo_id": fila.id})

    async def editar_flujo(self, flujo_id: int, datos: dict, version: int) -> dict:
        mapa, el, fl, antes = await self._iniciar(version)
        fila = self._buscar(fl, flujo_id, "FLUJO_NO_ENCONTRADO", "No encontramos ese flujo en tu mapa.")
        try:
            cambios = normalizar_flujo(datos, flujo_de_fila(fila))
        except ErrorValidacion as e:
            raise self._invalido(e)
        ids = {r.id for r in el}
        for campo in ("origen_id", "destino_id"):
            if campo in cambios and cambios[campo] not in ids:
                raise MapaDatosError(422, "DATOS_INVALIDOS", "El origen o el destino ya no está en el mapa.", campo=campo)
        if {"origen_id", "destino_id", "finalidad"} & cambios.keys():
            self._flujo_libre(fl, cambios.get("origen_id", fila.origen_id), cambios.get("destino_id", fila.destino_id),
                              cambios.get("finalidad", fila.finalidad), fila.id)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)
        if cambios and "pendiente_revision" not in datos and fila.pendiente_revision:
            fila.pendiente_revision = False
            cambios["pendiente_revision"] = False
        if cambios:
            fila.fecha_actualizacion = _ahora()
        return await self._guardar(mapa, "flujo_editado", Accion.MAPA_FLUJO_EDITADO, antes,
                                   {"flujo_id": fila.id, "campos": sorted(cambios)})

    async def eliminar_flujo(self, flujo_id: int, version: int) -> dict:
        mapa, _el, fl, antes = await self._iniciar(version)
        fila = self._buscar(fl, flujo_id, "FLUJO_NO_ENCONTRADO", "No encontramos ese flujo en tu mapa.")
        await self.db.delete(fila)
        return await self._guardar(mapa, "flujo_eliminado", Accion.MAPA_FLUJO_ELIMINADO, antes, {"flujo_id": flujo_id})

    async def confirmar_revision(self, version: int, elementos: list[int] | None, flujos: list[int] | None,
                                 todo: bool) -> dict:
        """Marca como revisado lo que venía de una plantilla o una sugerencia."""
        mapa, el, fl, antes = await self._iniciar(version)
        ids_e, ids_f = set(elementos or []), set(flujos or [])
        n_e = n_f = 0
        ahora = _ahora()
        for r in el:
            if r.pendiente_revision and (todo or r.id in ids_e):
                r.pendiente_revision, r.fecha_actualizacion = False, ahora
                n_e += 1
        for r in fl:
            if r.pendiente_revision and (todo or r.id in ids_f):
                r.pendiente_revision, r.fecha_actualizacion = False, ahora
                n_f += 1
        partes = []
        if n_e:
            partes.append(f"{n_e} elemento{'s' if n_e != 1 else ''}")
        if n_f:
            partes.append(f"{n_f} flujo{'s' if n_f != 1 else ''}")
        resumen = f"Se marcaron como revisados {' y '.join(partes)}." if partes else None
        return await self._guardar(mapa, "revision_confirmada", Accion.MAPA_REVISION_CONFIRMADA, antes,
                                   {"elementos_confirmados": n_e, "flujos_confirmados": n_f}, resumen)

    # ================================================================ plantillas (C4)
    async def plantillas(self) -> dict:
        return {"plantillas": mod_plantillas.catalogo_plantillas(await self.rubro()),
                "version": mod_plantillas.VERSION_PLANTILLAS}

    async def aplicar_plantilla(self, codigo: str, version: int) -> dict:
        plantilla = mod_plantillas.PLANTILLAS.get((codigo or "").strip())
        if plantilla is None:
            raise MapaDatosError(422, "PLANTILLA_INVALIDA", "Elige una de las plantillas disponibles.")
        mapa, el, fl, antes = await self._iniciar(version)
        por_clave = {r.clave: r.id for r in el if r.clave}
        por_nombre = {(r.tipo, r.nombre.casefold()): r.id for r in el}
        nuevos: list[MapaElemento] = []
        for ep in plantilla.elementos:
            existente = por_clave.get(ep.clave) or por_nombre.get((ep.tipo, ep.nombre.casefold()))
            if existente:
                por_clave[ep.clave] = existente
                continue
            nuevos.append(self._nuevo_elemento(mapa.id, {
                "tipo": ep.tipo, "subtipo": ep.subtipo, "nombre": ep.nombre, "descripcion": ep.descripcion,
                "pais": ep.pais, "responsable": ep.responsable, "proveedor": ep.proveedor,
                "categorias_datos": list(ep.datos), "categorias_titulares": list(ep.titulares),
                "nna_declarado": ep.nna, "rol_tercero": ep.rol}, origen="plantilla", clave=ep.clave,
                pendiente_revision=True))
        if len(el) + len(nuevos) > settings.MAPA_MAX_ELEMENTOS:
            raise MapaDatosError(422, "LIMITE_ELEMENTOS", f"Con esta plantilla el mapa superaría los "
                                 f"{settings.MAPA_MAX_ELEMENTOS} elementos permitidos.")
        self.db.add_all(nuevos)
        await self.db.flush()
        por_clave.update({r.clave: r.id for r in nuevos})
        claves_flujo = {r.clave for r in fl if r.clave}
        pares = {(r.origen_id, r.destino_id, (r.finalidad or "").casefold()) for r in fl}
        ahora = _ahora()
        flujos_nuevos = []
        for fp in plantilla.flujos:
            o, d = por_clave.get(fp.origen), por_clave.get(fp.destino)
            clave = f"{fp.origen}>{fp.destino}"
            if not o or not d or clave in claves_flujo or (o, d, fp.finalidad.casefold()) in pares:
                continue
            flujos_nuevos.append(MapaFlujo(
                mapa_id=mapa.id, origen_id=o, destino_id=d, finalidad=fp.finalidad, categorias_datos=list(fp.datos),
                categorias_titulares=list(fp.titulares), nna_declarado=fp.nna, frecuencia=fp.frecuencia,
                medio=fp.medio, cifrado=None, garantia=None, origen="plantilla", clave=clave,
                pendiente_revision=True, fecha_creacion=ahora, fecha_actualizacion=ahora))
        if len(fl) + len(flujos_nuevos) > settings.MAPA_MAX_FLUJOS:
            raise MapaDatosError(422, "LIMITE_FLUJOS", f"Con esta plantilla el mapa superaría los "
                                 f"{settings.MAPA_MAX_FLUJOS} flujos permitidos.")
        if not nuevos and not flujos_nuevos:
            await self.db.rollback()
            raise MapaDatosError(409, "PLANTILLA_SIN_CAMBIOS",
                                 "Tu mapa ya tiene todo lo que trae esta plantilla.")
        self.db.add_all(flujos_nuevos)
        if not mapa.plantilla_inicial:
            mapa.plantilla_inicial = plantilla.codigo
        resumen = (f"Se aplicó la plantilla «{plantilla.nombre}»: {len(nuevos)} elemento"
                   f"{'s' if len(nuevos) != 1 else ''} y {len(flujos_nuevos)} flujo"
                   f"{'s' if len(flujos_nuevos) != 1 else ''} por confirmar.")
        return await self._guardar(mapa, "plantilla_aplicada", Accion.MAPA_PLANTILLA_APLICADA, antes,
                                   {"plantilla": plantilla.codigo, "elementos_agregados": len(nuevos),
                                    "flujos_agregados": len(flujos_nuevos)}, resumen)

    # ================================================================ sugerencias desde la evaluación (C4)
    async def _respuestas_evaluacion(self) -> tuple[int | None, dict[str, bool]]:
        from app.application.use_cases.historial_empresa import evaluacion_mas_reciente
        from app.domain.models.pregunta_filtro import PreguntaFiltro
        from app.domain.models.respuesta_filtro import RespuestaFiltro

        ev = (await evaluacion_mas_reciente(self.db, self.empresa_id)
              or await evaluacion_mas_reciente(self.db, self.empresa_id, solo_completadas=False))
        if ev is None:
            return None, {}
        filas = (await self.db.execute(
            select(PreguntaFiltro.codigo, RespuestaFiltro.respuesta)
            .join(RespuestaFiltro, RespuestaFiltro.pregunta_id == PreguntaFiltro.id_pregunta)
            .where(RespuestaFiltro.evaluacion_id == ev))).all()
        return ev, {codigo: bool(resp) for codigo, resp in filas}

    async def sugerencias(self) -> dict:
        mapa, els, _fls = await self.dominio()
        ev, respuestas = await self._respuestas_evaluacion()
        descartadas = set((mapa.sugerencias_descartadas or []) if mapa else [])
        lista = mod_sugerencias.calcular(respuestas, els, descartadas)
        nombres = {e.id: e.nombre for e in els}
        return {
            "evaluacion_id": ev, "sin_evaluacion": ev is None,
            "sugerencias": [s.como_dict(nombres) for s in lista],
            "descartadas": len(descartadas),
        }

    async def aceptar_sugerencia(self, clave: str, version: int, origen_id: int | None) -> dict:
        _ev, respuestas = await self._respuestas_evaluacion()
        mapa, el, fl, antes = await self._iniciar(version)
        els = [elemento_de_fila(r) for r in el]
        s = mod_sugerencias.sugerencia(respuestas, els, clave, set(mapa.sugerencias_descartadas or []))
        if s is None:
            raise MapaDatosError(404, "SUGERENCIA_NO_DISPONIBLE",
                                 "Esta sugerencia ya no está disponible: puede que ya la hayas aplicado.")
        ids = {r.id for r in el}
        mapa_claves = {r.clave: r.id for r in el if r.clave}
        if origen_id is not None:
            if not s.conector or origen_id not in ids:
                raise MapaDatosError(422, "DATOS_INVALIDOS", "Elige un elemento de tu mapa como origen.",
                                     campo="origen_id")
            mapa_claves[s.conector] = origen_id
        elif s.usa_existente:
            mapa_claves[s.conector] = s.usa_existente
        nuevos = []
        for ep in s.elementos:
            if ep.clave in mapa_claves:
                continue
            nuevos.append(self._nuevo_elemento(mapa.id, {
                "tipo": ep.tipo, "subtipo": ep.subtipo, "nombre": ep.nombre, "descripcion": ep.descripcion,
                "pais": ep.pais, "responsable": ep.responsable, "categorias_datos": list(ep.datos),
                "categorias_titulares": list(ep.titulares), "nna_declarado": ep.nna, "rol_tercero": ep.rol},
                origen="evaluacion", clave=ep.clave, pendiente_revision=True))
        nombres = {(r.tipo, r.nombre.casefold()) for r in el}
        for n in nuevos:                   # mismo nombre que algo existente: se distingue
            if (n.tipo, n.nombre.casefold()) in nombres:
                n.nombre = f"{n.nombre} (sugerido)"[:120]
        if len(el) + len(nuevos) > settings.MAPA_MAX_ELEMENTOS:
            raise MapaDatosError(422, "LIMITE_ELEMENTOS", f"El mapa admite hasta {settings.MAPA_MAX_ELEMENTOS} elementos.")
        self.db.add_all(nuevos)
        await self.db.flush()
        mapa_claves.update({n.clave: n.id for n in nuevos})
        ahora = _ahora()
        creados = 0
        for i, f in enumerate(s.flujos):
            extremos = []
            for ref in (f.origen, f.destino):
                tipo, _, valor = ref.partition(":")
                extremos.append(int(valor) if tipo == "id" else mapa_claves.get(valor))
            o, d = extremos
            if not o or not d or o == d or o not in ids | {n.id for n in nuevos} or d not in ids | {n.id for n in nuevos}:
                continue
            self.db.add(MapaFlujo(
                mapa_id=mapa.id, origen_id=o, destino_id=d, finalidad=f.finalidad, categorias_datos=list(f.datos),
                categorias_titulares=list(f.titulares), nna_declarado=f.nna, frecuencia=f.frecuencia, medio=f.medio,
                cifrado=None, garantia=None, origen="evaluacion", clave=f"{s.clave}:{i}", pendiente_revision=True,
                fecha_creacion=ahora, fecha_actualizacion=ahora))
            creados += 1
        if len(fl) + creados > settings.MAPA_MAX_FLUJOS:
            raise MapaDatosError(422, "LIMITE_FLUJOS", f"El mapa admite hasta {settings.MAPA_MAX_FLUJOS} flujos.")
        return await self._guardar(mapa, "sugerencia_aceptada", Accion.MAPA_SUGERENCIA_ACEPTADA, antes,
                                   {"sugerencia": s.clave, "elementos_agregados": len(nuevos), "flujos_agregados": creados},
                                   f"Se agregó la sugerencia de la evaluación «{s.titulo}» (por confirmar).")

    async def descartar_sugerencia(self, clave: str, restablecer: bool = False) -> dict:
        """Descartar no cambia el contenido del mapa (no crea versión), pero queda en el audit_log."""
        mapa = await self._mapa(bloquear=True)
        if mapa is None:
            ahora = _ahora()
            mapa = MapaDatos(empresa_id=self.empresa_id, version=0, sugerencias_descartadas=[],
                             usuario_definitivo_id=self.usuario_id, fecha_creacion=ahora, fecha_actualizacion=ahora)
            self.db.add(mapa)
            try:
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()
                raise MapaDatosError(409, "MAPA_DESACTUALIZADO", "Actualiza la página y vuelve a intentarlo.")
        actuales = list(mapa.sugerencias_descartadas or [])
        if restablecer:
            nuevas: list[str] = []
        else:
            validas = {"llm_externo", "base_vectorial", "ia_nube", "datos_sensibles", "agente_ia",
                       "decisiones_automatizadas", "entrenamiento"}
            if clave not in validas:
                raise MapaDatosError(404, "SUGERENCIA_NO_DISPONIBLE", "Esta sugerencia no existe.")
            nuevas = sorted(set(actuales) | {clave})
        if nuevas != actuales:
            mapa.sugerencias_descartadas = nuevas
            self.bitacora.registrar(
                accion=Accion.MAPA_SUGERENCIA_DESCARTADA, entidad="mapa_datos", entidad_id=mapa.id, actor=self.actor,
                detalle={"sugerencia": None if restablecer else clave, "restablecidas": restablecer,
                         "descartadas": len(nuevas)})
            await self.db.commit()
        return await self.sugerencias()

    # ================================================================ versiones (C5)
    @staticmethod
    def _version_dict(v: MapaDatosVersion, con_contenido: bool = False) -> dict:
        d = {"numero": v.numero, "fecha": _iso(v.fecha), "accion": v.accion, "resumen": v.resumen,
             "elementos": v.elementos, "flujos": v.flujos, "huella": v.huella,
             "cambios_total": len(v.cambios or [])}
        if con_contenido:
            d["cambios"] = list(v.cambios or [])
            d["contenido"] = v.contenido
        return d

    async def listar_versiones(self, pagina: int = 1) -> dict:
        mapa = await self._mapa()
        if mapa is None:
            return {"items": [], "total": 0, "pagina": 1, "paginas": 0, "version_actual": 0}
        total = (await self.db.execute(select(func.count()).select_from(MapaDatosVersion)
                                       .where(MapaDatosVersion.mapa_id == mapa.id))).scalar_one()
        pagina = max(1, pagina)
        filas = (await self.db.execute(
            select(MapaDatosVersion).where(MapaDatosVersion.mapa_id == mapa.id)
            .order_by(MapaDatosVersion.numero.desc())
            .offset((pagina - 1) * TAMANO_PAGINA_VERSIONES).limit(TAMANO_PAGINA_VERSIONES))).scalars().all()
        return {"items": [self._version_dict(v) for v in filas], "total": total, "pagina": pagina,
                "paginas": -(-total // TAMANO_PAGINA_VERSIONES), "version_actual": mapa.version}

    async def _version(self, mapa_id: int, numero: int) -> MapaDatosVersion:
        v = (await self.db.execute(select(MapaDatosVersion).where(
            MapaDatosVersion.mapa_id == mapa_id, MapaDatosVersion.numero == numero))).scalar_one_or_none()
        if v is None:
            raise MapaDatosError(404, "VERSION_NO_ENCONTRADA", "No encontramos esa versión del mapa.")
        return v

    async def obtener_version(self, numero: int) -> dict:
        mapa = await self._mapa()
        if mapa is None:
            raise MapaDatosError(404, "VERSION_NO_ENCONTRADA", "No encontramos esa versión del mapa.")
        v = await self._version(mapa.id, numero)
        return {"version": self._version_dict(v, con_contenido=True), "es_actual": v.numero == mapa.version,
                "verificada": versiones.huella(v.contenido) == v.huella}

    async def restaurar_version(self, numero: int, version: int) -> dict:
        mapa, el, fl, antes = await self._iniciar(version)
        v = await self._version(mapa.id, numero)
        if v.numero == mapa.version:
            raise MapaDatosError(409, "YA_ES_LA_ACTUAL", "Esa ya es la versión actual del mapa.")
        objetivo_e, objetivo_f = versiones.desde_instantanea(v.contenido)
        if len(objetivo_e) > settings.MAPA_MAX_ELEMENTOS or len(objetivo_f) > settings.MAPA_MAX_FLUJOS:
            raise MapaDatosError(422, "LIMITE_ELEMENTOS", "Esa versión supera el tamaño máximo actual del mapa.")
        ids_e = {e.id for e in objetivo_e}
        ids_f = {f.id for f in objetivo_f}
        ahora = _ahora()
        # 1. fuera lo que no estaba en esa versión (primero los flujos)
        sobran_f = [r.id for r in fl if r.id not in ids_f or r.origen_id not in ids_e or r.destino_id not in ids_e]
        if sobran_f:
            await self.db.execute(delete(MapaFlujo).where(MapaFlujo.id.in_(sobran_f))
                                  .execution_options(synchronize_session="fetch"))
        for r in el:
            if r.id not in ids_e:
                await self.db.delete(r)
        await self.db.flush()
        # 2. elementos: se actualizan los que siguen y se recrean (con su mismo id) los eliminados
        actuales_e = {r.id: r for r in el if r.id in ids_e}
        for e in objetivo_e:
            valores = {c: getattr(e, c) for c in CAMPOS_ELEMENTO}
            valores.update(origen=e.origen if e.origen in ("manual", "plantilla", "evaluacion") else "manual",
                           clave=e.clave)
            if e.tipo != "tercero":
                valores["rol_tercero"] = valores["contrato_firmado"] = None
            r = actuales_e.get(e.id)
            if r is None:
                self.db.add(MapaElemento(id=e.id, mapa_id=mapa.id, fecha_creacion=ahora, fecha_actualizacion=ahora,
                                         **valores))
            elif any(getattr(r, k) != val for k, val in valores.items()):
                for k, val in valores.items():
                    setattr(r, k, val)
                r.fecha_actualizacion = ahora
        await self.db.flush()
        # 3. flujos
        quedan_f = {r.id: r for r in fl if r.id not in set(sobran_f)}
        for f in objetivo_f:
            valores = {c: getattr(f, c) for c in CAMPOS_FLUJO}
            valores.update(origen=f.origen if f.origen in ("manual", "plantilla", "evaluacion") else "manual",
                           clave=f.clave)
            r = quedan_f.get(f.id)
            if r is None:
                self.db.add(MapaFlujo(id=f.id, mapa_id=mapa.id, fecha_creacion=ahora, fecha_actualizacion=ahora,
                                      **valores))
            elif any(getattr(r, k) != val for k, val in valores.items()):
                for k, val in valores.items():
                    setattr(r, k, val)
                r.fecha_actualizacion = ahora
        resultado = await self._guardar(mapa, "version_restaurada", Accion.MAPA_VERSION_RESTAURADA, antes,
                                        {"version_restaurada": numero}, f"Se restauró la versión {numero} del mapa.")
        if resultado.get("cambio") is None:
            raise MapaDatosError(409, "YA_ES_LA_ACTUAL", "El mapa actual ya es igual a esa versión.")
        return resultado

    # ================================================================ informe (C3)
    async def historial_reciente(self, mapa: MapaDatos | None, cuantos: int = 10) -> list:
        from app.application.mapa_datos.pdf_mapa import VersionResumen

        if mapa is None:
            return []
        filas = (await self.db.execute(
            select(MapaDatosVersion.numero, MapaDatosVersion.fecha, MapaDatosVersion.resumen)
            .where(MapaDatosVersion.mapa_id == mapa.id).order_by(MapaDatosVersion.numero.desc()).limit(cuantos))).all()
        return [VersionResumen(n, f, r) for n, f, r in filas]

    async def datos_informe(self, filtros: analisis.FiltrosMapa):
        from app.application.mapa_datos.pdf_mapa import DatosInformeMapa

        mapa, els, fls = await self.dominio()
        if not els:
            raise MapaDatosError(409, "MAPA_VACIO", "Agrega al menos un elemento al mapa antes de generar el informe.")
        huella = versiones.huella(versiones.instantanea(els, fls))
        return DatosInformeMapa(
            razon_social=self.razon_social, rubro=await self.rubro(), version=mapa.version if mapa else 0,
            fecha_version=mapa.fecha_actualizacion if mapa else None, huella=huella, elementos=els, flujos=fls,
            filtros=filtros, generado=datetime.now(timezone.utc), historial=await self.historial_reciente(mapa))

    def registrar_informe(self, accion: str, version: int, filtros: analisis.FiltrosMapa, **extra) -> None:
        self.bitacora.registrar(
            accion=accion, entidad="mapa_datos", entidad_id=None, actor=self.actor,
            detalle={"version": version, "filtrado": filtros.activos, "empresa_id": self.empresa_id, **extra})
