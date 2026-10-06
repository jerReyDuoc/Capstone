from datetime import date
from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import FuenteClasificacion
from app.domain.ports.file_storage_port import FileStoragePort
from app.domain.ports.evidence_validator_port import EvidenceValidatorPort
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository

class ProcessEvidenceUseCase:
    def __init__(
        self,
        evidencia_repo: EvidenciaRepository,
        respuesta_repo: RespuestaRepository,
        storage: FileStoragePort,
        validator: EvidenceValidatorPort,
    ):
        self.evidencia_repo = evidencia_repo
        self.respuesta_repo = respuesta_repo
        self.storage = storage
        self.validator = validator

    async def execute(self, evidencia_id: int) -> Evidencia:
        evidencia = await self.evidencia_repo.get(evidencia_id)
        if not evidencia:
            raise ValueError(f"Evidencia {evidencia_id} no encontrada")

        evidencia.estado_validacion = EstadoValidacion.PROCESSING.value
        await self.evidencia_repo.update(evidencia)

        try:
            # 1. Recuperar contenido del archivo
            content_bytes = await self.storage.get(evidencia.storage_path)
            contenido = content_bytes.decode("utf-8", errors="ignore")

            # 2. Recuperar contexto del dominio
            respuesta = await self.respuesta_repo.get(evidencia.respuesta_id)
            if not respuesta:
                raise ValueError(f"Respuesta {evidencia.respuesta_id} no encontrada")

            control = None
            if respuesta.matriz_controles_id_control:
                control = await self.respuesta_repo.get_control(
                    respuesta.matriz_controles_id_control
                )

            # 3. Validar con LLM
            result = await self.validator.validate(contenido, control, respuesta)

            # 4. Persistir resultado crudo del LLM en Evidencias
            evidencia.clasificacion_llm = result.clasificacion
            evidencia.confianza = result.confianza
            evidencia.justificacion_llm = result.justificacion
            evidencia.datos_extraidos = result.datos_extraidos
            evidencia.errores_validacion = result.errores
            evidencia.fecha_procesada = date.today()

            # 5. Decisión automática sin humano
            if result.confianza >= settings.UMBRAL_CONFIANZA:
                respuesta.estado_clasificacion_final = result.clasificacion
                respuesta.fuente_clasificacion = FuenteClasificacion.LLM.value
                evidencia.estado_validacion = EstadoValidacion.VALIDATED.value
            else:
                # Fallback: se mantiene la clasificación del usuario
                respuesta.estado_clasificacion_final = respuesta.estado_clasificacion
                respuesta.fuente_clasificacion = FuenteClasificacion.USUARIO.value
                evidencia.estado_validacion = EstadoValidacion.REJECTED.value

            respuesta.confianza_clasificacion = result.confianza
            respuesta.fecha_validacion = date.today()

            await self.respuesta_repo.update(respuesta)
            return await self.evidencia_repo.update(evidencia)

        except Exception as e:
            evidencia.estado_validacion = EstadoValidacion.ERROR.value
            evidencia.errores_validacion = [str(e)]
            evidencia.fecha_procesada = date.today()
            return await self.evidencia_repo.update(evidencia)