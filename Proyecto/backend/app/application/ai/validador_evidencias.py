"""
Servicio de aplicación: implementa ValidadorEvidenciasPort usando el agente de IA.

ProcesarEvidenciaUseCase sigue dependiendo del mismo puerto de siempre. Desde HU-15 la
validación de evidencias es una SKILL del agente de LangGraph (app/application/ai/agente):
el agente la enruta a su nodo y ese nodo llama al GatewayIA con la tarea
VALIDAR_EVIDENCIA, así que sanitización, prompt, proveedor y métricas no cambian.
"""
from app.application.ai.agente import AgenteIA, HabilidadIA
from app.application.ai.gateway import GatewayIA
from app.domain.evidencias.validacion_evidencia import ValidacionEvidencia
from app.domain.ports.validador_evidencias_port import ValidadorEvidenciasPort
from app.domain.ports.registro_ia_port import ContextoLlamada


class ValidadorEvidenciasGateway(ValidadorEvidenciasPort):
    def __init__(self, gateway: GatewayIA, agente: AgenteIA | None = None):
        self.gateway = gateway
        self.agente = agente or AgenteIA(gateway)

    async def validate(
        self,
        contenido,
        control,
        respuesta,
        brecha=None,
        justificacion=None,
        contexto: ContextoLlamada | None = None,
    ) -> ValidacionEvidencia:
        if justificacion is None:
            justificacion = respuesta.justificacion_usuario
        salida = await self.agente.ejecutar(
            HabilidadIA.VALIDAR_EVIDENCIA,
            textos={"evidencia": contenido, "justificacion": justificacion},
            datos={"control": control, "respuesta": respuesta, "brecha": brecha},
            contexto=contexto,
        )
        return salida.resultado.data
