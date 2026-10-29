"""
HU-18 · Encadena cada fila nueva de la bitácora con la anterior (HMAC) al hacer flush.

Funciona para TODA inserción en bitacora_auditoria, venga de donde venga (BitacoraRepository
es el único que inserta). En PostgreSQL toma un advisory lock de transacción antes de leer
el último hash: dos transacciones simultáneas no pueden encadenarse al mismo eslabón (el
lock se libera al commit o rollback). En SQLite (pruebas) no hace falta.
"""
from __future__ import annotations

from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain import auditoria_hash
from app.domain.models.bitacora_auditoria import BitacoraAuditoria

LOCK_BITACORA = 918_273_645  # identificador arbitrario del advisory lock


def clave_bitacora() -> bytes:
    secreto = settings.BITACORA_CLAVE_HASH or settings.AUTH_SECRET or settings.ENTITY_MAP_KEY or "complianceai-dev"
    return auditoria_hash.derivar_clave(secreto)


def campos(fila: BitacoraAuditoria) -> dict:
    return {"id": fila.id, "fecha": fila.fecha, "actor_rol": fila.actor_rol, "actor_id": fila.actor_id,
            "accion": fila.accion, "entidad": fila.entidad, "entidad_id": fila.entidad_id,
            "resultado": fila.resultado, "detalle": fila.detalle,
            "hash_anterior": fila.hash_anterior, "hash": fila.hash}


def _encadenar(session: Session, flush_context, instances) -> None:
    nuevas = [o for o in session.new if isinstance(o, BitacoraAuditoria) and not o.hash]
    if not nuevas:
        return
    with session.no_autoflush:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_BITACORA})
        anterior = session.execute(
            select(BitacoraAuditoria.hash).where(BitacoraAuditoria.hash.is_not(None))
            .order_by(BitacoraAuditoria.id.desc()).limit(1)
        ).scalar_one_or_none()
    clave = clave_bitacora()
    # El orden de inserción (y por lo tanto de los id) es el orden en que se agregaron
    for fila in sorted(nuevas, key=lambda o: inspect(o).insert_order or 0):
        if fila.resultado is None:
            fila.resultado = "ok"
        fila.hash_anterior = anterior or auditoria_hash.GENESIS
        fila.hash = auditoria_hash.calcular(clave, campos(fila), fila.hash_anterior)
        anterior = fila.hash


def instalar() -> None:
    if not event.contains(Session, "before_flush", _encadenar):
        event.listen(Session, "before_flush", _encadenar)


async def verificar_cadena(session, lote: int = 1000) -> dict:
    """Recorre la bitácora por id y verifica cada eslabón (sin devolver texto de los registros)."""
    async def filas():
        ultimo = 0
        while True:
            bloque = (await session.execute(
                select(BitacoraAuditoria).where(BitacoraAuditoria.id > ultimo)
                .order_by(BitacoraAuditoria.id).limit(lote)
            )).scalars().all()
            if not bloque:
                return
            for f in bloque:
                yield campos(f)
            ultimo = bloque[-1].id

    datos = [f async for f in filas()]
    return auditoria_hash.verificar(datos, clave_bitacora())


instalar()
