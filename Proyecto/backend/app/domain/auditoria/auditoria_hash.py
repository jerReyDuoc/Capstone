"""
HU-18 / HU-09 · Hashes del audit_log. Funciones puras, sin BD.

1) Cadena HMAC fila a fila (HU-18)
   Cada fila guarda `hash_anterior` (el `hash` de la fila previa) y su propio `hash`:

       hash = HMAC-SHA256(clave, canónico(fila) || hash_anterior)

     - Cambiar cualquier campo de una fila cambia su hash: la verificación lo detecta.
     - Borrar o insertar una fila en medio rompe el eslabón siguiente.
     - Es un HMAC con clave: quien tenga acceso directo a la BD pero no la clave no puede
       recalcular la cadena para disimular un cambio.

   HU-09 agrega la IP a la fila. El canónico "v2" la incluye; las filas anteriores a HU-09
   (sin IP) siguen verificándose con "v1". Poner o quitar la IP de una fila ya encadenada
   cambia su versión y por lo tanto su hash: también se detecta.

2) Hash por lote (HU-09, criterio 3) — PÚBLICO, sin clave
       huella(fila) = SHA-256("<id>|" + canónico(fila))
       hash_lote    = SHA-256("\\n".join(huella(fila) for fila in lote))
       sello        = SHA-256(canónico_sello(lote, ..., sello_anterior))
   El Auditor Externo los recalcula con el archivo exportado (verificar_exportacion.py,
   solo librería estándar). La cadena de sellos impide cambiar un lote ya sellado sin
   que cambien todos los sellos siguientes, y los sellos que el auditor ya anotó.

El trigger de PostgreSQL ya impide UPDATE, DELETE y TRUNCATE; los hashes dejan evidencia
aunque alguien con superusuario lo desactive.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime

GENESIS = "0" * 64
VERSION = "v1"         # canónico sin IP (filas anteriores a HU-09)
VERSION_IP = "v2"      # HU-09: canónico con IP
VERSION_SELLO = "s1"


def _fecha(valor) -> str:
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None).isoformat(timespec="microseconds")
    if isinstance(valor, str):  # SQLite y el archivo exportado entregan texto
        return datetime.fromisoformat(valor).replace(tzinfo=None).isoformat(timespec="microseconds")
    return str(valor)


def _json(datos: dict) -> bytes:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


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
    if fila.get("ip"):  # HU-09
        datos["v"] = VERSION_IP
        datos["ip"] = fila["ip"]
    return _json(datos)


def calcular(clave: bytes, fila: dict, hash_anterior: str | None) -> str:
    return hmac.new(clave, canonico(fila, hash_anterior), hashlib.sha256).hexdigest()


def derivar_clave(secreto: str) -> bytes:
    return hashlib.sha256(f"bitacora-auditoria|{VERSION}|{secreto}".encode()).digest()


# ------------------------------------------------------------------ HU-09: lotes
def huella_fila(fila: dict) -> str:
    """SHA-256 público de la fila: su id + el mismo canónico que firma la cadena HMAC."""
    return hashlib.sha256(f"{int(fila['id'])}|".encode() + canonico(fila, fila.get("hash_anterior"))).hexdigest()


def hash_lote(filas) -> str:
    """`filas` en orden de id. Cualquier fila borrada, agregada, alterada o movida lo cambia."""
    return hashlib.sha256("\n".join(huella_fila(f) for f in filas).encode()).hexdigest()


def canonico_sello(sello: dict) -> bytes:
    return _json({
        "v": VERSION_SELLO,
        "lote": int(sello["id"]),
        "desde_id": int(sello["desde_id"]),
        "hasta_id": int(sello["hasta_id"]),
        "cantidad": int(sello["cantidad"]),
        "hash_lote": sello["hash_lote"],
        "fecha": _fecha(sello["fecha"]),
        "anterior": sello.get("sello_anterior") or GENESIS,
    })


def calcular_sello(sello: dict) -> str:
    return hashlib.sha256(canonico_sello(sello)).hexdigest()


def firmar_sello(clave: bytes, sello: str) -> str:
    return hmac.new(clave, f"audit-log-sello|{sello}".encode(), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ verificación
class VerificadorCadena:
    """
    Verifica la cadena HMAC fila a fila, de a poco (en lotes, sin cargar toda la tabla).
    Se le pasan las filas en orden de id con `agregar()`; `resultado()` entrega el resumen.
    """

    def __init__(self, clave: bytes):
        self.clave = clave
        self.total = self.sin_hash = self.verificadas = 0
        self.anterior: str | None = None
        self.iniciada = False
        self.falla: dict | None = None
        self.ultimo = {"id": None, "hash": None}

    def agregar(self, f: dict) -> bool:
        """Verifica una fila. Devuelve False si es la primera que falla."""
        self.total += 1
        if not f.get("hash"):
            self.sin_hash += 1
            if self.iniciada and self.falla is None:
                self.falla = {"id": f["id"], "motivo": "fila_sin_hash"}
                return False
            return True
        ok = True
        esperado = self.anterior if self.iniciada else (f.get("hash_anterior") or GENESIS)
        if self.falla is None and (f.get("hash_anterior") or GENESIS) != (esperado or GENESIS):
            self.falla = {"id": f["id"], "motivo": "eslabon_roto"}   # se borró o insertó una fila antes
            ok = False
        if self.falla is None and not hmac.compare_digest(calcular(self.clave, f, f.get("hash_anterior")), f["hash"]):
            self.falla = {"id": f["id"], "motivo": "contenido_alterado"}
            ok = False
        if self.falla is None:
            self.verificadas += 1
        self.iniciada = True
        self.anterior = f["hash"]
        self.ultimo = {"id": f["id"], "hash": f["hash"]}
        return ok

    def resultado(self) -> dict:
        return {
            "integra": self.falla is None,
            "total": self.total,
            "verificadas": self.verificadas,
            "sin_hash_previas": self.sin_hash,  # filas anteriores a la cadena (no deberían existir)
            "primera_falla": self.falla,
            "ancla": self.ultimo,               # anotar fuera del sistema para detectar borrados al final
        }


def verificar(filas, clave: bytes) -> dict:
    """
    `filas`: iterable de dicts en orden de id (con id, hash_anterior, hash y los campos).
    Devuelve el resultado sin texto de los registros: conteos, la primera falla y el ancla.
    """
    v = VerificadorCadena(clave)
    for f in filas:
        v.agregar(f)
    return v.resultado()


def verificar_sello(sello: dict, filas: list[dict], sello_anterior: str | None,
                    clave: bytes | None = None) -> str | None:
    """
    Verifica UN lote: sus filas (en orden de id, solo las del rango) contra su sello.
    Devuelve None si está bien o el motivo de la primera falla.
    """
    if (sello.get("sello_anterior") or GENESIS) != (sello_anterior or GENESIS):
        return "cadena_de_sellos_rota"          # se borró, agregó o reemplazó un sello
    if not hmac.compare_digest(calcular_sello(sello), sello["sello"]):
        return "sello_alterado"                 # se cambió un dato del propio sello
    if clave is not None and not hmac.compare_digest(firmar_sello(clave, sello["sello"]), sello.get("firma") or ""):
        return "firma_invalida"                 # el sello no lo emitió el sistema
    if len(filas) != int(sello["cantidad"]):
        return "cantidad_distinta"              # se borraron o agregaron filas en el rango
    if filas and (filas[0]["id"] != sello["desde_id"] or filas[-1]["id"] != sello["hasta_id"]):
        return "rango_distinto"
    if not hmac.compare_digest(hash_lote(filas), sello["hash_lote"]):
        return "hash_lote_distinto"             # una fila del lote cambió
    return None
