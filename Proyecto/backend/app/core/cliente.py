"""
Identificación del cliente para los límites de la encuesta pública (HU-19).

El navegador nunca habla directo con esta API: pasa por el BFF de Next.js
(frontend-next/app/bff/*), que reenvía la IP real del visitante en `X-Cliente-IP`
y se identifica con `X-BFF-Secret`. Solo si ese secreto coincide se confía en la IP
reenviada; si no, se usa la IP de la conexión (un cliente directo no puede falsear
su IP para esquivar los límites).

La IP es un dato personal: no se guarda ni en BD ni en Redis. Los contadores usan
una huella HMAC-SHA256 truncada, que no permite recuperar la IP sin el secreto.
"""
import hashlib
import hmac

from fastapi import Request

from app.core.config import settings

_IP_DESCONOCIDA = "desconocida"


def viene_del_bff(request: Request) -> bool:
    secreto = settings.BFF_SHARED_SECRET
    recibido = request.headers.get("x-bff-secret", "")
    return bool(secreto) and hmac.compare_digest(recibido.encode(), secreto.encode())


def ip_cliente(request: Request) -> str:
    if viene_del_bff(request):
        ip = request.headers.get("x-cliente-ip", "").strip()
        if ip:
            return ip[:64]
    return request.client.host if request.client else _IP_DESCONOCIDA


def huella(valor: str) -> str:
    clave = (settings.AUTH_SECRET or settings.ENTITY_MAP_KEY or "complianceai-dev").encode()
    return hmac.new(clave, valor.encode(), hashlib.sha256).hexdigest()[:32]
