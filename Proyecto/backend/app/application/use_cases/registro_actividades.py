"""
HU-35 · Registro de Actividades de Tratamiento (RAT) del cliente.

Como Usuario Definitivo (cliente), quiero llevar el Registro de Actividades de Tratamiento (RAT) de
mi empresa dentro de la plataforma, para cumplir la caracterización de actividades de tratamiento
que exigen la Ley 21.719 y su reglamento.

  C1  Cada actividad registra los 11 campos mínimos del reglamento, las medidas de seguridad y el
      rol de la empresa (app/domain/rat/catalogo.py: CAMPOS).
  C2  Sistemas, bases, terceros y flujos se ELIGEN DEL MAPA (HU-34) y no se ingresan dos veces
      (app/domain/rat/analisis.py: derivados). Un cambio en el mapa devuelve a revisión las
      actividades afectadas, en la MISMA transacción del cambio (marcar_afectadas_por_mapa, que
      llama MapaDatosCasos._guardar).
  C3  Completitud por actividad y global; una actividad no queda vigente con campos vacíos.
  C4  Estados borrador → en revisión → vigente → archivada (app/domain/rat/estados.py). Al quedar
      vigente se guarda una versión inmutable (rat_actividad_version, con trigger) y cada cambio
      queda en el audit_log (HU-09) en la misma transacción. Solo con contrato vigente.

Concurrencia: toda edición manda la `revision` de la actividad que vio el usuario. Si cambió (otra
pestaña o un cambio en el mapa), responde 409 ACTIVIDAD_DESACTUALIZADA y nada se pisa.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.mapa_datos import versiones as versiones_mapa
from app.domain.mapa_datos.modelo import Elemento, ErrorValidacion, Flujo
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.mapa_datos import MapaDatos, MapaElemento, MapaFlujo
from app.domain.models.rat import RatActividad, RatActividadVersion
from app.domain.rat import analisis, estados, modelo, versiones, vinculo_mapa
from app.domain.rat import catalogo as cat
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

MAX_ACTIVIDADES = 300
MAX_MOTIVOS = 20


class RatError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _elemento(r: MapaElemento) -> Elemento:
    from app.application.use_cases.mapa_datos import elemento_de_fila
    return elemento_de_fila(r)


def _flujo(r: MapaFlujo) -> Flujo:
    from app.application.use_cases.mapa_datos import flujo_de_fila
    return flujo_de_fila(r)


def _evaluar(contenido: dict, elementos: list[Elemento], flujos: list[Flujo]) -> tuple[dict, dict]:
    deriv = analisis.derivados(contenido, elementos, flujos)
    return deriv, analisis.completitud(contenido, deriv)


# ====================================================================== vínculo con el mapa (C2)
async def marcar_afectadas_por_mapa(db: AsyncSession, empresa_id: int, cambios: list[dict], antes: dict | None,
                                    despues: dict, version_mapa: int, actor, bitacora: BitacoraRepository) -> list[int]:
    """
    Lo llama el mapa de datos (MapaDatosCasos._guardar) ANTES de confirmar un cambio: las actividades
    que usan lo que cambió vuelven a revisión (las vigentes) o anotan el motivo (borradores y en
    revisión). No confirma la transacción: lo hace el mapa, así ambos cambios quedan juntos o ninguno.
    """
    if not vinculo_mapa.cambios_relevantes(cambios):
        return []
    filas = list((await db.execute(
        select(RatActividad).where(RatActividad.empresa_id == empresa_id, RatActividad.estado != cat.ARCHIVADA)
        .order_by(RatActividad.id).with_for_update())).scalars().all())
    if not filas:
        return []
    afectadas = vinculo_mapa.afectadas([{"id": f.id, "contenido": f.contenido} for f in filas], cambios, antes, despues)
    if not afectadas:
        return []
    elementos, flujos = versiones_mapa.desde_instantanea(despues)
    ahora = _ahora()
    vuelven = 0
    for f in filas:
        motivos = afectadas.get(f.id)
        if not motivos:
            continue
        nuevo_estado = estados.tras_cambio_en_mapa(f.estado)
        vuelven += int(nuevo_estado != f.estado)
        registro = [{"fecha": ahora.isoformat(), "texto": m, "version_mapa": version_mapa} for m in motivos]
        f.motivos_revision = (list(f.motivos_revision or []) + registro)[-MAX_MOTIVOS:]
        f.estado = nuevo_estado
        f.revision += 1
        f.fecha_actualizacion = ahora
        f.completitud = _evaluar(f.contenido, elementos, flujos)[1]["porcentaje"]
    bitacora.registrar(
        accion=Accion.RAT_MARCADA_REVISION, entidad="rat_actividad", entidad_id=None, actor=actor,
        detalle={"actividades": sorted(afectadas), "vuelven_a_revision": vuelven, "version_mapa": version_mapa})
    return sorted(afectadas)


# ====================================================================== casos de uso
class RegistroActividadesCasos:
    """`cliente` es el ClienteConServicio de app/core/servicio_pagado.py (contrato vigente)."""

    def __init__(self, db: AsyncSession, cliente):
        self.db = db
        self.actor = cliente.actor
        self.empresa_id: int = cliente.empresa.id
        self.usuario_id: int = cliente.usuario.id
        self.bitacora = BitacoraRepository(db)

    # ---------------------------------------------------------------- lectura
    async def _mapa(self) -> tuple[int, list[Elemento], list[Flujo]]:
        mapa = (await self.db.execute(select(MapaDatos).where(MapaDatos.empresa_id == self.empresa_id))) \
            .scalar_one_or_none()
        if mapa is None:
            return 0, [], []
        el = (await self.db.execute(select(MapaElemento).where(MapaElemento.mapa_id == mapa.id)
                                    .order_by(MapaElemento.id))).scalars().all()
        fl = (await self.db.execute(select(MapaFlujo).where(MapaFlujo.mapa_id == mapa.id)
                                    .order_by(MapaFlujo.id))).scalars().all()
        return mapa.version, [_elemento(r) for r in el], [_flujo(r) for r in fl]

    async def _actividad(self, actividad_id: int, bloquear: bool = False) -> RatActividad:
        q = select(RatActividad).where(RatActividad.id == actividad_id, RatActividad.empresa_id == self.empresa_id)
        if bloquear:
            q = q.with_for_update()
        fila = (await self.db.execute(q)).scalar_one_or_none()
        if fila is None:                  # lo de otra empresa no existe (404, no 403)
            raise RatError(404, "ACTIVIDAD_NO_ENCONTRADA", "No encontramos esa actividad en tu registro.")
        return fila

    @staticmethod
    def _resumen(deriv: dict, contenido: dict) -> dict:
        c = modelo.completar(contenido)
        return {
            "tipos_datos": len(deriv["tipos_datos"]),
            "hay_sensibles": deriv["hay_sensibles"],
            "incluye_nna": deriv["incluye_nna"],
            "sistemas": len(deriv["bases_datos"]),
            "terceros": len(deriv["terceros"]),
            "transferencias": len(deriv["transferencias"]),
            "paises": [p["nombre"] for p in deriv["paises"]],
            "base_licitud": cat.nombre(cat.BASES_POR_CODIGO, c["base_licitud"]) or None,
            "rol": cat.nombre(cat.ROLES_POR_CODIGO, c["rol"]) or None,
            "finalidades": len(c["finalidades"]),
        }

    def _vista(self, f: RatActividad, elementos: list[Elemento], flujos: list[Flujo], detalle: bool) -> dict:
        deriv, compl = _evaluar(f.contenido, elementos, flujos)
        datos = {
            "id": f.id,
            "nombre": f.nombre,
            "estado": f.estado,
            "estado_nombre": cat.nombre(cat.ESTADOS_POR_CODIGO, f.estado),
            "estado_previo": f.estado_previo,
            "revision": f.revision,
            "version_vigente": f.version_vigente,
            "editable": f.estado in estados.EDITABLES,
            "acciones": estados.acciones_disponibles(f.estado),
            "completitud": compl if detalle else {k: compl[k] for k in ("porcentaje", "completos", "total",
                                                                       "faltantes", "puede_quedar_vigente")},
            "motivos_revision": list(f.motivos_revision or []),
            "resumen": self._resumen(deriv, f.contenido),
            "area": modelo.completar(f.contenido).get("area"),
            "origen": getattr(f, "origen", None) or "manual",   # HU-39: "ia" = propuesta del asistente aceptada
            "fecha_creacion": _iso(f.fecha_creacion),
            "fecha_actualizacion": _iso(f.fecha_actualizacion),
            "fecha_vigencia": _iso(f.fecha_vigencia),
            "fecha_archivo": _iso(f.fecha_archivo),
        }
        if detalle:
            datos["contenido"] = modelo.completar(f.contenido)
            datos["derivados"] = deriv
        return datos

    async def listar(self) -> dict:
        version_mapa, elementos, flujos = await self._mapa()
        filas = list((await self.db.execute(
            select(RatActividad).where(RatActividad.empresa_id == self.empresa_id)
            .order_by(RatActividad.nombre))).scalars().all())
        vistas = [self._vista(f, elementos, flujos, detalle=False) for f in filas]
        activas = [v for v in vistas if v["estado"] != cat.ARCHIVADA]
        por_estado = {e: sum(1 for v in vistas if v["estado"] == e) for e in cat.CODIGOS_ESTADO}
        return {
            "actividades": vistas,
            "global": {
                **analisis.completitud_global([v["completitud"]["porcentaje"] for v in activas]),
                "por_estado": por_estado,
                "por_revisar": sum(1 for v in activas if v["motivos_revision"] and v["estado"] == cat.EN_REVISION),
            },
            "mapa": {"version": version_mapa, "elementos": len(elementos), "flujos": len(flujos),
                     "iniciado": bool(elementos)},
            "limites": {"max_actividades": MAX_ACTIVIDADES},
        }

    async def obtener(self, actividad_id: int) -> dict:
        f = await self._actividad(actividad_id)
        version_mapa, elementos, flujos = await self._mapa()
        return {"actividad": self._vista(f, elementos, flujos, detalle=True), "mapa": {"version": version_mapa}}

    # ---------------------------------------------------------------- rechazos (quedan en el audit_log)
    async def _rechazar(self, motivo: str, actividad_id: int | None, error: RatError) -> RatError:
        await self.db.rollback()
        self.bitacora.registrar(
            accion=Accion.RAT_CAMBIO_RECHAZADO, entidad="rat_actividad", entidad_id=actividad_id, actor=self.actor,
            resultado=RESULTADO_RECHAZADO, detalle={"motivo": motivo})
        await self.db.commit()
        return error

    def _invalido(self, e: ErrorValidacion) -> RatError:
        return RatError(422, "DATOS_INVALIDOS", e.mensaje, campo=e.campo)

    async def _verificar_revision(self, f: RatActividad, revision: int) -> None:
        if revision != f.revision:
            raise await self._rechazar("revision_desactualizada", f.id, RatError(
                409, "ACTIVIDAD_DESACTUALIZADA",
                "La actividad cambió desde que la abriste (en otra pestaña o por un cambio en el mapa de datos). "
                "Cargamos la versión más reciente: revisa y vuelve a intentarlo.", revision_actual=f.revision))

    async def _nombre_libre(self, nombre: str, excepto: int | None = None) -> None:
        q = select(RatActividad.id).where(RatActividad.empresa_id == self.empresa_id,
                                          func.lower(RatActividad.nombre) == nombre.lower())
        if excepto is not None:
            q = q.where(RatActividad.id != excepto)
        if (await self.db.execute(q.limit(1))).scalar_one_or_none() is not None:
            raise RatError(409, "NOMBRE_DUPLICADO", "Ya tienes una actividad con ese nombre. Usa otro para distinguirlas.",
                           campo="nombre")

    @staticmethod
    def _ajustar_al_mapa(contenido: dict, previo: dict | None, elementos: list[Elemento], flujos: list[Flujo]) -> dict:
        """
        Lo NUEVO que se elige debe existir en el mapa (lo ya elegido que el mapa eliminó se conserva
        para que la actividad avise y el usuario lo quite). Las categorías se limitan a las que el
        mapa registra para cada elemento o flujo (el subconjunto que usa la actividad).
        """
        por_id = {"elementos": {e.id: e for e in elementos}, "flujos": {f.id: f for f in flujos}}
        for clave in ("elementos", "flujos"):
            antes = {x["id"] for x in (previo or {}).get(clave, [])}
            for item in contenido[clave]:
                existente = por_id[clave].get(item["id"])
                if existente is None:
                    if item["id"] not in antes:
                        raise ErrorValidacion(clave, "Uno de los elementos elegidos ya no está en el mapa de datos. "
                                                     "Actualiza la página y vuelve a elegirlo.")
                    continue
                item["categorias_datos"] = [c for c in item["categorias_datos"] if c in existente.categorias_datos]
                item["categorias_titulares"] = [c for c in item["categorias_titulares"]
                                                if c in existente.categorias_titulares]
        return contenido

    # ---------------------------------------------------------------- crear y editar
    async def crear(self, datos: dict, origen: str = "manual", propuesta_ia_id: int | None = None) -> dict:
        """HU-39: `origen="ia"` y `propuesta_ia_id` cuando el usuario acepta una propuesta del asistente
        (la actividad entra igual como BORRADOR: nunca queda vigente sin pasar por su revisión)."""
        try:
            contenido = modelo.normalizar(datos)
        except ErrorValidacion as e:
            raise self._invalido(e)
        total = (await self.db.execute(select(func.count()).select_from(RatActividad)
                                       .where(RatActividad.empresa_id == self.empresa_id))).scalar() or 0
        if total >= MAX_ACTIVIDADES:
            raise await self._rechazar("limite_actividades", None, RatError(
                409, "LIMITE_ACTIVIDADES", f"Tu registro llegó al máximo de {MAX_ACTIVIDADES} actividades. Archiva o "
                                           "agrupa las que ya no uses."))
        await self._nombre_libre(contenido["nombre"])
        version_mapa, elementos, flujos = await self._mapa()
        try:
            contenido = self._ajustar_al_mapa(contenido, None, elementos, flujos)
        except ErrorValidacion as e:
            raise self._invalido(e)
        ahora = _ahora()
        f = RatActividad(
            empresa_id=self.empresa_id, nombre=contenido["nombre"], estado=cat.BORRADOR, contenido=contenido,
            revision=1, completitud=_evaluar(contenido, elementos, flujos)[1]["porcentaje"], motivos_revision=[],
            usuario_definitivo_id=self.usuario_id, fecha_creacion=ahora, fecha_actualizacion=ahora,
            origen=origen, propuesta_ia_id=propuesta_ia_id)
        self.db.add(f)
        await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.RAT_ACTIVIDAD_CREADA, entidad="rat_actividad", entidad_id=f.id, actor=self.actor,
            detalle={"campos": modelo.campos_cambiados(modelo.contenido_vacio(), contenido),
                     "completitud": f.completitud, "version_mapa": version_mapa, "origen": origen})
        await self.db.commit()
        return {"actividad": self._vista(f, elementos, flujos, detalle=True), "cambio": "creada"}

    async def editar(self, actividad_id: int, datos: dict, revision: int) -> dict:
        f = await self._actividad(actividad_id, bloquear=True)
        await self._verificar_revision(f, revision)
        if f.estado not in estados.EDITABLES:
            mensaje = ("Esta actividad está vigente y su versión ya no se puede modificar. Usa «Editar en una nueva "
                       "versión»: la vigente seguirá valiendo hasta que la nueva quede vigente."
                       if f.estado == cat.VIGENTE else "Reactiva la actividad para poder editarla.")
            raise await self._rechazar("no_editable", f.id, RatError(409, "ACTIVIDAD_NO_EDITABLE", mensaje))
        version_mapa, elementos, flujos = await self._mapa()
        try:
            contenido = modelo.normalizar(datos, f.contenido)
            contenido = self._ajustar_al_mapa(contenido, modelo.completar(f.contenido), elementos, flujos)
        except ErrorValidacion as e:
            raise self._invalido(e)
        cambiados = modelo.campos_cambiados(f.contenido, contenido)
        if not cambiados:
            await self.db.rollback()
            f = await self._actividad(actividad_id)
            return {"actividad": self._vista(f, elementos, flujos, detalle=True), "cambio": None}
        if "nombre" in cambiados:
            await self._nombre_libre(contenido["nombre"], excepto=f.id)
        f.contenido = contenido
        f.nombre = contenido["nombre"]
        f.revision += 1
        f.completitud = _evaluar(contenido, elementos, flujos)[1]["porcentaje"]
        f.fecha_actualizacion = _ahora()
        self.bitacora.registrar(
            accion=Accion.RAT_ACTIVIDAD_EDITADA, entidad="rat_actividad", entidad_id=f.id, actor=self.actor,
            detalle={"campos": cambiados, "estado": f.estado, "completitud": f.completitud,
                     "version_mapa": version_mapa})
        await self.db.commit()
        return {"actividad": self._vista(f, elementos, flujos, detalle=True), "cambio": "editada"}

    # ---------------------------------------------------------------- estados (C3, C4)
    async def _ultima_version(self, actividad_id: int) -> RatActividadVersion | None:
        return (await self.db.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id == actividad_id)
            .order_by(RatActividadVersion.numero.desc()).limit(1))).scalar_one_or_none()

    async def cambiar_estado(self, actividad_id: int, accion: str, revision: int) -> dict:
        f = await self._actividad(actividad_id, bloquear=True)
        await self._verificar_revision(f, revision)
        try:
            hacia = estados.destino(accion, f.estado, f.estado_previo, tuvo_vigente=f.version_vigente is not None)
        except estados.TransicionInvalida as e:
            raise await self._rechazar("transicion_invalida", f.id, RatError(409, "TRANSICION_INVALIDA", e.mensaje))
        version_mapa, elementos, flujos = await self._mapa()
        deriv, compl = _evaluar(f.contenido, elementos, flujos)
        desde = f.estado
        ahora = _ahora()
        nueva_version: RatActividadVersion | None = None
        cambios_version: list[str] = []

        if accion == "aprobar":
            if not compl["puede_quedar_vigente"]:
                faltan = ", ".join(x["titulo"].lower() for x in compl["faltantes"][:5])
                extra = "…" if len(compl["faltantes"]) > 5 else ""
                raise await self._rechazar("incompleta", f.id, RatError(
                    422, "ACTIVIDAD_INCOMPLETA",
                    f"Para dejarla vigente completa los datos obligatorios que faltan: {faltan}{extra}.",
                    faltantes=[x["codigo"] for x in compl["faltantes"]]))
            inst = versiones.instantanea(f.contenido, deriv)
            h = versiones.huella(inst)
            ultima = await self._ultima_version(f.id)
            if ultima is None or ultima.huella != h:
                cambios_version = versiones.diferencias(ultima.contenido if ultima else None, inst)
                numero = (ultima.numero if ultima else 0) + 1
                nueva_version = RatActividadVersion(
                    actividad_id=f.id, empresa_id=self.empresa_id, numero=numero, fecha=ahora,
                    usuario_definitivo_id=self.usuario_id, contenido=inst, huella=h, version_mapa=version_mapa,
                    resumen=("Primera versión vigente." if ultima is None else versiones.describir(cambios_version))[:300],
                    cambios=cambios_version)
                self.db.add(nueva_version)
                f.version_vigente = numero
            f.fecha_vigencia = ahora
            f.motivos_revision = []
        elif accion == "archivar":
            f.estado_previo = f.estado
            f.fecha_archivo = ahora
        elif accion == "reactivar":
            f.estado_previo = None
            f.fecha_archivo = None

        f.estado = hacia
        f.revision += 1
        f.completitud = compl["porcentaje"]
        f.fecha_actualizacion = ahora
        await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.RAT_ESTADO_CAMBIADO, entidad="rat_actividad", entidad_id=f.id, actor=self.actor,
            detalle={"accion": accion, "desde": desde, "hacia": hacia, "completitud": compl["porcentaje"],
                     "version_vigente": f.version_vigente})
        if nueva_version is not None:
            self.bitacora.registrar(
                accion=Accion.RAT_VERSION_VIGENTE, entidad="rat_actividad", entidad_id=f.id, actor=self.actor,
                detalle={"numero": nueva_version.numero, "huella": nueva_version.huella[:16],
                         "campos": cambios_version, "version_mapa": version_mapa})
        await self.db.commit()
        if accion == "aprobar":
            texto = (f"Quedó vigente la versión {f.version_vigente}." if nueva_version is not None
                     else f"Confirmaste que la versión {f.version_vigente} sigue al día: vuelve a estar vigente.")
        else:
            texto = {
                "enviar_revision": "La actividad quedó en revisión.",
                "volver_borrador": "La actividad volvió a borrador.",
                "nueva_version": "Abriste una nueva versión en borrador. La versión vigente sigue valiendo hasta que "
                                 "la nueva quede vigente.",
                "archivar": "La actividad quedó archivada.",
                "reactivar": ("Reactivaste la actividad: quedó en revisión para que confirmes que sigue al día."
                              if hacia == cat.EN_REVISION else "Reactivaste la actividad: quedó en borrador."),
            }[accion]
        return {"actividad": self._vista(f, elementos, flujos, detalle=True), "cambio": accion, "mensaje": texto,
                "version_creada": nueva_version.numero if nueva_version is not None else None}

    # ---------------------------------------------------------------- versiones
    async def listar_versiones(self, actividad_id: int) -> dict:
        f = await self._actividad(actividad_id)
        filas = (await self.db.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id == f.id)
            .order_by(RatActividadVersion.numero.desc()))).scalars().all()
        return {
            "version_vigente": f.version_vigente,
            "estado": f.estado,
            "versiones": [{"numero": v.numero, "fecha": _iso(v.fecha), "huella": v.huella, "resumen": v.resumen,
                           "cambios": [{"codigo": c, "titulo": versiones.TITULO_CAMBIO.get(c, c)} for c in v.cambios or []],
                           "version_mapa": v.version_mapa} for v in filas],
        }

    async def obtener_version(self, actividad_id: int, numero: int) -> dict:
        f = await self._actividad(actividad_id)
        v = (await self.db.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id == f.id,
                                              RatActividadVersion.numero == numero))).scalar_one_or_none()
        if v is None:
            raise RatError(404, "VERSION_NO_ENCONTRADA", "No encontramos esa versión de la actividad.")
        return {"numero": v.numero, "fecha": _iso(v.fecha), "huella": v.huella, "resumen": v.resumen,
                "version_mapa": v.version_mapa, "es_la_vigente": v.numero == f.version_vigente,
                "verificada": versiones.huella(v.contenido) == v.huella, "contenido": v.contenido}
