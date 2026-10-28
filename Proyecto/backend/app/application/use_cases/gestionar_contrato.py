"""
HU-30 criterio 1: el administrador renueva, suspende, reactiva o termina el contrato de una
empresa cliente desde el panel interno, y cada cambio queda en la bitácora (HU-09).

  renovar     nueva fecha de término (posterior a la actual y a hoy); deja el contrato
              'activo'. También levanta una suspensión o deshace una terminación mientras
              dure el plazo de gracia. Después del plazo ya no se puede (los datos pasan a
              retención, HU-25): 409 CONTRATO_FINALIZADO.
  suspender   corta el servicio pagado sin terminar el contrato (motivo obligatorio).
  reactivar   levanta la suspensión sin cambiar fechas.
  terminar    fin anticipado (motivo obligatorio); abre el plazo de gracia para que el
              usuario descargue sus documentos.

Cada operación bloquea la fila de la empresa (SELECT ... FOR UPDATE) para que dos
administradores no cambien el mismo contrato a la vez, y registra en la MISMA transacción
la fila de la bitácora con el estado y las fechas antes y después. Una operación no
permitida desde la situación actual responde 409 TRANSICION_CONTRATO_INVALIDA con las
operaciones que sí se pueden hacer.

No se cierran las sesiones del cliente al suspender o terminar: el token sigue sirviendo
para lo gratuito, sus documentos y ARCOP; el servicio pagado lo corta servicio_pagado.py
en la petición siguiente.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.domain.contrato import PERMITIDAS, EstadoContrato, MotivoContrato, Operacion, SituacionContrato
from app.domain.models.empresa import Empresa
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

# Una renovación no puede ir más allá de esto (protege de un año mal escrito: 2206 en vez de 2026).
MAX_ANIOS_RENOVACION = 10

ACCION_DE = {
    Operacion.RENOVAR: Accion.CONTRATO_RENOVADO,
    Operacion.SUSPENDER: Accion.CONTRATO_SUSPENDIDO,
    Operacion.REACTIVAR: Accion.CONTRATO_REACTIVADO,
    Operacion.TERMINAR: Accion.CONTRATO_TERMINADO,
}


class ContratoError(Exception):
    def __init__(self, mensaje: str, codigo: str, status_code: int, **extra):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code
        self.extra = extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def operaciones_posibles(situacion: SituacionContrato) -> list[str]:
    return sorted(op.value for op, desde in PERMITIDAS.items() if situacion in desde)


def _foto(e: Empresa, hoy: date) -> dict:
    """Lo que se guarda en la bitácora antes y después (sin datos personales)."""
    v = e.vigencia(hoy)
    return {
        "estado": e.estado_contrato, "situacion": v.situacion.value,
        "fecha_inicio": e.fecha_inicio_contrato.isoformat(), "fecha_termino": e.fecha_termino_contrato.isoformat(),
        "fin_gracia": v.fin_gracia.isoformat() if v.fin_gracia else None,
    }


def _motivo(valor: str | None) -> str:
    if valor not in MotivoContrato.valores():
        raise ContratoError(f"Indica el motivo: {', '.join(MotivoContrato.valores())}.", "MOTIVO_INVALIDO", 422,
                            campo="motivo", permitidos=MotivoContrato.valores())
    return valor


class GestionarContratoUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitacora = BitacoraRepository(db)

    async def _empresa(self, empresa_id: int) -> Empresa:
        empresa = (await self.db.execute(
            select(Empresa).where(Empresa.id == empresa_id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if empresa is None:
            raise ContratoError("Empresa no encontrada.", "NO_ENCONTRADO", 404)
        return empresa

    def _exigir(self, op: Operacion, e: Empresa, hoy: date) -> None:
        situacion = e.vigencia(hoy).situacion
        if situacion in PERMITIDAS[op]:
            return
        if situacion is SituacionContrato.FINALIZADO:
            raise ContratoError(
                "El contrato terminó y venció su plazo de gracia: los datos de la empresa quedan para las "
                "reglas de retención. Para volver a contratar se requiere un acuerdo nuevo.",
                "CONTRATO_FINALIZADO", 409, situacion=situacion.value, permitidas=[])
        raise ContratoError(
            f"No se puede {op.value} un contrato en situación '{situacion.value}'.",
            "TRANSICION_CONTRATO_INVALIDA", 409, situacion=situacion.value,
            permitidas=operaciones_posibles(situacion))

    async def _aplicar(self, actor: Actor, empresa_id: int, op: Operacion, cambio, **detalle) -> Empresa:
        try:
            ahora = _ahora()
            hoy = ahora.date()
            e = await self._empresa(empresa_id)
            self._exigir(op, e, hoy)
            antes = _foto(e, hoy)
            cambio(e, ahora, hoy)
            e.fecha_actualizacion_contrato = ahora
            despues = _foto(e, hoy)
            self.bitacora.registrar(
                accion=ACCION_DE[op], entidad="empresa", entidad_id=e.id, actor=actor, fecha=ahora,
                detalle={"antes": antes, "despues": despues, **detalle},
            )
            await self.db.commit()
        except ContratoError:
            await self.db.rollback()
            raise
        await self.db.refresh(e)
        return e

    # ------------------------------------------------------------ operaciones
    async def renovar(self, actor: Actor, empresa_id: int, nueva_fecha_termino: date) -> Empresa:
        def cambio(e: Empresa, ahora: datetime, hoy: date) -> None:
            if nueva_fecha_termino <= e.fecha_termino_contrato:
                raise ContratoError("La nueva fecha de término debe ser posterior a la actual "
                                    f"({e.fecha_termino_contrato.isoformat()}). Para acortarlo, termina el contrato.",
                                    "FECHA_RENOVACION_INVALIDA", 422, campo="fecha_termino_contrato")
            if nueva_fecha_termino < hoy:
                raise ContratoError("La nueva fecha de término no puede estar en el pasado.",
                                    "FECHA_RENOVACION_INVALIDA", 422, campo="fecha_termino_contrato")
            if nueva_fecha_termino > hoy + timedelta(days=365 * MAX_ANIOS_RENOVACION):
                raise ContratoError(f"Una renovación no puede superar {MAX_ANIOS_RENOVACION} años.",
                                    "FECHA_RENOVACION_INVALIDA", 422, campo="fecha_termino_contrato")
            e.fecha_termino_contrato = nueva_fecha_termino
            e.estado_contrato = EstadoContrato.ACTIVO.value
            e.fecha_suspension = e.motivo_suspension = None
            e.fecha_terminacion = e.motivo_terminacion = None

        return await self._aplicar(actor, empresa_id, Operacion.RENOVAR, cambio)

    async def suspender(self, actor: Actor, empresa_id: int, motivo: str | None) -> Empresa:
        motivo = _motivo(motivo)

        def cambio(e: Empresa, ahora: datetime, hoy: date) -> None:
            e.estado_contrato = EstadoContrato.SUSPENDIDO.value
            e.fecha_suspension, e.motivo_suspension = ahora, motivo

        return await self._aplicar(actor, empresa_id, Operacion.SUSPENDER, cambio, motivo=motivo)

    async def reactivar(self, actor: Actor, empresa_id: int) -> Empresa:
        def cambio(e: Empresa, ahora: datetime, hoy: date) -> None:
            e.estado_contrato = EstadoContrato.ACTIVO.value
            e.fecha_suspension = e.motivo_suspension = None

        return await self._aplicar(actor, empresa_id, Operacion.REACTIVAR, cambio)

    async def terminar(self, actor: Actor, empresa_id: int, motivo: str | None) -> Empresa:
        motivo = _motivo(motivo)

        def cambio(e: Empresa, ahora: datetime, hoy: date) -> None:
            e.estado_contrato = EstadoContrato.TERMINADO.value
            e.fecha_terminacion, e.motivo_terminacion = ahora, motivo
            e.fecha_suspension = e.motivo_suspension = None

        return await self._aplicar(actor, empresa_id, Operacion.TERMINAR, cambio, motivo=motivo)


def contrato_dict(e: Empresa, hoy: date | None = None) -> dict:
    """Contrato para el panel interno y para el propio cliente (sin datos personales)."""
    v = e.vigencia(hoy)
    return {
        "estado": e.estado_contrato,
        "fecha_inicio_contrato": e.fecha_inicio_contrato,
        "fecha_termino_contrato": e.fecha_termino_contrato,
        "fecha_suspension": e.fecha_suspension, "motivo_suspension": e.motivo_suspension,
        "fecha_terminacion": e.fecha_terminacion, "motivo_terminacion": e.motivo_terminacion,
        "fecha_fin_gracia": v.fin_gracia,
        "fecha_actualizacion": e.fecha_actualizacion_contrato,
        **v.como_dict(),
    }


async def empresas_con_gracia_vencida(db: AsyncSession, hoy: date | None = None) -> list[int]:
    """
    Criterio 3: empresas cuyo plazo de gracia ya venció, para que HU-25 aplique la retención.
    Se calcula en Python con la misma regla de app/domain/contrato.py (son pocas empresas).
    """
    hoy = hoy or date.today()
    filas = (await db.execute(
        select(Empresa).where(
            (Empresa.fecha_termino_contrato < hoy) | (Empresa.estado_contrato == EstadoContrato.TERMINADO.value)
        )
    )).scalars().all()
    return sorted(e.id for e in filas if e.vigencia(hoy).situacion is SituacionContrato.FINALIZADO)
