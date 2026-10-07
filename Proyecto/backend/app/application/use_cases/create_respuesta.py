from app.domain.models.evento_seguridad import OrigenEvento
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad


class InyeccionDetectadaError(ValueError):
    """La justificación fue bloqueada por la capa anti prompt-injection."""


class CreateRespuestaUseCase:
    def __init__(
        self,
        repo: RespuestaRepository,
        guard: PromptGuardPort | None = None,
        registrar_evento: RegistrarEventoSeguridad | None = None,
    ):
        self.repo = repo
        self.guard = guard
        self.registrar_evento = registrar_evento

    async def execute(
        self,
        evaluacion_id: int,
        matriz_control_id: int,
        estado_clasificacion: str,
        justificacion: str,
    ) -> Respuesta:
        # Validar que la clasificación sea una de las 4 que el usuario puede declarar
        valores_validos = EstadoClasificacion.declarables()
        if estado_clasificacion not in valores_validos:
            raise ValueError(
                f"Clasificación inválida: {estado_clasificacion}. "
                f"Debe ser una de: {', '.join(valores_validos)}"
            )

        # SEGURIDAD (bloqueo preventivo): la justificación es texto libre que luego
        # llega al prompt del LLM. Si parece una inyección, no se guarda.
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

        # Cargar el control para saber si tiene brecha asociada
        control = await self.repo.get_control(matriz_control_id)

        respuesta = Respuesta(
            evaluacion_id=evaluacion_id,
            matriz_controles_id_control=matriz_control_id,
            estado_clasificacion=estado_clasificacion,
            justificacion_usuario=justificacion,
            estado_clasificacion_final=estado_clasificacion,
            fuente_clasificacion=FuenteClasificacion.USUARIO.value,
        )

        # REGLA DE NEGOCIO: si declara "no_cumplido", asignar brecha directo
        if (
            estado_clasificacion == EstadoClasificacion.NO_CUMPLIDO.value
            and control
            and control.catalogo_brechas_id_brecha
        ):
            respuesta.catalogo_brechas_id_brecha = control.catalogo_brechas_id_brecha

        return await self.repo.create(respuesta)
