"""Cambios de estado (C3, C4) y versiones inmutables de una actividad."""
from __future__ import annotations

from app.domain.models.rat_modelo import RatActividadVersion
from app.domain.rat import estados, versiones_actividad as versiones
from app.domain.rat import catalogo as cat
from app.domain.auditoria.acciones import Accion
from app.application.rat.casos_uso.registro_actividades_casos.comun import RatError, _ahora, _iso, _evaluar


class EstadosMixin:
    """Cambios de estado (C3, C4) y versiones inmutables de una actividad."""

    # ---------------------------------------------------------------- estados (C3, C4)
    async def _ultima_version(self, actividad_id: int) -> RatActividadVersion | None:
        return await self.repo.ultima_version(actividad_id)

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
                self.repo.agregar(nueva_version)
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
        respuesta = {"actividad": self._vista(f, elementos, flujos, detalle=True), "cambio": accion, "mensaje": texto,
                     "version_creada": nueva_version.numero if nueva_version is not None else None}
        if accion == "aprobar":
            # HU-38 C3: con el registro vigente y completo, cuenta como evidencia en la evaluación (solo mejora)
            from app.application.rat.casos_uso.cruce_cumplimiento import aplicar_tras_aprobar

            respuesta["evidencia"] = await aplicar_tras_aprobar(self.db, self.cliente)
        return respuesta

    # ---------------------------------------------------------------- versiones
    async def listar_versiones(self, actividad_id: int) -> dict:
        f = await self._actividad(actividad_id)
        filas = await self.repo.versiones(f.id)
        return {
            "version_vigente": f.version_vigente,
            "estado": f.estado,
            "versiones": [{"numero": v.numero, "fecha": _iso(v.fecha), "huella": v.huella, "resumen": v.resumen,
                           "cambios": [{"codigo": c, "titulo": versiones.TITULO_CAMBIO.get(c, c)} for c in v.cambios or []],
                           "version_mapa": v.version_mapa} for v in filas],
        }

    async def obtener_version(self, actividad_id: int, numero: int) -> dict:
        f = await self._actividad(actividad_id)
        v = await self.repo.version(f.id, numero)
        if v is None:
            raise RatError(404, "VERSION_NO_ENCONTRADA", "No encontramos esa versión de la actividad.")
        return {"numero": v.numero, "fecha": _iso(v.fecha), "huella": v.huella, "resumen": v.resumen,
                "version_mapa": v.version_mapa, "es_la_vigente": v.numero == f.version_vigente,
                "verificada": versiones.huella(v.contenido) == v.huella, "contenido": v.contenido}
