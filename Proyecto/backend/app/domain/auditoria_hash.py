"""
HU-18 · Cadena de hashes de la bitácora de auditoría (HU-09). Funciones puras, sin BD.

Cada fila guarda `hash_anterior` (el `hash` de la fila previa) y su propio `hash`:

    hash = HMAC-SHA256(clave, canónico(fecha, actor, acción, entidad, resultado, detalle) || hash_anterior)

  - Cambiar cualquier campo de una fila cambia su hash: la verificación lo detecta.
  - Borrar o insertar una fila en medio rompe el eslabón siguiente (su hash_anterior ya no
    coincide).
  - Es un HMAC con clave (no un hash simple): quien tenga acceso directo a la BD pero no la
    clave no puede recalcular la cadena para disimular un cambio.
  - Lo que la cadena sola NO detecta es que se borren las ÚLTIMAS filas; para eso la
    verificación entrega el último hash, que conviene anotar fuera del sistema (ancla).

El trigger de PostgreSQL de HU-27 ya impide UPDATE y DELETE; la cadena deja evidencia aunque
alguien lo desactive.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime

GENESIS = "0" * 64
VERSION = "v1"


def _fecha(valor) -> str:
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None).isoformat(timespec="microseconds")
    if isinstance(valor, str):  # SQLite puede devolver texto
        return datetime.fromisoformat(valor).replace(tzinfo=None).isoformat(timespec="microseconds")
    return str(valor)


def canonico(fila: dict, hash_anterior: str | None) -> bytes:
    """Representación estable de la fila (las claves ordenadas, sin espacios)."""
    datos = {
        "v": VERSION,
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
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def calcular(clave: bytes, fila: dict, hash_anterior: str | None) -> str:
    return hmac.new(clave, canonico(fila, hash_anterior), hashlib.sha256).hexdigest()


def derivar_clave(secreto: str) -> bytes:
    return hashlib.sha256(f"bitacora-auditoria|{VERSION}|{secreto}".encode()).digest()


def verificar(filas, clave: bytes) -> dict:
    """
    `filas`: iterable de dicts en orden de id (con id, hash_anterior, hash y los campos).
    Devuelve el resultado sin texto de los registros: conteos, la primera falla y el ancla.
    """
    total = sin_hash = verificadas = 0
    anterior: str | None = None
    iniciada = False
    falla = None
    ultimo = {"id": None, "hash": None}
    for f in filas:
        total += 1
        if not f.get("hash"):
            if iniciada and falla is None:
                falla = {"id": f["id"], "motivo": "fila_sin_hash"}
            sin_hash += 1
            continue
        esperado_anterior = anterior if iniciada else (f.get("hash_anterior") or GENESIS)
        if falla is None and (f.get("hash_anterior") or GENESIS) != (esperado_anterior or GENESIS):
            falla = {"id": f["id"], "motivo": "eslabon_roto"}   # se borró o insertó una fila antes
        if falla is None and not hmac.compare_digest(calcular(clave, f, f.get("hash_anterior")), f["hash"]):
            falla = {"id": f["id"], "motivo": "contenido_alterado"}
        if falla is None:
            verificadas += 1
        iniciada = True
        anterior = f["hash"]
        ultimo = {"id": f["id"], "hash": f["hash"]}
    return {
        "integra": falla is None,
        "total": total,
        "verificadas": verificadas,
        "sin_hash_previas": sin_hash,   # filas anteriores a la cadena (no deberían existir tras la migración)
        "primera_falla": falla,
        "ancla": ultimo,                 # anotar fuera del sistema para detectar borrados al final
    }
