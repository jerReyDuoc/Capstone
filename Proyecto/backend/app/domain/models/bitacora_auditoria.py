from datetime import datetime
from sqlalchemy import Integer, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

RESULTADO_OK = "ok"
RESULTADO_RECHAZADO = "rechazado"


class BitacoraAuditoria(Base):
    """
    Bitácora de auditoría (BASE MÍNIMA de HU-09, creada en HU-27).

    Registro de solo inserción de las acciones relevantes del sistema: quién (rol e id),
    qué (acción), sobre qué (entidad e id), cuándo (UTC) y con qué resultado.

    Reglas:
      - Nunca se actualiza ni se borra. En PostgreSQL lo garantiza un trigger
        (migración b7e4d2a9c6f1); en el código solo existe `registrar()`.
      - HU-18: cada fila queda encadenada a la anterior con un HMAC (`hash_anterior`, `hash`;
        app/domain/auditoria_hash.py). Si alguien altera, borra o intercala una fila, la
        verificación (GET /api/admin/bitacora/verificacion) lo detecta.
      - `detalle` NO lleva datos personales: ids, conteos, estados y códigos. Nada de
        emails, nombres, contraseñas ni tokens (lo revisa scripts/auditoria_minimizacion.py).
      - Las acciones de negocio se registran en la MISMA transacción que la acción: si la
        acción se revierte, su registro también, y nunca queda una acción sin registro.

    HU-09 puede ampliarla (más acciones, filtros, exportación, retención).
    """
    __tablename__ = "bitacora_auditoria"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False, index=True)
    actor_rol: Mapped[str] = mapped_column("actor_rol", String(20), nullable=False)
    actor_id: Mapped[int | None] = mapped_column("actor_id", Integer, nullable=True)
    accion: Mapped[str] = mapped_column("accion", String(60), nullable=False, index=True)
    entidad: Mapped[str] = mapped_column("entidad", String(40), nullable=False)
    entidad_id: Mapped[int | None] = mapped_column("entidad_id", Integer, nullable=True)
    resultado: Mapped[str] = mapped_column("resultado", String(10), nullable=False, default=RESULTADO_OK)
    detalle: Mapped[dict | None] = mapped_column("detalle", JSON, nullable=True)
    # HU-18: cadena de hashes (los calcula infrastructure/repositories/bitacora_cadena.py al insertar)
    hash_anterior: Mapped[str | None] = mapped_column("hash_anterior", String(64), nullable=True)
    hash: Mapped[str | None] = mapped_column("hash", String(64), nullable=True, index=True)
