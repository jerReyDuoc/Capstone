from abc import ABC, abstractmethod
from dataclasses import dataclass

# HU-33: perfiles de revisión
#   justificacion  texto corto escrito por el usuario: revisión estricta (por defecto)
#   evidencia      documento formal: el vocabulario de cumplimiento (aprobar, ejecutar,
#                  registrar, marcar...) solo cuenta si va dirigido a la IA o al resultado
PERFIL_JUSTIFICACION = "justificacion"
PERFIL_EVIDENCIA = "evidencia"


@dataclass(frozen=True)
class ResultadoGuard:
    """Resultado de la revisión. `regla` identifica la regla que disparó, sin texto del usuario."""
    bloquear: bool
    regla: str | None = None
    categoria: str | None = None


class PromptGuardPort(ABC):
    """
    Capa de seguridad que se interpone entre el texto del usuario y el LLM
    (Prompt Injection + anonimización de datos personales, Ley 21.719).

    Los casos de uso dependen de esta interfaz, no de la implementación
    concreta (hoy: reglas + regex + NER opcional en infrastructure/security).
    """

    @abstractmethod
    def detectar_inyeccion(self, texto: str) -> bool:
        """True si el texto parece un intento de prompt injection / jailbreak / XSS (revisión estricta)."""
        ...

    def analizar(self, texto: str, perfil: str = PERFIL_JUSTIFICACION) -> ResultadoGuard:
        """
        HU-33: revisa el texto con el perfil indicado y dice qué regla disparó.
        Por defecto (implementaciones antiguas o dobles de prueba) aplica la revisión
        estricta de `detectar_inyeccion` y no informa la regla.
        """
        return ResultadoGuard(bool(self.detectar_inyeccion(texto or "")))

    @abstractmethod
    def anonimizar(self, texto: str) -> str:
        """Reemplaza RUT, correos, teléfonos, nombres y datos codificados por etiquetas."""
        ...
