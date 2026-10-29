"""
Cálculo de métricas de la capa de IA (funciones puras, sin BD).

- Operación del modelo: tasa de error (global y por tipo), latencia p50/p95,
  tokens y costo.
- Precisión del modelo: compara la clasificación del LLM con la revisión humana
  del Oficial de Cumplimiento (accuracy, precisión/recall/F1 por clase, matriz de
  confusión). Sin revisiones no hay precisión: se informa n=0.
- Tutor IA (HU-15): tipos de respuesta, tasa fuera de alcance, advertencias de la salida
  (p. ej. brechas citadas fuera del contexto) y mensajes bloqueados por prompt injection.
- Precisión del motor NER: contra un set etiquetado (gold set). Además de P/R/F1
  por tipo se reporta la "cobertura de PII": % de entidades reales que quedaron
  ocultas bajo CUALQUIER etiqueta. Es la métrica crítica: una entidad no cubierta
  es una fuga de datos personales.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

CLASES = ("cumplido", "parcialmente_cumplido", "no_cumplido")


@dataclass
class FilaLlamada:
    exito: bool
    tipo_error: str | None
    latencia_ms: float | None
    tokens_entrada: int | None
    tokens_salida: int | None
    costo_estimado_usd: float | None
    confianza: float | None
    advertencias: list | None
    sanitizado: bool


# ---------------------------------------------------------------- operación
def _percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    v = sorted(valores)
    k = (len(v) - 1) * p
    i, frac = int(k), k - int(k)
    return round(v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * frac, 2)


def resumen_operacion(filas: list[FilaLlamada], umbral_confianza: float) -> dict:
    total = len(filas)
    exitosas = [f for f in filas if f.exito]
    errores: dict[str, int] = {}
    for f in filas:
        if not f.exito:
            errores[f.tipo_error or "desconocido"] = errores.get(f.tipo_error or "desconocido", 0) + 1
    latencias = [f.latencia_ms for f in exitosas if f.latencia_ms is not None]
    baja_conf = [f for f in exitosas if f.confianza is not None and f.confianza < umbral_confianza]
    con_adv = [f for f in exitosas if f.advertencias]

    return {
        "total_llamadas": total,
        "exitosas": len(exitosas),
        "fallidas": total - len(exitosas),
        "tasa_error": round((total - len(exitosas)) / total, 4) if total else None,
        "errores_por_tipo": {
            t: {"cantidad": n, "tasa": round(n / total, 4)} for t, n in sorted(errores.items())
        },
        "tasa_baja_confianza": round(len(baja_conf) / len(exitosas), 4) if exitosas else None,
        "tasa_salida_con_advertencias": round(len(con_adv) / len(exitosas), 4) if exitosas else None,
        "llamadas_sin_sanitizar": sum(1 for f in filas if not f.sanitizado),
        "latencia_ms": {"p50": _percentil(latencias, 0.5), "p95": _percentil(latencias, 0.95)},
        "tokens": {
            "entrada": sum(f.tokens_entrada or 0 for f in exitosas),
            "salida": sum(f.tokens_salida or 0 for f in exitosas),
        },
        "costo_estimado_usd": round(sum(f.costo_estimado_usd or 0 for f in exitosas), 6),
    }


# ---------------------------------------------------------------- tutor (HU-15)
TIPOS_TUTOR = ("explicacion", "plan_accion", "orientacion", "fuera_de_alcance")


def resumen_tutor(filas: list[FilaLlamada], tipos: list[str | None], bloqueados: int) -> dict:
    """`filas` y `tipos` (llamadas_llm.clasificacion) son solo de la tarea tutor, en el mismo orden."""
    exitosas = [(f, t) for f, t in zip(filas, tipos) if f.exito]
    por_tipo = {t: 0 for t in TIPOS_TUTOR}
    adv: dict[str, int] = {}
    for f, t in exitosas:
        if t in por_tipo:
            por_tipo[t] += 1
        for a in f.advertencias or []:
            adv[a] = adv.get(a, 0) + 1
    n = len(exitosas)
    latencias = [f.latencia_ms for f, _ in exitosas if f.latencia_ms is not None]
    intentos = len(filas) + bloqueados
    return {
        "mensajes_respondidos": n,
        "mensajes_fallidos": len(filas) - n,
        "mensajes_bloqueados_inyeccion": bloqueados,   # todos los bloqueos del filtro de entrada (HU-18)
        "tasa_bloqueo_inyeccion": round(bloqueados / intentos, 4) if intentos else None,
        "respuestas_por_tipo": por_tipo,
        "tasa_fuera_de_alcance": round(por_tipo["fuera_de_alcance"] / n, 4) if n else None,
        "advertencias_por_tipo": dict(sorted(adv.items())),
        "latencia_ms": {"p50": _percentil(latencias, 0.5), "p95": _percentil(latencias, 0.95)},
    }


# ---------------------------------------------------------------- precisión del modelo
def precision_clasificacion(pares: Iterable[tuple[str, str]], clases=CLASES) -> dict:
    """`pares` = (predicho_por_llm, revisado_por_humano)."""
    pares = [(p, r) for p, r in pares if p in clases and r in clases]
    n = len(pares)
    matriz = {r: {p: 0 for p in clases} for r in clases}  # filas = real, columnas = predicho
    for p, r in pares:
        matriz[r][p] += 1

    por_clase = {}
    for c in clases:
        tp = matriz[c][c]
        fp = sum(matriz[r][c] for r in clases if r != c)
        fn = sum(matriz[c][p] for p in clases if p != c)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
        por_clase[c] = {
            "precision": _r(prec), "recall": _r(rec), "f1": _r(f1), "soporte": tp + fn,
        }

    aciertos = sum(1 for p, r in pares if p == r)
    f1s = [m["f1"] for m in por_clase.values() if m["f1"] is not None]
    return {
        "n_revisadas": n,
        "accuracy": _r(aciertos / n) if n else None,
        "tasa_error_modelo": _r(1 - aciertos / n) if n else None,
        "f1_macro": _r(sum(f1s) / len(f1s)) if f1s else None,
        "por_clase": por_clase,
        "matriz_confusion": {"filas": "revision_humana", "columnas": "llm", "valores": matriz},
    }


# ---------------------------------------------------------------- precisión del NER
@dataclass(frozen=True)
class EntidadGold:
    tipo: str
    inicio: int
    fin: int


def evaluar_ner(casos: Iterable[tuple[list[EntidadGold], list[EntidadGold]]]) -> dict:
    """
    `casos` = [(gold, predichas)] por texto, con offsets sobre el mismo texto.
    Un acierto exige mismo tipo y solapamiento de rango. La cobertura ignora el tipo.
    """
    tipos: dict[str, dict[str, int]] = {}
    gold_total = gold_cubiertas = 0

    def t(tipo):
        return tipos.setdefault(tipo, {"tp": 0, "fp": 0, "fn": 0})

    for gold, pred in casos:
        usados = set()
        for g in gold:
            gold_total += 1
            if any(p.inicio < g.fin and g.inicio < p.fin for p in pred):
                gold_cubiertas += 1
            match = next(
                (i for i, p in enumerate(pred)
                 if i not in usados and p.tipo == g.tipo and p.inicio < g.fin and g.inicio < p.fin),
                None,
            )
            if match is None:
                t(g.tipo)["fn"] += 1
            else:
                usados.add(match)
                t(g.tipo)["tp"] += 1
        for i, p in enumerate(pred):
            if i not in usados:
                t(p.tipo)["fp"] += 1

    reporte, TP, FP, FN = {}, 0, 0, 0
    for tipo, c in sorted(tipos.items()):
        TP, FP, FN = TP + c["tp"], FP + c["fp"], FN + c["fn"]
        prec = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        rec = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
        reporte[tipo] = {**c, "precision": _r(prec), "recall": _r(rec), "f1": _r(f1)}

    prec = TP / (TP + FP) if TP + FP else None
    rec = TP / (TP + FN) if TP + FN else None
    return {
        "por_tipo": reporte,
        "micro": {
            "precision": _r(prec), "recall": _r(rec),
            "f1": _r(2 * prec * rec / (prec + rec)) if prec and rec else None,
        },
        "cobertura_pii": _r(gold_cubiertas / gold_total) if gold_total else None,
        "entidades_gold": gold_total,
    }


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)
