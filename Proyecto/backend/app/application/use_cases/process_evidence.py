"""
Validación de una evidencia (lo ejecuta el worker ARQ).

HU-06 (decisión del PO, 16-oct): el archivo llega CIFRADO desde la API. Aquí se
descifra en memoria, la capa de seguridad revisa el original y la capa de IA lo
anonimiza antes del LLM. Al terminar (con cualquier resultado) el archivo cifrado
se REEMPLAZA por solo el texto anonimizado y se borra: en disco no queda el original.
Si el motor de anonimización falla, el archivo se deja cifrado (nunca en claro).
"""
import logging
from datetime import date

from app.application.ai.anonimizador import AnonimizadorPII
from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.models.respuesta import Respuesta, EstadoClasificacion, FuenteClasificacion
from app.domain.ports.file_storage_port import FileStoragePort
from app.domain.ports.evidence_validator_port import EvidenceValidatorPort
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.application.ai.gateway import CapaIAError
from app.domain.models.evento_seguridad import OrigenEvento
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository

logger = logging.getLogger("evidencias")

NOMBRE_TEXTO_ANONIMIZADO = "evidencia_anonimizada.txt"


class ProcessEvidenceUseCase:
    def __init__(
        self,
        evidencia_repo: EvidenciaRepository,
        respuesta_repo: RespuestaRepository,
        storage: FileStoragePort,
        validator: EvidenceValidatorPort,
        guard: PromptGuardPort | None = None,
        registrar_evento: RegistrarEventoSeguridad | None = None,
        anonimizador: AnonimizadorPII | None = None,
    ):
        self.evidencia_repo = evidencia_repo
        self.respuesta_repo = respuesta_repo
        self.storage = storage
        self.validator = validator
        self.guard = guard
        self.registrar_evento = registrar_evento
        # HU-06: el worker lo inyecta (factory.crear_anonimizador); sin él el archivo no se toca.
        self.anonimizador = anonimizador

    async def execute(self, evidencia_id: int) -> Evidencia:
        evidencia = await self.evidencia_repo.get(evidencia_id)
        if not evidencia:
            raise ValueError(f"Evidencia {evidencia_id} no encontrada")
        evidencia = await self._validar(evidencia)
        await self._conservar_solo_anonimizado(evidencia)
        return evidencia

    async def _conservar_solo_anonimizado(self, evidencia: Evidencia) -> None:
        """
        HU-06: reemplaza el archivo (cifrado) por su texto anonimizado y borra el original.
        Nunca rompe el flujo: si algo falla, el archivo queda cifrado y se registra en el log
        (sin contenido), para reintentarlo con scripts/migrar_pii_hu06.py.
        """
        anterior = evidencia.storage_path
        if self.anonimizador is None or not self.anonimizador.habilitado or not anterior:
            return
        try:
            original = await self.storage.get(anterior)
            anonimo = await self.anonimizador.anonimizar(original.decode("utf-8", errors="ignore")) or ""
            guardar = getattr(self.storage, "save_plano", self.storage.save)
            nueva = await guardar(anonimo.encode("utf-8"), NOMBRE_TEXTO_ANONIMIZADO)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-06: no se pudo anonimizar el archivo de la evidencia %s (%s); "
                         "queda cifrado", evidencia.id_evidencia, type(e).__name__)
            return
        try:
            evidencia.storage_path = nueva
            await self.evidencia_repo.update(evidencia)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-06: no se pudo registrar el archivo anonimizado de la evidencia %s (%s)",
                         evidencia.id_evidencia, type(e).__name__)
            await self._borrar(nueva)
            return
        await self._borrar(anterior)

    async def _borrar(self, ruta: str) -> None:
        try:
            await self.storage.delete(ruta)
        except Exception as e:  # noqa: BLE001
            logger.error("HU-06: no se pudo borrar un archivo de evidencia (%s)", type(e).__name__)

    async def _validar(self, evidencia: Evidencia) -> Evidencia:
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
            #    La detección de inyección mira el fragmento que verá el LLM. La
            #    anonimización y el recorte los hace la capa de IA (sanitiza primero
            #    y recorta después, para no dejar PII cortada a medias).
            fragmento = contenido[: settings.MAX_CHARS_EVIDENCIA_LLM]
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

                if self.guard.detectar_inyeccion(fragmento):
                    if settings.MODO_SEGURIDAD_EVIDENCIA == "bloquear":
                        # Bloqueo preventivo: NO se llama al LLM
                        await self._bloquear_por_seguridad(
                            respuesta, evidencia, OrigenEvento.EVIDENCIA.value, fragmento, control
                        )
                        await self.respuesta_repo.update(respuesta)
                        return await self.evidencia_repo.update(evidencia)
                    # Modo "marcar": se registra y se sigue, pero sin fallback al usuario
                    evidencia_sospechosa = True
                    await self._registrar(respuesta, evidencia, OrigenEvento.EVIDENCIA.value, fragmento, control)

            # 3. Validar con LLM a través de la capa de Políticas e IA.
            #    Ley 21.719: el validador sanitiza (NER) antes de que algo salga al
            #    proveedor; si no puede sanitizar, aborta (CapaIAError).
            try:
                result = await self.validator.validate(
                    contenido, control, respuesta, brecha, justificacion=justificacion,
                    contexto=ContextoLlamada(
                        evaluacion_id=respuesta.evaluacion_id,
                        respuesta_id=respuesta.id,
                        evidencia_id=evidencia.id_evidencia,
                    ),
                )
            except CapaIAError as e:
                # La respuesta conserva su estado; la evidencia queda en error con un
                # mensaje sin datos personales. La métrica ya la registró la capa de IA.
                evidencia.estado_validacion = EstadoValidacion.ERROR.value
                evidencia.errores_validacion = [f"[{e.tipo_error}] {e.mensaje_usuario}"]
                evidencia.fecha_procesada = date.today()
                return await self.evidencia_repo.update(evidencia)

            # 4. Persistir el resultado crudo del LLM en Evidencias
            evidencia.clasificacion_llm = result.clasificacion
            evidencia.confianza = result.confianza
            evidencia.justificacion_llm = result.justificacion
            # T-06 (minimización): `datos_extraidos` es un diccionario libre que el LLM
            # arma a partir de la evidencia, sin finalidad ni consumidor definidos (ni el
            # backend ni el frontend lo usan). No se persiste: cualquier dato que el NER
            # no hubiera detectado quedaría duplicado aquí.
            evidencia.datos_extraidos = None
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
        respuesta.sincronizar_brecha(control)
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
            respuesta.sincronizar_brecha(control)
            return

        # Regla 1: Si el LLM no está seguro, fallback al usuario
        if result.confianza < settings.UMBRAL_CONFIANZA:
            respuesta.estado_clasificacion_final = respuesta.estado_clasificacion
            respuesta.fuente_clasificacion = FuenteClasificacion.USUARIO.value
            evidencia.estado_validacion = EstadoValidacion.REJECTED.value
            respuesta.confianza_clasificacion = result.confianza
            respuesta.fecha_validacion = date.today()
            respuesta.sincronizar_brecha(control)
            return

        # Regla 2: El LLM decide la clasificación final
        respuesta.estado_clasificacion_final = result.clasificacion
        respuesta.fuente_clasificacion = FuenteClasificacion.LLM.value
        respuesta.confianza_clasificacion = result.confianza
        respuesta.fecha_validacion = date.today()
        evidencia.estado_validacion = EstadoValidacion.VALIDATED.value

        # Regla 3: BRECHA (regla de negocio, no LLM): se asigna si el estado final es
        # no_cumplido y se quita en cualquier otro (p. ej. una evidencia nueva lo mejora)
        respuesta.sincronizar_brecha(control)