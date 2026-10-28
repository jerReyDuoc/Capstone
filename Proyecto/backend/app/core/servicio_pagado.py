"""
Acceso al servicio pagado de la empresa cliente (cursos HU-26 y remediación HU-17).

PUNTO ÚNICO para HU-30 (reglas del contrato): toda ruta del servicio pagado depende de
`empresa_con_servicio`, y la decisión de si la empresa puede usarlo vive solo en
`servicio_habilitado()`. Hoy es "contrato vigente" (fecha_inicio ≤ hoy ≤ fecha_termino),
lo mismo que ya exige el login del cliente. Cuando HU-30 agregue suspensión, renovación o
un plazo de gracia, basta con cambiar esta función (y su mensaje); las rutas no cambian.

Respuestas:
  401  sin token o sesión cerrada (lo resuelve obtener_actor)
  403  NO_AUTORIZADO           otro rol (admin, encuestado, referente)
  403  CONTRATO_NO_VIGENTE     la empresa no tiene el servicio habilitado
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.database import get_db


def servicio_habilitado(empresa, hoy: date | None = None) -> bool:
    """HU-30 extiende esta regla. Hoy: contrato vigente."""
    return bool(empresa is not None and empresa.contrato_vigente(hoy))


@dataclass(frozen=True)
class ClienteConServicio:
    actor: Actor
    usuario: object      # UsuarioDefinitivo
    empresa: object      # Empresa


async def empresa_con_servicio(
    actor: Actor = Depends(requerir_rol(Rol.CLIENTE)),
    db: AsyncSession = Depends(get_db),
) -> ClienteConServicio:
    from app.domain.models.empresa import Empresa
    from app.domain.models.usuario_definitivo import UsuarioDefinitivo

    usuario = await db.get(UsuarioDefinitivo, actor.id)
    empresa = await db.get(Empresa, usuario.empresa_id) if usuario else None
    if not servicio_habilitado(empresa):
        raise HTTPException(status_code=403, detail={
            "codigo": "CONTRATO_NO_VIGENTE",
            "mensaje": "El servicio de tu empresa no está activo. Contacta a Therion Labs para renovarlo.",
        })
    return ClienteConServicio(actor=actor, usuario=usuario, empresa=empresa)
