"""Flujo de validación de una evidencia con la capa de seguridad y de IA."""
from datetime import date
from types import SimpleNamespace

from app.application.ai.verificacion_salida_evidencias import INYECCION
from app.application.evidencias.archivos import recuperar_fragmentos, terminos_control
from app.application.fabricas import fabricas
from app.core.config import settings
from app.domain.models.evidencia import Evidencia, EstadoValidacion
from app.domain.ports.extractor_texto_port import ArchivoIlegibleError
from app.domain.ports.guardia_prompt_port import PERFIL_EVIDENCIA, PERFIL_JUSTIFICACION
from app.domain.ports.registro_ia_port import ContextoLlamada
from app.application.ai.gateway import CapaIAError
from app.domain.models.evento_seguridad import OrigenEvento
from app.application.evidencias.casos_uso.procesar_evidencia.comun import (
    AVISO_RESPUESTA_CAMBIADA,
    AVISO_VERIFICACION,
    _texto_alerta,
)


def _declarado(respuesta) -> dict:
    """T-13: lo que el usuario declaró (estado y justificación), para comparar antes y después del LLM."""
    return {"estado": respuesta.estado_clasificacion, "justificacion": respuesta.justificacion_usuario or ""}


class ValidacionMixin:
    """Flujo de validación de una evidencia con la capa de seguridad y de IA."""

    async def _validar(self, evidencia: Evidencia) -> Evidencia:
        evidencia.estado_validacion = EstadoValidacion.PROCESSING.value
        await self.evidencia_repo.update(evidencia)

        try:
            # 1. Cargar contexto (el BACKEND lee de la BD, no el LLM)
            content_bytes = await self.storage.get(evidencia.storage_path)
            # HU-17: texto real según el tipo del archivo (PDF, DOCX, TXT)
            try:
                contenido = fabricas().extractor_texto.extraer_texto(content_bytes)
            except ArchivoIlegibleError as e:
                return await self._sin_texto(evidencia, str(e))
            # En la remediación un archivo sin texto se rechaza antes del LLM (en el cuestionario
            # sigue el flujo de siempre: el LLM con poca certeza deja la declaración del usuario).
            if evidencia.es_remediacion and len(contenido.strip()) < settings.EVIDENCIA_MIN_CARACTERES:
                return await self._sin_texto(
                    evidencia,
                    "No encontramos texto legible en el archivo (¿es un PDF escaneado?). "
                    "Sube una versión con texto seleccionable.",
                )

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

            # HU-17 C2: verificación local de los términos del control (no sale del servidor)
            if control is not None:
                evidencia.terminos_control = terminos_control(contenido, control)

            # HU-17 C2 · RAG local: si el documento no cabe en el prompt, el LLM recibe los
            # pasajes más relevantes para el control (no solo las primeras páginas)
            contenido, rag = recuperar_fragmentos(contenido, control, settings.MAX_CHARS_EVIDENCIA_LLM)
            if rag["aplicado"] and evidencia.terminos_control is not None:
                evidencia.terminos_control = {**evidencia.terminos_control, "rag": rag}

            # HU-17: en la remediación la declaración y la justificación son las de la evidencia
            remediacion = evidencia.es_remediacion
            respuesta_prompt = respuesta
            if remediacion:
                respuesta_prompt = SimpleNamespace(
                    id=respuesta.id, evaluacion_id=respuesta.evaluacion_id,
                    estado_clasificacion=evidencia.estado_declarado,
                    justificacion_usuario=evidencia.justificacion_remediacion,
                    matriz_controles_id_control=respuesta.matriz_controles_id_control,
                )

            # 2. CAPA DE SEGURIDAD (antes de que nada llegue al LLM)
            #    La detección de inyección mira el fragmento que verá el LLM. La
            #    anonimización y el recorte los hace la capa de IA (sanitiza primero
            #    y recorta después, para no dejar PII cortada a medias).
            fragmento = contenido[: settings.MAX_CHARS_EVIDENCIA_LLM]
            justificacion = (evidencia.justificacion_remediacion if remediacion
                             else respuesta.justificacion_usuario) or ""

            evidencia_sospechosa = False
            if self.guard:
                # HU-33: la justificación (texto corto del usuario) mantiene la revisión
                # ESTRICTA; la evidencia (documento formal) usa las reglas con contexto: el
                # vocabulario de cumplimiento solo cuenta si va dirigido a la IA o al resultado.
                # La justificación ya se revisó al crear la respuesta; se revisa de
                # nuevo por defensa en profundidad (filas antiguas, ediciones directas).
                det = self.guard.analizar(justificacion, PERFIL_JUSTIFICACION)
                if det.bloquear:
                    if remediacion:
                        return await self._rechazar_remediacion(respuesta, evidencia, OrigenEvento.JUSTIFICACION.value,
                                                                justificacion, control, det.regla)
                    await self._bloquear_por_seguridad(
                        respuesta, evidencia, OrigenEvento.JUSTIFICACION.value, justificacion, control, det.regla
                    )
                    await self.respuesta_repo.update(respuesta)
                    return await self.evidencia_repo.update(evidencia)

                det = self.guard.analizar(fragmento, PERFIL_EVIDENCIA)
                if det.bloquear:
                    if remediacion:
                        return await self._rechazar_remediacion(respuesta, evidencia, OrigenEvento.EVIDENCIA.value,
                                                                fragmento, control, det.regla)
                    if settings.MODO_SEGURIDAD_EVIDENCIA == "bloquear":
                        # Bloqueo preventivo: NO se llama al LLM
                        await self._bloquear_por_seguridad(
                            respuesta, evidencia, OrigenEvento.EVIDENCIA.value, fragmento, control, det.regla
                        )
                        await self.respuesta_repo.update(respuesta)
                        return await self.evidencia_repo.update(evidencia)
                    # Modo "marcar": se registra y se sigue, pero sin fallback al usuario
                    evidencia_sospechosa = True
                    await self._registrar(respuesta, evidencia, OrigenEvento.EVIDENCIA.value, fragmento, control,
                                          det.regla)

            # T-13: lo que declaró el usuario ANTES de llamar al LLM (la validación puede tardar y el usuario
            # puede cambiar su respuesta mientras tanto)
            declarado_antes = _declarado(respuesta)

            # 3. Validar con LLM a través de la capa de Políticas e IA.
            #    Ley 21.719: el validador sanitiza (NER) antes de que algo salga al
            #    proveedor; si no puede sanitizar, aborta (CapaIAError).
            try:
                result = await self.validator.validate(
                    contenido, control, respuesta_prompt, brecha, justificacion=justificacion,
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

            # T-13: se relee la respuesta CON BLOQUEO. Si el usuario la cambió mientras se revisaba el
            # documento, la clasificación de la IA no se aplica (se conserva su elección).
            respuesta = await self._releer_respuesta(respuesta)
            if _declarado(respuesta) != declarado_antes:
                return await self._descartar_por_cambio(evidencia, respuesta, declarado_antes)

            # 3b. HU-07: verificar la salida del modelo ANTES de usarla o guardarla
            verificacion = self._verificar(result, contenido, justificacion, control, brecha,
                                           respuesta_prompt.estado_clasificacion)
            if verificacion is not None:
                result = verificacion.salida if verificacion.salida is not None else result
                if self._retener(verificacion, result):
                    await self._registrar(
                        respuesta, evidencia, OrigenEvento.SALIDA_LLM.value, _texto_alerta(result), control,
                        f"salida.{verificacion.principal.codigo}", tipo=verificacion.principal.categoria,
                    )
                    if settings.MODO_VERIFICACION_SALIDA == "bloquear":
                        self._retener_propuesta(respuesta, evidencia, control, verificacion, remediacion)
                        if not remediacion:
                            await self.respuesta_repo.update(respuesta)
                        return await self.evidencia_repo.update(evidencia)
                    evidencia_sospechosa = evidencia_sospechosa or verificacion.tiene(INYECCION)
                else:
                    verificacion = None  # nada grave: se sigue como siempre

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
            if remediacion:
                self._decidir_remediacion(respuesta, control, evidencia, result)
            else:
                await self._apply_classification_decision(
                    respuesta, control, evidencia, result, evidencia_sospechosa
                )
            if evidencia_sospechosa:
                evidencia.errores_validacion = list(evidencia.errores_validacion or []) + [
                    "Advertencia de seguridad: la evidencia contiene texto que parece "
                    "instrucciones para la IA. Evento registrado para revisión."
                ]
            if verificacion is not None:  # HU-07 en modo "marcar"
                evidencia.errores_validacion = list(evidencia.errores_validacion or []) + [AVISO_VERIFICACION]

            await self.respuesta_repo.update(respuesta)
            return await self.evidencia_repo.update(evidencia)

        except Exception as e:
            evidencia.estado_validacion = EstadoValidacion.ERROR.value
            evidencia.errores_validacion = [str(e)]
            evidencia.fecha_procesada = date.today()
            return await self.evidencia_repo.update(evidencia)
    async def _releer_respuesta(self, respuesta):
        releer = getattr(self.respuesta_repo, "releer_bloqueada", None)
        if releer is None:          # dobles de prueba: la misma respuesta (sin cambios)
            return respuesta
        actual = await releer(respuesta.id)
        if actual is None:
            raise ValueError(f"Respuesta {respuesta.id} no encontrada")
        return actual

    async def _descartar_por_cambio(self, evidencia: Evidencia, respuesta, antes: dict) -> Evidencia:
        """T-13: la respuesta cambió durante la validación. La evidencia queda rechazada con un aviso
        claro para volver a subirla, la respuesta no se toca y el descarte queda en el audit_log."""
        evidencia.estado_validacion = EstadoValidacion.REJECTED.value
        evidencia.clasificacion_llm = None
        evidencia.confianza = None
        evidencia.justificacion_llm = None
        evidencia.datos_extraidos = None
        evidencia.errores_validacion = [AVISO_RESPUESTA_CAMBIADA]
        evidencia.fecha_procesada = date.today()
        if self.auditar_descarte is not None:
            self.auditar_descarte(evidencia, respuesta, {
                "motivo": "respuesta_cambiada",
                "estado_antes": antes["estado"], "estado_actual": respuesta.estado_clasificacion,
                "justificacion_cambio": antes["justificacion"] != (respuesta.justificacion_usuario or ""),
            })
        return await self.evidencia_repo.update(evidencia)   # confirma y libera el bloqueo

    async def _sin_texto(self, evidencia: Evidencia, mensaje: str) -> Evidencia:
        """Archivo sin texto legible: no se gasta una llamada al LLM; la respuesta no cambia."""
        evidencia.estado_validacion = EstadoValidacion.REJECTED.value
        evidencia.errores_validacion = [mensaje]
        evidencia.fecha_procesada = date.today()
        return await self.evidencia_repo.update(evidencia)
