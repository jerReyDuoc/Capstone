"""
HU-07 — Prueba EN VIVO del test-set de alucinaciones contra el modelo configurado.

La prueba automática (tests/test_hu07_verificacion_salida.py) mide la parte determinista: que
el verificador de salida detecte cada salida problemática del test-set y no retenga las
correctas. Este script manda las mismas evidencias al modelo REAL (local con Ollama o Groq),
pasando por toda la capa de IA (NER local → prompt versionado → proveedor → verificador), y
mide lo que hace el modelo:

  tasa de alucinación     salidas con al menos una afirmación sin respaldo (según el
                          verificador) o con "cumplido/parcial" sobre una evidencia que la
                          verdad de referencia marca como sin contenido útil.  Umbral: < 2 %.
  tasa residual           alucinaciones que el verificador NO detectó (solo las ve la verdad
                          de referencia): es lo que llegaría a la organización.  Umbral: < 2 %.
  validez sintáctica      salidas que cumplen el schema y la verificación de formato.
  exactitud               clasificación del modelo igual a la verdad de referencia (informativa).
  latencia y costo        p50/p95 y tokens (el costo usa LLM_PRECIO_* del .env).

Se usan los casos distintos de (documento, declarado, justificación): las salidas del archivo
son simuladas para la prueba automática; aquí se ignoran y responde el modelo.

No toca la base de datos (métricas en memoria). Las evidencias son sintéticas.

Uso (desde Proyecto/):

    # Modelo local (perfil modelo-local del compose, LLM_PROVIDER=ollama en el .env)
    docker compose exec worker python scripts/evaluar_alucinaciones.py --salida /tmp/hu07
    # Forzar el proveedor y el modelo sin tocar el .env
    docker compose exec worker python scripts/evaluar_alucinaciones.py --proveedor ollama --modelo qwen2.5:7b-instruct
    docker compose exec worker python scripts/evaluar_alucinaciones.py --proveedor groq --limite 20
    docker compose cp worker:/tmp/hu07 ./evaluacion_hu07

Genera resultado.json (un registro por caso, sin textos) e informe.md.
Código de salida: 0 si se cumplen los umbrales, 1 si no, 2 si el modelo no respondió.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.ai.gateway import AIGateway, CapaIAError, PreciosModelo  # noqa: E402
from app.application.ai.politicas import TareaIA, crear_politicas  # noqa: E402
from app.application.ai.verificacion_salida import verificar_evidencia  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.domain.ports.registro_ia_port import ContextoLlamada, RegistroIAPort  # noqa: E402
from app.infrastructure.security.ner_sanitizer import NERSanitizer  # noqa: E402

DATASET = Path(__file__).resolve().parents[1] / "tests" / "data" / "alucinaciones_evidencias.jsonl"
UMBRAL_ALUCINACION = 0.02
UMBRAL_RESIDUAL = 0.02
FAVORABLES = ("cumplido", "parcialmente_cumplido")


class RegistroMemoria(RegistroIAPort):
    def __init__(self):
        self.llamadas = []

    async def guardar_llamada(self, registro):
        self.llamadas.append(registro)
        return len(self.llamadas)

    async def guardar_sanitizaciones(self, registros):
        pass


def _proveedor(nombre: str | None, modelo: str | None):
    if nombre:
        settings.LLM_PROVIDER = nombre
    if modelo:
        settings.LLM_MODEL = modelo
    from app.infrastructure.llm.factory import crear_proveedor
    return crear_proveedor()


def _casos(limite: int | None, todos: bool = False) -> list[dict]:
    vistos, salida = set(), []
    for linea in DATASET.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        c = json.loads(linea)
        clave = (c["documento"], c["declarado"], c["justificacion_usuario"])
        if clave in vistos and not todos:
            continue
        vistos.add(clave)
        salida.append(c)
    return salida[:limite] if limite else salida


def _percentil(v: list[float], p: float) -> float | None:
    if not v:
        return None
    v = sorted(v)
    k = (len(v) - 1) * p
    i = int(k)
    return round(v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (k - i), 1)


async def evaluar(args) -> int:
    proveedor = _proveedor(args.proveedor, args.modelo)
    registro = RegistroMemoria()
    gateway = AIGateway(
        provider=proveedor, sanitizer=NERSanitizer(), registro=registro,
        politicas=crear_politicas(max_chars_evidencia=settings.MAX_CHARS_EVIDENCIA_LLM,
                                  max_chars_justificacion=settings.MAX_CHARS_JUSTIFICACION_LLM,
                                  max_tokens_salida=settings.LLM_MAX_TOKENS_SALIDA,
                                  timeout_s=settings.LLM_TIMEOUT_S),
        sanitizer_enabled=True,
        precios=PreciosModelo(settings.LLM_PRECIO_ENTRADA_USD_1M, settings.LLM_PRECIO_SALIDA_USD_1M),
    )
    casos = _casos(args.limite, args.todos)
    print(f"Proveedor {proveedor.nombre} · modelo {proveedor.modelo_por_defecto} · {len(casos)} casos")

    filas = []
    for i, c in enumerate(casos, start=1):
        control = SimpleNamespace(**c["control"])
        respuesta = SimpleNamespace(estado_clasificacion=c["declarado"], justificacion_usuario=c["justificacion_usuario"])
        inicio = time.perf_counter()
        fila = {"id": c["id"], "documento": c["documento"], "verdad": c["verdad"]["clasificacion"]}
        try:
            r = await gateway.ejecutar(
                TareaIA.VALIDAR_EVIDENCIA,
                textos={"evidencia": c["evidencia"], "justificacion": c["justificacion_usuario"]},
                datos={"control": control, "respuesta": respuesta, "brecha": None},
                contexto=ContextoLlamada(),
            )
        except CapaIAError as e:
            fila.update(error=e.tipo_error, latencia_ms=round((time.perf_counter() - inicio) * 1000, 1))
            filas.append(fila)
            print(f"  [{i}/{len(casos)}] {c['id']} error {e.tipo_error}")
            continue
        enviados = r.textos_sanitizados
        v = verificar_evidencia(r.data, evidencia=enviados.get("evidencia"), justificacion=enviados.get("justificacion"),
                                control=control, declarado=c["declarado"])
        sin_contenido = c["verdad"].get("evidencia_suficiente") is False
        aluc_verdad = r.data.clasificacion in FAVORABLES and sin_contenido
        aluc_verif = v.alucinacion
        fila.update(
            clasificacion=r.data.clasificacion, confianza=r.data.confianza,
            exacto=r.data.clasificacion == c["verdad"]["clasificacion"],
            codigos=v.codigos, bloqueante=v.bloqueante,
            alucinacion=aluc_verif or aluc_verdad,
            residual=aluc_verdad and not aluc_verif,
            sintaxis_ok=not any(h.categoria == "salida_insegura" and h.bloqueante for h in v.hallazgos),
            latencia_ms=round((time.perf_counter() - inicio) * 1000, 1),
        )
        filas.append(fila)
        marca = "ALUCINA" if fila["alucinacion"] else ("revisión" if v.bloqueante else "ok")
        print(f"  [{i}/{len(casos)}] {c['id']} {r.data.clasificacion} ({r.data.confianza:.2f}) {marca}")

    respondidas = [f for f in filas if "error" not in f]
    if not respondidas:
        print("El modelo no respondió ningún caso (revisa el proveedor, el modelo y la red).")
        return 2
    n = len(respondidas)
    tasa = sum(f["alucinacion"] for f in respondidas) / n
    residual = sum(f["residual"] for f in respondidas) / n
    exactitud = sum(f["exacto"] for f in respondidas) / n
    sintaxis = sum(f["sintaxis_ok"] for f in respondidas) / n
    lat = [f["latencia_ms"] for f in respondidas]
    tokens_in = sum(ll.tokens_entrada or 0 for ll in registro.llamadas if ll.exito)
    tokens_out = sum(ll.tokens_salida or 0 for ll in registro.llamadas if ll.exito)
    costo = sum(ll.costo_estimado_usd or 0 for ll in registro.llamadas if ll.exito)
    codigos = Counter(c for f in respondidas for c in f["codigos"])
    resumen = {
        "proveedor": proveedor.nombre, "modelo": proveedor.modelo_por_defecto,
        "casos": len(filas), "respondidos": n, "errores": Counter(f["error"] for f in filas if "error" in f),
        "tasa_alucinacion": round(tasa, 4), "tasa_residual": round(residual, 4),
        "exactitud": round(exactitud, 4), "validez_sintactica": round(sintaxis, 4),
        "latencia_ms": {"p50": _percentil(lat, 0.5), "p95": _percentil(lat, 0.95)},
        "tokens": {"entrada": tokens_in, "salida": tokens_out}, "costo_estimado_usd": round(costo, 6),
        "hallazgos_por_codigo": dict(codigos.most_common()),
        "umbrales": {"tasa_alucinacion": UMBRAL_ALUCINACION, "tasa_residual": UMBRAL_RESIDUAL},
    }
    cumple = tasa < UMBRAL_ALUCINACION and residual < UMBRAL_RESIDUAL
    resumen["cumple"] = cumple

    destino = Path(args.salida)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "resultado.json").write_text(json.dumps({"resumen": resumen, "casos": filas}, ensure_ascii=False,
                                                       indent=2), encoding="utf-8")
    lineas = [
        "# Evaluación de alucinaciones del modelo (validación de evidencias)", "",
        f"- Proveedor / modelo: **{resumen['proveedor']} / {resumen['modelo']}**",
        f"- Casos: {len(filas)} (respondidos {n})",
        f"- Tasa de alucinación: **{tasa:.1%}** (umbral < {UMBRAL_ALUCINACION:.0%})",
        f"- Tasa residual (no detectada por el verificador): **{residual:.1%}** (umbral < {UMBRAL_RESIDUAL:.0%})",
        f"- Validez sintáctica: {sintaxis:.1%}",
        f"- Exactitud frente a la verdad de referencia: {exactitud:.1%}",
        f"- Latencia p50 / p95: {resumen['latencia_ms']['p50']} / {resumen['latencia_ms']['p95']} ms",
        f"- Tokens entrada / salida: {tokens_in} / {tokens_out} · costo estimado USD {costo:.4f}",
        f"- Resultado: **{'CUMPLE' if cumple else 'NO CUMPLE'}**", "",
        "## Hallazgos del verificador", "",
        *[f"- `{c}`: {k}" for c, k in codigos.most_common()],
        "", "## Casos con alucinación", "",
        *[f"- {f['id']} ({f['documento']}): {f['clasificacion']} · {', '.join(f['codigos']) or 'solo verdad de referencia'}"
          for f in respondidas if f["alucinacion"]],
    ]
    (destino / "informe.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas[2:11]))
    print(f"\nResultados en {destino}/resultado.json e informe.md")
    return 0 if cumple else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--proveedor", choices=["groq", "ollama"], help="por defecto, LLM_PROVIDER del .env")
    p.add_argument("--modelo", help="por defecto, LLM_MODEL del .env")
    p.add_argument("--limite", type=int, help="máximo de casos")
    p.add_argument("--todos", action="store_true",
                   help="enviar los 124 casos aunque repitan la misma entrada (por defecto, una vez cada entrada)")
    p.add_argument("--salida", default="/tmp/hu07")
    sys.exit(asyncio.run(evaluar(p.parse_args())))


if __name__ == "__main__":
    main()
