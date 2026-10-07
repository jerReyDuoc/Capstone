from datetime import date
from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
from app.domain.ports.file_storage_port import FileStoragePort
from app.domain.ports.evidence_validator_port import EvidenceValidatorPort
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.domain.models.evento_seguridad import OrigenEvento
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository


class ProcessEvidenceUseCase:
    def __init__(
        self,
        evidencia_repo: EvidenciaRepository,
        respuesta_repo: RespuestaRepository,
        storage: FileStoragePort,
        validator: EvidenceValidatorPort,
        guard: PromptGuardPort | None = None,
        registrar_evento: RegistrarEventoSeguridad | None = None,
    ):
        self.evidencia_repo = evidencia_repo
        self.respuesta_repo = respuesta_repo
        self.storage = storage
        self.validator = validator
        self.guard = guard
        self.registrar_evento = registrar_evento

    async def execute(self, evidencia_id: int) -> Evidencia:
        evidencia = await self.evidencia_repo.get(evidencia_id)
        if not evidencia:
            raise ValueError(f"Evidencia {evidencia_id} no encontrada")

        evidencia.estado_validacion = EstadoValidacion.PROCESSING.value
        await self.evidencia_repo.update(evidencia)

        try:
            # 1. Cargar contexto (el BACKEND lee de la BD, no el LLM)
            content_bytes = await self.storage.get(evidencia.storage_path)
            contenido = content_bytes.decode("utf-8", errors="ignore")

            respuesta = await self.respuesta_repo.get(evidencia.respuesta_id)
            if not respuesta:
                raise ValueError(f"Respuesta {evidencia.respuesta_id} no encontrada")

            control = None
            if respuesta.matriz_controles_id_control:
                control = await self.respuesta_repo.get_control(
                    respuesta.matriz_controles_id_control
                )

            # Cargar la brecha asociada al control (si existe) para pasarla al LLM
            # como CONTEXTO, no como decisión.
            brecha = None
            if control and control.catalogo_brechas_id_brecha:
                brecha = await self.respuesta_repo.get_brecha(
                    control.catalogo_brechas_id_brecha
                )

            # 2. CAPA DE SEGURIDAD (antes de que nada llegue al LLM)
            #    Solo se analiza/envía el fragmento que realmente verá el LLM.
            contenido = contenido[: settings.MAX_CHARS_EVIDENCIA_LLM]
            justificacion = respuesta.justificacion_usuario or ""

            evidencia_sospechosa = False
            if self.guard:
                # La justificación ya se revisó al crear la respuesta; se revisa de
                # nuevo por defensa en profundidad (filas antiguas, ediciones directas).
                if self.guard.detectar_inyeccion(justificacion):
                    await self._bloquear_por_seguridad(
                        respuesta, evidencia, OrigenEvento.JUSTIFICACION.value, justificacion, control
                    )
                    await self.respuesta_repo.update(respuesta)
                    return await self.evidencia_repo.update(evidencia)

                if self.guard.detectar_inyeccion(contenido):
                    if settings.MODO_SEGURIDAD_EVIDENCIA == "bloquear":
                        # Bloqueo preventivo: NO se llama al LLM
                        await self._bloquear_por_seguridad(
                            respuesta, evidencia, OrigenEvento.EVIDENCIA.value, contenido, control
                        )
                        await self.respuesta_repo.update(respuesta)
                        return await self.evidencia_repo.update(evidencia)
                    # Modo "marcar": se registra y se sigue, pero sin fallback al usuario
                    evidencia_sospechosa = True
                    await self._registrar(respuesta, evidencia, OrigenEvento.EVIDENCIA.value, contenido, control)

                # Ley 21.719: el LLM externo nunca recibe datos personales en claro
                contenido = self.guard.anonimizar(contenido)
                justificacion = self.guard.anonimizar(justificacion)

            # 3. Validar con LLM (solo texto entra, solo JSON sale)
            result = await self.validator.validate(
                contenido, control, respuesta, brecha, justificacion=justificacion
            )

            # 4. Persistir el resultado crudo del LLM en Evidencias
            evidencia.clasificacion_llm = result.clasificacion
            evidencia.confianza = result.confianza
            evidencia.justificacion_llm = result.justificacion
            evidencia.datos_extraidos = result.datos_extraidos
            evidencia.errores_validacion = result.errores
            evidencia.fecha_procesada = date.today()

            # 5. DECISIÓN DEL BACKEND (no del LLM)
            await self._apply_classification_decision(
                respuesta, control, evidencia, result, evidencia_sospechosa
            )
            if evidencia_sospechosa:
                evidencia.errores_validacion = list(evidencia.errores_validacion or []) + [
                    "Advertencia de seguridad: la evidencia contiene texto que parece "
                    "instrucciones para la IA. Evento registrado para revisión."
                ]

            await self.respuesta_repo.update(respuesta)
            return await self.evidencia_repo.update(evidencia)

        except Exception as e:
            evidencia.estado_validacion = EstadoValidacion.ERROR.value
            evidencia.errores_validacion = [str(e)]
            evidencia.fecha_procesada = date.today()
            return await self.evidencia_repo.update(evidencia)

    async def _bloquear_por_seguridad(
        self, respuesta: Respuesta, evidencia: Evidencia, origen: str, texto: str, control
    ) -> None:
        """
        Posible prompt injection: la evidencia se rechaza sin pasar por el LLM y la
        respuesta queda en 'requiere_revision' (cuenta como 0 puntos en el resumen)
        hasta que el Oficial de Cumplimiento la revise.
        """
        evidencia.estado_validacion = EstadoValidacion.REJECTED.value
        evidencia.clasificacion_llm = None
        evidencia.confianza = None
        evidencia.errores_validacion = [
            f"Bloqueo preventivo: posible prompt injection en la {origen}. "
            "La evidencia no fue enviada al LLM y quedó pendiente de revisión."
        ]
        evidencia.fecha_procesada = date.today()

        respuesta.estado_clasificacion_final = EstadoClasificacion.REQUIERE_REVISION.value
        respuesta.fuente_clasificacion = FuenteClasificacion.SEGURIDAD.value
        respuesta.confianza_clasificacion = None
        respuesta.fecha_validacion = date.today()
        await self._registrar(respuesta, evidencia, origen, texto, control)

    async def _registrar(self, respuesta, evidencia, origen: str, texto: str, control) -> None:
        if self.registrar_evento:
            await self.registrar_evento.execute(
                texto=texto,
                origen=origen,
                evaluacion_id=respuesta.evaluacion_id,
                matriz_control_id=getattr(control, "id_control", None),
                respuesta_id=respuesta.id,
                evidencia_id=evidencia.id_evidencia,
            )

    async def _apply_classification_decision(
        self,
        respuesta: Respuesta,
        control,
        evidencia: Evidencia,
        result,
        evidencia_sospechosa: bool = False,
    ) -> None:
        """
        Aplica las reglas de negocio sobre el resultado del LLM.
        Esta es la capa donde el BACKEND decide, no el LLM.
        """
        # Regla 0 (seguridad): evidencia sospechosa + LLM inseguro -> NO se acepta la
        # declaración del usuario (sería justo lo que busca un ataque); queda en revisión.
        if evidencia_sospechosa and result.confianza < settings.UMBRAL_CONFIANZA:
            respuesta.estado_clasificacion_final = EstadoClasificacion.REQUIERE_REVISION.value
            respuesta.fuente_clasificacion = FuenteClasificacion.SEGURIDAD.value
            respuesta.confianza_clasificacion = result.confianza
            respuesta.fecha_validacion = date.today()
            evidencia.estado_validacion = EstadoValidacion.REJECTED.value
            return

        # Regla 1: Si el LLM no está seguro, fallback al usuario
        if result.confianza < settings.UMBRAL_CONFIANZA:
            respuesta.estado_clasificacion_final = respuesta.estado_clasificacion
            respuesta.fuente_clasificacion = FuenteClasificacion.USUARIO.value
            evidencia.estado_validacion = EstadoValidacion.REJECTED.value
            respuesta.confianza_clasificacion = result.confianza
            respuesta.fecha_validacion = date.today()
            return

        # Regla 2: El LLM decide la clasificación final
        respuesta.estado_clasificacion_final = result.clasificacion
        respuesta.fuente_clasificacion = FuenteClasificacion.LLM.value
        respuesta.confianza_clasificacion = result.confianza
        respuesta.fecha_validacion = date.today()
        evidencia.estado_validacion = EstadoValidacion.VALIDATED.value

        # Regla 3: ASIGNACIÓN AUTOMÁTICA DE BRECHA (regla de negocio, no LLM)
        if result.clasificacion == EstadoClasificacion.NO_CUMPLIDO.value:
            if control and control.catalogo_brechas_id_brecha:
                respuesta.catalogo_brechas_id_brecha = control.catalogo_brechas_id_brecha