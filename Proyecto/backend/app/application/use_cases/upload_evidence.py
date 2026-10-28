import hashlib
from datetime import date

from fastapi import UploadFile

from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import EstadoClasificacion
from app.domain.ports.file_storage_port import FileStoragePort
from app.application.ai.anonimizador import AnonimizacionError, AnonimizadorPII
from app.application.evidencias.archivos import MIME, ArchivoNoAdmitidoError, detectar_tipo
from app.application.use_cases.create_respuesta import (
    AnonimizacionNoDisponibleError,
    EvaluacionCerradaError,
    RespuestaRechazadaError,
)
from app.core.config import settings
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository


class TipoArchivoNoAdmitidoError(RespuestaRechazadaError):
    """HU-17 (T-SM-55): solo PDF, DOCX y TXT, comprobados por su contenido."""
    status_code = 415
    codigo = "TIPO_NO_ADMITIDO"


class ArchivoDemasiadoGrandeError(RespuestaRechazadaError):
    status_code = 413
    codigo = "ARCHIVO_DEMASIADO_GRANDE"


def validar_archivo(nombre: str | None, contenido: bytes) -> str:
    """Tamaño máximo y lista blanca de tipos. Devuelve el MIME real del archivo."""
    if len(contenido) > settings.EVIDENCIA_MAX_MB * 1024 * 1024:
        raise ArchivoDemasiadoGrandeError(f"El archivo supera el máximo de {settings.EVIDENCIA_MAX_MB} MB.")
    try:
        return MIME[detectar_tipo(nombre, contenido)]
    except ArchivoNoAdmitidoError as e:
        raise TipoArchivoNoAdmitidoError(str(e)) from e


class UploadEvidenceUseCase:
    """
    Caso de uso: subir una evidencia asociada a una respuesta.

    Reglas de negocio aplicadas aquí:
    - Solo se admiten evidencias para respuestas declaradas 'cumplido',
      'parcialmente_cumplido' o 'requiere_revision' (HU-02: en este último el LLM
      decide con la evidencia si el control es cumplido, parcial o no cumplido).
    - Las respuestas con 'no_cumplido' o 'no_aplica' NO requieren evidencia.
    - El archivo se guarda en el storage configurado (local por defecto).
    - Se calcula un hash SHA-256 del contenido para detectar duplicados.
    - No se admiten evidencias en evaluaciones cerradas (409 EVALUACION_CERRADA).
    - HU-06: el storage de la API cifra el archivo en reposo (lo inyecta la ruta) y el
      nombre del archivo se guarda anonimizado ("CV_Juan_Perez.pdf" -> "CV_[NOMBRE_ANON].pdf").
      El hash SHA-256 se calcula sobre el contenido original (detección de duplicados);
      no permite reconstruir el documento.
    """

    def __init__(
        self,
        evidencia_repo: EvidenciaRepository,
        respuesta_repo: RespuestaRepository,
        storage: FileStoragePort,
        evaluaciones: EvaluacionRepository,
        anonimizador: AnonimizadorPII | None = None,
    ):
        self.evidencia_repo = evidencia_repo
        self.respuesta_repo = respuesta_repo
        self.storage = storage
        self.evaluaciones = evaluaciones
        self.anonimizador = anonimizador

    async def execute(self, respuesta_id: int, file: UploadFile) -> Evidencia:
        # 1. Verificar que la respuesta existe
        respuesta = await self.respuesta_repo.get(respuesta_id)
        if not respuesta:
            raise ValueError(f"Respuesta {respuesta_id} no encontrada")

        # 1b. La evaluación debe seguir abierta: tras completarla el puntaje ya
        #     está fijado y una evidencia nueva lo cambiaría después del cierre.
        contexto = await self.evaluaciones.get_contexto(respuesta.evaluacion_id)
        if contexto is not None and contexto.cerrada:
            raise EvaluacionCerradaError(
                f"La evaluación {respuesta.evaluacion_id} está cerrada "
                f"({contexto.estado_progreso}): ya no admite evidencias"
            )

        # 2. Regla de negocio: solo cumplido, parcialmente_cumplido y requiere_revision
        #    llevan evidencia
        clasificacion_actual = respuesta.estado_clasificacion
        if not clasificacion_actual:
            raise ValueError(
                f"La respuesta {respuesta_id} no tiene clasificación declarada"
            )

        if not EstadoClasificacion.requiere_evidencia(clasificacion_actual):
            raise ValueError(
                f"No se puede subir evidencia para la clasificación "
                f"'{clasificacion_actual}'. Solo 'cumplido', 'parcialmente_cumplido' "
                f"y 'requiere_revision' llevan evidencia."
            )

        # 3. Leer contenido y calcular hash
        content = await file.read()
        if not content:
            raise ValueError("El archivo está vacío")

        # 3a. HU-17: tamaño máximo y solo PDF, DOCX o TXT (por contenido, no solo por extensión)
        validar_archivo(file.filename, content)

        hash_archivo = hashlib.sha256(content).hexdigest()

        # 3b. HU-06: el nombre del archivo también puede traer datos personales
        nombre_archivo = file.filename or "evidencia"
        if self.anonimizador is not None:
            try:
                nombre_archivo = await self.anonimizador.anonimizar_nombre_archivo(nombre_archivo)
            except AnonimizacionError as e:
                raise AnonimizacionNoDisponibleError(
                    "No se pudo anonimizar el nombre del archivo (motor de anonimización no "
                    "disponible). Por seguridad no se guardó la evidencia."
                ) from e

        # 4. Guardar el archivo en el storage (cifrado en reposo; el nombre en disco es un UUID)
        storage_path = await self.storage.save(content, nombre_archivo)

        # 5. Crear el registro en BD
        evidencia = Evidencia(
            respuesta_id=respuesta_id,
            nombre_archivo=nombre_archivo,
            storage_path=storage_path,
            mime_type=file.content_type or "application/octet-stream",
            hash_archivo=hash_archivo,
            estado_validacion=EstadoValidacion.PENDING.value,
            fecha_subida=date.today(),
        )

        return await self.evidencia_repo.create(evidencia)