"""HU-18: cadena de hashes en la bitácora de auditoría (registro inmutable verificable)

  - bitacora_auditoria.hash_anterior / hash   HMAC-SHA256 encadenado (app/domain/auditoria_hash.py)

Las filas existentes se encadenan aquí, en orden de id, con la misma clave que usa la
aplicación (BITACORA_CLAVE_HASH o, si está vacía, AUTH_SECRET). Para eso se desactiva un
momento el trigger de solo inserción de HU-27 (en la misma transacción de la migración).

Revision ID: c3d9a1f7e5b8
Revises: b8f1c3d5e7a2
Create Date: 2026-10-28 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d9a1f7e5b8'
down_revision: Union[str, None] = 'b8f1c3d5e7a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGER = 'trg_bitacora_auditoria_solo_insercion'


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table('bitacora_auditoria') as t:
        t.add_column(sa.Column('hash_anterior', sa.String(length=64), nullable=True))
        t.add_column(sa.Column('hash', sa.String(length=64), nullable=True))
        t.create_index('ix_bitacora_auditoria_hash', ['hash'], unique=False)

    # Encadenar lo que ya existe (offline --sql no tiene filas: se omite)
    if context_offline():
        return
    from app.domain import auditoria_hash
    from app.infrastructure.repositories.bitacora_cadena import clave_bitacora

    bind = op.get_bind()
    filas = bind.execute(sa.text(
        'SELECT id, fecha, actor_rol, actor_id, accion, entidad, entidad_id, resultado, detalle '
        'FROM bitacora_auditoria ORDER BY id')).mappings().all()
    if not filas:
        return
    if _es_postgres():
        op.execute(f'ALTER TABLE bitacora_auditoria DISABLE TRIGGER {_TRIGGER}')
    clave = clave_bitacora()
    anterior = auditoria_hash.GENESIS
    import json
    for f in filas:
        fila = dict(f)
        if isinstance(fila.get("detalle"), str):  # según el driver, JSON puede llegar como texto
            fila["detalle"] = json.loads(fila["detalle"])
        h = auditoria_hash.calcular(clave, fila, anterior)
        bind.execute(sa.text('UPDATE bitacora_auditoria SET hash_anterior = :a, hash = :h WHERE id = :i'),
                     {"a": anterior, "h": h, "i": f["id"]})
        anterior = h
    if _es_postgres():
        op.execute(f'ALTER TABLE bitacora_auditoria ENABLE TRIGGER {_TRIGGER}')


def context_offline() -> bool:
    from alembic import context
    return context.is_offline_mode()


def downgrade() -> None:
    with op.batch_alter_table('bitacora_auditoria') as t:
        t.drop_index('ix_bitacora_auditoria_hash')
        t.drop_column('hash')
        t.drop_column('hash_anterior')
