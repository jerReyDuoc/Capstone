"""
HU-25 · Plazo de retención de los usuarios temporales (criterio 1: configurable).

El plazo es el número de días que se conservan los datos de un usuario temporal DESPUÉS de
que vence su acceso (usuario_temporal.fecha_expiracion). Vencido ese plazo, la tarea
programada (aplicar_retencion.py, regla R1) lo anonimiza con la misma rutina que una
supresión ARCOP aprobada y conserva sus puntajes para el benchmark.

Tres modos, que elige el Oficial de Privacidad en /admin/retencion:
  entorno      rige RETENCION_DATOS_TITULAR_DIAS (vacía = sin retención). Estado inicial.
  plazo        rige el número de días fijado en el panel (entre RETENCION_TITULAR_MIN_DIAS
               y RETENCION_TITULAR_MAX_DIAS).
  desactivada  la regla R1 no se aplica (p. ej. mientras se revisa un plazo con legal).

Cada cambio queda en el audit_log (retencion.configuracion_cambiada) con el valor anterior y
el nuevo, en la misma transacción. Las lecturas usan columnas, no la entidad ORM: el bloqueo
de ejecución se actualiza con UPDATE directo y una entidad en caché quedaría desfasada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.core.config import settings
from app.domain.models.configuracion_retencion import (
    FUENTE_ENTORNO,
    FUENTE_PANEL,
    ID_UNICO,
    ConfiguracionRetencion as Conf,
)
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

MODO_ENTORNO = "entorno"
MODO_PLAZO = "plazo"
MODO_DESACTIVADA = "desactivada"
MODOS = (MODO_ENTORNO, MODO_PLAZO, MODO_DESACTIVADA)


class RetencionError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje = status, codigo, mensaje


@dataclass(frozen=True)
class PlazoTitular:
    """Plazo que rige hoy. dias=None: regla R1 desactivada."""
    dias: int | None
    fuente: str                       # entorno | panel
    fecha_actualizacion: datetime | None = None
    ejecucion_desde: datetime | None = None

    @property
    def activa(self) -> bool:
        return self.dias is not None

    @property
    def modo(self) -> str:
        if self.fuente == FUENTE_ENTORNO:
            return MODO_ENTORNO
        return MODO_PLAZO if self.dias is not None else MODO_DESACTIVADA

    def como_dict(self) -> dict:
        return {"modo": self.modo, "fuente": self.fuente, "plazo_titular_dias": self.dias, "activa": self.activa}


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


ahora_utc = _ahora


async def asegurar_fila(s: AsyncSession) -> None:
    """La migración siembra la fila; si falta (BD de pruebas, borrado manual) se crea en 'entorno'."""
    if await s.scalar(select(Conf.id).where(Conf.id == ID_UNICO)) is not None:
        return
    s.add(Conf(id=ID_UNICO, fuente_plazo=FUENTE_ENTORNO, plazo_titular_dias=None))
    try:
        await s.commit()
    except IntegrityError:  # otra sesión la creó al mismo tiempo
        await s.rollback()


async def plazo_titular_vigente(s: AsyncSession) -> PlazoTitular:
    await asegurar_fila(s)
    fila = (await s.execute(
        select(Conf.fuente_plazo, Conf.plazo_titular_dias, Conf.fecha_actualizacion, Conf.ejecucion_desde)
        .where(Conf.id == ID_UNICO)
    )).one()
    if fila.fuente_plazo == FUENTE_PANEL:
        return PlazoTitular(fila.plazo_titular_dias, FUENTE_PANEL, fila.fecha_actualizacion, fila.ejecucion_desde)
    return PlazoTitular(settings.RETENCION_DATOS_TITULAR_DIAS, FUENTE_ENTORNO, fila.fecha_actualizacion,
                        fila.ejecucion_desde)


def validar_cambio(modo: str, dias: int | None) -> int | None:
    """Devuelve el plazo a guardar (None si no corresponde) o lanza RetencionError 422."""
    if modo not in MODOS:
        raise RetencionError(422, "MODO_INVALIDO", f"El modo debe ser uno de: {', '.join(MODOS)}.")
    if modo != MODO_PLAZO:
        return None
    minimo, maximo = settings.RETENCION_TITULAR_MIN_DIAS, settings.RETENCION_TITULAR_MAX_DIAS
    if dias is None or isinstance(dias, bool) or not isinstance(dias, int) or not minimo <= dias <= maximo:
        raise RetencionError(422, "PLAZO_INVALIDO",
                             f"El plazo debe ser un número entero de días entre {minimo} y {maximo}.")
    return dias


async def actualizar_plazo(s: AsyncSession, actor: Actor, *, modo: str, dias: int | None) -> PlazoTitular:
    nuevo_dias = validar_cambio(modo, dias)
    antes = await plazo_titular_vigente(s)
    fuente = FUENTE_ENTORNO if modo == MODO_ENTORNO else FUENTE_PANEL
    if antes.fuente == fuente and (fuente == FUENTE_ENTORNO or antes.dias == nuevo_dias):
        return antes  # sin cambios: no se ensucia el audit_log
    ahora = _ahora()
    await s.execute(update(Conf).where(Conf.id == ID_UNICO)
                    .values(fuente_plazo=fuente, plazo_titular_dias=nuevo_dias, fecha_actualizacion=ahora)
                    .execution_options(synchronize_session=False))
    despues = (PlazoTitular(settings.RETENCION_DATOS_TITULAR_DIAS, FUENTE_ENTORNO, ahora)
               if fuente == FUENTE_ENTORNO else PlazoTitular(nuevo_dias, FUENTE_PANEL, ahora))
    BitacoraRepository(s).registrar(
        accion=Accion.RETENCION_CONFIGURACION, entidad="configuracion_retencion", entidad_id=ID_UNICO,
        actor=actor, detalle={"regla": "R1", "antes": antes.como_dict(), "despues": despues.como_dict(),
                              "valor_entorno_dias": settings.RETENCION_DATOS_TITULAR_DIAS},
    )
    await s.commit()
    return despues


# ------------------------------------------------------------------ ejecución en curso
async def tomar_bloqueo(s: AsyncSession, marca: datetime) -> bool:
    """
    Marca la ejecución en curso. Devuelve False si ya hay otra (cron y manual a la vez).
    En PostgreSQL el UPDATE condicional es atómico: la segunda transacción espera a la
    primera y, al reevaluar el WHERE, no actualiza nada.
    """
    await asegurar_fila(s)
    abandonada = marca - timedelta(minutes=settings.RETENCION_BLOQUEO_MAX_MIN)
    res = await s.execute(
        update(Conf).where(Conf.id == ID_UNICO,
                           or_(Conf.ejecucion_desde.is_(None), Conf.ejecucion_desde < abandonada))
        .values(ejecucion_desde=marca).execution_options(synchronize_session=False)
    )
    await s.commit()
    return (res.rowcount or 0) == 1


async def liberar_bloqueo(s: AsyncSession, marca: datetime) -> None:
    await s.execute(update(Conf).where(Conf.id == ID_UNICO, Conf.ejecucion_desde == marca)
                    .values(ejecucion_desde=None).execution_options(synchronize_session=False))
    await s.commit()


def proxima_ejecucion(ahora: datetime | None = None) -> datetime:
    """Próxima corrida del cron diario (UTC, sin zona, como el resto de las fechas de la API)."""
    ahora = ahora or _ahora()
    hoy = ahora.replace(hour=settings.RETENCION_HORA_UTC, minute=0, second=0, microsecond=0)
    return hoy if hoy > ahora else hoy + timedelta(days=1)
