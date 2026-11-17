"""Rechazos, validaciones, creación y edición de actividades."""
from __future__ import annotations

from app.domain.mapa_datos.modelo_mapa import Elemento, ErrorValidacion, Flujo
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.rat_modelo import RatActividad
from app.domain.rat import estados, modelo_actividad as modelo
from app.domain.rat import catalogo as cat
from app.domain.auditoria.acciones import Accion
from app.application.rat.casos_uso.registro_actividades_casos.comun import MAX_ACTIVIDADES, RatError, _ahora, _evaluar


class EdicionMixin:
    """Rechazos, validaciones, creación y edición de actividades."""

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
        if await self.repo.nombre_en_uso(self.empresa_id, nombre, excepto):
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
        total = await self.repo.contar_actividades(self.empresa_id)
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
        self.repo.agregar(f)
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
