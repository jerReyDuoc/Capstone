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
        """
        HU-06: con el sanitizador activo se usa el MISMO motor que antes del LLM
        (NERSanitizer: también direcciones y etiquetas fijas). Si ese motor no está
        disponible se usa seguridad.anonimizar (regex de RUT, correo, teléfono y datos
        codificados; nombres si hay spaCy; falla si REQUIERE_NER=1).
        """
        if not texto:
            return texto
        if settings.SANITIZER_ENABLED:
            try:
                from app.infrastructure.security.ner_sanitizer import NERSanitizer
                return NERSanitizer().sanitizar(texto).texto
            except Exception:  # noqa: BLE001  (SanitizacionError: spaCy no disponible)
                pass
        _compartir_modelo_ner()
        return seguridad.anonimizar(texto)


def _compartir_modelo_ner() -> None:
    """
    T-04: seguridad.py carga su propia copia de spaCy (pipeline completo) la primera
    vez que anonimiza. Si el sanitizador está activo, se le entrega el modelo del
    motor NER (pipeline mínimo, ya precalentado): un solo modelo por proceso.
    Si spaCy no está, seguridad.py conserva su comportamiento (y REQUIERE_NER).
    """
    if not settings.SANITIZER_ENABLED or seguridad._NLP_INTENTADO:
        return
    try:
        from app.infrastructure.security.ner_sanitizer import cargar_spacy
        cargar_spacy()
    except Exception:  # noqa: BLE001
        pass


