"""
HU-29 · Evaluaciones de la empresa cliente: historial, reevaluación y "la más reciente".

  historial_de_empresa()        lee de la BD las evaluaciones de la empresa (migradas y
                                reevaluaciones) con sus resultados por dimensión y arma el
                                historial con app/application/informes/historial.py.
  IniciarReevaluacionUseCase    criterio 2: la evaluación nueva pertenece a la empresa desde
                                que nace (empresa_id, origen 'empresa') y NO crea usuario
                                temporal: no hay encuestado anónimo, clave de acceso ni
                                aviso legal de la landing. La responde el usuario definitivo
                                con su sesión (app/api/dependencias/alcance.py ya le da acceso a las
                                evaluaciones de su empresa).
  evaluacion_mas_reciente()     la regla única de "evaluación más reciente" (formación,
                                tutor IA y el resumen del historial).
  rubro_id_de_evaluacion()      rubro para la comparativa: el de la empresa o, si no tiene,
                                el del usuario temporal.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes.historial import DimensionFila, EvaluacionFila, construir_historial
from app.application.fabricas import fabricas
from app.domain.auth.actor import Actor
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import ORIGEN_EMPRESA, Evaluacion
from app.domain.auditoria.acciones import Accion

ESTADO_EN_PROGRESO = "en_progreso"


class ReevaluacionError(Exception):
    def __init__(self, status_code: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status_code, self.codigo, self.extra = status_code, codigo, extra

    def detalle(self) -> dict:
        return {"codigo": self.codigo, "mensaje": str(self), **self.extra}


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ consultas comunes
async def evaluacion_mas_reciente(db: AsyncSession, empresa_id: int, *, solo_completadas: bool = True) -> int | None:
    """
    Id de la evaluación más reciente de la empresa que ya tiene resultados (resumen). Por
    defecto solo las completadas: una reevaluación a medio responder no reemplaza a la
    última evaluación terminada (su resumen sería solo una vista previa).
    """
    return await fabricas().historial_empresa(db).evaluacion_mas_reciente(empresa_id, solo_completadas)


async def evaluacion_en_curso(db: AsyncSession, empresa_id: int) -> Evaluacion | None:
    return await fabricas().historial_empresa(db).evaluacion_en_curso(empresa_id)


async def rubro_id_de_evaluacion(db: AsyncSession, evaluacion: Evaluacion | None) -> int | None:
    """El rubro de la empresa manda; si la evaluación no tiene empresa, el del usuario temporal."""
    if evaluacion is None:
        return None
    if evaluacion.empresa_id is not None:
        rubro = await fabricas().historial_empresa(db).rubro_de_empresa(evaluacion.empresa_id)
        if rubro is not None:
            return rubro
    if evaluacion.usuario_temporal_id is not None:
        return await fabricas().historial_empresa(db).rubro_de_usuario_temporal(evaluacion.usuario_temporal_id)
    return None


# ------------------------------------------------------------------ criterio 1: historial
async def filas_de_empresa(db: AsyncSession, empresa_id: int) -> list[EvaluacionFila]:
    repo = fabricas().historial_empresa(db)
    evaluaciones = await repo.evaluaciones_de_empresa(empresa_id)
    if not evaluaciones:
        return []
    ids = [e.id for e in evaluaciones]
    por_evaluacion: dict[int, list[DimensionFila]] = {i: [] for i in ids}
    for r, d in await repo.resumenes_con_dominio(ids):
        por_evaluacion[r.evaluacion_id].append(DimensionFila(
            dominio_id=d.id, dominio=d.nombre_dominio or f"Dominio {d.id}", puntaje=r.puntaje_obtenido,
            controles=r.total_controles_evaluados, nivel=r.nivel_madurez,
        ))
    return [
        EvaluacionFila(
            id=e.id, origen=e.origen, estado=e.estado_progreso, fecha_inicio=e.fecha_inicio,
            fecha_completado=e.fecha_completado, fecha_migracion=e.fecha_migracion,
            dimensiones=tuple(por_evaluacion[e.id]),
        )
        for e in evaluaciones
    ]


async def historial_de_empresa(db: AsyncSession, empresa_id: int) -> dict:
    return construir_historial(await filas_de_empresa(db, empresa_id))


# ------------------------------------------------------------------ criterio 2: reevaluación
class IniciarReevaluacionUseCase:
    """
    Crea la evaluación nueva de la empresa. Una sola abierta a la vez: si ya hay una en
    curso se responde 409 con su id para que el usuario la retome (no se pierde lo avanzado).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = fabricas().historial_empresa(db)
        self.bitacora = fabricas().bitacora(db)

    async def execute(self, actor: Actor, empresa: Empresa) -> Evaluacion:
        # Bloquea la fila de la empresa hasta el commit: dos clics simultáneos no crean dos
        # evaluaciones abiertas (en PostgreSQL además lo impide uq_evaluacion_empresa_en_curso).
        await self.repo.bloquear_empresa(empresa.id)
        abierta = await evaluacion_en_curso(self.db, empresa.id)
        if abierta is not None:
            raise ReevaluacionError(
                409, "EVALUACION_EN_CURSO",
                "Tu empresa ya tiene una evaluación en curso. Continúala antes de iniciar otra.",
                evaluacion_id=abierta.id,
            )
        anterior = await evaluacion_mas_reciente(self.db, empresa.id)
        evaluacion = Evaluacion(
            fecha_inicio=date.today(),
            estado_progreso=ESTADO_EN_PROGRESO,
            usuario_temporal_id=None,          # criterio 2: sin usuario temporal
            empresa_id=empresa.id,
            origen=ORIGEN_EMPRESA,
            filtro_completado=False,
            es_prueba=False,
            clave_acceso_hash=None,
        )
        self.repo.agregar_evaluacion(evaluacion)
        await self.db.flush()
        self.bitacora.registrar(
            accion=Accion.EVALUACION_REEVALUACION_INICIADA, entidad="evaluacion", entidad_id=evaluacion.id,
            actor=actor, detalle={"empresa_id": empresa.id, "evaluacion_anterior_id": anterior},
        )
        await self.db.commit()
        return evaluacion
