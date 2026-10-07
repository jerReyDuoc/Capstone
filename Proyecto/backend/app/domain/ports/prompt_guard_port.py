from abc import ABC, abstractmethod


class PromptGuardPort(ABC):
    """
    Capa de seguridad que se interpone entre el texto del usuario y el LLM
    (Prompt Injection + anonimización de datos personales, Ley 21.719).

    Los casos de uso dependen de esta interfaz, no de la implementación
    concreta (hoy: reglas + regex + NER opcional en infrastructure/security).
    """

    @abstractmethod
    def detectar_inyeccion(self, texto: str) -> bool:
        """True si el texto parece un intento de prompt injection / jailbreak / XSS."""
        ...

    @abstractmethod
    def anonimizar(self, texto: str) -> str:
        """Reemplaza RUT, correos, teléfonos, nombres y datos codificados por etiquetas."""
        ...
