from dataclasses import dataclass


@dataclass(frozen=True)
class PromptRenderizado:
    system: str
    user: str
    version: str


def escapar_para_prompt(texto: str | None) -> str:
    """Escapa < y > para que el texto no confiable no pueda cerrar los delimitadores
    (<justificacion_usuario>, <evidencia_adjunta>) del prompt."""
    return (texto or "").replace("<", "&lt;").replace(">", "&gt;")
