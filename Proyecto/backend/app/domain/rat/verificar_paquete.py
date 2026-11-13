#!/usr/bin/env python3
"""
Verificación independiente del paquete de evidencia de una revisión interna del registro de actividades
(ComplianceIA / Therion Labs). Solo usa la librería estándar de Python 3.10+.

Uso:
    python verificar_paquete.py <carpeta descomprimida>      (o la ruta del .zip)

Comprueba:
  1. El SHA-256 de cada archivo contra manifiesto.json, y que no falten ni sobren archivos.
  2. La huella de cada versión de actividad (historial/versiones_actividades.json).
  3. La huella del registro: la recalcula desde esas versiones y la compara con la del manifiesto (la misma
     que imprimen el informe del registro y la constancia de revisión).

Sale con código 0 si todo cuadra y 1 si algo no coincide.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _lector(ruta: Path):
    if ruta.is_file() and zipfile.is_zipfile(ruta):
        z = zipfile.ZipFile(io.BytesIO(ruta.read_bytes()))
        nombres = {i.filename for i in z.infolist() if not i.is_dir()}
        return nombres, z.read
    base = ruta
    nombres = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    return nombres, lambda n: (base / n).read_bytes()


def huella_version(instantanea: dict) -> str:
    datos = {"actividad": instantanea.get("actividad", {}), "mapa": instantanea.get("mapa", {})}
    return _sha(json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def huella_registro(versiones: list[dict]) -> str:
    partes = [[v["actividad_id"], "vigente", v["numero"], v["huella"], v.get("estado", "vigente")]
              for v in sorted(versiones, key=lambda x: x["actividad_id"])]
    texto = json.dumps({"formato": 1, "actividades": partes}, ensure_ascii=False, separators=(",", ":"))
    return _sha(texto.encode("utf-8"))


def verificar(ruta: Path) -> bool:
    nombres, leer = _lector(ruta)
    if "manifiesto.json" not in nombres:
        print("✗ No se encontró manifiesto.json: ¿es la carpeta del paquete?")
        return False
    manifiesto = json.loads(leer("manifiesto.json").decode("utf-8"))
    print(f"Paquete {manifiesto.get('codigo')} · {manifiesto.get('empresa')}")
    rev = manifiesto.get("revision") or {}
    print(f"Revisión interna N.º {rev.get('numero')} ({rev.get('estado')}) · versión del registro "
          f"{rev.get('version_rat') or '—'}")
    ok = True

    esperados = manifiesto.get("archivos") or {}
    for nombre, h in sorted(esperados.items()):
        if nombre not in nombres:
            print(f"✗ Falta {nombre}")
            ok = False
        elif _sha(leer(nombre)) != h:
            print(f"✗ {nombre} fue modificado (su SHA-256 no coincide)")
            ok = False
    for nombre in sorted(nombres - set(esperados) - {"manifiesto.json"}):
        print(f"✗ Sobra {nombre} (no es parte del paquete)")
        ok = False
    if ok:
        print(f"✓ {len(esperados)} archivos íntegros (SHA-256)")

    if "historial/versiones_actividades.json" in nombres:
        versiones = json.loads(leer("historial/versiones_actividades.json").decode("utf-8")).get("versiones") or []
        malas = [v for v in versiones if huella_version(v.get("contenido") or {}) != v.get("huella")]
        for v in malas:
            print(f"✗ La versión {v.get('numero')} de la actividad {v.get('actividad_id')} no coincide con su huella")
        if not malas:
            print(f"✓ {len(versiones)} versiones de actividades coinciden con su huella")
        ok = ok and not malas
        esperada = manifiesto.get("huella_registro")
        if esperada and versiones:
            calculada = huella_registro(versiones)
            if calculada == esperada:
                print(f"✓ Huella del registro recalculada: {calculada[:16].upper()}")
            else:
                print("✗ La huella del registro recalculada no coincide con la del manifiesto")
                ok = False
    print("RESULTADO: el paquete es íntegro." if ok else "RESULTADO: el paquete NO es íntegro.")
    return ok


if __name__ == "__main__":
    try:  # la consola de Windows no siempre usa UTF-8
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(0 if verificar(Path(sys.argv[1])) else 1)
