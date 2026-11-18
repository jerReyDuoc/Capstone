"""Mapa de datos: ciclo de un cambio (versión, bloqueo, guardado) y edición de elementos y flujos."""
from __future__ import annotations

from app.application.mapa_datos.casos_uso.comun import MAX_CAMBIOS_GUARDADOS, MapaDatosError, _ahora, elemento_de_fila, flujo_de_fila
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.errores import ConflictoIntegridadError
from app.domain.mapa_datos import versiones_mapa as versiones
from app.domain.mapa_datos.modelo_mapa import ErrorValidacion, normalizar_elemento, normalizar_flujo
from app.domain.models.bitacora_auditoria import RESULTADO_RECHAZADO
from app.domain.models.mapa_datos_tablas import MapaDatos, MapaDatosVersion, MapaElemento, MapaFlujo


class EdicionMixin:
    """Depende de los atributos que fija MapaDatosCasos.__init__ (db, actor, empresa_id, bitacora, ...)."""

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
            self.repo.agregar(mapa)
            try:
                await self.repo.volcar()
            except ConflictoIntegridadError:  # otra petición creó el mapa al mismo tiempo
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
        self.repo.agregar(MapaDatosVersion(
            mapa_id=mapa.id, empresa_id=self.empresa_id, numero=mapa.version, fecha=mapa.fecha_actualizacion,
            usuario_definitivo_id=self.usuario_id, accion=accion_version, resumen=texto,
            cambios=cambios[:MAX_CAMBIOS_GUARDADOS], contenido=despues, huella=versiones.huella(despues),
            elementos=len(el), flujos=len(fl),
        ))
        # HU-35 criterio 2: las actividades del registro que usan lo que cambió vuelven a revisión, en
        # esta misma transacción (si algo falla, no se guarda ni el cambio del mapa ni la marca).
        from app.application.rat.casos_uso.registro_actividades_casos import marcar_afectadas_por_mapa

        afectadas = await marcar_afectadas_por_mapa(self.db, self.empresa_id, cambios, antes, despues, mapa.version,
                                                    self.actor, self.bitacora)
        self.bitacora.registrar(
            accion=accion_audit, entidad="mapa_datos", entidad_id=mapa.id, actor=self.actor,
            detalle={"version": mapa.version, "cambios": len(cambios), "elementos_total": len(el),
                     "flujos_total": len(fl), **detalle})
        # T-12: sin confirmar, el cambio queda en la transacción de quien llama (un solo commit)
        if getattr(self, "confirmar", True):
            await self.db.commit()
        else:
            await self.db.flush()
        return {**self._armar_vista(mapa, el, fl), "cambio": {"version": mapa.version, "resumen": texto,
                                                       "actividades_afectadas": len(afectadas)}}

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

    async def crear_elemento(self, datos: dict, version: int, origen: str = "manual",
                             propuesta_ia_id: int | None = None) -> dict:
        """HU-39: `origen="ia"` y `propuesta_ia_id` cuando el usuario acepta una propuesta del asistente."""
        try:
            campos = normalizar_elemento(datos)
        except ErrorValidacion as e:
            raise self._invalido(e)
        mapa, el, _fl, antes = await self._iniciar(version)
        if len(el) >= settings.MAPA_MAX_ELEMENTOS:
            raise MapaDatosError(422, "LIMITE_ELEMENTOS",
                                 f"El mapa admite hasta {settings.MAPA_MAX_ELEMENTOS} elementos.")
        self._nombre_libre(el, campos["nombre"], campos["tipo"])
        fila = self._nuevo_elemento(mapa.id, campos, origen=origen)
        fila.propuesta_ia_id = propuesta_ia_id
        self.repo.agregar(fila)
        await self.db.flush()
        self.ultimo_id = fila.id
        return await self._guardar(mapa, "elemento_creado", Accion.MAPA_ELEMENTO_CREADO, antes,
                                   {"elemento_id": fila.id, "tipo": fila.tipo, "origen": origen})

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
            await self.repo.eliminar_flujos(sus_flujos)
        tipo = fila.tipo
        await self.repo.eliminar(fila)
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

    async def crear_flujo(self, datos: dict, version: int, origen: str = "manual",
                          propuesta_ia_id: int | None = None) -> dict:
        """HU-39: `origen="ia"` y `propuesta_ia_id` cuando el usuario acepta una propuesta del asistente."""
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
        fila = MapaFlujo(mapa_id=mapa.id, origen=origen, clave=None, fecha_creacion=ahora, fecha_actualizacion=ahora,
                         propuesta_ia_id=propuesta_ia_id, **base)
        self.repo.agregar(fila)
        await self.db.flush()
        self.ultimo_id = fila.id
        return await self._guardar(mapa, "flujo_creado", Accion.MAPA_FLUJO_CREADO, antes,
                                   {"flujo_id": fila.id, "origen": origen})

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
        await self.repo.eliminar(fila)
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
