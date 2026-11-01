from datetime import datetime
from sqlalchemy import CheckConstraint, Integer, String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

RESULTADO_OK = "ok"
RESULTADO_RECHAZADO = "rechazado"
RESULTADO_ERROR = "error"          # HU-09: la acción se intentó y falló por un error del sistema
RESULTADO_OMITIDO = "omitido"      # HU-31: no se ejecutó a propósito (p. ej. aviso sin destinatario)
RESULTADOS = (RESULTADO_OK, RESULTADO_RECHAZADO, RESULTADO_ERROR, RESULTADO_OMITIDO)

# Actores sin id propio (no son una cuenta): quien no tiene token y los procesos internos.
ROLES_SIN_ID = ("anonimo", "sistema")


class BitacoraAuditoria(Base):
    """
    HU-09 · audit_log: log INMUTABLE de las acciones del sistema (Ley 21.719, art. 14 ter).

    Nació como "bitacora_auditoria" (base mínima de HU-27, cadena HMAC de HU-18); HU-09 la
    renombra a `audit_log`, que es el nombre del criterio de aceptación. La clase conserva
    su nombre para no tocar los ~40 lugares que registran acciones (alias: AuditLog).

    Cada fila: cuándo (`fecha`, UTC), quién (`actor_rol` + `actor_id`; "sistema" para los
    procesos internos), desde dónde (`ip`), qué (`accion`, `entidad`, `entidad_id`) y con qué
    `resultado` (ok / rechazado / error / omitido). Los cinco son obligatorios (criterio 2): en
    PostgreSQL los exigen restricciones CHECK y en el código `BitacoraRepository.registrar()`.

    Inmutable (criterio 1), con tres capas:
      1. Permisos: la API y el worker se conectan con un rol (DB_APP_USER) que en esta
         tabla solo tiene SELECT e INSERT. Sin UPDATE, DELETE ni TRUNCATE.
      2. Triggers: UPDATE, DELETE y TRUNCATE lanzan error, aunque los intente el dueño.
      3. Evidencia: cadena HMAC fila a fila (HU-18) y sellos SHA-256 por lote
         (audit_log_sello, criterio 3). Si alguien con superusuario desactiva los triggers
         y cambia algo, la verificación lo detecta y dice en qué lote.

    `ip` es dato personal (la única excepción de minimización de la tabla, documentada en
    app/core/catalogo_datos_personales.py). `detalle` NO lleva datos personales: ids, conteos,
    estados y códigos; nada de emails, nombres, contraseñas ni tokens.

    Las acciones de negocio se registran en la MISMA transacción que la acción: si la acción
    se revierte, su registro también, y nunca queda una acción sin registro.
    """
    __tablename__ = "audit_log"
    __table_args__ = (
        # En PostgreSQL la migración de HU-09 las crea NOT VALID: rigen para toda fila nueva
        # (las filas previas a HU-09 no tienen IP y no se pueden modificar).
        CheckConstraint("ip IS NOT NULL AND length(ip) > 0", name="ck_audit_log_ip_obligatoria"),
        CheckConstraint("resultado IN ('ok', 'rechazado', 'error', 'omitido')", name="ck_audit_log_resultado"),
        CheckConstraint("actor_rol IN ('anonimo', 'sistema') OR actor_id IS NOT NULL", name="ck_audit_log_actor"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False, index=True)
    actor_rol: Mapped[str] = mapped_column("actor_rol", String(20), nullable=False)
    actor_id: Mapped[int | None] = mapped_column("actor_id", Integer, nullable=True)
    accion: Mapped[str] = mapped_column("accion", String(60), nullable=False, index=True)
    entidad: Mapped[str] = mapped_column("entidad", String(40), nullable=False)
    entidad_id: Mapped[int | None] = mapped_column("entidad_id", Integer, nullable=True)
    resultado: Mapped[str] = mapped_column("resultado", String(10), nullable=False, default=RESULTADO_OK)
    detalle: Mapped[dict | None] = mapped_column("detalle", JSON, nullable=True)
    # HU-09: IP de origen (normalizada) o "sistema:worker" / "sistema:cli" para procesos internos
    ip: Mapped[str | None] = mapped_column("ip", String(64), nullable=True)
    # HU-18: cadena de hashes (los calcula infrastructure/repositories/bitacora_cadena.py al insertar)
    hash_anterior: Mapped[str | None] = mapped_column("hash_anterior", String(64), nullable=True)
    hash: Mapped[str | None] = mapped_column("hash", String(64), nullable=True, index=True)


AuditLog = BitacoraAuditoria
