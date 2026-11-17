"""Middleware ASGI que fija la IP de cada petición para el audit_log (HU-09)."""
from starlette.requests import Request

from app.api.dependencias.identificacion_cliente import ip_cliente
from app.core.contexto_auditoria import fijar_ip_peticion, restablecer_ip_peticion


class ContextoAuditoriaMiddleware:
    """Middleware ASGI puro: fija la IP de la petición para toda su duración."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        token = fijar_ip_peticion(ip_cliente(Request(scope)))
        try:
            await self.app(scope, receive, send)
        finally:
            restablecer_ip_peticion(token)
