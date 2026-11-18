"""Reportes de una evaluación: resumen, benchmark sectorial y comparativa (HU-10/HU-12/HU-29). A-41."""
from __future__ import annotations

from app.application.benchmark.sector import bloque_sector, publicar_fila
from app.application.evaluacion.casos_uso.generar_resumen import nivel_madurez
from app.application.informes.ficha import SIN_APLICABLES, orden_dimension
from app.core.config import settings
from app.domain.benchmark.k_anonimato import SUPRIMIDA, diferencia, posicion
from app.domain.ports.repositorios_consultas import ReportesPort

GENERAL = "Puntaje general"


class ReporteNoDisponibleError(Exception):
    """El recurso del reporte no existe o falta un paso previo (la ruta responde 404)."""


class ReportesEvaluacionUseCase:
    def __init__(self, repo: ReportesPort):
        self.repo = repo

    async def evaluacion_tiene_empresa(self, evaluacion_id: int) -> bool:
        return await self.repo.evaluacion_tiene_empresa(evaluacion_id)

    async def resumen(self, evaluacion_id: int) -> dict:
        """Los resúmenes guardados por dominio + puntaje general."""
        filas = await self.repo.resumenes_con_dominio(evaluacion_id)
        if not filas:
            raise ReporteNoDisponibleError("No hay resumen generado. Llama a POST /cerrar primero.")

        dominios = []
        total_controles = 0
        suma_ponderada = 0.0
        for resumen, dominio in filas:
            dominios.append({
                "dominio_id": dominio.id,
                "dominio": dominio.nombre_dominio,
                "puntaje": resumen.puntaje_obtenido,
                "nivel_madurez": resumen.nivel_madurez,
                "total_controles_evaluados": resumen.total_controles_evaluados,
            })
            total_controles += resumen.total_controles_evaluados or 0
            suma_ponderada += (resumen.puntaje_obtenido or 0) * (resumen.total_controles_evaluados or 0)

        puntaje_general = round(suma_ponderada / total_controles, 2) if total_controles > 0 else 0.0

        # T-20: siempre todas las dimensiones del catálogo (las 4 de HU-03), en orden estable.
        # Las que no tienen fila (todas sus preguntas N/A) van sin puntaje; el global no cambia
        # porque se calculó arriba solo con las filas existentes.
        for d in dominios:
            d.update(sin_controles_aplicables=False, etiqueta=None)
        con_fila = {d["dominio_id"] for d in dominios}
        for dominio in await self.repo.dominios():
            if dominio.id not in con_fila:
                dominios.append({
                    "dominio_id": dominio.id,
                    "dominio": dominio.nombre_dominio,
                    "puntaje": None,
                    "nivel_madurez": None,
                    "total_controles_evaluados": 0,
                    "sin_controles_aplicables": True,
                    "etiqueta": SIN_APLICABLES,
                })
        dominios.sort(key=lambda d: orden_dimension(d["dominio"]))
        return {
            "evaluacion_id": evaluacion_id,
            "puntaje_general": puntaje_general,
            "nivel_madurez_general": nivel_madurez(puntaje_general),
            "total_controles_evaluados": total_controles,
            "dominios": dominios,
        }

    async def benchmark(self, rubro_id: int | None = None) -> list[dict]:
        """Promedios agregados por rubro (HU-10); las cohortes < k salen suprimidas."""
        filas = await self.repo.benchmark_con_rubro_y_dominio(rubro_id)
        return [
            {
                "rubro_id": rubro.id,
                "rubro": rubro.nombre_rubro,
                "dominio_id": dominio.id if dominio else None,
                "dominio": dominio.nombre_dominio if dominio else GENERAL,
                "k_minimo": settings.K_ANONIMATO_MINIMO,
                **publicar_fila(bm).como_dict(),
            }
            for bm, rubro, dominio in filas
        ]

    async def comparativa(self, evaluacion_id: int) -> dict:
        """Compara el resumen con la meta de cumplimiento y con el sector (rubro)."""
        evaluacion = await self.repo.obtener_evaluacion(evaluacion_id)
        if not evaluacion:
            raise ReporteNoDisponibleError("Evaluación no encontrada")

        # HU-29: el rubro de la empresa (la reevaluación no tiene usuario temporal)
        rubro_id = await self.repo.rubro_id_de_evaluacion(evaluacion)
        rubro = await self.repo.obtener_rubro(rubro_id) if rubro_id is not None else None

        resumenes = await self.repo.resumenes_con_dominio(evaluacion_id)
        if not resumenes:
            raise ReporteNoDisponibleError("Genera el resumen primero con POST /cerrar")

        bench = await self.repo.benchmark_del_rubro(rubro_id)
        general = publicar_fila(bench.get(None)) if rubro_id is not None else SUPRIMIDA

        meta = settings.META_CUMPLIMIENTO_PUNTAJE
        comparativas = []
        suma = controles = 0.0
        for resumen, dominio in sorted(resumenes, key=lambda rd: rd[1].nombre_dominio or ""):
            puntaje = resumen.puntaje_obtenido
            # Si el rubro completo está suprimido, ninguna dimensión se publica (coherencia)
            pub = publicar_fila(bench.get(dominio.id)) if general.suficiente else SUPRIMIDA
            if puntaje is not None and resumen.total_controles_evaluados:
                suma += puntaje * resumen.total_controles_evaluados
                controles += resumen.total_controles_evaluados
            comparativas.append({
                "dominio_id": dominio.id,
                "dominio": dominio.nombre_dominio,
                "tu_puntaje": puntaje,
                "tu_nivel": resumen.nivel_madurez,
                "promedio_industria": pub.promedio,
                "mediana_industria": pub.mediana,
                "percentil_25": pub.p25,
                "percentil_75": pub.p75,
                "cohorte_suficiente": pub.suficiente,
                "referencia_suficiente": pub.suficiente,  # nombre previo (HU-12)
                "empresas": pub.empresas,
                "muestras": pub.empresas,                 # nombre previo; null si la cohorte es < k
                "diferencia_vs_promedio": diferencia(puntaje, pub),
                "posicion": posicion(puntaje, pub),
                "meta": meta,
                "diferencia_vs_meta": round((puntaje or 0) - meta, 2),
                "cumple_meta": (puntaje or 0) >= meta,
            })

        tu_general = round(suma / controles, 2) if controles else None
        suprimidas = sum(1 for c in comparativas if not c["cohorte_suficiente"])
        return {
            "evaluacion_id": evaluacion_id,
            "rubro_id": rubro_id,
            "meta_puntaje": meta,
            "meta_nivel": nivel_madurez(meta),
            "k_minimo": settings.K_ANONIMATO_MINIMO,
            "muestras_minimas": settings.K_ANONIMATO_MINIMO,  # nombre previo (HU-12)
            "sector": bloque_sector(rubro_id, rubro.nombre_rubro if rubro else None, bench.get(None),
                                    tu_general, suprimidas, len(comparativas)),
            "comparativas": comparativas,
        }
