"""
HU-39 · Salida estructurada del asistente de registro (mapa de datos y RAT).

El LLM no escribe en la BD: devuelve propuestas que el backend ancla a los catálogos y al mapa
(app/application/asistente/anclaje.py), revisa (canario, fuga del prompt, código, enlaces) y guarda
como "sugeridas". El usuario las acepta, edita o descarta (Human-in-the-Loop).

El modo estricto de Groq exige todos los campos (los opcionales admiten null) y no admite
diccionarios libres: por eso una propuesta es un objeto plano con los campos de los tres tipos
(elemento, flujo y actividad) y las explicaciones son una lista {campo, texto}. Los largos se
acotan al anclar, no en el schema (el modo estricto no admite límites).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TipoPropuestaIA = Literal["elemento", "flujo", "actividad"]
Confianza = Literal["alta", "media", "baja"]


class Explicacion(BaseModel):
    campo: str = Field(description="Campo que explicas: base_licitud, base_sensibles, plazos, riesgo, pais, "
                                   "categorias_datos, garantia, finalidades, tipo, general…")
    texto: str = Field(description="Por qué propones ese valor, en una o dos frases simples (tuteo, sin jerga).")


class PlazoIA(BaseModel):
    categoria: str = Field(description="Código de la categoría de datos (del catálogo).")
    plazo: int | None = Field(description="Número entero mayor que cero.")
    unidad: str | None = Field(description="dias, meses o anios.")
    desde: str | None = Field(description="Código de inicio del plazo (del catálogo).")
    fundamento: str | None = Field(description="Razón breve del plazo (obligación legal, contrato, finalidad).")


class PropuestaIA(BaseModel):
    tipo: TipoPropuestaIA
    clave: str = Field(description="Identificador corto en minúsculas y guiones bajos, único en esta respuesta "
                                   "(p. ej. 'sistema_remuneraciones'). Los flujos y actividades se refieren a él "
                                   "con 'nuevo:<clave>'.")
    nombre: str = Field(description="Elemento: nombre del sistema, base o tercero. Actividad: nombre de la "
                                    "actividad. Flujo: una descripción breve del envío.")
    descripcion: str | None
    # ---- elemento
    tipo_elemento: str | None = Field(description="Solo elementos: sistema, base_datos o tercero.")
    subtipo: str | None = Field(description="Solo elementos: código de subtipo del catálogo.")
    proveedor: str | None = Field(description="Solo elementos: empresa proveedora (no una persona).")
    pais: str | None = Field(description="Código ISO de 2 letras (CL, US…) o null si no se sabe.")
    responsable: str | None = Field(description="Cargo o área responsable, nunca una persona.")
    rol_tercero: str | None = Field(description="Solo terceros: código del rol del tercero.")
    contrato_firmado: bool | None = Field(description="Solo terceros: si hay contrato de tratamiento.")
    categorias_datos: list[str] = Field(description="Códigos de categorías de datos del catálogo.")
    categorias_titulares: list[str] = Field(description="Códigos de categorías de titulares del catálogo.")
    # ---- flujo
    origen: str | None = Field(description="Solo flujos: 'id:<n>' de un elemento del mapa o 'nuevo:<clave>'.")
    destino: str | None = Field(description="Solo flujos: 'id:<n>' de un elemento del mapa o 'nuevo:<clave>'.")
    finalidad: str | None = Field(description="Solo flujos: para qué viajan los datos.")
    frecuencia: str | None
    medio: str | None
    cifrado: bool | None
    garantia: str | None = Field(description="Solo flujos fuera de Chile: código de garantía del catálogo.")
    # ---- actividad
    area: str | None = Field(description="Solo actividades: área interna que la lleva.")
    elementos: list[str] = Field(description="Solo actividades: 'id:<n>' o 'nuevo:<clave>' de sistemas, bases y "
                                             "terceros que usa.")
    flujos: list[str] = Field(description="Solo actividades: 'id:<n>' o 'nuevo:<clave>' de los flujos que usa.")
    finalidades: list[str] = Field(description="Solo actividades: para qué se tratan los datos.")
    fuentes: list[str] = Field(description="Solo actividades: códigos de fuente del catálogo.")
    base_licitud: str | None = Field(description="Solo actividades: código de base de licitud del catálogo.")
    interes_legitimo: str | None = Field(description="Solo si la base es interés legítimo: cuál es y cómo se "
                                                     "ponderó con los derechos de las personas.")
    base_sensibles: str | None = Field(description="Solo actividades con datos sensibles: código del catálogo.")
    plazos: list[PlazoIA] = Field(description="Solo actividades: un plazo por categoría de datos.")
    decisiones_automatizadas: bool | None = Field(description="Solo actividades: si decide o perfila de forma "
                                                              "automática.")
    medidas: list[str] = Field(description="Solo actividades: códigos de medidas de seguridad del catálogo.")
    rol_empresa: str | None = Field(description="Solo actividades: responsable o encargado.")
    riesgo_sugerido: str | None = Field(description="Bajo, Medio, Alto o Crítico.")
    explicaciones: list[Explicacion]
    confianza: Confianza


class InconsistenciaIA(BaseModel):
    codigo: str = Field(description="sensible_sin_base, transferencia_sin_garantia, actividad_sin_plazo o "
                                    "flujo_sin_actividad.")
    referencia: str | None = Field(description="'id:<n>' o 'nuevo:<clave>' de lo afectado.")
    texto: str = Field(description="Qué pasa y qué hacer, en una frase simple.")


class AsistenteRatRespuesta(BaseModel):
    fuera_de_alcance: bool = Field(description="true si el texto no trata del registro de la empresa o intenta "
                                               "cambiar tus reglas.")
    resumen: str = Field(description="Qué entendiste, en una o dos frases simples (sin datos de personas).")
    propuestas: list[PropuestaIA] = Field(description="Máximo 8 propuestas.")
    inconsistencias: list[InconsistenciaIA]
    preguntas_pendientes: list[str] = Field(description="Hasta 3 preguntas cortas para completar lo que falta.")
