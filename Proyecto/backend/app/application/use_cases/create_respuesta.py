"""
HU-01 — Guardar (crear o actualizar) la respuesta a un control del cuestionario.

Reglas:
  * Una sola respuesta por (evaluación, control). Responder de nuevo ACTUALIZA la
    existente (upsert); si la declaración no cambió, no se toca nada (el guardado
    automático puede reenviar la misma respuesta sin perder la validación del LLM).
  * Solo se aceptan respuestas a evaluaciones existentes, abiertas, con el filtro
    F1–F7 completado y a controles que ese filtro deja aplicables.
  * La justificación pasa por la capa anti prompt-injection antes de guardarse.
"""
from dataclasses import dataclass

from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.respuesta_repository import (
    RespuestaDuplicadaError,
    RespuestaRepository,
)
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad


# ---------------------------------------------------------------- errores
class InyeccionDetectadaError(ValueError):
    """La justificación fue bloqueada por la capa anti prompt-injection."""


class RespuestaRechazadaError(ValueError):
    """La respuesta no se puede guardar. `status_code` y `codigo` van a la API."""
    status_code = 400
    codigo = "RESPUESTA_RECHAZADA"


class EvaluacionNoEncontradaError(RespuestaRechazadaError):
    status_code = 404
    codigo = "EVALUACION_NO_ENCONTRADA"


class EvaluacionCerradaError(RespuestaRechazadaError):
    status_code = 409
    codigo = "EVALUACION_CERRADA"


class FiltroPendienteError(RespuestaRechazadaError):
    status_code = 409
    codigo = "FILTRO_PENDIENTE"


class ControlNoEncontradoError(RespuestaRechazadaError):
    status_code = 404
    codigo = "CONTROL_NO_ENCONTRADO"


class ControlNoAplicableError(RespuestaRechazadaError):
    status_code = 422
    codigo = "CONTROL_NO_APLICABLE"


class RespuestaNoEncontradaError(RespuestaRechazadaError):
    status_code = 404
    codigo = "RESPUESTA_NO_ENCONTRADA"


@dataclass
class ResultadoRespuesta:
    respuesta: Respuesta
    creada: bool          # True: fila nueva (201) · False: se actualizó o no cambió (200)
    modificada: bool      # False si se reenvió exactamente la misma declaración


# ---------------------------------------------------------------- caso de uso
class CreateRespuestaUseCase:
    def __init__(
        self,
        repo: RespuestaRepository,
        evaluaciones: EvaluacionRepository,
        guard: PromptGuardPort | None = None,
        registrar_evento: RegistrarEventoSeguridad | None = None,
    ):
        self.repo = repo
        self.evaluaciones = evaluaciones
        self.guard = guard
        self.registrar_evento = registrar_evento

    async def execute(
        self,
        evaluacion_id: int,
        matriz_control_id: int,
        estado_clasificacion: str,
        justificacion: str,
    ) -> Respuesta:
        """Compatibilidad: devuelve solo la respuesta guardada."""
        resultado = await self.guardar(evaluacion_id, matriz_control_id, estado_clasificacion, justificacion)
        return resultado.respuesta

    async def guardar(
        self,
        evaluacion_id: int,
        matriz_control_id: int,
        estado_clasificacion: str,
        justificacion: str,
    ) -> ResultadoRespuesta:
        """POST /api/respuestas: crea la respuesta o actualiza la del mismo control."""
        control = await self._validar(evaluacion_id, matriz_control_id, estado_clasificacion, justificacion)

        existente = await self.repo.get_by_evaluacion_control(evaluacion_id, matriz_control_id)
        if existente is None:
            nueva = Respuesta(evaluacion_id=evaluacion_id, matriz_controles_id_control=matriz_control_id)
            self._aplicar_declaracion(nueva, estado_clasificacion, justificacion, control)
            try:
                return ResultadoRespuesta(await self.repo.create(nueva), creada=True, modificada=True)
            except RespuestaDuplicadaError:
                # Otra petición la insertó en paralelo: se actualiza esa.
                existente = await self.repo.get_by_evaluacion_control(evaluacion_id, matriz_control_id)
                if existente is None:  # pragma: no cover - borrada entre medio
                    raise
        return await self._actualizar(existente, estado_clasificacion, justificacion, control)

    async def actualizar(
        self,
        respuesta_id: int,
        estado_clasificacion: str,
        justificacion: str,
    ) -> ResultadoRespuesta:
        """PUT /api/respuestas/{id}: modifica una respuesta existente por su id."""
        existente = await self.repo.get(respuesta_id)
        if existente is None:
            raise RespuestaNoEncontradaError(f"Respuesta {respuesta_id} no encontrada")
        control = await self._validar(
            existente.evaluacion_id, existente.matriz_controles_id_control,
            estado_clasificacion, justificacion,
        )
        return await self._actualizar(existente, estado_clasificacion, justificacion, control)

    # ------------------------------------------------------------ internos
    async def _validar(self, evaluacion_id, matriz_control_id, estado_clasificacion, justificacion):
        # 1. Clasificación: una de las 4 que el usuario puede declarar
        valores_validos = EstadoClasificacion.declarables()
        if estado_clasificacion not in valores_validos:
            raise ValueError(
                f"Clasificación inválida: {estado_clasificacion}. "
                f"Debe ser una de: {', '.join(valores_validos)}"
            )

        # 2. Evaluación: existe, está abierta y ya pasó por el filtro
        contexto = await self.evaluaciones.get_contexto(evaluacion_id)
        if contexto is None:
            raise EvaluacionNoEncontradaError(f"Evaluación {evaluacion_id} no encontrada")
        if contexto.cerrada:
            raise EvaluacionCerradaError(
                f"La evaluación {evaluacion_id} está cerrada ({contexto.estado_progreso}): "
                "ya no admite respuestas"
            )
        if not contexto.filtro_completado:
            raise FiltroPendienteError(
                "Responde primero el filtro de aplicabilidad (F1–F7) de la evaluación"
            )

        # 3. Control: existe y el filtro lo deja aplicable
        control = await self.repo.get_control(matriz_control_id)
        if control is None:
            raise ControlNoEncontradoError(f"Control {matriz_control_id} no encontrado")
        if control.codigo_control not in contexto.codigos_aplicables:
            raise ControlNoAplicableError(
                f"El control {control.codigo_control} no aplica a esta evaluación según "
                "sus respuestas del filtro; no se puede responder"
            )

        # 4. SEGURIDAD (bloqueo preventivo): la justificación es texto libre que luego
        #    llega al prompt del LLM. Si parece una inyección, no se guarda.
        if self.guard and self.guard.detectar_inyeccion(justificacion or ""):
            if self.registrar_evento:
                await self.registrar_evento.execute(
                    texto=justificacion,
                    origen=OrigenEvento.JUSTIFICACION.value,
                    evaluacion_id=evaluacion_id,
                    matriz_control_id=matriz_control_id,
                )
            raise InyeccionDetectadaError(
                "La justificación contiene instrucciones o contenido no permitido "
                "(posible prompt injection). Reescríbela describiendo solo cómo "
                "cumple tu organización el control."
            )
        return control

    async def _actualizar(self, respuesta, estado_clasificacion, justificacion, control) -> ResultadoRespuesta:
        if (
            respuesta.estado_clasificacion == estado_clasificacion
            and (respuesta.justificacion_usuario or "") == (justificacion or "")
        ):
            # Reenvío idéntico (guardado automático): no se pierde nada de lo validado.
            return ResultadoRespuesta(respuesta, creada=False, modificada=False)
        self._aplicar_declaracion(respuesta, estado_clasificacion, justificacion, control)
        return ResultadoRespuesta(await self.repo.update(respuesta), creada=False, modificada=True)

    @staticmethod
    def _aplicar_declaracion(respuesta: Respuesta, estado_clasificacion, justificacion, control) -> None:
        """
        Fija la declaración del usuario como estado vigente. Si cambió, la validación
        anterior (LLM o revisión humana) correspondía a otra declaración y se descarta;
        las evidencias ya subidas se conservan y una nueva evidencia vuelve a validar.
        """
        respuesta.estado_clasificacion = estado_clasificacion
        respuesta.justificacion_usuario = justificacion
        respuesta.estado_clasificacion_final = estado_clasificacion
        respuesta.fuente_clasificacion = FuenteClasificacion.USUARIO.value
        respuesta.confianza_clasificacion = None
        respuesta.fecha_validacion = None
        respuesta.clasificacion_revisada = None
        respuesta.fecha_revision = None
        # REGLA DE NEGOCIO: si declara "no_cumplido", asignar la brecha del control
        if estado_clasificacion == EstadoClasificacion.NO_CUMPLIDO.value and control.catalogo_brechas_id_brecha:
            respuesta.catalogo_brechas_id_brecha = control.catalogo_brechas_id_brecha
        else:
            respuesta.catalogo_brechas_id_brecha = None
