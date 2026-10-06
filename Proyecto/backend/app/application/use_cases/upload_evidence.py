import hashlib
from datetime import date
from fastapi import UploadFile
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.ports.file_storage_port import FileStoragePort
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository

class UploadEvidenceUseCase:
    def __init__(
        self,
        evidencia_repo: EvidenciaRepository,
        respuesta_repo: RespuestaRepository,
        storage: FileStoragePort,
    ):
        self.evidencia_repo = evidencia_repo
        self.respuesta_repo = respuesta_repo
        self.storage = storage

    async def execute(self, respuesta_id: int, file: UploadFile) -> Evidencia:
        respuesta = await self.respuesta_repo.get(respuesta_id)
        if not respuesta:
            raise ValueError(f"Respuesta {respuesta_id} no encontrada")

        content = await file.read()
        storage_path = await self.storage.save(content, file.filename)
        hash_archivo = hashlib.sha256(content).hexdigest()

        evidencia = Evidencia(
            respuesta_id=respuesta_id,
            nombre_archivo=file.filename,
            storage_path=storage_path,
            mime_type=file.content_type or "application/octet-stream",
            hash_archivo=hash_archivo,
            estado_validacion=EstadoValidacion.PENDING.value,
            fecha_subida=date.today(),
        )
        return await self.evidencia_repo.create(evidencia)