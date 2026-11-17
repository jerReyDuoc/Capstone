"""Revisión interna: resumen de la revisión periódica y recordatorio diario (worker)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.informes.formato import ZONA
from app.application.rat import correo_revision as CR
from app.application.rat.casos_uso.revision_interna.comun import _ahora, _fecha_txt, _hoy_chile, _iso
from app.core.config import settings
from app.domain.auditoria.acciones import ROL_SISTEMA, Accion
from app.domain.models.rat_revision import RatRevisionConfig
from app.domain.ports.correo_port import CorreoFallidoError, CorreoNoDisponibleError
from app.domain.rat import revision as R

logger = logging.getLogger(__name__)


# ====================================================================== resumen para otras pantallas
async def resumen_periodicidad(db: AsyncSession, empresa_id: int) -> dict:
    """Estado de la revisión periódica (consultas livianas): lo muestra la lista del registro (criterio 5)."""
    repo = fabricas().revision_interna(db)
    ultima = await repo.ultima_revisada(empresa_id)
    en_curso = await repo.numero_revision_en_curso(empresa_id)
    primera = await repo.primera_vigencia(empresa_id)
    cfg = await repo.config(empresa_id)
    plazo = cfg.plazo_meses if cfg else settings.REVISION_RAT_PLAZO_MESES
    aviso = cfg.aviso_dias if cfg else settings.REVISION_RAT_AVISO_DIAS
    est = R.periodicidad(_hoy_chile(), _hoy_chile(ultima.fecha_revision) if ultima else None,
                         _hoy_chile(primera) if primera else None, plazo, aviso)
    return {**est, "plazo_meses": plazo, "en_curso": en_curso,
            "ultima": {"fecha": _iso(ultima.fecha_revision), "version_rat": ultima.version_rat,
                       "numero": ultima.numero} if ultima else None}


# ====================================================================== recordatorio diario (worker)
async def enviar_recordatorios(db: AsyncSession, ahora: datetime | None = None) -> dict:
    """
    C5: para cada empresa con contrato vigente y registro con versiones vigentes, si la revisión periódica vence
    pronto o está vencida, envía UN recordatorio por etapa (y lo repite cada REVISION_RAT_REPETIR_DIAS mientras
    siga vencida). Queda en el audit_log como acción del sistema. Un fallo en una empresa no frena a las demás.
    """
    repo = fabricas().revision_interna(db)
    ahora = ahora or datetime.now(timezone.utc)
    hoy = ahora.astimezone(ZONA).date()
    if settings.CORREO_MODO == "desactivado":
        return {"revisadas": 0, "enviados": 0, "motivo": "correo_desactivado"}
    primeras = await repo.primeras_vigencias_por_empresa()
    ultimas = await repo.ultimas_revisiones_por_empresa()
    enviados, fallidos, revisadas = 0, 0, 0
    for empresa_id in sorted(primeras):
        empresa = await repo.empresa(empresa_id)
        if empresa is None or not empresa.contrato_vigente(settings.CONTRATO_GRACIA_DIAS, hoy=hoy):
            continue
        usuario = await repo.usuario_definitivo(empresa_id)
        if usuario is None or not usuario.activo:
            continue
        revisadas += 1
        cfg = await repo.config(empresa_id)
        plazo = cfg.plazo_meses if cfg else settings.REVISION_RAT_PLAZO_MESES
        aviso = cfg.aviso_dias if cfg else settings.REVISION_RAT_AVISO_DIAS
        if cfg is not None and not cfg.recordatorio_correo:
            continue
        ultima = ultimas.get(empresa_id)
        est = R.periodicidad(hoy, _hoy_chile(ultima) if ultima else None, _hoy_chile(primeras[empresa_id]), plazo, aviso)
        etapa = R.toca_recordar(est, _hoy_chile(cfg.ultimo_recordatorio) if cfg and cfg.ultimo_recordatorio else None,
                                cfg.etapa_recordatorio if cfg else None, hoy, settings.REVISION_RAT_REPETIR_DIAS)
        if etapa is None:
            continue
        texto, html = CR.cuerpo_recordatorio(empresa.razon_social, est, plazo, _fecha_txt(ultima),
                                             settings.REVISION_RAT_URL)
        try:
            modo = await fabricas().correo.enviar(usuario.email, CR.asunto_recordatorio(est["estado"], empresa.razon_social),
                                       texto, html, [])
        except (CorreoFallidoError, CorreoNoDisponibleError, ValueError) as e:
            fallidos += 1
            logger.warning("[revision_rat] recordatorio fallido empresa %s: %s", empresa_id, type(e).__name__)
            continue
        if cfg is None:
            cfg = RatRevisionConfig(empresa_id=empresa_id, plazo_meses=plazo, aviso_dias=aviso, recordatorio_correo=True,
                                    fecha_actualizacion=_ahora())
            db.add(cfg)
        # Con la fecha de esta corrida (no la del reloj): así la repetición cada N días se cuenta bien
        cfg.ultimo_recordatorio = ahora.astimezone(timezone.utc).replace(tzinfo=None)
        cfg.etapa_recordatorio = etapa
        fabricas().bitacora(db).registrar(
            accion=Accion.REVISION_RAT_RECORDATORIO, entidad="rat_revision_config", entidad_id=empresa_id,
            actor_rol=ROL_SISTEMA, detalle={"estado": est["estado"], "vence": est["vence"], "dias": est["dias"],
                                            "plazo_meses": plazo, "modo": modo})
        await db.commit()
        enviados += 1
    return {"revisadas": revisadas, "enviados": enviados, "fallidos": fallidos}
