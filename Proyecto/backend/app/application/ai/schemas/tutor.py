"""
HU-15 · Salida estructurada del Agente IA Tutor.

El LLM nunca devuelve texto libre: devuelve este schema (Structured Outputs de Groq) y
el agente lo valida y lo ancla al contexto antes de mostrarlo o guardarlo.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


class NivelTutor(str, Enum):
    INICIAL = "Inicial"
    INTERMEDIO = "Intermedio"
    AVANZADO = "Avanzado"

    @classmethod
    def valores(cls) -> list[str]:
        return [n.value for n in cls]

    @classmethod
    def normalizar(cls, valor: str | None) -> "NivelTutor | None":
        if not valor:
            return None
        v = str(valor).strip().lower()
        for n in cls:
            if n.value.lower() == v:
                return n
        return None


class TipoRespuestaTutor(str, Enum):
    EXPLICACION = "explicacion"            # explica una obligación o una brecha
    PLAN_ACCION = "plan_accion"            # pasos para cerrar una o más brechas
    ORIENTACION = "orientacion"            # recomendación contextual / siguiente paso
    FUERA_DE_ALCANCE = "fuera_de_alcance"  # la pregunta no es de gobernanza/las brechas


# v1.1 (prueba del equipo, 28-oct): lista cerrada. Con texto libre el modelo escribía áreas
# que el NER confundía con nombres ("Equipo de [NOMBRE_ANON]") y variaban en cada respuesta.
# Una lista cerrada no puede traer datos personales y no necesita anonimizarse.
# (Comentario y no docstring: el docstring viajaría en el JSON Schema hacia el LLM.)
class ResponsableSugerido(str, Enum):
    ENCARGADO_DATOS = "Encargado de Datos"
    OFICIAL_CUMPLIMIENTO = "Oficial de Cumplimiento"
    ALTA_DIRECCION = "Alta dirección / Directorio"
    TI = "Equipo de TI"
    SEGURIDAD = "Seguridad de la información"
    RIESGOS = "Gestión de Riesgos"
    LEGAL = "Asesoría legal"
    PERSONAS = "Personas / RR. HH."
    AUDITORIA = "Auditoría interna"
    DUENO_PROCESO = "Dueño del proceso o sistema de IA"
    COMPRAS = "Compras / Proveedores"


class PasoAccion(BaseModel):
    orden: int = Field(description="Número del paso, desde 1.")
    accion: str = Field(description="Qué hacer, en una o dos frases concretas.")
    responsable_sugerido: ResponsableSugerido | None = Field(
        None, description="Área responsable, de la lista. Nunca un nombre de persona.")
    evidencia_esperada: str | None = Field(
        None, description="Documento o registro que demuestra el paso (sirve como evidencia para la remediación).")


class TutorRespuesta(BaseModel):
    tipo: TipoRespuestaTutor = Field(description="Tipo de respuesta.")
    respuesta: str = Field(description="Respuesta principal para el usuario, en español, adaptada al nivel.")
    pasos: list[PasoAccion] = Field(
        default_factory=list, description="Pasos ordenados. Obligatorios si tipo = plan_accion.")
    brechas_referenciadas: list[str] = Field(
        default_factory=list,
        description="Códigos EXACTOS de las brechas del contexto a las que se refiere la respuesta.")
    sugerencias: list[str] = Field(
        default_factory=list,
        description=("Hasta 3 mensajes que el USUARIO podría enviarte a continuación, escritos en primera "
                     "persona como si él te los escribiera (p. ej. '¿Cómo hago el inventario del paso 1?'). "
                     "Nunca preguntas dirigidas al usuario."))
    # v1.1: NO lo genera el modelo (no va en el JSON Schema; inventaba números de artículo). Lo
    # completa el agente con el framework y el artículo REALES de los controles citados.
    referencias_normativas: SkipJsonSchema[list[str]] = Field(default_factory=list)
