"""
HU-39 criterio 3 · Documentos que sube la empresa (políticas, contratos con proveedores, avisos).

Reutiliza la extracción de HU-17 (app/application/evidencias/archivos.py: detectar_tipo, extraer_texto y
el RAG local recuperar_fragmentos) y agrega lo propio del asistente:

  tipo_documento()       política, contrato con proveedor, aviso u otro (reglas por palabras clave, sin LLM).
  densidad_pii()         entidades personales (NER) por cada 1.000 caracteres. Sobre el umbral el archivo
                         parece una planilla o un listado de personas y se rechaza ANTES del LLM: el
                         asistente lee documentos que describen procesos, no bases de datos de titulares.
  pasajes_relevantes()   los pasajes que más hablan de tratamiento de datos (BM25 de HU-17 con un
                         vocabulario de tratamiento en vez de los términos de un control).

Lógica pura: se prueba sin BD ni LLM.
"""
from __future__ import annotations

import re
import unicodedata
from types import SimpleNamespace

from app.application.evidencias.archivos import recuperar_fragmentos

# Vocabulario con que se buscan los pasajes útiles para el mapa y el RAT
_VOCABULARIO = SimpleNamespace(
    evidencia_esperada="finalidad tratamiento datos personales conservación plazo eliminación transferencia "
                       "internacional encargado proveedor terceros",
    obligacion="consentimiento contrato obligación legal interés legítimo titulares derechos seguridad cifrado",
    pregunta_evaluacion="sistema servidor nube país alojamiento base registro clientes trabajadores sensibles",
)

_REGLAS_TIPO: dict[str, tuple[str, ...]] = {
    "aviso": ("aviso de privacidad", "le informamos", "te informamos", "sus datos personales seran",
              "tus datos personales seran", "puede ejercer", "puedes ejercer", "derechos de acceso",
              "responsable del tratamiento es", "politica de cookies"),
    "contrato_proveedor": ("contrato", "las partes", "el proveedor", "el prestador", "encargado del tratamiento",
                           "prestacion de servicios", "clausula", "por cuenta del responsable", "subencargado",
                           "el cliente"),
    "politica": ("politica de", "procedimiento", "alcance", "objetivo", "roles y responsabilidades", "vigencia",
                 "aprobada por", "colaboradores", "se aplica a"),
}
NOMBRES_TIPO = {"politica": "Política o procedimiento interno", "contrato_proveedor": "Contrato con un proveedor",
                "aviso": "Aviso de privacidad", "otro": "Otro documento"}


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def tipo_documento(texto: str) -> str:
    """El tipo con más coincidencias (al menos 2); "otro" si no hay señales claras."""
    t = _plano(texto[:60000])
    puntajes = {tipo: sum(t.count(frase) for frase in frases) for tipo, frases in _REGLAS_TIPO.items()}
    tipo, puntos = max(puntajes.items(), key=lambda x: x[1])
    return tipo if puntos >= 2 else "otro"


def densidad_pii(entidades: int, caracteres: int) -> float:
    """Entidades personales por cada 1.000 caracteres."""
    if caracteres <= 0:
        return 0.0
    return round(1000 * entidades / caracteres, 2)


def parece_listado_de_personas(entidades: int, caracteres: int, umbral: float) -> bool:
    # Un documento muy corto con un par de nombres (firmas) no es un listado
    return entidades >= 10 and densidad_pii(entidades, caracteres) > umbral


def pasajes_relevantes(texto: str, max_chars: int) -> tuple[str, dict]:
    """(texto para el LLM, metadatos {aplicado, pasajes_total, pasajes_usados}). Si cabe, va completo."""
    return recuperar_fragmentos(texto, _VOCABULARIO, max_chars)
