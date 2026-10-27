"""
Bitácora de auditoría (base mínima de HU-09, creada en HU-27).

`registrar()` solo agrega la fila a la sesión: la confirma el commit de la acción de
negocio que se está auditando (misma transacción). Para un intento rechazado, el caso
de uso registra y hace commit él mismo antes de responder el error.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.domain.models.bitacora_auditoria import RESULTADO_OK, BitacoraAuditoria

# Actor "sistema" (sin token): p. ej. quien abre un enlace de activación.
ROL_SISTEMA = "sistema"
ROL_ANONIMO = "anonimo"


class Accion:
    """Acciones auditadas. HU-09 puede agregar más; no cambiar las existentes."""
    SOLICITUD_CONTRATACION_CREADA = "solicitud_contratacion.creada"
    SOLICITUD_CONTRATACION_ESTADO = "solicitud_contratacion.estado_cambiado"
    EMPRESA_CREADA = "empresa.creada"
    USUARIO_DEFINITIVO_CREADO = "usuario_definitivo.creado"
    EVALUACION_MIGRADA = "evaluacion.migrada_a_empresa"
    USUARIO_TEMPORAL_CERRADO = "usuario_temporal.cerrado_por_migracion"
    ACTIVACION_EMITIDA = "activacion.enlace_emitido"
    ACTIVACION_CORREO = "activacion.correo"
    ACTIVACION_USADA = "activacion.cuenta_activada"
    ACTIVACION_RECHAZADA = "activacion.rechazada"
    CLIENTE_LOGIN = "cliente.inicio_sesion"


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
                  fecha: datetime | None = None) -> BitacoraAuditoria:
        if detalle is not None:
            _validar_detalle(detalle)
        fila = BitacoraAuditoria(
            fecha=fecha or _ahora(),
            actor_rol=actor.rol if actor else (actor_rol or ROL_ANONIMO),
            actor_id=actor.id if actor else actor_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            resultado=resultado,
            detalle=detalle,
        )
        self.session.add(fila)
        return fila

    async def listar(self, *, entidad: str | None = None, entidad_id: int | None = None,
                     accion: str | None = None, page: int = 1, size: int = 50) -> tuple[list[BitacoraAuditoria], int]:
        filtros = []
        if entidad:
            filtros.append(BitacoraAuditoria.entidad == entidad)
        if entidad_id is not None:
            filtros.append(BitacoraAuditoria.entidad_id == entidad_id)
        if accion:
            filtros.append(BitacoraAuditoria.accion == accion)
        total = (await self.session.execute(
            select(func.count()).select_from(BitacoraAuditoria).where(*filtros)
        )).scalar_one()
        filas = (await self.session.execute(
            select(BitacoraAuditoria).where(*filtros)
            .order_by(BitacoraAuditoria.id.desc()).offset((page - 1) * size).limit(size)
        )).scalars().all()
        return list(filas), total
