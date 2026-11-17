"""Lectura del registro para el informe RAT: fuentes de actividades, mapa, rubro y marca de revisión."""
from __future__ import annotations

from datetime import datetime

from app.application.rat import armado_informe_rat as I
from app.domain.mapa_datos.modelo_mapa import Elemento, Flujo
from app.domain.models.rat_modelo import RatActividadVersion
from app.domain.rat import analisis_rat as analisis
from app.application.rat.casos_uso.generar_informe.comun import _ahora, marca_de_revision


class LecturaRegistroMixin:
    async def _rubro(self) -> str | None:
        if self.rubro_id is None:
            return None
        return await self.repo.nombre_rubro(self.rubro_id)

    async def _mapa(self) -> tuple[list[Elemento], list[Flujo]]:
        from app.application.rat.casos_uso.registro_actividades_casos import RegistroActividadesCasos

        _, els, fls = await RegistroActividadesCasos(self.db, self.cliente)._mapa()
        return els, fls

    async def _fuentes(self) -> tuple[list[I.FuenteActividad], int]:
        filas = await self.repo.actividades_no_archivadas(self.empresa_id)
        archivadas = await self.repo.contar_archivadas(self.empresa_id)
        con_vigente = [f.id for f in filas if f.version_vigente is not None]
        versiones: dict[tuple[int, int], RatActividadVersion] = {}
        if con_vigente:
            for v in await self.repo.versiones_de_actividades(con_vigente):
                versiones[(v.actividad_id, v.numero)] = v
        # HU-38: el mapa se lee siempre (también para las vigentes): la matriz de riesgos necesita saber qué
        # sistemas con IA usa cada actividad, y la instantánea no guarda el subtipo de los elementos.
        els, fls = await self._mapa() if filas else ([], [])
        fuentes = []
        for f in filas:
            v = versiones.get((f.id, f.version_vigente)) if f.version_vigente is not None else None
            if v is not None:
                fuentes.append(I.FuenteActividad(
                    id=f.id, nombre=f.nombre, estado=f.estado, version_vigente=f.version_vigente,
                    fecha_vigencia=f.fecha_vigencia, fecha_actualizacion=f.fecha_actualizacion,
                    motivos_revision=tuple(f.motivos_revision or []), instantanea=v.contenido,
                    huella_version=v.huella, fecha_version=v.fecha,
                    sistemas_ia=tuple(analisis.sistemas_ia_en((v.contenido or {}).get("mapa") or {}, els))))
            else:
                deriv = analisis.derivados(f.contenido, els, fls)
                fuentes.append(I.FuenteActividad(
                    id=f.id, nombre=f.nombre, estado=f.estado, version_vigente=None,
                    fecha_vigencia=f.fecha_vigencia, fecha_actualizacion=f.fecha_actualizacion,
                    motivos_revision=tuple(f.motivos_revision or []), contenido=f.contenido, derivados=deriv,
                    completitud=analisis.completitud(f.contenido, deriv)))
        return fuentes, int(archivadas)

    async def armar(self, generado: datetime | None = None) -> I.InformeRat:
        fuentes, archivadas = await self._fuentes()
        inf = I.armar(fuentes, generado or _ahora(), self.razon_social, self.rut, await self._rubro(), archivadas)
        # HU-40 criterio 3: si esta versión (misma huella) tiene una revisión interna, el informe lleva la marca
        return inf.con_revision(await self._marca(huella=inf.huella))

    async def _marca(self, huella: str | None = None, revision_id: int | None = None) -> I.MarcaRevision | None:
        if revision_id is None and huella is None:
            return None
        r = await self.repo.revision_revisada(self.empresa_id, revision_id=revision_id, huella=huella)
        return marca_de_revision(r)
