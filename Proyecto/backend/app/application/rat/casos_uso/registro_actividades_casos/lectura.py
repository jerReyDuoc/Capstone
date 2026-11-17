"""Lectura del registro: mapa, vista de actividades, listado y detalle."""
from __future__ import annotations

from app.domain.mapa_datos.modelo_mapa import Elemento, Flujo
from app.domain.models.rat_modelo import RatActividad
from app.domain.rat import analisis_rat as analisis, estados, modelo_actividad as modelo, riesgos
from app.domain.rat import catalogo as cat
from app.application.rat.casos_uso.registro_actividades_casos.comun import (
    logger,
    MAX_ACTIVIDADES,
    RatError,
    _iso,
    _elemento,
    _flujo,
    _evaluar,
)

class LecturaMixin:
    """Lectura del registro: mapa, vista de actividades, listado y detalle."""

    # ---------------------------------------------------------------- lectura
    async def _mapa(self) -> tuple[int, list[Elemento], list[Flujo]]:
        mapa = await self.repo.mapa(self.empresa_id)
        if mapa is None:
            return 0, [], []
        el = await self.repo.elementos_del_mapa(mapa.id)
        fl = await self.repo.flujos_del_mapa(mapa.id)
        return mapa.version, [_elemento(r) for r in el], [_flujo(r) for r in fl]

    async def _actividad(self, actividad_id: int, bloquear: bool = False) -> RatActividad:
        fila = await self.repo.actividad(actividad_id, self.empresa_id, bloquear=bloquear)
        if fila is None:                 # lo de otra empresa no existe (404, no 403)
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
        # HU-38 C1: nivel de riesgo con reglas explicables (lo que la actividad dice hoy). Sin nada elegido
        # del mapa todavía no hay con qué calcularlo (None).
        riesgo = riesgos.evaluar(f.id, f.nombre, modelo.completar(f.contenido), deriv,
                                 faltantes=len(compl["faltantes"])).como_dict() \
            if deriv["elementos"] or deriv["flujos"] else None
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
            "riesgo": riesgo if detalle or riesgo is None else {k: riesgo[k] for k in (
                "nivel", "puntaje", "probabilidad", "impacto", "requiere_pia", "motivos_pia", "mayor_riesgo")},
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
        filas = await self.repo.actividades(self.empresa_id)
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
            # HU-38 C1: cuántas actividades activas son de mayor riesgo y cuántas piden evaluación de impacto
            "riesgos": {
                "por_nivel": {n: sum(1 for v in activas if (v["riesgo"] or {}).get("nivel") == n) for n in riesgos.NIVELES},
                "mayor_riesgo": sum(1 for v in activas if (v["riesgo"] or {}).get("mayor_riesgo")),
                "pia_recomendadas": sum(1 for v in activas if (v["riesgo"] or {}).get("requiere_pia")),
                "metodologia": riesgos.METODOLOGIA, "metodologia_pia": riesgos.METODOLOGIA_PIA,
                "referencia": riesgos.REFERENCIA_MATRIZ,
            },
            "mapa": {"version": version_mapa, "elementos": len(elementos), "flujos": len(flujos),
                     "iniciado": bool(elementos)},
            "limites": {"max_actividades": MAX_ACTIVIDADES},
            # HU-40 criterio 5: estado de la revisión interna periódica (para el aviso de la lista)
            "revision_interna": await self._revision_interna(),
        }

    async def _revision_interna(self) -> dict | None:
        from app.application.rat.casos_uso.revision_interna import resumen_periodicidad

        try:
            return await resumen_periodicidad(self.db, self.empresa_id)
        except Exception:  # noqa: BLE001 - el aviso es secundario: nunca debe romper la lista del registro
            logger.exception("HU-40: no se pudo calcular el estado de la revisión interna")
            return None

    async def obtener(self, actividad_id: int) -> dict:
        f = await self._actividad(actividad_id)
        version_mapa, elementos, flujos = await self._mapa()
        return {"actividad": self._vista(f, elementos, flujos, detalle=True), "mapa": {"version": version_mapa}}
