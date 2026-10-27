"""
HU-27 criterio 2: migración transaccional de la evaluación temporal a la empresa.

Qué "pasa a la empresa" y cómo
-----------------------------
Las respuestas, evidencias, resumen (puntajes por dimensión), plan formativo e informes
cuelgan TODOS de la evaluación: respuestas.Evaluacion_id, evidencias -> respuesta,
resumen.Evaluacion_id, y el plan formativo y el informe PDF se calculan desde esos datos
(GET /plan-formativo, /informe/pdf). Por eso migrar = reasignar la evaluación a la
empresa (evaluacion.empresa_id). No se copia nada: copiar duplicaría datos (Ley 21.719,
minimización) y dejaría dos versiones de la verdad. Al cliente se le abre el acceso por
evaluacion.empresa_id (app/core/alcance.py) y al usuario temporal se le cierra.

En la MISMA transacción, por cada solicitud:
  1. Bloquea la solicitud y la evaluación (SELECT ... FOR UPDATE en PostgreSQL), para que
     dos administradores no migren lo mismo a la vez.
  2. Valida: solicitud 'contratada' y con autorización expresa; evaluación completada,
     no migrada; titular no anonimizado y sin solicitudes ARCOP abiertas.
  3. evaluacion.empresa_id = empresa; la clave de acceso se borra (deja de funcionar).
  4. Usuario temporal: se borra su email y la marca de invitación y se fija
     fecha_anonimizacion -> sus tokens dejan de servir y no puede volver a entrar.
  5. Solicitud: estado 'migrada', empresa_id, y se borran los datos de contacto (pasaron
     al usuario definitivo: no se duplican).
  6. Bitácora: una fila por evaluación migrada y por usuario temporal cerrado.
Si cualquier validación falla se lanza MigracionError y quien llama hace rollback de
TODO (también de la empresa y del usuario si venía del alta). Este módulo nunca hace commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.solicitud_arcop import EstadoSolicitudARCOP, SolicitudARCOP
from app.domain.models.solicitud_contratacion import EstadoSolicitudContratacion, SolicitudContratacion
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

MAX_SOLICITUDES_POR_OPERACION = 20


class MigracionError(Exception):
    def __init__(self, mensaje: str, codigo: str, status_code: int = 409, **extra):
        super().__init__(mensaje)
        self.codigo = codigo
        self.status_code = status_code
        self.extra = extra


@dataclass(frozen=True)
class EvaluacionMigrada:
    solicitud_id: int
    evaluacion_id: int
    usuario_temporal_id: int | None
    respuestas: int
    evidencias: int
    dimensiones_resumen: int

    def como_dict(self) -> dict:
        return {
            "solicitud_id": self.solicitud_id,
            "evaluacion_id": self.evaluacion_id,
            "respuestas": self.respuestas,
            "evidencias": self.evidencias,
            "dimensiones_resumen": self.dimensiones_resumen,
            # Se calculan desde la evaluación: quedan disponibles para la empresa sin copiarse
            "plan_formativo": self.dimensiones_resumen > 0,
            "informe_pdf": self.dimensiones_resumen > 0,
        }


class MigradorEvaluaciones:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitacora = BitacoraRepository(db)

    @staticmethod
    def normalizar_ids(solicitudes_ids: list[int]) -> list[int]:
        ids = sorted({int(i) for i in (solicitudes_ids or [])})
        if not ids:
            raise MigracionError("Selecciona al menos una solicitud de contratación.", "SOLICITUD_REQUERIDA", 422)
        if len(ids) > MAX_SOLICITUDES_POR_OPERACION:
            raise MigracionError(
                f"Puedes migrar como máximo {MAX_SOLICITUDES_POR_OPERACION} evaluaciones por operación.",
                "DEMASIADAS_SOLICITUDES", 422,
            )
        return ids

    async def _contar(self, evaluacion_id: int) -> tuple[int, int, int]:
        respuestas = (await self.db.execute(
            select(func.count()).select_from(Respuesta).where(Respuesta.evaluacion_id == evaluacion_id)
        )).scalar_one()
        evidencias = (await self.db.execute(
            select(func.count()).select_from(Evidencia).join(Respuesta, Evidencia.respuesta_id == Respuesta.id)
            .where(Respuesta.evaluacion_id == evaluacion_id)
        )).scalar_one()
        dimensiones = (await self.db.execute(
            select(func.count()).select_from(Resumen).where(Resumen.evaluacion_id == evaluacion_id)
        )).scalar_one()
        return respuestas, evidencias, dimensiones

    async def _arcop_abierta(self, evaluacion: Evaluacion) -> bool:
        condicion = SolicitudARCOP.evaluacion_id == evaluacion.id
        if evaluacion.usuario_temporal_id is not None:
            condicion = or_(condicion, SolicitudARCOP.usuario_temporal_id == evaluacion.usuario_temporal_id)
        return (await self.db.scalar(
            select(SolicitudARCOP.id)
            .where(condicion, SolicitudARCOP.estado.not_in(list(EstadoSolicitudARCOP.finales())))
            .limit(1)
        )) is not None

    async def _validar(self, solicitud_id: int, solicitud: SolicitudContratacion | None,
                       evaluacion: Evaluacion | None, usuario: UsuarioTemporal | None) -> None:
        def error(mensaje, codigo, status=409):
            return MigracionError(mensaje, codigo, status, solicitud_id=solicitud_id)

        if solicitud is None:
            raise error(f"La solicitud {solicitud_id} no existe.", "SOLICITUD_NO_ENCONTRADA", 404)
        if solicitud.estado == EstadoSolicitudContratacion.MIGRADA.value or (
                evaluacion is not None and evaluacion.empresa_id is not None):
            raise error(f"La evaluación de la solicitud {solicitud_id} ya fue migrada a una empresa.",
                        "EVALUACION_YA_MIGRADA")
        if solicitud.estado != EstadoSolicitudContratacion.CONTRATADA.value:
            raise error(f"La solicitud {solicitud_id} no está marcada como contratada "
                        f"(estado: {solicitud.estado}).", "SOLICITUD_NO_CONTRATADA")
        if not solicitud.autoriza_migracion:
            raise error(f"La solicitud {solicitud_id} no autoriza traspasar la evaluación a la empresa.",
                        "MIGRACION_NO_AUTORIZADA")
        if evaluacion is None:
            raise error(f"La evaluación de la solicitud {solicitud_id} no existe.", "EVALUACION_NO_ENCONTRADA", 404)
        if not evaluacion.esta_cerrada:
            raise error(f"La evaluación #{evaluacion.id} aún no está completada.", "EVALUACION_NO_COMPLETADA")
        if usuario is not None and usuario.fecha_anonimizacion is not None:
            raise error(f"Los datos del usuario temporal de la evaluación #{evaluacion.id} ya fueron "
                        "suprimidos; no se puede migrar.", "TITULAR_ANONIMIZADO")
        if await self._arcop_abierta(evaluacion):
            raise error(f"La evaluación #{evaluacion.id} tiene una solicitud ARCOP en curso: "
                        "resuélvela antes de migrar.", "ARCOP_PENDIENTE")

    async def migrar(self, empresa: Empresa, solicitudes_ids: list[int], actor: Actor,
                     ahora: datetime) -> list[EvaluacionMigrada]:
        migradas: list[EvaluacionMigrada] = []
        for solicitud_id in self.normalizar_ids(solicitudes_ids):
            solicitud = await self.db.scalar(
                select(SolicitudContratacion).where(SolicitudContratacion.id == solicitud_id).with_for_update()
            )
            evaluacion = await self.db.scalar(
                select(Evaluacion).where(Evaluacion.id == solicitud.evaluacion_id).with_for_update()
            ) if solicitud else None
            usuario = await self.db.scalar(
                select(UsuarioTemporal).where(UsuarioTemporal.id == evaluacion.usuario_temporal_id).with_for_update()
            ) if evaluacion and evaluacion.usuario_temporal_id else None

            await self._validar(solicitud_id, solicitud, evaluacion, usuario)
            respuestas, evidencias, dimensiones = await self._contar(evaluacion.id)

            # 3. la evaluación (y todo lo que cuelga de ella) pasa a la empresa
            evaluacion.empresa_id = empresa.id
            evaluacion.fecha_migracion = ahora
            evaluacion.clave_acceso_hash = None  # la clave temporal deja de funcionar

            # 4. usuario temporal cerrado y anonimizado (sin duplicar el contacto)
            if usuario is not None:
                usuario.email = None
                usuario.validacion_invitacion = None
                usuario.fecha_anonimizacion = ahora

            # 5. solicitud migrada; su contacto ya vive solo en el usuario definitivo
            solicitud.estado = EstadoSolicitudContratacion.MIGRADA.value
            solicitud.empresa_id = empresa.id
            solicitud.fecha_migracion = ahora
            solicitud.fecha_actualizacion = ahora
            solicitud.nombre_contacto = None
            solicitud.cargo_contacto = None
            solicitud.email_contacto = None
            solicitud.telefono_contacto = None

            resultado = EvaluacionMigrada(
                solicitud_id=solicitud.id, evaluacion_id=evaluacion.id,
                usuario_temporal_id=usuario.id if usuario else None,
                respuestas=respuestas, evidencias=evidencias, dimensiones_resumen=dimensiones,
            )
            # 6. bitácora (misma transacción)
            self.bitacora.registrar(
                accion=Accion.EVALUACION_MIGRADA, entidad="evaluacion", entidad_id=evaluacion.id, actor=actor,
                detalle={"empresa_id": empresa.id, **resultado.como_dict()}, fecha=ahora,
            )
            if usuario is not None:
                self.bitacora.registrar(
                    accion=Accion.USUARIO_TEMPORAL_CERRADO, entidad="usuario_temporal", entidad_id=usuario.id,
                    actor=actor, fecha=ahora,
                    detalle={"empresa_id": empresa.id, "evaluacion_id": evaluacion.id,
                             "clave_acceso_revocada": True, "contacto_borrado": True},
                )
            migradas.append(resultado)
            await self.db.flush()
        return migradas
