"""
Clave de acceso del encuestado anónimo (encuesta pública) a sus derechos ARCOP.

El encuestado no tiene cuenta ni invitación: la única forma de demostrar que es
dueño de los datos de una evaluación es una clave secreta asociada a ella.

  - Se genera con `generar_clave_acceso()` y se muestra UNA sola vez.
    (HU-19 la llamará al crear la evaluación pública; mientras tanto la emite un
    administrador con POST /api/auth/encuestado/clave.)
  - En BD solo se guarda su hash PBKDF2 (igual que las contraseñas de admin).
  - Formato legible para dictar/copiar: XXXX-XXXX-XXXX (alfabeto Crockford sin
    caracteres ambiguos, ~60 bits de azar).
  - Generar una clave nueva invalida la anterior para iniciar sesión. Al anonimizar
    la evaluación (supresión aprobada) la clave se borra y los tokens dejan de servir.
"""
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import hash_password, verificar_password
from app.domain.models.evaluacion import Evaluacion

_ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32 (sin I, L, O, U)
_TRADUCCION = str.maketrans({"O": "0", "I": "1", "L": "1"})
_GRUPOS, _LARGO_GRUPO = 3, 4


class EvaluacionNoEncontradaError(Exception):
    pass


def nueva_clave() -> str:
    grupos = (
        "".join(secrets.choice(_ALFABETO) for _ in range(_LARGO_GRUPO))
        for _ in range(_GRUPOS)
    )
    return "-".join(grupos)


def normalizar_clave(clave: str) -> str:
    """Acepta minúsculas, espacios, guiones y confusiones típicas (O/0, I/L/1)."""
    limpia = "".join(ch for ch in (clave or "").upper() if ch.isalnum()).translate(_TRADUCCION)
    return limpia


def hash_clave(clave: str) -> str:
    return hash_password(normalizar_clave(clave))


def verificar_clave(clave: str, almacenado: str | None) -> bool:
    if not almacenado:
        return False
    return verificar_password(normalizar_clave(clave), almacenado)


async def generar_clave_acceso(db: AsyncSession, evaluacion_id: int) -> str:
    """Crea (o reemplaza) la clave de la evaluación y la devuelve en claro UNA vez."""
    evaluacion = await db.get(Evaluacion, evaluacion_id)
    if evaluacion is None:
        raise EvaluacionNoEncontradaError("Evaluación no encontrada")
    clave = nueva_clave()
    evaluacion.clave_acceso_hash = hash_clave(clave)
    await db.commit()
    return clave
