"""Puerto de credenciales: hash/verificación de contraseñas y emisión de tokens bearer."""
from __future__ import annotations

from typing import Protocol


class CredencialesPort(Protocol):
    def hash_password(self, password: str, iteraciones: int = ...) -> str: ...

    def verificar_password(self, password: str, almacenado: str) -> bool: ...

    def verificar_password_senuelo(self, password: str) -> None: ...

    def emitir_token(self, usuario_id: int, rol: str, ttl_min: int | None = None, secreto: str | None = None,
                     sid: str | None = None) -> str: ...
