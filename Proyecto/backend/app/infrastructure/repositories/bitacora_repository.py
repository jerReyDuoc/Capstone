"""
HU-09 · audit_log (nació como la bitácora mínima de HU-27).

`registrar()` solo agrega la fila a la sesión: la confirma el commit de la acción de
negocio que se está auditando (misma transacción). Para un intento rechazado, el caso
de uso registra y hace commit él mismo antes de responder el error.

Campos obligatorios de cada registro (criterio 2): fecha, actor (rol + id, o "sistema"),
IP, acción y resultado. La IP la toma sola de la petición en curso
(app/core/contexto_auditoria.py); fuera de una petición queda "sistema:worker"/"sistema:cli".
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.core.contexto_auditoria import ip_actual, normalizar_ip
from app.domain.models.bitacora_auditoria import RESULTADO_OK, RESULTADOS, ROLES_SIN_ID, BitacoraAuditoria
from app.domain.auditoria.acciones import ROL_ANONIMO, acciones_de_categoria
from app.infrastructure.repositories import bitacora_cadena  # noqa: F401  HU-18: instala la cadena de hashes


# Claves que nunca pueden ir en `detalle` (datos personales o secretos).
_CLAVES_PROHIBIDAS = frozenset({
    "email", "correo", "nombre", "telefono", "password", "contrasena", "clave", "token", "rut_persona",
})


def _validar_detalle(valor, ruta: str = "detalle") -> None:
    if isinstance(valor, dict):
        for k, v in valor.items():
            if str(k).lower() in _CLAVES_PROHIBIDAS:
                raise ValueError(f"La bitácora no admite '{k}' en {ruta}: no guarda datos personales ni secretos.")
            _validar_detalle(v, f"{ruta}.{k}")
    elif isinstance(valor, (list, tuple)):
        for i, v in enumerate(valor):
            _validar_detalle(v, f"{ruta}[{i}]")
    elif isinstance(valor, str) and "@" in valor:
        raise ValueError(f"La bitácora no admite correos en {ruta}.")


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BitacoraRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def registrar(self, *, accion: str, entidad: str, entidad_id: int | None = None,
                  actor: Actor | None = None, actor_rol: str | None = None, actor_id: int | None = None,
                  detalle: dict | None = None, resultado: str = RESULTADO_OK,
                  fecha: datetime | None = None, ip: str | None = None) -> BitacoraAuditoria:
        if detalle is not None:
            _validar_detalle(detalle)
        # HU-09 criterio 2: los campos obligatorios se validan aquí (y en PostgreSQL con CHECK)
        if not accion or not entidad:
            raise ValueError("audit_log: la acción y la entidad son obligatorias.")
        if resultado not in RESULTADOS:
            raise ValueError(f"audit_log: resultado inválido ({resultado}); debe ser uno de {', '.join(RESULTADOS)}.")
        rol = actor.rol if actor else (actor_rol or ROL_ANONIMO)
        uid = actor.id if actor else actor_id
        if uid is None and rol not in ROLES_SIN_ID:
            raise ValueError(f"audit_log: el actor '{rol}' debe llevar su id (solo anonimo y sistema van sin id).")
        fila = BitacoraAuditoria(
            fecha=fecha or _ahora(),
            actor_rol=rol,
            actor_id=uid,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            resultado=resultado,
            detalle=detalle,
            ip=normalizar_ip(ip) if ip else ip_actual(),
        )
        self.session.add(fila)
        return fila

    async def listar(self, *, entidad: str | None = None, entidad_id: int | None = None,
                     accion: str | None = None, page: int = 1, size: int = 50,
                     desde: datetime | None = None, hasta: datetime | None = None,
                     categoria: str | None = None, resultado: str | None = None,
                     actor_rol: str | None = None) -> tuple[list[BitacoraAuditoria], int]:
        filtros = []
        if entidad:
            filtros.append(BitacoraAuditoria.entidad == entidad)
        if entidad_id is not None:
            filtros.append(BitacoraAuditoria.entidad_id == entidad_id)
        if accion:
            filtros.append(BitacoraAuditoria.accion == accion)
        # HU-09: filtros del Auditor Externo
        if desde is not None:
            filtros.append(BitacoraAuditoria.fecha >= desde)
        if hasta is not None:
            filtros.append(BitacoraAuditoria.fecha < hasta)
        if categoria:
            filtros.append(BitacoraAuditoria.accion.in_(acciones_de_categoria(categoria)))
        if resultado:
            filtros.append(BitacoraAuditoria.resultado == resultado)
        if actor_rol:
            filtros.append(BitacoraAuditoria.actor_rol == actor_rol)
        total = (await self.session.execute(
            select(func.count()).select_from(BitacoraAuditoria).where(*filtros)
        )).scalar_one()
        filas = (await self.session.execute(
            select(BitacoraAuditoria).where(*filtros)
            .order_by(BitacoraAuditoria.id.desc()).offset((page - 1) * size).limit(size)
        )).scalars().all()
        return list(filas), total
