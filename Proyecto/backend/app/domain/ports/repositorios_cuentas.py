"""Puertos de repositorio de las cuentas: sesiones, credenciales, enlaces de activación/recuperación y auditores."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.models.auditoria_externa_modelo import UsuarioAuditor
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.sesion_modelo import SesionUsuario, TokenRecuperacion
from app.domain.models.usuario_admin import UsuarioAdmin
from app.domain.models.usuario_definitivo import TokenActivacion, UsuarioDefinitivo
from app.domain.models.usuario_temporal import UsuarioTemporal


class SesionRepositoryPort(Protocol):
    """Sesiones revocables (HU-28). Ninguna operación hace commit."""

    async def agregar(self, fila: SesionUsuario) -> None:
        """Agrega la sesión y hace flush (para conocer su id)."""
        ...

    async def por_sid_hash(self, sid_hash: str) -> SesionUsuario | None:
        """Sesión cuyo identificador (SHA-256) coincide, o None."""
        ...

    async def cerrar_todas(self, rol: str, actor_id: int, motivo: str, ahora: datetime) -> int:
        """Cierra las sesiones abiertas y vigentes de la cuenta; devuelve cuántas cerró."""
        ...


class CuentasRepositoryPort(Protocol):
    """Búsquedas de cuentas y datos asociados para iniciar sesión y recuperar la contraseña."""

    async def admin_por_email(self, email: str) -> UsuarioAdmin | None:
        """Administrador por correo (sin distinguir mayúsculas)."""
        ...

    async def auditor_por_email(self, email: str) -> UsuarioAuditor | None:
        """Auditor externo por correo (sin distinguir mayúsculas)."""
        ...

    async def usuario_definitivo_por_email(self, email: str) -> UsuarioDefinitivo | None:
        """Usuario definitivo por correo (sin distinguir mayúsculas)."""
        ...

    async def usuario_definitivo(self, usuario_id: int) -> UsuarioDefinitivo | None: ...

    async def usuario_temporal(self, usuario_id: int) -> UsuarioTemporal | None: ...

    async def evaluacion(self, evaluacion_id: int) -> Evaluacion | None: ...

    async def empresa(self, empresa_id: int) -> Empresa | None: ...

    async def tiene_evaluacion_publica(self, usuario_temporal_id: int) -> bool:
        """El usuario temporal es el anónimo de la encuesta pública (tiene una evaluación de origen público)."""
        ...

    async def cuenta_con_contrasena_por_id(self, rol: str, cuenta_id: int) -> UsuarioDefinitivo | UsuarioAdmin | None:
        """Cuenta del rol 'cliente' (usuario definitivo) o, en otro caso, administrador."""
        ...

    async def cuenta_con_contrasena_por_email(self, rol: str, email: str) -> UsuarioDefinitivo | UsuarioAdmin | None:
        """Igual que `cuenta_con_contrasena_por_id`, buscando por correo (sin distinguir mayúsculas)."""
        ...


class TokensCuentaRepositoryPort(Protocol):
    """Enlaces de un solo uso (activación HU-27 y recuperación HU-28). Ninguna operación hace commit."""

    async def revocar_recuperaciones_vigentes(self, rol: str, actor_id: int, ahora: datetime) -> None: ...

    async def agregar_recuperacion(self, fila: TokenRecuperacion) -> None:
        """Agrega el enlace y hace flush (para conocer su id)."""
        ...

    async def recuperacion_por_hash(self, token_hash: str) -> TokenRecuperacion | None: ...

    async def marcar_recuperacion_usada(self, token_id: int, ahora: datetime) -> int:
        """UPDATE condicional (solo si sigue sin usar ni revocar); devuelve las filas afectadas."""
        ...

    async def revocar_otras_recuperaciones(self, rol: str, actor_id: int, excepto_id: int, ahora: datetime) -> None: ...

    async def revocar_activaciones_vigentes(self, usuario_definitivo_id: int, ahora: datetime) -> None: ...

    async def agregar_activacion(self, fila: TokenActivacion) -> None:
        """Agrega el enlace y hace flush (para conocer su id)."""
        ...

    async def activacion_por_hash(self, token_hash: str) -> TokenActivacion | None: ...

    async def marcar_activacion_usada(self, token_id: int, ahora: datetime) -> int:
        """UPDATE condicional (solo si sigue sin usar ni revocar); devuelve las filas afectadas."""
        ...


class AuditoresRepositoryPort(Protocol):
    """Cuentas del Auditor Externo (HU-09). Ninguna operación hace commit."""

    async def existe_email(self, email: str) -> bool:
        """Hay una cuenta con ese correo (sin distinguir mayúsculas)."""
        ...

    async def agregar(self, auditor: UsuarioAuditor) -> None:
        """Agrega la cuenta y hace flush (para conocer su id)."""
        ...

    async def obtener(self, auditor_id: int) -> UsuarioAuditor | None: ...

    async def listar(self) -> list[UsuarioAuditor]:
        """Todas las cuentas, la más reciente (id mayor) primero."""
        ...
