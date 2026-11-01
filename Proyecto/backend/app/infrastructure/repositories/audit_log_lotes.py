"""
HU-09 criterio 3 · Verificación de integridad del audit_log por hash en LOTE.

Sellado (worker cada AUDIT_SELLO_CADA_MIN minutos, y antes de cada exportación):
  toma las filas aún sin sellar, en orden de id, las corta en lotes de AUDIT_LOTE_TAMANO
  y por cada lote inserta un AuditLogSello con su hash_lote, su sello (encadenado al sello
  anterior) y la firma HMAC del sello. El último lote puede quedar incompleto: no se espera
  a juntar 500 filas para dejar evidencia.

  Toma el MISMO advisory lock que el encadenamiento de filas (bitacora_cadena.py). Cada
  transacción que inserta en audit_log lo conserva hasta su commit, así que al sellar no
  hay filas "en vuelo" con un id menor que otra ya confirmada.

Verificación:
  recorre el log una sola vez, en orden y de a bloques, y comprueba a la vez
    - la cadena HMAC fila a fila (HU-18): contenido alterado, eslabón roto;
    - cada lote contra su sello: cantidad, rango, hash_lote, cadena y firma de los sellos;
    - que no haya filas fuera de un lote (una fila "nueva" con id ya sellado).
  Devuelve conteos, la primera falla de la cadena y las fallas por lote (sin el contenido
  de los registros), más el ancla: último lote, sello e id. El ancla conviene anotarla
  fuera del sistema (el auditor la conserva): un borrado de las últimas filas o lotes solo
  se detecta comparando con ella.

Ninguna función hace commit: el sellado va en la transacción de quien llama.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, text

from app.core.config import settings
from app.domain import auditoria_hash
from app.domain.models.auditoria_externa import ALGORITMO_LOTE, AuditLogSello
from app.infrastructure.repositories.bitacora_cadena import LOCK_BITACORA, clave_bitacora, filas_en_orden

MAX_FALLAS_INFORMADAS = 20


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sello_dict(s: AuditLogSello) -> dict:
    return {"id": s.id, "desde_id": s.desde_id, "hasta_id": s.hasta_id, "cantidad": s.cantidad,
            "hash_lote": s.hash_lote, "sello_anterior": s.sello_anterior, "sello": s.sello,
            "firma": s.firma, "algoritmo": s.algoritmo, "fecha": s.fecha}


async def _bloquear(session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_BITACORA})


async def ultimo_sello(session) -> AuditLogSello | None:
    return (await session.execute(
        select(AuditLogSello).order_by(AuditLogSello.id.desc()).limit(1)
    )).scalar_one_or_none()


async def sellar_pendientes(session, tamano: int | None = None, ahora: datetime | None = None) -> list[AuditLogSello]:
    """Sella las filas sin lote. Devuelve los sellos nuevos (vacío si no había pendientes). NO hace commit."""
    tamano = tamano or settings.AUDIT_LOTE_TAMANO
    await _bloquear(session)
    previo = await ultimo_sello(session)
    numero = previo.id if previo else 0
    anterior = previo.sello if previo else auditoria_hash.GENESIS
    desde = previo.hasta_id if previo else 0
    clave = clave_bitacora()
    fecha = ahora or _ahora()
    nuevos: list[AuditLogSello] = []
    lote: list[dict] = []

    def cerrar() -> None:
        nonlocal numero, anterior, lote
        numero += 1
        datos = {"id": numero, "desde_id": lote[0]["id"], "hasta_id": lote[-1]["id"], "cantidad": len(lote),
                 "hash_lote": auditoria_hash.hash_lote(lote), "sello_anterior": anterior, "fecha": fecha}
        datos["sello"] = auditoria_hash.calcular_sello(datos)
        fila = AuditLogSello(**datos, firma=auditoria_hash.firmar_sello(clave, datos["sello"]), algoritmo=ALGORITMO_LOTE)
        session.add(fila)
        nuevos.append(fila)
        anterior = datos["sello"]
        lote = []

    async for f in filas_en_orden(session, desde_id=desde):
        lote.append(f)
        if len(lote) >= tamano:
            cerrar()
    if lote:
        cerrar()
    if nuevos:
        await session.flush()
    return nuevos


async def listar_sellos(session, page: int = 1, size: int = 50) -> tuple[list[AuditLogSello], int]:
    total = (await session.execute(select(func.count()).select_from(AuditLogSello))).scalar_one()
    filas = (await session.execute(
        select(AuditLogSello).order_by(AuditLogSello.id.desc()).offset((page - 1) * size).limit(size)
    )).scalars().all()
    return list(filas), total


async def sellos_que_cubren(session, desde: datetime | None, hasta: datetime | None) -> list[AuditLogSello]:
    """
    Lotes COMPLETOS que contienen al menos una fila con fecha en [desde, hasta). La
    exportación entrega lotes enteros: si se recortara un lote, su hash ya no se podría
    recalcular.
    """
    from app.domain.models.bitacora_auditoria import BitacoraAuditoria

    filtros = []
    if desde is not None:
        filtros.append(BitacoraAuditoria.fecha >= desde)
    if hasta is not None:
        filtros.append(BitacoraAuditoria.fecha < hasta)
    rango = (await session.execute(
        select(func.min(BitacoraAuditoria.id), func.max(BitacoraAuditoria.id)).where(*filtros)
    )).one()
    if rango[0] is None:
        return []
    return list((await session.execute(
        select(AuditLogSello)
        .where(AuditLogSello.hasta_id >= rango[0], AuditLogSello.desde_id <= rango[1])
        .order_by(AuditLogSello.id)
    )).scalars().all())


async def verificar_lotes(session, bloque: int = 1000) -> dict:
    """Verifica la cadena HMAC y cada lote sellado en una sola pasada (ver docstring del módulo)."""
    clave = clave_bitacora()
    sellos = [sello_dict(s) for s in (await session.execute(
        select(AuditLogSello).order_by(AuditLogSello.id))).scalars().all()]
    cadena = auditoria_hash.VerificadorCadena(clave)
    fallas: list[dict] = []
    con_falla = 0
    i = 0
    buffer: list[dict] = []
    anterior: str | None = None
    en_lotes = pendientes = fuera = 0
    primera_fuera: int | None = None

    def cerrar(s: dict) -> None:
        nonlocal anterior, con_falla
        motivo = auditoria_hash.verificar_sello(s, buffer, anterior, clave)
        if motivo:
            con_falla += 1
            if len(fallas) < MAX_FALLAS_INFORMADAS:
                fallas.append({"lote": s["id"], "desde_id": s["desde_id"], "hasta_id": s["hasta_id"], "motivo": motivo})
        anterior = s["sello"]

    async for f in filas_en_orden(session, lote=bloque):
        cadena.agregar(f)
        while i < len(sellos) and f["id"] > sellos[i]["hasta_id"]:
            cerrar(sellos[i])
            buffer = []
            i += 1
        if i < len(sellos) and f["id"] >= sellos[i]["desde_id"]:
            buffer.append(f)
            en_lotes += 1
        elif i < len(sellos):
            fuera += 1  # id anterior al lote que sigue: fila agregada después de sellar
            primera_fuera = primera_fuera or f["id"]
        else:
            pendientes += 1
    while i < len(sellos):  # lotes cuyas filas ya no están (o faltan algunas)
        cerrar(sellos[i])
        buffer = []
        i += 1

    if fuera and len(fallas) < MAX_FALLAS_INFORMADAS:
        fallas.append({"lote": None, "desde_id": primera_fuera, "hasta_id": None, "motivo": "filas_fuera_de_lote"})
    res_cadena = cadena.resultado()
    ultimo = sellos[-1] if sellos else None
    return {
        "integra": res_cadena["integra"] and con_falla == 0 and fuera == 0,
        "metodo": "hash_en_lote",
        "algoritmo": ALGORITMO_LOTE,
        "fecha_verificacion": _ahora(),
        "lotes": {"total": len(sellos), "verificados_ok": len(sellos) - con_falla, "con_falla": con_falla,
                  "fallas": fallas},
        "filas": {"total": res_cadena["total"], "en_lotes": en_lotes, "pendientes_de_sello": pendientes,
                  "fuera_de_lote": fuera},
        "cadena": res_cadena,
        "ancla": {"ultimo_lote": ultimo["id"] if ultimo else None,
                  "ultimo_sello": ultimo["sello"] if ultimo else None,
                  "ultimo_id": res_cadena["ancla"]["id"], "ultimo_hash": res_cadena["ancla"]["hash"]},
    }
