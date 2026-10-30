"""
HU-10 · Comparativa sectorial con protección k-anónima.

Reglas puras (sin base de datos) para publicar estadísticas de un sector sin exponer a
las empresas que lo forman. Las usan el recálculo del benchmark (update_benchmark.py), la
comparativa de una evaluación, el panorama por sector y el informe PDF.

Qué es la "cohorte" (k)
    El número de ORGANIZACIONES DISTINTAS del rubro con puntaje en esa dimensión. No es el
    número de evaluaciones: una empresa que se reevalúa, o un encuestado que repite la
    encuesta con el mismo usuario temporal, sigue siendo UNA sola organización (cuenta su
    evaluación más reciente). Así nadie "infla" la cohorte repitiendo la encuesta.

Reglas de publicación (criterios 2 y 3)
    1. k < K_ANONIMATO_MINIMO (5)   -> se suprime TODO: promedio, mediana, percentiles,
       diferencia e incluso el valor exacto de k (solo se informa "menos de 5"). Saber que
       en un rubro hay 2 empresas ya acota quiénes son.
    2. k >= K_ANONIMATO_MINIMO      -> se publica el promedio, redondeado a entero.
    3. k >= K_ANONIMATO_DISTRIBUCION (10) -> además mediana y percentiles 25/75. Con
       cohortes chicas un percentil (o la mediana) coincide con el puntaje EXACTO de una
       empresa concreta, por eso exigen una cohorte mayor.
    Nunca se publican máximo ni mínimo: son siempre el puntaje de una sola empresa.

Por qué se redondea a entero (ataque de diferenciación)
    Si alguien observa el promedio antes y después de que una competidora complete su
    evaluación, puede despejar su puntaje: x = prom_6 * 6 - prom_5 * 5. Con 2 decimales lo
    obtiene casi exacto; con el promedio en enteros el error del despeje es de hasta ±5,5
    puntos, que ya no identifica su nivel con precisión. Ver CAMBIOS_HU10.md (riesgo residual).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

K_POR_DEFECTO = 5
K_DISTRIBUCION_POR_DEFECTO = 10

Posicion = Literal["bajo_cuartil_inferior", "franja_central", "sobre_cuartil_superior",
                   "bajo_promedio", "sobre_promedio", "en_promedio"]


# --------------------------------------------------------------- organizaciones (k)
@dataclass(frozen=True)
class FilaCandidata:
    """Una evaluación completada y no de prueba, con lo necesario para saber de quién es."""
    evaluacion_id: int
    empresa_id: int | None
    usuario_temporal_id: int | None


def clave_organizacion(f: FilaCandidata) -> str:
    """
    Identidad de la organización evaluada, de la más fuerte a la más débil:
    la empresa cliente (HU-27) manda; si no hay, el usuario temporal del encuestado; si
    tampoco (datos antiguos), la evaluación misma.
    """
    if f.empresa_id is not None:
        return f"empresa:{f.empresa_id}"
    if f.usuario_temporal_id is not None:
        return f"temporal:{f.usuario_temporal_id}"
    return f"evaluacion:{f.evaluacion_id}"


def evaluaciones_por_organizacion(filas: Iterable[FilaCandidata]) -> set[int]:
    """De cada organización cuenta solo su evaluación más reciente (mayor id)."""
    ultima: dict[str, int] = {}
    for f in filas:
        clave = clave_organizacion(f)
        if f.evaluacion_id > ultima.get(clave, -1):
            ultima[clave] = f.evaluacion_id
    return set(ultima.values())


# --------------------------------------------------------------------- estadísticas
def percentil(ordenados: list[float], q: float) -> float | None:
    """Percentil con interpolación lineal (mismo método que numpy por defecto)."""
    if not ordenados:
        return None
    pos = (len(ordenados) - 1) * q
    bajo = int(pos)
    alto = min(bajo + 1, len(ordenados) - 1)
    return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (pos - bajo)


@dataclass(frozen=True)
class Estadisticas:
    """Estadísticas internas de una cohorte. Se guardan en la tabla benchmark; NUNCA se
    publican tal cual: pasan antes por `publicar()`."""
    empresas: int
    promedio: float | None
    mediana: float | None
    p25: float | None
    p75: float | None
    maximo: float | None
    minimo: float | None


def calcular(valores: Iterable[float | None]) -> Estadisticas:
    validos = sorted(v for v in valores if v is not None)
    if not validos:
        return Estadisticas(0, None, None, None, None, None, None)
    return Estadisticas(
        empresas=len(validos),
        promedio=round(sum(validos) / len(validos), 2),
        mediana=round(percentil(validos, 0.5), 2),
        p25=round(percentil(validos, 0.25), 2),
        p75=round(percentil(validos, 0.75), 2),
        maximo=round(validos[-1], 2),
        minimo=round(validos[0], 2),
    )


# ------------------------------------------------------------------- publicación
def cohorte_suficiente(empresas: int | None, k_minimo: int = K_POR_DEFECTO) -> bool:
    return (empresas or 0) >= max(1, k_minimo)


def _entero(v: float | None) -> int | None:
    # round() de Python redondea al par (62.5 -> 62); para un tablero se espera 62.5 -> 63
    return None if v is None else int(v + 0.5) if v >= 0 else -int(-v + 0.5)


@dataclass(frozen=True)
class Publicacion:
    """Lo único que sale hacia la API, la interfaz o el PDF."""
    suficiente: bool
    empresas: int | None            # None si la cohorte es insuficiente (no se revela k)
    promedio: int | None
    mediana: int | None
    p25: int | None
    p75: int | None

    def como_dict(self) -> dict:
        return {
            "cohorte_suficiente": self.suficiente,
            "empresas": self.empresas,
            "promedio": self.promedio,
            "mediana": self.mediana,
            "percentil_25": self.p25,
            "percentil_75": self.p75,
        }


SUPRIMIDA = Publicacion(False, None, None, None, None, None)


def publicar(empresas: int | None, promedio: float | None, mediana: float | None,
             p25: float | None, p75: float | None, *,
             k_minimo: int = K_POR_DEFECTO,
             k_distribucion: int = K_DISTRIBUCION_POR_DEFECTO) -> Publicacion:
    """Aplica la supresión. Recibe los valores internos (de la tabla benchmark)."""
    if not cohorte_suficiente(empresas, k_minimo) or promedio is None:
        return SUPRIMIDA
    distribucion = (empresas or 0) >= max(k_minimo, k_distribucion)
    return Publicacion(
        suficiente=True,
        empresas=empresas,
        promedio=_entero(promedio),
        mediana=_entero(mediana) if distribucion else None,
        p25=_entero(p25) if distribucion else None,
        p75=_entero(p75) if distribucion else None,
    )


def posicion(puntaje: float | None, pub: Publicacion, tolerancia: float = 2.0) -> Posicion | None:
    """
    Dónde queda la empresa frente a su sector, sin revelar puntajes ajenos: con
    percentiles, en qué franja (cuartil inferior, mitad central, cuartil superior); si solo
    hay promedio, sobre / bajo / en el promedio (± `tolerancia` puntos).
    """
    if puntaje is None or not pub.suficiente or pub.promedio is None:
        return None
    if pub.p25 is not None and pub.p75 is not None:
        if puntaje < pub.p25:
            return "bajo_cuartil_inferior"
        if puntaje > pub.p75:
            return "sobre_cuartil_superior"
        return "franja_central"
    dif = puntaje - pub.promedio
    if abs(dif) <= tolerancia:
        return "en_promedio"
    return "sobre_promedio" if dif > 0 else "bajo_promedio"


def diferencia(puntaje: float | None, pub: Publicacion) -> float | None:
    """Puntos de la empresa frente al promedio PUBLICADO (el redondeado)."""
    if puntaje is None or not pub.suficiente or pub.promedio is None:
        return None
    return round(puntaje - pub.promedio, 1)
