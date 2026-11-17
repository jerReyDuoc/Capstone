"""Mapa de datos: historial de versiones (listar, obtener y restaurar)."""
from __future__ import annotations

from sqlalchemy import delete, func, select

from app.application.mapa_datos.casos_uso.comun import TAMANO_PAGINA_VERSIONES, MapaDatosError, _ahora, _iso
from app.core.config import settings
from app.domain.auditoria.acciones import Accion
from app.domain.mapa_datos import versiones
from app.domain.mapa_datos.modelo import CAMPOS_ELEMENTO, CAMPOS_FLUJO
from app.domain.models.mapa_datos import MapaDatosVersion, MapaElemento, MapaFlujo


class VersionesMixin:
    """Depende de los atributos que fija MapaDatosCasos.__init__ (db, actor, empresa_id, bitacora, ...)."""

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
