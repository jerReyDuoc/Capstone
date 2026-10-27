"""
Verificación del CAPTCHA (Cloudflare Turnstile) en el servidor, HU-19.

Por qué Turnstile: no exige resolver imágenes (casi siempre es invisible), es gratuito
y no instala cookies de seguimiento publicitario, lo que simplifica el aviso legal
frente a la Ley 21.719.

El token del widget es de UN solo uso y vence a los 300 s. Se valida aquí (no en el
frontend) para que llamar directo a la API no lo salte.

Falla "cerrado": si Cloudflare no responde, el CAPTCHA se da por no superado.
Sin TURNSTILE_SECRET_KEY (solo development/test, en production no arranca) se omite.
"""
import logging
import uuid
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ACCION_INICIAR = "iniciar_encuesta"
ACCION_CONTRATACION = "solicitar_contratacion"  # HU-31


@dataclass(frozen=True)
class ResultadoCaptcha:
    valido: bool
    motivo: str | None = None


async def verificar_captcha(token: str, ip: str | None, accion: str = ACCION_INICIAR) -> ResultadoCaptcha:
    secreto = settings.TURNSTILE_SECRET_KEY
    if not secreto:
        logger.warning("TURNSTILE_SECRET_KEY vacío: CAPTCHA omitido (solo %s)", settings.APP_ENV)
        return ResultadoCaptcha(True, "omitido")
    if not token or len(token) > 2048:
        return ResultadoCaptcha(False, "token_ausente")

    datos = {
        "secret": secreto,
        "response": token,
        # Reintentos idempotentes: Cloudflare no lo cuenta como reutilización
        "idempotency_key": str(uuid.uuid4()),
    }
    if ip and ip != "desconocida":
        datos["remoteip"] = ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as cliente:
            r = await cliente.post(settings.TURNSTILE_VERIFY_URL, data=datos)
            cuerpo = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Turnstile no respondió (%s)", type(e).__name__)
        return ResultadoCaptcha(False, "verificador_no_disponible")

    if not cuerpo.get("success"):
        codigos = ",".join(cuerpo.get("error-codes") or []) or "rechazado"
        return ResultadoCaptcha(False, codigos)
    # La acción la fija el widget del frontend; impide reciclar un token de otro formulario
    if cuerpo.get("action") and cuerpo["action"] != accion:
        return ResultadoCaptcha(False, "accion_distinta")
    return ResultadoCaptcha(True)
