"""
Acceso al servicio pagado de la empresa cliente según la vigencia de su contrato (HU-30).

Dos guardas, una por tipo de ruta. Las reglas viven en app/domain/contrato.py:

  empresa_con_servicio     cursos (HU-26), remediación (HU-17), espacio de la empresa (HU-28)
                           y lo que venga del servicio pagado: tutor IA y borradores.
                           Solo con contrato VIGENTE.
  empresa_con_documentos   descargar los documentos de la empresa (constancias, y los
                           borradores cuando existan). Con contrato vigente, pendiente,
                           suspendido o en plazo de gracia; no después (HU-25).

Lo gratuito (evaluación, resultados, informe PDF y plan formativo) y los derechos ARCOP NO
usan estas guardas: siguen disponibles para el cliente aunque no tenga contrato.

Respuestas:
  401  sin token o sesión cerrada (lo resuelve obtener_actor)
  403  NO_AUTORIZADO            otro rol (admin, encuestado, referente)
  403  CONTRATO_NO_VIGENTE      la empresa no tiene el servicio habilitado (con su situación
                                y, si corresponde, hasta cuándo puede descargar documentos)
  403  PLAZO_GRACIA_VENCIDO     terminó el plazo para descargar documentos
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.database import get_db


def servicio_habilitado(empresa, hoy: date | None = None) -> bool:
    """¿La empresa puede usar el servicio pagado hoy? Solo con contrato vigente."""
    return bool(empresa is not None and empresa.vigencia(hoy).servicio_habilitado)


def documentos_habilitados(empresa, hoy: date | None = None) -> bool:
    """¿Puede descargar sus documentos? Hasta el fin del plazo de gracia."""
    return bool(empresa is not None and empresa.vigencia(hoy).documentos_disponibles)


@dataclass(frozen=True)
class ClienteConServicio:
    actor: Actor
    usuario: object      # UsuarioDefinitivo
    empresa: object      # Empresa


def contrato_no_vigente(empresa, codigo: str = "CONTRATO_NO_VIGENTE") -> HTTPException:
    detalle = {"codigo": codigo, "mensaje": "El servicio de tu empresa no está activo. Contacta a Therion Labs."}
    if empresa is not None:
        v = empresa.vigencia()
        detalle.update(mensaje=v.mensaje(), situacion=v.situacion.value,
                       documentos_disponibles_hasta=v.como_dict()["documentos_disponibles_hasta"])
    return HTTPException(status_code=403, detail=detalle)


async def _cliente(actor: Actor, db: AsyncSession):
    from app.domain.models.empresa import Empresa
    from app.domain.models.usuario_definitivo import UsuarioDefinitivo

    usuario = await db.get(UsuarioDefinitivo, actor.id)
    empresa = await db.get(Empresa, usuario.empresa_id) if usuario else None
    return usuario, empresa


async def empresa_con_servicio(
    actor: Actor = Depends(requerir_rol(Rol.CLIENTE)),
    db: AsyncSession = Depends(get_db),
) -> ClienteConServicio:
    usuario, empresa = await _cliente(actor, db)
    # Por nombre del módulo (no una copia local): las pruebas pueden reemplazar la regla.
    if not servicio_habilitado(empresa):
        raise contrato_no_vigente(empresa)
    return ClienteConServicio(actor=actor, usuario=usuario, empresa=empresa)


async def empresa_con_documentos(
    actor: Actor = Depends(requerir_rol(Rol.CLIENTE)),
    db: AsyncSession = Depends(get_db),
) -> ClienteConServicio:
    usuario, empresa = await _cliente(actor, db)
    if not documentos_habilitados(empresa):
        raise contrato_no_vigente(empresa, "PLAZO_GRACIA_VENCIDO")
    return ClienteConServicio(actor=actor, usuario=usuario, empresa=empresa)
