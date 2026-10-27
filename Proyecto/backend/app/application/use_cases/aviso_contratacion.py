"""
HU-31 criterio 3 · Aviso por correo a Therion Labs de cada solicitud de contratación nueva.

- Se envía DESPUÉS del commit de la solicitud: si el correo falla, la solicitud ya quedó
  en la bandeja del administrador y la persona no ve ningún error (el aviso es interno).
- Minimización (Ley 21.719): el correo NO lleva nombre, correo ni teléfono de la persona,
  solo el número de solicitud, la empresa declarada, el cargo, el puntaje y el enlace a la
  bandeja, donde el equipo ve el contacto con su sesión de administrador. Así el contacto
  no queda copiado en buzones ni reenvíos.
- El resultado (enviado, omitido o fallido) queda en la bitácora (HU-09), sin datos personales.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.core.config import settings
from app.domain.models.bitacora_auditoria import RESULTADO_OK
from app.domain.models.resumen import Resumen
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

RESULTADO_OMITIDO = "omitido"
RESULTADO_FALLIDO = "fallido"


@dataclass(frozen=True)
class ResultadoAviso:
    enviado: bool
    modo: str | None = None
    motivo: str | None = None


def cuerpo_aviso(solicitud_id: int, empresa: str, cargo: str, evaluacion_id: int,
                 puntaje: float | None, bandeja_url: str) -> tuple[str, str, str]:
    """(asunto, texto plano, html). Sin datos de contacto de la persona."""
    p = "sin puntaje" if puntaje is None else f"{puntaje:.1f}".replace(".", ",") + " / 100"
    asunto = f"Nueva solicitud de contratación #{solicitud_id} · {empresa}"[:180]
    texto = (
        "Hola, equipo comercial:\n\n"
        f"Llegó una nueva solicitud para contratar ComplianceIA desde los resultados del autodiagnóstico.\n\n"
        f"Solicitud: #{solicitud_id}\n"
        f"Empresa declarada: {empresa}\n"
        f"Cargo de quien la envía: {cargo}\n"
        f"Evaluación vinculada: #{evaluacion_id} ({p})\n\n"
        f"Revisa el contacto y cambia el estado en la bandeja: {bandeja_url}\n\n"
        "Por protección de datos, este correo no incluye el nombre, el correo ni el teléfono de la persona.\n"
    )
    e = html.escape
    cuerpo_html = (
        "<p>Hola, equipo comercial:</p>"
        "<p>Llegó una nueva solicitud para contratar ComplianceIA desde los resultados del autodiagnóstico.</p>"
        "<ul>"
        f"<li><strong>Solicitud:</strong> #{solicitud_id}</li>"
        f"<li><strong>Empresa declarada:</strong> {e(empresa)}</li>"
        f"<li><strong>Cargo de quien la envía:</strong> {e(cargo)}</li>"
        f"<li><strong>Evaluación vinculada:</strong> #{evaluacion_id} ({e(p)})</li>"
        "</ul>"
        f'<p><a href="{e(bandeja_url, quote=True)}">Abrir la bandeja de solicitudes</a></p>'
        "<p><small>Por protección de datos, este correo no incluye el nombre, el correo ni el teléfono "
        "de la persona.</small></p>"
    )
    return asunto, texto, cuerpo_html


async def avisar_nueva_solicitud(db: AsyncSession, solicitud: SolicitudContratacion) -> ResultadoAviso:
    destino = (settings.CONTRATACION_AVISO_EMAIL or "").strip()
    if not destino:
        resultado = ResultadoAviso(enviado=False, motivo="SIN_DESTINATARIO")
    else:
        puntaje = await db.scalar(
            select(func.avg(Resumen.puntaje_obtenido)).where(Resumen.evaluacion_id == solicitud.evaluacion_id))
        asunto, texto, cuerpo_html = cuerpo_aviso(
            solicitud.id, solicitud.razon_social_declarada or "(sin empresa)", solicitud.cargo_contacto or "(sin cargo)",
            solicitud.evaluacion_id, float(puntaje) if puntaje is not None else None,
            settings.CONTRATACION_BANDEJA_URL,
        )
        try:
            modo = await correo.enviar(destino, asunto, texto, cuerpo_html, [])
            resultado = ResultadoAviso(enviado=True, modo=modo)
        except correo.CorreoNoDisponibleError:
            resultado = ResultadoAviso(enviado=False, motivo="CORREO_NO_DISPONIBLE")
        except (correo.CorreoFallidoError, ValueError) as e:
            logger.warning("No se pudo enviar el aviso de contratación (%s)", type(e).__name__)
            resultado = ResultadoAviso(enviado=False, motivo="CORREO_FALLIDO")

    BitacoraRepository(db).registrar(
        accion=Accion.SOLICITUD_CONTRATACION_AVISO, entidad="solicitud_contratacion", entidad_id=solicitud.id,
        actor_rol="sistema",
        resultado=RESULTADO_OK if resultado.enviado else (
            RESULTADO_OMITIDO if resultado.motivo == "SIN_DESTINATARIO" else RESULTADO_FALLIDO),
        detalle={"modo": resultado.modo, "motivo": resultado.motivo},
    )
    await db.commit()
    return resultado
