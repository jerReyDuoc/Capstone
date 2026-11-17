"""Mapa de datos: datos del informe (C3) y su registro en la bitácora."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.application.mapa_datos.casos_uso.comun import MapaDatosError
from app.domain.mapa_datos import analisis, versiones
from app.domain.models.mapa_datos import MapaDatos, MapaDatosVersion


class ExportacionMixin:
    """Depende de los atributos que fija MapaDatosCasos.__init__ (db, actor, empresa_id, bitacora, ...)."""

    # ================================================================ informe (C3)
    async def historial_reciente(self, mapa: MapaDatos | None, cuantos: int = 10) -> list:
        from app.application.mapa_datos.informe_mapa import VersionResumen

        if mapa is None:
            return []
        filas = (await self.db.execute(
            select(MapaDatosVersion.numero, MapaDatosVersion.fecha, MapaDatosVersion.resumen)
            .where(MapaDatosVersion.mapa_id == mapa.id).order_by(MapaDatosVersion.numero.desc()).limit(cuantos))).all()
        return [VersionResumen(n, f, r) for n, f, r in filas]

    async def datos_informe(self, filtros: analisis.FiltrosMapa):
        from app.application.mapa_datos.informe_mapa import DatosInformeMapa

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
