"""
HU-18 · Puerto del filtro de entrada del agente de IA.

El agente pasa por aquí TODO texto no confiable antes del NER y del LLM. A diferencia de
PromptGuardPort (que solo responde "¿es inyección?"), este puerto dice QUÉ tipo de ataque
es, para auditarlo y medirlo por categoría.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class CategoriaAtaque(str, Enum):
    INYECCION = "inyeccion"            # "ignora las instrucciones anteriores"
    JAILBREAK = "jailbreak"            # cambio de rol o "sin restricciones" (DAN, modo desarrollador)
    FUGA_PROMPT = "fuga_prompt"        # pedir el system prompt, las reglas o el contexto en bruto
    DELIMITADORES = "delimitadores"    # etiquetas del prompt o roles falsos (</mensaje_usuario>, system:)
    CODIFICADO = "codificado"          # instrucciones ocultas en base64/hex/unicode
    USO_INDEBIDO = "uso_indebido"      # falsificar evidencia, ocultar incidentes o incumplimientos

    @classmethod
    def valores(cls) -> list[str]:
        return [c.value for c in cls]


@dataclass(frozen=True)
class ResultadoFiltro:
    bloquear: bool
    categoria: CategoriaAtaque | None = None
    regla: str | None = None           # identificador de la regla que disparó (sin texto del usuario)

    @classmethod
    def limpio(cls) -> "ResultadoFiltro":
        return cls(False)


class FiltroAgentePort(ABC):
    @abstractmethod
    def evaluar(self, texto: str, previos: list[str] | None = None) -> ResultadoFiltro:
        """
        `texto`: el mensaje nuevo. `previos`: los últimos mensajes del mismo usuario (ya
        anonimizados), para detectar un ataque repartido en varios turnos.
        """
        ...
