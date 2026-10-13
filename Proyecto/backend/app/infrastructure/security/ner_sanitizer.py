"""
Motor NER de sanitización (implementa SanitizerPort).

Motor híbrido, el mismo enfoque que usan herramientas como Microsoft Presidio:
  - Reglas (regex + validación) para datos con formato: RUT, correo, teléfono,
    direcciones con prefijo vial y datos codificados (Base64/Hex/Bin/B32).
  - Modelo estadístico spaCy (es_core_news_md) para lo que no tiene formato:
    nombres de persona (PER) y direcciones sin prefijo (LOC + número).

A diferencia de `seguridad.anonimizar` (que reemplaza en cadena y pierde las
posiciones), aquí primero se DETECTAN todos los spans, luego se fusionan los
solapados y al final se reemplaza en una sola pasada. Eso permite devolver el
mapa de entidades (tipo, valor, inicio, fin) para auditoría.

Reglas de negocio:
  - Etiquetas fijas: el mismo tipo SIEMPRE produce la misma etiqueta ([RUT_ANON]).
  - Fail-closed: si spaCy/modelo no cargan o algo falla, se lanza SanitizacionError.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.domain.ports.sanitizer_port import (
    EntidadDetectada,
    ResultadoSanitizacion,
    SanitizacionError,
    SanitizerPort,
    TipoEntidad,
)
from app.infrastructure.security import seguridad as _seg

VERSION_MOTOR = "1.0.0"
MODELO_NER = _seg.MODELO_NER  # es_core_news_md
# Caracteres extra que se analizan después del límite para no cortar una entidad
MARGEN_RECORTE = 500
# Profundidad de decodificación de datos codificados (igual que seguridad.py)
PROFUNDIDAD_DECODIFICACION = 3

# Prioridad al fusionar spans solapados (gana el mayor)
_PRIORIDAD = {
    TipoEntidad.CODIFICADO: 6,
    TipoEntidad.CORREO: 5,
    TipoEntidad.TELEFONO: 4,
    TipoEntidad.RUT: 3,
    TipoEntidad.DIRECCION: 2,
    TipoEntidad.NOMBRE: 1,
}

# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------
# Correo con ofuscación: "@", "[at]", "(arroba)", " arroba " y ".", "[punto]", " punto "
_AT = r"(?:@|\s*[\[\(\{]\s*(?:arroba|at)\s*[\]\)\}]\s*|\s+arroba\s+)"
_DOT = r"(?:\.|\s*[\[\(\{]\s*(?:punto|dot)\s*[\]\)\}]\s*|\s+punto\s+)"
_PALABRA_CORREO = r"[A-Za-z0-9_%+\-]+"
_RE_CORREO = re.compile(
    rf"(?<![A-Za-z0-9_%+\-.])"
    rf"{_PALABRA_CORREO}(?:{_DOT}{_PALABRA_CORREO})*"
    rf"{_AT}"
    rf"[A-Za-z0-9\-]+(?:{_DOT}[A-Za-z0-9\-]+)*{_DOT}[A-Za-z]{{2,}}"
    rf"(?![A-Za-z0-9\-])",
    re.IGNORECASE,
)

# Contexto que indica que un número es un RUT aunque su dígito verificador no calce
_RE_CONTEXTO_RUT = re.compile(r"(?i)(?:\brut\b|r\.u\.t|\brun\b|c[eé]dula|\bc\.?i\.?\b)[\s:.#Nº°n-]*$")

# Direcciones con prefijo vial chileno: "Av. Providencia 1234, depto 56, Providencia"
_PREFIJO_VIA = (
    r"(?i:calle|avenida|avda\.?|av\.?|pasaje|psje\.?|pje\.?|diagonal|alameda|paseo|"
    r"poblaci[oó]n|pobl\.?|condominio)"
)
_PALABRA_VIA = r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'.]+"
_NUMERO = r"(?:(?i:n[°º.]?|#|n[uú]mero|num\.?)\s*)?\d{1,5}\b"
_COMPLEMENTO = (
    r"(?:\s*[,\-]?\s*(?i:departamento|depto\.?|dpto\.?|oficina|of\.?|casa|block|torre|piso)\b\.?"
    r"\s*[\w\-]{1,6})*"
)
_COMUNA = r"(?:\s*,\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de\s+|del\s+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})?"
_RE_DIRECCION = re.compile(
    rf"\b{_PREFIJO_VIA}\s+(?:{_PALABRA_VIA}\s+){{0,5}}?{_NUMERO}{_COMPLEMENTO}{_COMUNA}"
)
# Número inmediatamente después de una entidad LOC de spaCy: "Los Leones 1234"
_RE_NUMERO_TRAS_LOC = re.compile(rf"^\s*{_NUMERO}{_COMPLEMENTO}")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def dv_rut(cuerpo: str) -> str:
    """Dígito verificador (módulo 11) de un RUT chileno."""
    suma, factor = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def rut_valido(texto: str) -> bool:
    limpio = re.sub(r"[^0-9kK]", "", texto).upper()
    if len(limpio) < 8:
        return False
    return dv_rut(limpio[:-1]) == limpio[-1]


@dataclass
class _Span:
    tipo: TipoEntidad
    inicio: int
    fin: int
    fuente: str


# ---------------------------------------------------------------------------
# Carga de spaCy (una vez por proceso)
# ---------------------------------------------------------------------------
_NLP = None
_NLP_LOCK = threading.Lock()


def cargar_spacy():
    """Carga es_core_news_md. Lanza excepción si no está: el sanitizador es fail-closed."""
    global _NLP
    if _NLP is None:
        with _NLP_LOCK:
            if _NLP is None:
                import spacy  # noqa: WPS433 (import diferido: es pesado)
                _NLP = spacy.load(MODELO_NER, disable=["parser", "lemmatizer"])
    return _NLP


# ---------------------------------------------------------------------------
# Sanitizador
# ---------------------------------------------------------------------------
class NERSanitizer(SanitizerPort):
    def __init__(self, cargar_nlp: Callable[[], object] = cargar_spacy):
        # Inyectable para tests (un NLP falso); en producción carga spaCy.
        self._cargar_nlp = cargar_nlp

    # ------------------------------------------------------------ API pública
    def sanitizar(self, texto: str, max_chars: int | None = None) -> ResultadoSanitizacion:
        inicio_t = time.perf_counter()
        try:
            nlp = self._cargar_nlp()
            if nlp is None:
                raise SanitizacionError("Motor NER no disponible")

            texto = texto or ""
            ventana = texto if max_chars is None else texto[: max_chars + MARGEN_RECORTE]
            t = _seg.normalizar(ventana)

            spans = self._detectar_reglas(t, PROFUNDIDAD_DECODIFICACION)
            spans += self._detectar_ner(nlp, t)
            spans = self._fusionar(spans)

            corte = len(t) if max_chars is None else min(len(t), max_chars)
            truncado = len(t) > corte or len(texto) > len(ventana)
            texto_san, entidades = self._reemplazar(t, spans, corte)

            return ResultadoSanitizacion(
                texto=texto_san,
                entidades=entidades,
                motor=self._descripcion_motor(nlp),
                truncado=truncado,
                duracion_ms=round((time.perf_counter() - inicio_t) * 1000, 2),
            )
        except SanitizacionError:
            raise
        except Exception as e:  # cualquier fallo -> fail-closed
            # No se incluye str(e): podría contener fragmentos del texto original.
            raise SanitizacionError(f"Fallo del motor de sanitización ({type(e).__name__})") from e

    # ------------------------------------------------------------ detección por reglas
    def _detectar_reglas(self, t: str, prof: int) -> list[_Span]:
        spans: list[_Span] = []

        if prof > 0:
            spans += self._detectar_codificados(t, prof)

        for m in _RE_CORREO.finditer(t):
            spans.append(_Span(TipoEntidad.CORREO, m.start(), m.end(), "regex"))

        for m in _seg._RE_TEL.finditer(t):
            spans.append(_Span(TipoEntidad.TELEFONO, m.start(), m.end(), "regex"))

        for m in _seg._RE_RUT.finditer(t):
            tipo = self._clasificar_numero(t, m)
            if tipo:
                spans.append(_Span(tipo, m.start(), m.end(), "regex"))

        for m in _seg._RE_PALABRAS.finditer(t):  # RUT dictado: "uno cinco cuatro..."
            fin = m.start() + len(m.group(0).rstrip(" ,.-\n\t"))
            spans.append(_Span(TipoEntidad.RUT, m.start(), fin, "regex"))

        for m in _RE_DIRECCION.finditer(t):
            spans.append(_Span(TipoEntidad.DIRECCION, m.start(), m.end(), "regex"))

        return spans

    @staticmethod
    def _clasificar_numero(t: str, m: re.Match) -> TipoEntidad | None:
        """
        Decide si un candidato de la regex de RUT es RUT, teléfono o un número cualquiera.
        Se privilegia NO filtrar PII (recall) sin anonimizar montos o fechas al azar:
          - formato explícito de RUT (12.345.678-9 / 12345678-K) -> RUT aunque el DV no calce
          - precedido de "RUT", "RUN", "cédula"...               -> RUT
          - 9 dígitos que empiezan en 9 (celular)                  -> teléfono
          - dígito verificador válido                              -> RUT
          - 9 dígitos que empiezan en 2 (fijo Santiago)            -> teléfono
          - resto (montos, fechas 20240315, folios)                -> no es PII
        """
        crudo = m.group(0)
        digitos = re.sub(r"[^0-9kK]", "", crudo)
        formato_rut = bool(re.search(r"-\s*[\dkK]$", crudo)) or crudo[-1] in "kK"
        if formato_rut or _RE_CONTEXTO_RUT.search(t[max(0, m.start() - 25): m.start()]):
            return TipoEntidad.RUT
        if len(digitos) == 9 and digitos[0] == "9":
            return TipoEntidad.TELEFONO
        if rut_valido(digitos):
            return TipoEntidad.RUT
        if len(digitos) == 9 and digitos[0] == "2":
            return TipoEntidad.TELEFONO
        return None

    def _detectar_codificados(self, t: str, prof: int) -> list[_Span]:
        """Un token Base64/Hex/Bin/B32 que al decodificarse contiene PII se oculta completo."""
        spans = []
        pares = (
            (_seg._RE_BIN, _seg._dec_bin),
            (_seg._RE_HEX, _seg._dec_hex),
            (_seg._RE_B32, _seg._dec_b32),
            (_seg._RE_B64, _seg._dec_b64),
        )
        for rx, dec in pares:
            for m in rx.finditer(t):
                decodificado = dec(m.group(0))
                if decodificado and _seg._imprimible(decodificado):
                    if self._detectar_reglas(_seg.normalizar(decodificado), prof - 1):
                        spans.append(_Span(TipoEntidad.CODIFICADO, m.start(), m.end(), "decodificado"))
        return spans

    # ------------------------------------------------------------ detección NER
    def _detectar_ner(self, nlp, t: str) -> list[_Span]:
        if not t.strip():
            return []
        if len(t) >= getattr(nlp, "max_length", 10**9):
            nlp.max_length = len(t) + 1

        spans: list[_Span] = []
        for e in nlp(t).ents:
            if e.label_ == "PER" and _seg._entidad_valida(e.text):
                spans.append(_Span(TipoEntidad.NOMBRE, e.start_char, e.end_char, "ner"))
            elif e.label_ == "LOC":
                num = _RE_NUMERO_TRAS_LOC.match(t[e.end_char:])
                if num:  # "Los Leones 1234" -> dirección
                    spans.append(_Span(TipoEntidad.DIRECCION, e.start_char, e.end_char + num.end(), "ner"))

        # spaCy rinde mal con NOMBRES EN MAYÚSCULAS: segunda pasada en 'Capitalizado'
        # (misma longitud -> mismos offsets). Solo se aceptan nombres de >= 2 palabras
        # que en el original estén en mayúscula, para no tocar siglas (SAP, ARCOP).
        alt = _seg._RE_MAYUS.sub(lambda m: m.group(0).capitalize(), t)
        if alt != t:
            for e in nlp(alt).ents:
                original = t[e.start_char:e.end_char]
                if (e.label_ == "PER" and original.isupper() and len(original.split()) >= 2
                        and _seg._entidad_valida(original)):
                    spans.append(_Span(TipoEntidad.NOMBRE, e.start_char, e.end_char, "ner"))
        return spans

    # ------------------------------------------------------------ fusión y reemplazo
    @staticmethod
    def _fusionar(spans: list[_Span]) -> list[_Span]:
        """Une spans solapados (unión de rangos: nunca queda un trozo de PII afuera)."""
        fusion: list[_Span] = []
        for s in sorted(spans, key=lambda s: (s.inicio, -(s.fin - s.inicio))):
            if s.fin <= s.inicio:
                continue
            if fusion and s.inicio < fusion[-1].fin:
                ult = fusion[-1]
                ult.fin = max(ult.fin, s.fin)
                if _PRIORIDAD[s.tipo] > _PRIORIDAD[ult.tipo]:
                    ult.tipo = s.tipo
                if s.fuente not in ult.fuente.split("+"):
                    ult.fuente = f"{ult.fuente}+{s.fuente}"
            else:
                fusion.append(_Span(s.tipo, s.inicio, s.fin, s.fuente))
        return fusion

    @staticmethod
    def _reemplazar(t: str, spans: list[_Span], corte: int):
        partes, entidades, pos = [], [], 0
        for s in spans:
            if s.inicio >= corte:
                break
            partes.append(t[pos:s.inicio])
            partes.append(s.tipo.etiqueta)
            entidades.append(EntidadDetectada(s.tipo, t[s.inicio:s.fin], s.inicio, s.fin, s.fuente))
            pos = s.fin
        if pos < corte:
            partes.append(t[pos:corte])
        return "".join(partes), entidades

    @staticmethod
    def _descripcion_motor(nlp) -> str:
        meta = getattr(nlp, "meta", None) or {}
        modelo = f"{meta.get('lang', 'es')}_{meta.get('name', MODELO_NER)}@{meta.get('version', '?')}"
        return f"ner_sanitizer/{VERSION_MOTOR}; spacy:{modelo}"
