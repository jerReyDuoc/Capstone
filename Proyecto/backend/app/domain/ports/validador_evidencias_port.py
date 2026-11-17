from abc import ABC, abstractmethod
from app.domain.evidencias.validacion_evidencia import ValidacionEvidencia
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.catalogo_brechas import CatalogoBrechas
from app.domain.ports.registro_ia_port import ContextoLlamada


class ValidadorEvidenciasPort(ABC):
    @abstractmethod
    async def validate(
        self,
        contenido: str,
        control: MatrizControl,
        respuesta: Respuesta,
        brecha: CatalogoBrechas | None = None,
        justificacion: str | None = None,
        contexto: ContextoLlamada | None = None,
    ) -> ValidacionEvidencia:
        """
        Valida una evidencia contra el control y la clasificación declarada.
        El LLM NO tiene acceso a la BD: solo recibe el prompt y devuelve JSON.

        `contenido` y `justificacion` llegan EN CLARO: la implementación es
        responsable de sanitizarlos antes de que salgan hacia el proveedor
        (ver app/application/ai/gateway.py). Si `justificacion` es None se usa
        la de `respuesta`. `contexto` sirve para las métricas y la auditoría.
        """
        ...
