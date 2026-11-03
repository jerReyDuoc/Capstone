"""
HU-16 · Salida estructurada del Agente IA al adaptar un borrador.

El LLM no escribe el documento completo: reescribe algunas cláusulas de la plantilla
para la empresa y propone notas de revisión. El backend valida y ancla esa salida
(app/application/borradores/salida_ia.py) y arma el documento con su propio generador.

Sin límites de largo en el schema (el modo estricto de Groq no los admite): se acotan
al anclar la salida.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SeccionBorrador(BaseModel):
    clausula_id: str = Field(description="Identificador de la cláusula adaptada, copiado tal cual de la lista.")
    texto: str = Field(
        description="Texto adaptado de la cláusula, en español formal. Párrafos y viñetas con '- '; "
                    "sin títulos, tablas, código ni enlaces. Conserva o agrega marcadores [COMPLETAR: ...] "
                    "para todo dato de la empresa que no conozcas."
    )


class BorradorIA(BaseModel):
    introduccion: str = Field(
        description="Un párrafo breve que contextualiza el documento para el rubro y la situación de la "
                    "empresa. Vacío si no aporta."
    )
    secciones: list[SeccionBorrador] = Field(
        description="Cláusulas adaptadas (máximo 6): primero las PRIORITARIAS y las que piden las "
                    "instrucciones de la empresa. Deja fuera las que no necesitan cambios."
    )
    notas_revision: list[str] = Field(
        description="Hasta 5 puntos concretos que la empresa debe verificar o completar antes de aprobar."
    )
