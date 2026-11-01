#!/usr/bin/env python3
"""
Verificación INDEPENDIENTE de una exportación del audit_log de ComplianceIA (HU-09).

Para el Auditor Externo: no necesita acceso al sistema ni claves, solo Python 3.10+ (librería
estándar). Uso, en la carpeta donde descomprimió el ZIP:

    python verificar_exportacion.py .
    python verificar_exportacion.py . --ancla <sello anotado en una exportación anterior>

Comprueba:
  1. El SHA-256 de cada archivo contra manifiesto.json.
  2. Por cada lote: que sus registros (audit_log.jsonl) sean exactamente `cantidad`, desde
     `desde_id` hasta `hasta_id`, y que el hash del lote recalculado sea `hash_lote`.
     Cualquier registro alterado, agregado, quitado o reordenado cambia ese hash.
  3. La cadena de sellos: cada sello se recalcula con sus datos y apunta al anterior.
  4. El enlace entre registros: el hash_anterior de cada uno es el hash del previo.
  5. Con --ancla: que ese sello (de una exportación anterior) aparezca idéntico.

Lo que este script NO puede comprobar es la firma HMAC de cada registro y de cada sello
(requiere la clave del sistema): ese resultado viene en verificacion.json.

Código de salida: 0 si todo está bien, 1 si hay alguna falla, 2 si faltan archivos.
Este archivo es una copia exacta de app/domain/verificar_exportacion.py del sistema.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

GENESIS = "0" * 64


# ---------------------------------------------------------------- mismo canónico que el sistema
def _fecha(valor) -> str:
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None).isoformat(timespec="microseconds")
    if isinstance(valor, str):
        return datetime.fromisoformat(valor).replace(tzinfo=None).isoformat(timespec="microseconds")
    return str(valor)


def _json(datos: dict) -> bytes:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def canonico(fila: dict, hash_anterior: str | None) -> bytes:
    datos = {
        "v": "v1",
        "fecha": _fecha(fila.get("fecha")),
        "actor_rol": fila.get("actor_rol"),
        "actor_id": fila.get("actor_id"),
        "accion": fila.get("accion"),
        "entidad": fila.get("entidad"),
        "entidad_id": fila.get("entidad_id"),
        "resultado": fila.get("resultado"),
        "detalle": fila.get("detalle"),
        "anterior": hash_anterior or GENESIS,
    }
    if fila.get("ip"):
        datos["v"] = "v2"
        datos["ip"] = fila["ip"]
    return _json(datos)


def huella_fila(fila: dict) -> str:
    return hashlib.sha256(f"{int(fila['id'])}|".encode() + canonico(fila, fila.get("hash_anterior"))).hexdigest()


def hash_lote(filas) -> str:
    return hashlib.sha256("\n".join(huella_fila(f) for f in filas).encode()).hexdigest()


def calcular_sello(s: dict) -> str:
    return hashlib.sha256(_json({
        "v": "s1", "lote": int(s["id"]), "desde_id": int(s["desde_id"]), "hasta_id": int(s["hasta_id"]),
        "cantidad": int(s["cantidad"]), "hash_lote": s["hash_lote"], "fecha": _fecha(s["fecha"]),
        "anterior": s.get("sello_anterior") or GENESIS,
    })).hexdigest()


# ---------------------------------------------------------------- verificación
def verificar(carpeta: Path, ancla: str | None = None) -> dict:
    fallas: list[str] = []
    faltan = [n for n in ("manifiesto.json", "audit_log.jsonl", "lotes.json") if not (carpeta / n).is_file()]
    if faltan:
        return {"ok": False, "faltan_archivos": faltan, "fallas": [f"falta el archivo {n}" for n in faltan]}

    manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    for nombre, esperado in manifiesto.get("archivos", {}).items():
        ruta = carpeta / nombre
        if not ruta.is_file():
            fallas.append(f"{nombre}: falta (está en el manifiesto)")
        elif hashlib.sha256(ruta.read_bytes()).hexdigest() != esperado:
            fallas.append(f"{nombre}: su SHA-256 no coincide con el manifiesto (archivo modificado)")

    registros = [json.loads(l) for l in (carpeta / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    lotes = json.loads((carpeta / "lotes.json").read_text(encoding="utf-8"))
    if manifiesto.get("registros") is not None and manifiesto["registros"] != len(registros):
        fallas.append(f"el manifiesto declara {manifiesto['registros']} registros y el archivo trae {len(registros)}")

    ids = [r["id"] for r in registros]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        fallas.append("los registros no están en orden de id o hay ids repetidos")
    for previo, actual in zip(registros, registros[1:]):
        if actual.get("hash_anterior") != previo.get("hash"):
            fallas.append(f"registro {actual['id']}: su hash_anterior no es el hash del registro {previo['id']} "
                          "(falta un registro entre ambos o se alteró)")
            break

    anterior = manifiesto.get("sello_anterior_al_primer_lote") or GENESIS
    usados = 0
    for s in lotes:
        if (s.get("sello_anterior") or GENESIS) != anterior:
            fallas.append(f"lote {s['id']}: no apunta al sello del lote anterior (cadena de sellos rota)")
        if calcular_sello(s) != s["sello"]:
            fallas.append(f"lote {s['id']}: el sello no corresponde a sus datos (sello alterado)")
        ini = bisect.bisect_left(ids, s["desde_id"])
        fin = bisect.bisect_right(ids, s["hasta_id"])
        del_lote = registros[ini:fin]
        usados += len(del_lote)
        if len(del_lote) != int(s["cantidad"]):
            fallas.append(f"lote {s['id']}: trae {len(del_lote)} registros y el sello dice {s['cantidad']}")
        elif hash_lote(del_lote) != s["hash_lote"]:
            fallas.append(f"lote {s['id']}: el hash recalculado no coincide (algún registro fue alterado)")
        anterior = s["sello"]
    if usados != len(registros):
        fallas.append(f"{len(registros) - usados} registros no pertenecen a ningún lote")
    if lotes and manifiesto.get("ultimo_sello") not in (None, lotes[-1]["sello"]):
        fallas.append("el último sello del manifiesto no es el del último lote")

    ancla_ok = None
    if ancla:
        ancla_ok = any(s["sello"] == ancla.strip().lower() for s in lotes)
        if not ancla_ok:
            primero = lotes[0]["id"] if lotes else None
            fallas.append(f"el sello ancla no aparece en esta exportación (si es de un lote anterior al {primero}, "
                          "exporte un rango que lo incluya)")

    verificacion = {}
    if (carpeta / "verificacion.json").is_file():
        verificacion = json.loads((carpeta / "verificacion.json").read_text(encoding="utf-8"))
    return {
        "ok": not fallas,
        "registros": len(registros),
        "lotes": len(lotes),
        "primer_lote": lotes[0]["id"] if lotes else None,
        "ultimo_lote": lotes[-1]["id"] if lotes else None,
        "ultimo_sello": lotes[-1]["sello"] if lotes else None,
        "ancla_encontrada": ancla_ok,
        "verificacion_del_sistema_integra": verificacion.get("integra"),
        "fallas": fallas,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verifica una exportación del audit_log de ComplianceIA (HU-09).")
    p.add_argument("carpeta", nargs="?", default=".", help="carpeta con los archivos del ZIP")
    p.add_argument("--ancla", help="sello de una exportación anterior que debe seguir igual")
    p.add_argument("--json", action="store_true", help="imprime el resultado en JSON")
    a = p.parse_args(argv)
    r = verificar(Path(a.carpeta), a.ancla)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(f"Registros: {r.get('registros')}  Lotes: {r.get('lotes')} "
              f"({r.get('primer_lote')} a {r.get('ultimo_lote')})")
        print(f"Último sello (anótelo como ancla): {r.get('ultimo_sello')}")
        if r.get("verificacion_del_sistema_integra") is not None:
            print(f"Verificación del sistema al exportar (incluye firmas HMAC): "
                  f"{'ÍNTEGRO' if r['verificacion_del_sistema_integra'] else 'CON FALLAS'}")
        if r["ok"]:
            print("RESULTADO: OK — los hashes de lote, la cadena de sellos y los archivos coinciden.")
        else:
            print("RESULTADO: FALLA")
            for f in r["fallas"]:
                print(f"  - {f}")
    if r.get("faltan_archivos"):
        return 2
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
