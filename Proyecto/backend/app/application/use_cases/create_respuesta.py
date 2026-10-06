from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
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
        # Validar que la clasificación sea una de las 4 permitidas
        valores_validos = [e.value for e in EstadoClasificacion]
        if estado_clasificacion not in valores_validos:
            raise ValueError(
                f"Clasificación inválida: {estado_clasificacion}. "
                f"Debe ser una de: {', '.join(valores_validos)}"
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