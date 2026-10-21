"""
Límites contra abuso de la encuesta pública (HU-19 criterio 3).

Solo aplican a evaluaciones con origen='publica': las de invitación ya están
controladas por la propia invitación.

  - Evidencias: máximo por evaluación (cuenta en BD) y por IP y día (Redis).
  - Cuota diaria de validaciones con IA: cada evidencia subida dispara una validación
    con el LLM. Se cuenta por evaluación y en total (tope de costo de toda la encuesta
    pública). Se reinicia a medianoche de ZONA_HORARIA_CUOTAS.

Se RESERVA antes de guardar el archivo y se DEVUELVE si la subida falla, así un
archivo rechazado (vacío, clasificación sin evidencia, etc.) no gasta cuota.
Los reintentos internos del LLM (LLM_REINTENTOS_SALIDA) no cuentan: la cuota es de
validaciones, que es lo que la persona percibe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone, tzinfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cliente import huella
from app.core.config import settings
from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
from app.domain.models.evidencia import Evidencia
from app.domain.models.respuesta import Respuesta
from app.infrastructure.cache.limitador import Limitador


def zona_cuotas() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(settings.ZONA_HORARIA_CUOTAS)
    except Exception:  # noqa: BLE001  (imagen sin tzdata): Chile continental UTC-3
        return timezone(timedelta(hours=-3))


def ventana_diaria(ahora: datetime | None = None) -> tuple[str, int, datetime]:
    """(fecha local AAAA-MM-DD, segundos hasta medianoche local, momento del reinicio en UTC)."""
    tz = zona_cuotas()
    local = (ahora or datetime.now(timezone.utc)).astimezone(tz)
    reinicio = datetime.combine(local.date() + timedelta(days=1), dtime.min, tzinfo=tz)
    segundos = max(60, int((reinicio - local).total_seconds()))
    return local.date().isoformat(), segundos, reinicio.astimezone(timezone.utc)


class LimiteEncuestaError(Exception):
    def __init__(self, mensaje: str, codigo: str, reintentar_en_s: int | None = None,
                 reinicia_en: datetime | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.reintentar_en_s = reintentar_en_s
        self.reinicia_en = reinicia_en


@dataclass
class Reserva:
    limitador: Limitador
    claves: list[str] = field(default_factory=list)

    async def devolver(self) -> None:
        for clave in self.claves:
            await self.limitador.devolver(clave)
        self.claves.clear()


class LimitesEncuesta:
    def __init__(self, db: AsyncSession, limitador: Limitador):
        self.db = db
        self.limitador = limitador

    async def es_publica(self, evaluacion_id: int) -> bool:
        origen = await self.db.scalar(select(Evaluacion.origen).where(Evaluacion.id == evaluacion_id))
        return origen == ORIGEN_PUBLICA

    async def evidencias_usadas(self, evaluacion_id: int) -> int:
        return int(await self.db.scalar(
            select(func.count(Evidencia.id_evidencia))
            .join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .where(Respuesta.evaluacion_id == evaluacion_id)
        ) or 0)

    async def reservar_evidencia(self, respuesta_id: int, ip: str) -> Reserva | None:
        """None si la evaluación no es pública (sin límites) o la respuesta no existe."""
        evaluacion_id = await self.db.scalar(select(Respuesta.evaluacion_id).where(Respuesta.id == respuesta_id))
        if evaluacion_id is None or not await self.es_publica(evaluacion_id):
            return None

        if await self.evidencias_usadas(evaluacion_id) >= settings.ENCUESTA_MAX_EVIDENCIAS_EVALUACION:
            raise LimiteEncuestaError(
                f"Alcanzaste el máximo de {settings.ENCUESTA_MAX_EVIDENCIAS_EVALUACION} evidencias "
                "de esta evaluación. Puedes seguir respondiendo sin adjuntar más.",
                "LIMITE_EVIDENCIAS",
            )

        fecha, ventana, reinicio = ventana_diaria()
        reserva = Reserva(self.limitador)
        pasos = [
            (f"ev:ip:{huella(ip)}:{fecha}", settings.ENCUESTA_MAX_EVIDENCIAS_IP_DIA, "LIMITE_EVIDENCIAS_IP",
             "Se alcanzó el máximo diario de evidencias desde tu red. Podrás subir más mañana."),
            (f"llm:eval:{evaluacion_id}:{fecha}", settings.LLM_CUOTA_DIARIA_EVALUACION, "CUOTA_LLM_AGOTADA",
             "Usaste todas las validaciones con IA de hoy para esta evaluación. Tus respuestas siguen "
             "guardadas; podrás adjuntar más evidencias después del reinicio."),
            (f"llm:global:{fecha}", settings.LLM_CUOTA_DIARIA_GLOBAL, "CUOTA_LLM_GLOBAL_AGOTADA",
             "La validación con IA alcanzó su capacidad diaria. Tus respuestas siguen guardadas; "
             "podrás adjuntar evidencias después del reinicio."),
        ]
        for clave, limite, codigo, mensaje in pasos:
            if limite <= 0:
                continue
            consumo = await self.limitador.consumir(clave, limite, ventana)
            reserva.claves.append(clave)
            if not consumo.permitido:
                await reserva.devolver()
                raise LimiteEncuestaError(mensaje, codigo, consumo.reintentar_en_s, reinicio)
        return reserva

    async def estado(self, evaluacion_id: int) -> dict:
        fecha, ventana, reinicio = ventana_diaria()
        usadas_ev = await self.evidencias_usadas(evaluacion_id)
        usadas_llm = await self.limitador.usados(f"llm:eval:{evaluacion_id}:{fecha}")
        usadas_global = await self.limitador.usados(f"llm:global:{fecha}")
        lim_ev = settings.ENCUESTA_MAX_EVIDENCIAS_EVALUACION
        lim_llm = settings.LLM_CUOTA_DIARIA_EVALUACION
        lim_global = settings.LLM_CUOTA_DIARIA_GLOBAL
        return {
            "evaluacion_id": evaluacion_id,
            "evidencias": {"usadas": usadas_ev, "limite": lim_ev, "restantes": max(0, lim_ev - usadas_ev)},
            "validaciones_ia": {
                "usadas": usadas_llm,
                "limite": lim_llm,
                "restantes": max(0, lim_llm - usadas_llm) if lim_llm > 0 else None,
                "reinicia_en": reinicio.isoformat().replace("+00:00", "Z"),
            },
            "servicio_ia_disponible": lim_global <= 0 or usadas_global < lim_global,
        }
