"""
Dobles de prueba de la capa de Políticas e IA.
No requieren spaCy, BD ni API key: el NLP, el proveedor y el registro son falsos.
"""
from types import SimpleNamespace

from app.application.ai.gateway import AIGateway, PreciosModelo
from app.application.ai.politicas import crear_politicas
from app.application.schemas.evidence_validation import EvidenceValidation
from app.domain.ports.llm_provider_port import LLMProviderError, LLMProviderPort, LLMResponse
from app.domain.ports.registro_ia_port import RegistroIAPort
from app.infrastructure.security.ner_sanitizer import NERSanitizer


class StubNLP:
    """Imita spaCy: marca como PER/LOC las cadenas configuradas."""
    max_length = 10**6
    meta = {"lang": "es", "name": "stub", "version": "0"}

    def __init__(self, nombres=(), lugares=()):
        self.nombres, self.lugares = tuple(nombres), tuple(lugares)

    def __call__(self, texto):
        ents = []
        for etiqueta, items in (("PER", self.nombres), ("LOC", self.lugares)):
            for item in items:
                i = texto.find(item)
                while i >= 0:
                    ents.append(SimpleNamespace(label_=etiqueta, start_char=i,
                                                end_char=i + len(item), text=item))
                    i = texto.find(item, i + 1)
        return SimpleNamespace(ents=ents)


def sanitizer_stub(nombres=("Juan Pérez", "María González"), lugares=()):
    return NERSanitizer(lambda: StubNLP(nombres, lugares))


class FakeProvider(LLMProviderPort):
    nombre = "fake"
    modelo_por_defecto = "fake-model"

    def __init__(self, clasificacion="cumplido", confianza=0.95, error: LLMProviderError | None = None):
        self.clasificacion, self.confianza, self.error = clasificacion, confianza, error
        self.requests = []

    async def generar(self, req):
        self.requests.append(req)
        if self.error:
            raise self.error
        return LLMResponse(
            data=EvidenceValidation(
                clasificacion=self.clasificacion, confianza=self.confianza,
                justificacion="simulado", respalda_clasificacion_usuario=True,
                evidencia_suficiente=True,
            ),
            proveedor=self.nombre, modelo=self.modelo_por_defecto,
            tokens_entrada=1200, tokens_salida=300, latencia_ms=42.0,
        )

    def todo_lo_enviado(self) -> str:
        return "\n".join(r.system + "\n" + r.user for r in self.requests)


class FakeRegistro(RegistroIAPort):
    def __init__(self, fallar_sanitizaciones=False):
        self.llamadas, self.sanitizaciones = [], []
        self.fallar_sanitizaciones = fallar_sanitizaciones

    async def guardar_llamada(self, registro):
        self.llamadas.append(registro)
        return len(self.llamadas)

    async def guardar_sanitizaciones(self, registros):
        if self.fallar_sanitizaciones:
            raise RuntimeError("BD caída")
        self.sanitizaciones.extend(registros)


def crear_gateway(provider=None, sanitizer=None, registro=None, sanitizer_enabled=True,
                  max_chars_evidencia=8000):
    return AIGateway(
        provider=provider or FakeProvider(),
        sanitizer=sanitizer or sanitizer_stub(),
        registro=registro or FakeRegistro(),
        politicas=crear_politicas(max_chars_evidencia=max_chars_evidencia),
        sanitizer_enabled=sanitizer_enabled,
        precios=PreciosModelo(entrada_usd_1m=0.10, salida_usd_1m=0.50),
    )


def crear_validador(**kw):
    from app.application.ai.evidence_validator import GatewayEvidenceValidator  # usa modelos SQLAlchemy
    gw = crear_gateway(**kw)
    return GatewayEvidenceValidator(gw), gw
