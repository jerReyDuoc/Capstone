"""
HU-39 · Salida estructurada del asistente de registro (mapa de datos y RAT).

El LLM no escribe en la BD: devuelve propuestas que el backend ancla a los catálogos y al mapa
(app/application/asistente/anclaje.py), revisa (canario, fuga del prompt, código, enlaces) y guarda
como "sugeridas". El usuario las acepta, edita o descarta (Human-in-the-Loop).

v1.1 (tokens): el modo estricto de Groq obliga a escribir TODOS los campos de cada objeto. Con una
propuesta plana (los campos de los tres tipos juntos) cada propuesta costaba ~35 claves y las
respuestas chocaban con el límite de tokens por minuto del proveedor. Ahora cada propuesta trae solo
su bloque (`elemento`, `flujo` o `actividad`) y los otros dos van en null.

El modo estricto no admite diccionarios libres (las explicaciones son una lista {campo, texto}) ni
límites de largo (se acotan al anclar).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TipoPropuestaIA = Literal["elemento", "flujo", "actividad"]
Confianza = Literal["alta", "media", "baja"]


class Explicacion(BaseModel):
    campo: str = Field(description="base_licitud, base_sensibles, plazos, riesgo, pais, garantia, tipo o general.")
    texto: str = Field(description="Por qué, en una o dos frases simples.")


class PlazoIA(BaseModel):
    categoria: str
    plazo: int | None
    unidad: str | None
    desde: str | None
    fundamento: str | None


class ElementoIA(BaseModel):
    tipo_elemento: str = Field(description="sistema, base_datos o tercero.")
    subtipo: str | None
    proveedor: str | None = Field(description="Empresa proveedora, nunca una persona.")
    pais: str | None = Field(description="ISO de 2 letras o null.")
    responsable: str | None = Field(description="Cargo o área, nunca una persona.")
    rol_tercero: str | None
    contrato_firmado: bool | None
    categorias_datos: list[str]
    categorias_titulares: list[str]


class FlujoIA(BaseModel):
    origen: str = Field(description="'id:<n>' o 'nuevo:<clave>' de un elemento.")
    destino: str = Field(description="'id:<n>' o 'nuevo:<clave>' de un elemento.")
    finalidad: str | None
    categorias_datos: list[str]
    garantia: str | None = Field(description="Solo si sale de Chile.")
    cifrado: bool | None


class ActividadIA(BaseModel):
    area: str | None
    elementos: list[str] = Field(description="'id:<n>' o 'nuevo:<clave>'.")
    flujos: list[str] = Field(description="'id:<n>' o 'nuevo:<clave>'.")
    finalidades: list[str]
    base_licitud: str | None
    interes_legitimo: str | None
    base_sensibles: str | None
    plazos: list[PlazoIA]
    riesgo_sugerido: str | None = Field(description="Bajo, Medio, Alto o Crítico.")


class PropuestaIA(BaseModel):
    tipo: TipoPropuestaIA
    clave: str = Field(description="Minúsculas y guiones bajos, única en la respuesta.")
    nombre: str
    elemento: ElementoIA | None = Field(description="Solo si tipo = elemento; si no, null.")
    flujo: FlujoIA | None = Field(description="Solo si tipo = flujo; si no, null.")
    actividad: ActividadIA | None = Field(description="Solo si tipo = actividad; si no, null.")
    explicaciones: list[Explicacion]
    confianza: Confianza


class InconsistenciaIA(BaseModel):
    codigo: str
    referencia: str | None
    texto: str


class AsistenteRatRespuesta(BaseModel):
    fuera_de_alcance: bool
    resumen: str = Field(description="Qué entendiste, en una o dos frases simples.")
    propuestas: list[PropuestaIA] = Field(description="Máximo 6.")
    inconsistencias: list[InconsistenciaIA]
    preguntas_pendientes: list[str] = Field(description="Hasta 2 preguntas cortas.")
