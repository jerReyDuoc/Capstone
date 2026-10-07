import hashlib
import logging
from datetime import datetime, timezone

from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.ports.prompt_guard_port import PromptGuardPort

logger = logging.getLogger("seguridad")

MAX_EXTRACTO = 500


class RegistrarEventoSeguridad:
    """
    Guarda un intento de prompt injection y emite la alerta al Oficial de
    Cumplimiento (por ahora: log WARNING; aquí se conectaría correo/Slack).
    Nunca debe romper el flujo principal: si falla el registro, solo se loguea.
    """

    def __init__(self, repo, guard: PromptGuardPort):
        self.repo = repo
        self.guard = guard

    async def execute(
        self,
        texto: str,
        origen: str,
        evaluacion_id: int | None = None,
        matriz_control_id: int | None = None,
        respuesta_id: int | None = None,
        evidencia_id: int | None = None,
    ) -> EventoSeguridad | None:
        hash_texto = hashlib.sha256((texto or "").encode("utf-8", errors="ignore")).hexdigest()
        try:
            extracto = self.guard.anonimizar((texto or "")[:MAX_EXTRACTO])
        except Exception:  # p. ej. REQUIERE_NER=1 sin spaCy: no guardamos texto
            extracto = None

        logger.warning(
            "Prompt injection detectada (origen=%s, evaluacion=%s, respuesta=%s, evidencia=%s, hash=%s)",
            origen, evaluacion_id, respuesta_id, evidencia_id, hash_texto[:12],
        )
        try:
            return await self.repo.create(EventoSeguridad(
                fecha=datetime.now(timezone.utc).replace(tzinfo=None),
                tipo="prompt_injection",
                origen=origen,
                evaluacion_id=evaluacion_id,
                matriz_control_id=matriz_control_id,
                respuesta_id=respuesta_id,
                evidencia_id=evidencia_id,
                extracto=extracto,
                hash_texto=hash_texto,
                revisado=False,
            ))
        except Exception:
            logger.exception("No se pudo registrar el evento de seguridad")
            return None
