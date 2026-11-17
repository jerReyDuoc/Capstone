"""
HU-31 · Textos de los dos consentimientos de la solicitud de contratación.

Son SEPARADOS a propósito (criterio 2): cada uno tiene su propia versión y su fecha de
aceptación en solicitud_contratacion. Si el PO cambia un texto, se sube SOLO su versión
en el .env (CONSENTIMIENTO_CONTACTO_VERSION o CONSENTIMIENTO_CONTRATACION_VERSION); el
frontend los lee de GET /api/contratacion/consentimiento, así que no hay que tocarlo.

Textos PROVISORIOS hasta que el PO apruebe los definitivos (pendiente "textos de
consentimiento" de HU-27). Redactados en lenguaje claro: qué datos, para qué, qué pasa
después y cómo se retira (Ley 21.719, consentimiento libre, informado y específico).
"""
from dataclasses import dataclass

from app.core.config import settings

CONTACTO = "contacto"
MIGRACION = "migracion"

TEXTO_CONTACTO = (
    "Autorizo a Therion Labs a usar mi nombre, cargo, empresa, correo y teléfono (si lo indiqué) "
    "solo para contactarme sobre la contratación de ComplianceIA. Si la contratación no se concreta, "
    "estos datos se eliminan. Puedo retirar esta autorización cuando quiera ejerciendo mis derechos "
    "sobre datos personales."
)

TEXTO_MIGRACION = (
    "Si mi empresa contrata, autorizo a Therion Labs a asociarle esta evaluación con sus respuestas, "
    "evidencias anonimizadas, resultados, plan formativo e informes, para continuar sin repetir el "
    "autodiagnóstico. Desde ese momento mi clave temporal deja de funcionar y el acceso pasa a la "
    "cuenta de la empresa."
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
