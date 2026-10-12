"""
Adaptador de PromptGuardPort basado en el módulo `seguridad.py`
(repositorio ComplianceAI-Prompt-Injection).

`seguridad.py` se copia tal cual desde ese repo: si lo actualizas allá
(nuevos patrones, nuevos tests), vuelve a copiarlo aquí.
"""
import os

from app.core.config import settings
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.infrastructure.security import seguridad
from app.application.ai.prompts.base import escapar_para_prompt  # noqa: F401  (re-export)

# seguridad.py lee REQUIERE_NER desde os.environ; pydantic-settings no lo exporta solo.
if settings.REQUIERE_NER:
    os.environ["REQUIERE_NER"] = "1"


class ReglasPromptGuard(PromptGuardPort):
    def detectar_inyeccion(self, texto: str) -> bool:
        if not texto:
            return False
        return seguridad.detectar_inyeccion(texto)

    def anonimizar(self, texto: str) -> str:
        if not texto:
            return texto
        return seguridad.anonimizar(texto)


