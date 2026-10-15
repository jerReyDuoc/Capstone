"""
Benchmark y profiling del motor NER de anonimización (T-04: < 2,0 s por página).

Uso (desde Proyecto/backend, con el venv activo o dentro del contenedor):

    python scripts/benchmark_ner.py                     # 30 páginas de 3.000 caracteres
    python scripts/benchmark_ner.py --paginas 100 --chars 3000
    python scripts/benchmark_ner.py --evidencia 8000    # documento completo (MAX_CHARS_EVIDENCIA_LLM)
    python scripts/benchmark_ner.py --perfil            # + cProfile: funciones más costosas
    python scripts/benchmark_ner.py --json reporte.json # guarda el resultado

    # En Docker (servidor de pruebas):
    docker compose exec worker python scripts/benchmark_ner.py --paginas 100

Mide el MISMO camino que usa el worker: NERSanitizer().sanitizar(texto, max_chars),
con el modelo ya cargado (la carga se mide aparte, ocurre una sola vez al iniciar).
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import platform
import pstats
import statistics
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests"))

# Variables mínimas para importar la configuración sin un .env real
for k, v in {
    "DATABASE_URL": "postgresql+asyncpg://x:x@127.0.0.1:1/x",
    "DATABASE_URL_SYNC": "postgresql://x:x@127.0.0.1:1/x",
    "REDIS_URL": "redis://127.0.0.1:1",
    "GROQ_API_KEY": "gsk_benchmark",
}.items():
    os.environ.setdefault(k, v)

from _corpus_ner import paginas  # noqa: E402
from app.infrastructure.security import ner_sanitizer  # noqa: E402

LIMITE_S = 2.0


def _percentil(valores: list[float], p: float) -> float:
    orden = sorted(valores)
    k = (len(orden) - 1) * p
    i = int(k)
    return orden[i] if i + 1 >= len(orden) else orden[i] + (orden[i + 1] - orden[i]) * (k - i)


def medir(textos: list[str], max_chars: int | None, repeticiones: int) -> dict:
    s = ner_sanitizer.NERSanitizer()
    tiempos, entidades = [], 0
    for _ in range(repeticiones):
        for t in textos:
            ini = time.perf_counter()
            r = s.sanitizar(t, max_chars=max_chars)
            tiempos.append(time.perf_counter() - ini)
            entidades += len(r.entidades)
    total_chars = sum(len(t) for t in textos) * repeticiones
    return {
        "muestras": len(tiempos),
        "chars_por_texto": round(total_chars / len(tiempos)),
        "p50_ms": round(statistics.median(tiempos) * 1000, 1),
        "p95_ms": round(_percentil(tiempos, 0.95) * 1000, 1),
        "p99_ms": round(_percentil(tiempos, 0.99) * 1000, 1),
        "max_ms": round(max(tiempos) * 1000, 1),
        "media_ms": round(statistics.fmean(tiempos) * 1000, 1),
        "ms_por_1000_chars": round(sum(tiempos) * 1000 / (total_chars / 1000), 2),
        "entidades_por_texto": round(entidades / len(tiempos), 1),
        "motor": r.motor,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paginas", type=int, default=30)
    ap.add_argument("--chars", type=int, default=3000, help="caracteres por página")
    ap.add_argument("--evidencia", type=int, default=0,
                    help="además, mide documentos de N caracteres con max_chars=N (p. ej. 8000)")
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--perfil", action="store_true", help="imprime las 20 funciones más costosas (cProfile)")
    ap.add_argument("--json", type=str, default="", help="ruta donde guardar el reporte")
    a = ap.parse_args()

    ini = time.perf_counter()
    ner_sanitizer.cargar_spacy()
    carga_s = time.perf_counter() - ini

    reporte = {
        "entorno": {"python": platform.python_version(), "cpu": platform.processor() or platform.machine(),
                    "nucleos": os.cpu_count(), "so": platform.platform()},
        "pipeline_spacy": list(ner_sanitizer.cargar_spacy().pipe_names),
        "carga_modelo_s": round(carga_s, 2),
        "limite_por_pagina_ms": LIMITE_S * 1000,
        "pagina": medir(paginas(a.paginas, chars=a.chars), None, a.repeticiones),
    }
    if a.evidencia:
        docs = paginas(max(5, a.paginas // 5), chars=a.evidencia + 500)
        reporte["evidencia"] = medir(docs, a.evidencia, a.repeticiones)
        reporte["evidencia"]["ms_por_pagina_equivalente"] = round(
            reporte["evidencia"]["p95_ms"] * a.chars / a.evidencia, 1)

    p95 = reporte["pagina"]["p95_ms"]
    reporte["cumple_T04"] = p95 < LIMITE_S * 1000
    print(json.dumps(reporte, indent=2, ensure_ascii=False))

    if a.perfil:
        textos = paginas(min(a.paginas, 20), chars=a.chars)
        s = ner_sanitizer.NERSanitizer()
        prof = cProfile.Profile()
        prof.enable()
        for t in textos:
            s.sanitizar(t)
        prof.disable()
        salida = io.StringIO()
        pstats.Stats(prof, stream=salida).sort_stats("cumulative").print_stats(20)
        print(salida.getvalue())

    if a.json:
        Path(a.json).write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nT-04 {'CUMPLE' if reporte['cumple_T04'] else 'NO CUMPLE'}: p95 por página = {p95} ms "
          f"(límite {LIMITE_S * 1000:.0f} ms)")
    return 0 if reporte["cumple_T04"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
