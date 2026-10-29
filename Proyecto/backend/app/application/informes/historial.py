"""
HU-29 · Historial de evaluaciones de la empresa y su evolución (lógica PURA).

No importa SQLAlchemy ni FastAPI (se prueba sin BD en tests/test_hu29_historial_documentos.py).
La lectura de la BD está en app/application/use_cases/historial_empresa.py.

Reglas:
  - Puntaje global de una evaluación = promedio de sus dimensiones ponderado por los
    controles evaluados (la misma fórmula de GET /api/evaluaciones/{id}/resumen y del
    informe PDF), con el nivel de madurez de siempre (inicial / en_desarrollo /
    gestionado / optimizado).
  - "La más reciente" de una empresa es la de mayor id: los ids son correlativos y una
    reevaluación siempre se crea después de las evaluaciones migradas. No se usa
    fecha_migracion (las reevaluaciones no la tienen) ni fecha_inicio (es solo un día).
  - La evolución (gráfico) usa solo las evaluaciones COMPLETADAS con resultados, de la
    más antigua a la más reciente. Una reevaluación en curso aparece en el historial,
    pero no en el gráfico: su vista previa (POST /cerrar) no es un resultado definitivo.
  - Benchmark (criterio 2): de cada empresa cuenta solo su evaluación completada más
    reciente. Las evaluaciones sin empresa (encuestados anónimos) cuentan cada una,
    porque cada usuario temporal es una organización distinta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

from app.application.informes.analisis import ETIQUETA_MADUREZ, nivel_madurez

ESTADOS_CERRADOS = frozenset({"completada", "cerrada"})
ORIGEN_EMPRESA = "empresa"

TIPO_REEVALUACION = "reevaluacion"   # la inició el usuario definitivo desde la cuenta
TIPO_MIGRADA = "migrada"             # viene del autodiagnóstico (usuario temporal), HU-27


@dataclass(frozen=True)
class DimensionFila:
    dominio_id: int
    dominio: str
    puntaje: float | None
    controles: int | None
    nivel: str | None = None


@dataclass(frozen=True)
class EvaluacionFila:
    id: int
    origen: str | None
    estado: str | None
    fecha_inicio: date | None
    fecha_completado: datetime | None = None
    fecha_migracion: datetime | None = None
    dimensiones: tuple[DimensionFila, ...] = field(default_factory=tuple)

    @property
    def completada(self) -> bool:
        return self.estado in ESTADOS_CERRADOS

    @property
    def con_resultados(self) -> bool:
        return bool(self.dimensiones)

    @property
    def tipo(self) -> str:
        return TIPO_REEVALUACION if self.origen == ORIGEN_EMPRESA else TIPO_MIGRADA

    @property
    def fecha_referencia(self) -> date | None:
        """Cuándo se hizo: el día en que se completó o, si falta (anteriores a HU-29), el de inicio."""
        if self.fecha_completado is not None:
            return self.fecha_completado.date()
        return self.fecha_inicio


def puntaje_global(dimensiones: Iterable[DimensionFila]) -> float | None:
    """Promedio ponderado por controles. None si la evaluación no tiene resultados."""
    dims = list(dimensiones)
    if not dims:
        return None
    total = sum(d.controles or 0 for d in dims)
    if total:
        return round(sum((d.puntaje or 0) * (d.controles or 0) for d in dims) / total, 2)
    con_puntaje = [d.puntaje for d in dims if d.puntaje is not None]
    return round(sum(con_puntaje) / len(con_puntaje), 2) if con_puntaje else 0.0


def _iso(valor: date | datetime | None) -> str | None:
    return valor.isoformat() if valor is not None else None


def _nivel(puntaje: float | None) -> dict | None:
    if puntaje is None:
        return None
    codigo = nivel_madurez(puntaje)
    return {"codigo": codigo, "etiqueta": ETIQUETA_MADUREZ[codigo]}


def mas_reciente_completada(filas: Iterable[EvaluacionFila]) -> EvaluacionFila | None:
    candidatas = [f for f in filas if f.completada and f.con_resultados]
    return max(candidatas, key=lambda f: f.id) if candidatas else None


def construir_historial(filas: Iterable[EvaluacionFila]) -> dict:
    """
    Historial completo de la empresa: la tabla de "Mis evaluaciones" (de la más reciente a
    la más antigua) y las series del gráfico de evolución global y por dimensión.
    """
    todas = sorted(filas, key=lambda f: f.id)
    completadas = [f for f in todas if f.completada and f.con_resultados]
    vigente = completadas[-1] if completadas else None
    en_curso = next((f for f in reversed(todas) if not f.completada), None)

    globales = {f.id: puntaje_global(f.dimensiones) for f in todas}
    anterior: dict[int, float | None] = {}
    previo = None
    for f in completadas:
        anterior[f.id] = previo
        previo = globales[f.id]

    def variacion(f: EvaluacionFila) -> float | None:
        base = anterior.get(f.id)
        actual = globales[f.id]
        return round(actual - base, 2) if base is not None and actual is not None else None

    evaluaciones = []
    for f in reversed(todas):
        p = globales[f.id]
        evaluaciones.append({
            "id": f.id,
            "tipo": f.tipo,
            "origen": f.origen,
            "estado_progreso": f.estado,
            "completada": f.completada,
            "fecha": _iso(f.fecha_referencia),
            "fecha_inicio": _iso(f.fecha_inicio),
            "fecha_completado": _iso(f.fecha_completado),
            "fecha_migracion": _iso(f.fecha_migracion),
            # Una evaluación en curso puede tener una vista previa: no se informa como puntaje
            "puntaje_global": p if f.completada else None,
            "nivel": _nivel(p) if f.completada else None,
            "variacion": variacion(f) if f.completada else None,
            "vigente": vigente is not None and f.id == vigente.id,
            "dimensiones": [
                {"dominio_id": d.dominio_id, "dominio": d.dominio, "puntaje": d.puntaje,
                 "nivel": d.nivel or (nivel_madurez(d.puntaje) if d.puntaje is not None else None)}
                for d in sorted(f.dimensiones, key=lambda d: d.dominio)
            ] if f.completada else [],
        })

    # Series del gráfico: un punto por evaluación completada, de la más antigua a la más reciente
    nombres: dict[int, str] = {}
    for f in completadas:
        for d in f.dimensiones:
            nombres.setdefault(d.dominio_id, d.dominio)
    serie_global = [
        {"evaluacion_id": f.id, "fecha": _iso(f.fecha_referencia), "puntaje": globales[f.id],
         "nivel": _nivel(globales[f.id])}
        for f in completadas
    ]
    series_dimension = []
    for dominio_id, nombre in sorted(nombres.items(), key=lambda kv: kv[1]):
        puntos = []
        for f in completadas:
            d = next((x for x in f.dimensiones if x.dominio_id == dominio_id), None)
            # La dimensión puede no aplicar en una evaluación (filtro F1–F7): punto vacío
            puntos.append({"evaluacion_id": f.id, "fecha": _iso(f.fecha_referencia),
                           "puntaje": d.puntaje if d is not None else None})
        series_dimension.append({"dominio_id": dominio_id, "dominio": nombre, "puntos": puntos})

    primera = serie_global[0]["puntaje"] if serie_global else None
    ultima = serie_global[-1]["puntaje"] if serie_global else None
    return {
        "resumen": {
            "total": len(todas),
            "completadas": len(completadas),
            "evaluacion_vigente_id": vigente.id if vigente else None,
            "evaluacion_en_curso_id": en_curso.id if en_curso else None,
            "puntaje_actual": ultima,
            "nivel_actual": _nivel(ultima),
            "variacion_total": round(ultima - primera, 2)
            if len(serie_global) > 1 and primera is not None and ultima is not None else None,
        },
        "evaluaciones": evaluaciones,
        "evolucion": {"global": serie_global, "dimensiones": series_dimension},
    }


# ------------------------------------------------------------------ benchmark (criterio 2)
def evaluaciones_para_benchmark(filas: Iterable[tuple[int, int | None]]) -> set[int]:
    """
    filas: (evaluacion_id, empresa_id) de las evaluaciones que ya cumplen el resto de las
    reglas del benchmark (completadas, no de prueba). Devuelve los ids que cuentan: todas
    las que no tienen empresa y, de cada empresa, solo la más reciente (mayor id).
    """
    por_empresa: dict[int, int] = {}
    sueltas: set[int] = set()
    for evaluacion_id, empresa_id in filas:
        if empresa_id is None:
            sueltas.add(evaluacion_id)
        elif evaluacion_id > por_empresa.get(empresa_id, -1):
            por_empresa[empresa_id] = evaluacion_id
    return sueltas | set(por_empresa.values())


def mediana(valores: Iterable[float]) -> float | None:
    ordenados = sorted(v for v in valores if v is not None)
    n = len(ordenados)
    if not n:
        return None
    return ordenados[n // 2] if n % 2 else (ordenados[n // 2 - 1] + ordenados[n // 2]) / 2
