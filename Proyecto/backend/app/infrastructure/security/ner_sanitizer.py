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

Rendimiento (T-04, objetivo < 2,0 s por página; ver scripts/benchmark_ner.py):
  - Pipeline mínimo: el NER de es_core_news_md trae su propio tok2vec, así que se
    cargan SOLO "ner" (sin tok2vec compartido, morphologizer, parser,
    attribute_ruler ni lemmatizer). Mismas entidades, ~45 % menos de CPU.
  - La segunda pasada para NOMBRES EN MAYÚSCULAS ya no reprocesa el texto entero:
    solo corre si hay secuencias de >= 2 palabras en mayúscula, y solo sobre una
    ventana alrededor de cada una (las siglas sueltas como ISO o DPO no la activan).
  - Un único modelo por proceso, compartido con seguridad.py (antes se cargaban dos)
    y precalentado al cargarse, para que la primera evidencia no pague la latencia.

Precisión (v1.1.0):
  - "la Ley 21.719", "artículo 14"... no son direcciones aunque spaCy marque LOC + número.
  - Cargos sin nombre ("Presidenta del Directorio") no son NOMBRE; con nombre
    ("Gerente General Pedro Soto", que spaCy marca ORG) se anonimiza solo el nombre.
  - "Los Leones 456" (LOC que ya incluye el número) se reconoce como dirección.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable

from app.domain.ports.sanitizer_port import (
    EntidadDetectada,
    ResultadoSanitizacion,
    SanitizacionError,
    SanitizerPort,
    TipoEntidad,
)
from app.infrastructure.security import seguridad as _seg

logger = logging.getLogger(__name__)

VERSION_MOTOR = "1.1.0"
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
# \w (Unicode) y no [A-Za-z]: "matías.díaz@empresa.cl" se anonimizaba solo desde
# la última letra con tilde ("az@empresa.cl"), dejando visible "matías.dí" (v1.1.0).
_PALABRA_CORREO = r"[\w%+\-]+"
_RE_CORREO = re.compile(
    rf"(?<![\w%+\-.])"
    rf"{_PALABRA_CORREO}(?:{_DOT}{_PALABRA_CORREO})*"
    rf"{_AT}"
    rf"[\w\-]+(?:{_DOT}[\w\-]+)*{_DOT}[A-Za-z]{{2,}}"
    rf"(?![\w\-])",
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
# LOC que ya incluye el número: spaCy suele devolver "Los Leones 456" como un solo LOC
_RE_LOC_TERMINA_EN_NUMERO = re.compile(r"\s\d{1,5}$")
_RE_COMPLEMENTO_TRAS = re.compile(_COMPLEMENTO)  # siempre calza (puede ser vacío)

# ---------------------------------------------------------------------------
# Léxicos de precisión (falsos positivos vistos en la prueba en vivo del 13-oct)
# ---------------------------------------------------------------------------
# Una "dirección" que en realidad es una referencia normativa: "la Ley 21.719",
# "artículo 14", "ISO 27001", "NCh 2777". Se compara sin tildes y en minúscula.
_NORMATIVOS = {
    "ley", "leyes", "decreto", "dl", "dfl", "ds", "articulo", "art", "arts", "norma", "normas",
    "iso", "nch", "iec", "circular", "resolucion", "res", "capitulo", "cap", "titulo", "anexo",
    "seccion", "version", "inciso", "numeral", "pagina", "pag", "tabla", "figura", "codigo",
    "reglamento", "oficio", "acta", "folio", "clausula",
}
# Cargos, tratamientos y conectores: se recortan de los bordes de un NOMBRE. Si no
# queda nada, no era una persona ("Presidenta del Directorio").
_CARGOS = {
    "presidente", "presidenta", "vicepresidente", "vicepresidenta", "director", "directora",
    "directorio", "gerente", "subgerente", "gerencia", "jefe", "jefa", "jefatura", "encargado",
    "encargada", "oficial", "secretario", "secretaria", "ministro", "ministra", "subsecretario",
    "subsecretaria", "fiscal", "coordinador", "coordinadora", "analista", "auditor", "auditora",
    "consejero", "consejera", "asesor", "asesora", "abogado", "abogada", "administrador",
    "administradora", "tesorero", "tesorera", "ejecutivo", "ejecutiva", "general", "comite",
    "cumplimiento", "proteccion", "datos", "personales", "seguridad", "informacion", "riesgos",
    "tecnologias", "tecnologia", "ti", "operaciones", "finanzas", "legal", "area", "unidad",
    "sr", "sra", "srta", "senor", "senora", "senorita", "don", "dona", "dr", "dra", "ing",
    "lic", "prof", "profesor", "profesora", "de", "del", "la", "el", "los", "las", "y", "e",
}
# Un ORG/MISC solo puede ser "cargo + nombre" si empieza con un cargo (no con "de", "la"...)
_CARGOS_INICIALES = _CARGOS - {"de", "del", "la", "el", "los", "las", "y", "e"}
# Palabras de organización: un ORG/MISC con alguna de ellas no se trata como persona.
_ORGANIZACION = {
    "banco", "ministerio", "universidad", "empresa", "empresas", "sociedad", "servicio",
    "superintendencia", "agencia", "consejo", "instituto", "fundacion", "corporacion",
    "municipalidad", "gobierno", "camara", "tribunal", "corte", "comision", "asociacion",
    "sa", "spa", "ltda", "eirl", "inc", "corp", "group", "grupo", "holding", "estado",
}
# Secuencias de >= 2 palabras en MAYÚSCULA (candidatas a nombre: "MARÍA GONZÁLEZ ROJAS").
# Solo estas activan la segunda pasada; una sigla suelta (ISO, DPO, SAP) no.
_PAL_MAYUS = r"[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ'\-]*"
_RE_RACHA_MAYUS = re.compile(rf"\b{_PAL_MAYUS}(?:[ \t]+{_PAL_MAYUS})+\b")
# Contexto que se agrega a cada lado de la racha para que el modelo tenga de dónde inferir
CONTEXTO_MAYUS = 80
_RE_TOKEN = re.compile(r"\S+")


def _plano(palabra: str) -> str:
    """minúscula, sin tildes ni puntuación de borde: 'Artículo,' -> 'articulo'."""
    p = unicodedata.normalize("NFD", palabra.lower().strip(".,;:()[]{}\"'«»"))
    return "".join(c for c in p if unicodedata.category(c) != "Mn")


def _descartable_en_borde(palabra: str) -> bool:
    """Cargo/conector, o verbo en pretérito al inicio de oración que spaCy pega al
    nombre ("Asistió", "Aprobó", "Firmó"). Los nombres no terminan en -ó."""
    limpia = palabra.strip(".,;:()[]{}\"'«»")
    return _plano(limpia) in _CARGOS or (len(limpia) >= 4 and limpia.lower().endswith("ó"))


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
# Componentes que NO necesita el NER de es_core_news_md (su "ner" trae tok2vec propio)
_COMPONENTES_EXCLUIDOS = ["tok2vec", "morphologizer", "parser", "senter", "attribute_ruler", "lemmatizer"]
_TEXTO_CALENTAMIENTO = (
    "La política fue aprobada por Juan Pérez Soto, Encargado de Protección de Datos, "
    "en la oficina de Av. Providencia 1234, Santiago. MARÍA GONZÁLEZ ROJAS revisó el acta."
)


def _cargar_pipeline_minimo():
    import spacy  # noqa: WPS433 (import diferido: es pesado)
    try:
        nlp = spacy.load(MODELO_NER, exclude=_COMPONENTES_EXCLUIDOS)
        if "ner" not in nlp.pipe_names:
            raise ValueError("el modelo no trae componente 'ner'")
        nlp(_TEXTO_CALENTAMIENTO)  # falla aquí si el ner dependiera de un tok2vec compartido
        return nlp
    except (OSError, ImportError):
        raise  # modelo no instalado: fail-closed, no hay alternativa
    except Exception as e:  # noqa: BLE001
        # Otro modelo (p. ej. uno cuyo ner escucha a un tok2vec compartido): pipeline
        # completo, sin parser ni lemmatizer. Más lento, igual de preciso.
        logger.warning("Pipeline NER mínimo no disponible para %s (%s); se usa el completo.",
                       MODELO_NER, type(e).__name__)
        nlp = spacy.load(MODELO_NER, disable=["parser", "lemmatizer"])
        nlp(_TEXTO_CALENTAMIENTO)
        return nlp


def cargar_spacy():
    """
    Carga el modelo UNA vez por proceso (pipeline mínimo + precalentado) y lo
    comparte con seguridad.py, que antes cargaba su propia copia.
    Lanza excepción si no está: el sanitizador es fail-closed.
    """
    global _NLP
    if _NLP is None:
        with _NLP_LOCK:
            if _NLP is None:
                nlp = _cargar_pipeline_minimo()
                # seguridad.py (anonimizar de los eventos de seguridad) usa solo .ents:
                # se le entrega la misma instancia en vez de cargar una segunda copia.
                _seg._NLP, _seg._NLP_INTENTADO = nlp, True
                _NLP = nlp
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
            if e.label_ == "PER":
                s = self._persona(t, e.start_char, e.end_char)
                if s:
                    spans.append(s)
            elif e.label_ in ("ORG", "MISC"):
                s = self._persona_con_cargo(t, e.start_char, e.end_char)
                if s:
                    spans.append(s)
            elif e.label_ == "LOC":
                s = self._direccion(t, e.start_char, e.end_char)
                if s:
                    spans.append(s)

        # spaCy rinde mal con NOMBRES EN MAYÚSCULAS: segunda pasada en 'Capitalizado'
        # (misma longitud -> mismos offsets). Solo se aceptan nombres de >= 2 palabras
        # que en el original estén en mayúscula, para no tocar siglas (SAP, ARCOP).
        # Optimización T-04: se procesan solo ventanas alrededor de las rachas de
        # palabras en mayúscula, no el documento completo otra vez.
        ventanas = self._ventanas_mayusculas(t)
        if ventanas:
            textos_alt = [_seg._RE_MAYUS.sub(lambda m: m.group(0).capitalize(), t[i:f]) for i, f in ventanas]
            for (ini_v, _), doc in zip(ventanas, self._procesar_lote(nlp, textos_alt)):
                for e in doc.ents:
                    a, b = ini_v + e.start_char, ini_v + e.end_char
                    original = t[a:b]
                    if e.label_ == "PER" and original.isupper() and len(original.split()) >= 2:
                        s = self._persona(t, a, b)
                        if s:
                            spans.append(s)
        return spans

    # ------------------------------------------------------------ ayudas NER
    @staticmethod
    def _procesar_lote(nlp, textos: list[str]) -> Iterable:
        pipe = getattr(nlp, "pipe", None)
        return pipe(textos) if callable(pipe) else (nlp(x) for x in textos)

    @staticmethod
    def _ventanas_mayusculas(t: str) -> list[tuple[int, int]]:
        """Rangos [ini, fin) con contexto alrededor de cada racha de >= 2 palabras en
        MAYÚSCULA que tenga al menos una palabra de 3+ letras. Se fusionan los solapados
        y se ajustan a espacios para no partir palabras."""
        ventanas: list[list[int]] = []
        for m in _RE_RACHA_MAYUS.finditer(t):
            if not any(len(p) >= 3 for p in m.group(0).split()):
                continue
            ini = max(0, m.start() - CONTEXTO_MAYUS)
            fin = min(len(t), m.end() + CONTEXTO_MAYUS)
            while ini > 0 and not t[ini - 1].isspace():
                ini -= 1
            while fin < len(t) and not t[fin].isspace():
                fin += 1
            if ventanas and ini <= ventanas[-1][1]:
                ventanas[-1][1] = max(ventanas[-1][1], fin)
            else:
                ventanas.append([ini, fin])
        return [(i, f) for i, f in ventanas]

    @staticmethod
    def _recortar_cargos(t: str, ini: int, fin: int) -> tuple[int, int] | None:
        """Quita de los bordes del span cargos, tratamientos, conectores y verbos en
        pretérito ("Asistió la Presidenta del Directorio"). None si no queda nada."""
        tokens = [(m.start() + ini, m.end() + ini, m.group(0)) for m in _RE_TOKEN.finditer(t[ini:fin])]
        while tokens and _descartable_en_borde(tokens[0][2]):
            tokens.pop(0)
        while tokens and _descartable_en_borde(tokens[-1][2]):
            tokens.pop()
        if not tokens:
            return None
        a, b = tokens[0][0], tokens[-1][1]
        while b > a and t[b - 1] in ".,;:":
            b -= 1
        return a, b

    def _persona(self, t: str, ini: int, fin: int) -> _Span | None:
        rango = self._recortar_cargos(t, ini, fin)
        if not rango or not _seg._entidad_valida(t[rango[0]:rango[1]]):
            return None
        return _Span(TipoEntidad.NOMBRE, rango[0], rango[1], "ner")

    def _persona_con_cargo(self, t: str, ini: int, fin: int) -> _Span | None:
        """spaCy marca 'Gerente General Pedro Soto Rojas' como ORG: si el span EMPIEZA con
        un cargo y lo que queda son >= 2 palabras Capitalizadas que no son de organización,
        es una persona. Un ORG/MISC sin cargo al inicio se deja como está."""
        palabras = t[ini:fin].split()
        if not palabras or _plano(palabras[0]) not in _CARGOS_INICIALES:
            return None
        rango = self._recortar_cargos(t, ini, fin)
        if not rango:
            return None
        resto = t[rango[0]:rango[1]].split()
        if (len(resto) >= 2 and all(p[:1].isupper() for p in resto)
                and not any(_plano(p) in _ORGANIZACION or _plano(p) in _CARGOS for p in resto)):
            return self._persona(t, *rango)
        return None

    @staticmethod
    def _direccion(t: str, ini: int, fin: int) -> _Span | None:
        texto = t[ini:fin]
        palabras = texto.split()
        if not palabras or any(_plano(p) in _NORMATIVOS for p in palabras):
            return None  # "la Ley" + 21.719, "Artículo" + 14
        num = _RE_NUMERO_TRAS_LOC.match(t[fin:])
        if num:  # "Los Leones" + " 1234" -> dirección
            return _Span(TipoEntidad.DIRECCION, ini, fin + num.end(), "ner")
        if _RE_LOC_TERMINA_EN_NUMERO.search(texto) and len(palabras) >= 2:
            # spaCy ya incluyó el número: "Los Leones 456"; se extiende al complemento ("depto 5")
            return _Span(TipoEntidad.DIRECCION, ini, fin + _RE_COMPLEMENTO_TRAS.match(t[fin:]).end(), "ner")
        return None

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
