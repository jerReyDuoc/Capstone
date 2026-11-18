"""
HU-31 · Textos de los dos consentimientos de la solicitud de contratación.

Son SEPARADOS a propósito (criterio 2): cada uno tiene su propia versión y su fecha de
aceptación en solicitud_contratacion. Si el PO cambia un texto, se sube SOLO su versión
en el .env (CONSENTIMIENTO_CONTACTO_VERSION o CONSENTIMIENTO_CONTRATACION_VERSION); el
frontend los lee de GET /api/contratacion/consentimiento, así que no hay que tocarlo.

Textos PROVISORIOS hasta que el PO apruebe los definitivos (pendiente "textos de
consentimiento" de HU-27). Redactados en lenguaje claro: qué datos, para qué, qué pasa
después y cómo se retira (Ley 21.719, consentimiento libre, informado y específico).

T-21: cada texto nombra su FINALIDAD, su PLAZO y la forma de RETIRO (desde «Mis derechos»);
por eso las dos versiones subieron a 2026-11-v1. Cada solicitud guarda la versión que aceptó
y la fecha de aceptación; las anteriores conservan la suya (no se reescriben).
"""
from dataclasses import dataclass

from app.core.config import settings

CONTACTO = "contacto"
MIGRACION = "migracion"

TEXTO_CONTACTO = (
    "Autorizo a Therion Labs a usar mi nombre, cargo, empresa, correo y teléfono (si lo indiqué) "
    "para contactarme por la contratación de ComplianceIA. Si la contratación no se concreta, "
    "estos datos se conservan hasta 6 meses y luego se eliminan. Puedo retirar esta autorización "
    "cuando quiera desde «Mis derechos»."
)

TEXTO_MIGRACION = (
    "Si mi empresa contrata, autorizo a Therion Labs a traspasar este diagnóstico (respuestas, "
    "evidencias anonimizadas, resultados, plan formativo e informes) a la cuenta de la empresa, para "
    "continuar sin repetir el autodiagnóstico. Desde ese momento mi clave temporal deja de funcionar. "
    "La asociación se mantiene mientras dure el contrato y sus 30 días hábiles de gracia. Puedo retirar "
    "esta autorización cuando quiera desde «Mis derechos»."
)


@dataclass(frozen=True)
class Consentimiento:
    clave: str
    titulo: str
    texto: str
    version: str

    def como_dict(self) -> dict:
        return {"clave": self.clave, "titulo": self.titulo, "texto": self.texto, "version": self.version}


def vigentes() -> dict[str, Consentimiento]:
    return {
        CONTACTO: Consentimiento(CONTACTO, "Contacto comercial", TEXTO_CONTACTO,
                                 settings.CONSENTIMIENTO_CONTACTO_VERSION),
        MIGRACION: Consentimiento(MIGRACION, "Asociar mi evaluación a la empresa", TEXTO_MIGRACION,
                                  settings.CONSENTIMIENTO_CONTRATACION_VERSION),
    }
