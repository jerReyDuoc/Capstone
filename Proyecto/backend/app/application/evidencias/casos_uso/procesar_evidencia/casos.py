"""Caso de uso: validación de una evidencia (lo ejecuta el worker ARQ)."""
from typing import Awaitable, Callable

from app.application.ai.anonimizador import AnonimizadorPII
from app.application.ai.verificacion_salida_evidencias import VerificacionSalida, verificar_evidencia
from app.domain.models.evidencia import Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.ports.almacenamiento_port import AlmacenamientoPort
from app.domain.ports.validador_evidencias_port import ValidadorEvidenciasPort
from app.domain.ports.guardia_prompt_port import GuardiaPromptPort
from app.application.auditoria.casos_uso.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.application.evidencias.casos_uso.procesar_evidencia.anonimizado_evidencia import AnonimizadoMixin
from app.application.evidencias.casos_uso.procesar_evidencia.decision_clasificacion import DecisionMixin
from app.application.evidencias.casos_uso.procesar_evidencia.remediacion_evidencia import RemediacionMixin
from app.application.evidencias.casos_uso.procesar_evidencia.seguridad_evidencia import SeguridadMixin
from app.application.evidencias.casos_uso.procesar_evidencia.flujo_validacion_evidencia import ValidacionMixin
from app.application.evidencias.casos_uso.procesar_evidencia.verificacion_evidencia import VerificacionMixin
from app.domain.ports.repositorios import EvidenciaRepositoryPort, RespuestaRepositoryPort


class ProcesarEvidenciaUseCase(
    ValidacionMixin, RemediacionMixin, AnonimizadoMixin, SeguridadMixin, VerificacionMixin, DecisionMixin,
):
    def __init__(
        self,
        evidencia_repo: EvidenciaRepositoryPort,
        respuesta_repo: RespuestaRepositoryPort,
        storage: AlmacenamientoPort,
        validator: ValidadorEvidenciasPort,
        guard: GuardiaPromptPort | None = None,
        registrar_evento: RegistrarEventoSeguridad | None = None,
        anonimizador: AnonimizadorPII | None = None,
        recalcular: Callable[[int], Awaitable[object]] | None = None,
        puntaje_actual: Callable[[int], Awaitable[float | None]] | None = None,
        auditar: Callable[[Evidencia, Respuesta | None], Awaitable[None]] | None = None,
        auditar_supresion: Callable[[Evidencia], None] | None = None,
        verificador: Callable[..., VerificacionSalida] | None = verificar_evidencia,
    ):
        self.evidencia_repo = evidencia_repo
        self.respuesta_repo = respuesta_repo
        self.storage = storage
        self.validator = validator
        self.guard = guard
        self.registrar_evento = registrar_evento
        # HU-06: el worker lo inyecta (factory.crear_anonimizador); sin él el archivo no se toca.
        self.anonimizador = anonimizador
        # HU-17: recalcula el resumen (puntaje y radar) cuando una remediación mejora un control.
        # El worker inyecta GenerarResumenUseCase; recibe el id de la evaluación.
        self.recalcular = recalcular
        # HU-17: lee el puntaje general vigente (antes y después del recálculo)
        self.puntaje_actual = puntaje_actual
        # HU-17: registra el resultado de la remediación en la bitácora (HU-09)
        self.auditar = auditar
        # HU-09: registra en el audit_log (sin commit) que el archivo original se suprimió y
        # quedó solo su texto anonimizado; va en la misma transacción que el cambio de ruta.
        self.auditar_supresion = auditar_supresion
        # HU-07: verificación de la salida del modelo (None la desactiva; solo para pruebas)
        self.verificador = verificador

    async def execute(self, evidencia_id: int) -> Evidencia:
        evidencia = await self.evidencia_repo.get(evidencia_id)
        if not evidencia:
            raise ValueError(f"Evidencia {evidencia_id} no encontrada")
        previo = None
        if evidencia.es_remediacion:
            r = await self.respuesta_repo.get(evidencia.respuesta_id)
            previo = r.estado_clasificacion_final or r.estado_clasificacion if r else None
            evidencia.estado_previo = previo
        evidencia = await self._validar(evidencia)
        await self._conservar_solo_anonimizado(evidencia)
        if evidencia.es_remediacion:
            await self._cerrar_remediacion(evidencia, previo)
        return evidencia
