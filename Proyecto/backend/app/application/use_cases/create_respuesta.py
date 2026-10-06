from app.domain.models.respuesta import Respuesta, FuenteClasificacion
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository

class CreateRespuestaUseCase:
    def __init__(self, repo: RespuestaRepository):
        self.repo = repo

    async def execute(
        self,
        evaluacion_id: int,
        matriz_control_id: int,
        estado_clasificacion: str,
        justificacion: str,
    ) -> Respuesta:
        respuesta = Respuesta(
            evaluacion_id=evaluacion_id,
            matriz_controles_id_control=matriz_control_id,
            estado_clasificacion=estado_clasificacion,
            justificacion_usuario=justificacion,
            # Por defecto, la final es la del usuario hasta que el LLM valide
            estado_clasificacion_final=estado_clasificacion,
            fuente_clasificacion=FuenteClasificacion.USUARIO.value,
        )
        return await self.repo.create(respuesta)