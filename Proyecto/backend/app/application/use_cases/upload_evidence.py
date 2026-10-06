import hashlib
from datetime import date

from fastapi import UploadFile

from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import EstadoClasificacion
from app.domain.ports.file_storage_port import FileStoragePort
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository


class UploadEvidenceUseCase:
    """
    Caso de uso: subir una evidencia asociada a una respuesta.

    Reglas de negocio aplicadas aquí:
    - Solo se admiten evidencias para respuestas con clasificación
      'cumplido' o 'parcialmente_cumplido'.
    - Las respuestas con 'no_cumplido' o 'no_aplica' NO requieren evidencia.
    - El archivo se guarda en el storage configurado (local por defecto).
    - Se calcula un hash SHA-256 del contenido para detectar duplicados.
    """

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
        # 1. Verificar que la respuesta existe
        respuesta = await self.respuesta_repo.get(respuesta_id)
        if not respuesta:
            raise ValueError(f"Respuesta {respuesta_id} no encontrada")

        # 2. Regla de negocio: solo cumplido/parcialmente_cumplido requieren evidencia
        clasificacion_actual = respuesta.estado_clasificacion
        if not clasificacion_actual:
            raise ValueError(
                f"La respuesta {respuesta_id} no tiene clasificación declarada"
            )

        if not EstadoClasificacion.requiere_evidencia(clasificacion_actual):
            raise ValueError(
                f"No se puede subir evidencia para la clasificación "
                f"'{clasificacion_actual}'. Solo 'cumplido' y "
                f"'parcialmente_cumplido' requieren evidencia."
            )

        # 3. Leer contenido y calcular hash
        content = await file.read()
        if not content:
            raise ValueError("El archivo está vacío")

        hash_archivo = hashlib.sha256(content).hexdigest()

        # 4. Guardar el archivo en el storage
        storage_path = await self.storage.save(content, file.filename)

        # 5. Crear el registro en BD
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