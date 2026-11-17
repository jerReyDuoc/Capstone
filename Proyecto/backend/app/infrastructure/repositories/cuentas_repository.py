"""Cuentas (admin, usuario definitivo, auditor), enlaces de activación/recuperación y datos de inicio de sesión."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth.actor import Rol
from app.domain.models.auditoria_externa_modelo import UsuarioAuditor
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.sesion_modelo import TokenRecuperacion
from app.domain.models.usuario_admin import UsuarioAdmin
from app.domain.models.usuario_definitivo import TokenActivacion, UsuarioDefinitivo
from app.domain.models.usuario_temporal import UsuarioTemporal


class CuentasRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def admin_por_email(self, email: str) -> UsuarioAdmin | None:
        result = await self.session.execute(
            select(UsuarioAdmin).where(func.lower(UsuarioAdmin.email) == email)
        )
        return result.scalar_one_or_none()

    async def auditor_por_email(self, email: str) -> UsuarioAuditor | None:
        return await self.session.scalar(select(UsuarioAuditor).where(func.lower(UsuarioAuditor.email) == email))

    async def usuario_definitivo_por_email(self, email: str) -> UsuarioDefinitivo | None:
        return await self.session.scalar(
            select(UsuarioDefinitivo).where(func.lower(UsuarioDefinitivo.email) == email)
        )

    async def usuario_definitivo(self, usuario_id: int) -> UsuarioDefinitivo | None:
        return await self.session.get(UsuarioDefinitivo, usuario_id)

    async def usuario_temporal(self, usuario_id: int) -> UsuarioTemporal | None:
        return await self.session.get(UsuarioTemporal, usuario_id)

    async def evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def empresa(self, empresa_id: int) -> Empresa | None:
        return await self.session.get(Empresa, empresa_id)

    async def tiene_evaluacion_publica(self, usuario_temporal_id: int) -> bool:
        publica = await self.session.scalar(
            select(Evaluacion.id).where(
                Evaluacion.usuario_temporal_id == usuario_temporal_id,
                Evaluacion.origen == ORIGEN_PUBLICA,
            ).limit(1)
        )
        return publica is not None

    @staticmethod
    def _modelo_cuenta(rol: str):
        return UsuarioDefinitivo if rol == Rol.CLIENTE.value else UsuarioAdmin

    async def cuenta_con_contrasena_por_id(self, rol: str, cuenta_id: int):
        return await self.session.get(self._modelo_cuenta(rol), cuenta_id)

    async def cuenta_con_contrasena_por_email(self, rol: str, email: str):
        modelo = self._modelo_cuenta(rol)
        return await self.session.scalar(select(modelo).where(func.lower(modelo.email) == email))


class TokensCuentaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------------------------------------------------------------- recuperación (HU-28)
    async def revocar_recuperaciones_vigentes(self, rol: str, actor_id: int, ahora: datetime) -> None:
        await self.session.execute(
            update(TokenRecuperacion)
            .where(TokenRecuperacion.actor_rol == rol, TokenRecuperacion.actor_id == actor_id,
                   TokenRecuperacion.fecha_uso.is_(None), TokenRecuperacion.fecha_revocacion.is_(None))
            .values(fecha_revocacion=ahora)
            .execution_options(synchronize_session=False)
        )

    async def agregar_recuperacion(self, fila: TokenRecuperacion) -> None:
        self.session.add(fila)
        await self.session.flush()

    async def recuperacion_por_hash(self, token_hash: str) -> TokenRecuperacion | None:
        return await self.session.scalar(
            select(TokenRecuperacion).where(TokenRecuperacion.token_hash == token_hash))

    async def marcar_recuperacion_usada(self, token_id: int, ahora: datetime) -> int:
        return (await self.session.execute(
            update(TokenRecuperacion)
            .where(TokenRecuperacion.id == token_id, TokenRecuperacion.fecha_uso.is_(None),
                   TokenRecuperacion.fecha_revocacion.is_(None))
            .values(fecha_uso=ahora)
            .execution_options(synchronize_session=False)
        )).rowcount

    async def revocar_otras_recuperaciones(self, rol: str, actor_id: int, excepto_id: int,
                                           ahora: datetime) -> None:
        await self.session.execute(
            update(TokenRecuperacion)
            .where(TokenRecuperacion.actor_rol == rol, TokenRecuperacion.actor_id == actor_id,
                   TokenRecuperacion.id != excepto_id,
                   TokenRecuperacion.fecha_uso.is_(None), TokenRecuperacion.fecha_revocacion.is_(None))
            .values(fecha_revocacion=ahora)
            .execution_options(synchronize_session=False)
        )

    # ---------------------------------------------------------------- activación (HU-27)
    async def revocar_activaciones_vigentes(self, usuario_definitivo_id: int, ahora: datetime) -> None:
        await self.session.execute(
            update(TokenActivacion)
            .where(TokenActivacion.usuario_definitivo_id == usuario_definitivo_id,
                   TokenActivacion.fecha_uso.is_(None), TokenActivacion.fecha_revocacion.is_(None))
            .values(fecha_revocacion=ahora)
            .execution_options(synchronize_session=False)
        )

    async def agregar_activacion(self, fila: TokenActivacion) -> None:
        self.session.add(fila)
        await self.session.flush()

    async def activacion_por_hash(self, token_hash: str) -> TokenActivacion | None:
        return await self.session.scalar(select(TokenActivacion).where(TokenActivacion.token_hash == token_hash))

    async def marcar_activacion_usada(self, token_id: int, ahora: datetime) -> int:
        return (await self.session.execute(
            update(TokenActivacion)
            .where(TokenActivacion.id == token_id, TokenActivacion.fecha_uso.is_(None),
                   TokenActivacion.fecha_revocacion.is_(None))
            .values(fecha_uso=ahora)
            .execution_options(synchronize_session=False)
        )).rowcount


class AuditoresRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def existe_email(self, email: str) -> bool:
        existe = await self.session.scalar(select(func.count()).select_from(UsuarioAuditor)
                                           .where(func.lower(UsuarioAuditor.email) == email))
        return bool(existe)

    async def agregar(self, auditor: UsuarioAuditor) -> None:
        self.session.add(auditor)
        await self.session.flush()

    async def obtener(self, auditor_id: int) -> UsuarioAuditor | None:
        return await self.session.get(UsuarioAuditor, auditor_id)

    async def listar(self) -> list[UsuarioAuditor]:
        return list((await self.session.execute(
            select(UsuarioAuditor).order_by(UsuarioAuditor.id.desc()))).scalars().all())
