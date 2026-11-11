"""
Verificación de la SALIDA del modelo en la validación de evidencias (OWASP Top 10 for LLM).

El modelo propone una clasificación para un control y la explica. Antes de que el backend use
esa propuesta (o la guarde y la muestre), esta capa la revisa con reglas deterministas, sin
llamar a otro modelo y sin salir del servidor:

  Verificación sintáctica (LLM05 · Improper Output Handling)
      sintaxis.clasificacion_invalida   la clasificación no es uno de los tres valores admitidos
      sintaxis.confianza_invalida       la confianza no es un número entre 0 y 1
      sintaxis.codigo_activo            HTML, <script>, manejadores on...= o "javascript:"
      sintaxis.enlace_externo           un enlace o imagen markdown que no está en la evidencia
      sintaxis.caracteres_ocultos       caracteres invisibles, bidi o de control (se quitan)
      sintaxis.longitud_excesiva        textos demasiado largos (se recortan)

  Alucinación (LLM09 · Misinformation). Una ALUCINACIÓN es una afirmación de la salida que no
  tiene respaldo en el material que recibió el modelo (la evidencia, la justificación del
  usuario y los datos del control) o un cumplimiento declarado sobre una evidencia sin
  contenido útil:
      alucinacion.cumplimiento_sin_evidencia   "cumplido" o "parcial" con evidencia vacía o que
                                               el propio modelo declara insuficiente
      alucinacion.cita_inexistente             un texto entre comillas que no está en el material
      alucinacion.dato_inexistente             un valor de `datos_extraidos` que no está en la evidencia
      alucinacion.cifra_inexistente            una cifra (≥ 3 dígitos o porcentaje) que no aparece
      alucinacion.fecha_inexistente            una fecha que no aparece en el material
      alucinacion.articulo_inexistente         un artículo, cláusula o sección que no es del control
                                               ni aparece en la evidencia
      alucinacion.control_ajeno                el código de otro control de la matriz
      alucinacion.norma_no_verificada          una ley o norma que no es del control (solo advertencia)

  Fuga de contexto (LLM02 · Sensitive Information Disclosure, LLM07 · System Prompt Leakage)
      fuga.datos_personales             RUT válido, correo o teléfono en la salida (el modelo solo
                                        recibió texto anonimizado: o lo inventó o se filtró)
      fuga.reidentificacion             intenta "adivinar" a quién corresponde una etiqueta [X_ANON]
      fuga.prompt_sistema               reproduce el system prompt o sus delimitadores internos

  Inyección que llegó al modelo (LLM01 · Prompt Injection)
      inyeccion.obediencia              la salida dice que siguió instrucciones del documento
      inyeccion.no_degradada            reconoce instrucciones dirigidas a la IA pero no clasifica
                                        "no_cumplido" (lo exige el system prompt)

  Coherencia (solo advertencias: quedan en las métricas)
      divergencia_sin_explicar, justificacion_vacia      (las de siempre, mismos códigos)
      coherencia.respaldo_contradictorio  (respalda_clasificacion_usuario no calza con lo declarado)

Los hallazgos BLOQUEANTES hacen que el backend no aplique la propuesta del modelo: la respuesta
queda para revisión humana (ver ProcessEvidenceUseCase) y se registra una alerta de seguridad.
`sanear()` devuelve además una copia de la salida segura de guardar y mostrar (sin datos
personales, sin código activo, sin enlaces no respaldados y con largos acotados).

Este módulo es puro (sin BD, red ni modelo): se prueba con tests/data/alucinaciones_evidencias.jsonl.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.rut import digito_verificador

CLASIFICACIONES = ("cumplido", "parcialmente_cumplido", "no_cumplido")
FAVORABLES = ("cumplido", "parcialmente_cumplido")

MAX_JUSTIFICACION = 4000
MAX_ERROR = 300
MAX_ERRORES = 10

# Categorías (tipo del evento de seguridad) y su referencia OWASP Top 10 for LLM (2025)
ALUCINACION = "alucinacion"
FUGA = "fuga_contexto"
INYECCION = "inyeccion_salida"
SINTAXIS = "salida_insegura"
COHERENCIA = "coherencia"
OWASP = {ALUCINACION: "LLM09", FUGA: "LLM02", INYECCION: "LLM01", SINTAXIS: "LLM05", COHERENCIA: "LLM09"}
# Orden para elegir la categoría principal de una salida con varios hallazgos
PRIORIDAD = (FUGA, INYECCION, SINTAXIS, ALUCINACION, COHERENCIA)

# Códigos que solo son advertencias (no retienen la propuesta del modelo)
CODIGOS_NO_BLOQUEANTES = frozenset({
    "sintaxis.caracteres_ocultos", "sintaxis.longitud_excesiva", "alucinacion.norma_no_verificada",
    "divergencia_sin_explicar", "justificacion_vacia", "coherencia.respaldo_contradictorio",
})
# Prefijo del código -> categoría (para las métricas, que solo guardan los códigos)
CATEGORIA_POR_PREFIJO = {"alucinacion.": ALUCINACION, "fuga.": FUGA, "inyeccion.": INYECCION, "sintaxis.": SINTAXIS}

TEXTO_FUGA = ("La explicación automática se ocultó porque incluía información interna del sistema. "
              "El equipo de revisión verá el caso completo.")


@dataclass(frozen=True)
class Hallazgo:
    codigo: str            # "alucinacion.cita_inexistente" (nunca contiene texto del usuario)
    categoria: str         # alucinacion | fuga_contexto | inyeccion_salida | salida_insegura | coherencia
    bloqueante: bool
    cantidad: int = 1      # cuántas veces apareció (p. ej. 2 citas sin respaldo)

    @property
    def owasp(self) -> str:
        return OWASP[self.categoria]


@dataclass(frozen=True)
class VerificacionSalida:
    hallazgos: tuple[Hallazgo, ...] = ()
    salida: Any = None     # copia saneada de la salida (segura de guardar y mostrar)

    @property
    def bloqueante(self) -> bool:
        return any(h.bloqueante for h in self.hallazgos)

    @property
    def codigos(self) -> list[str]:
        return [h.codigo for h in self.hallazgos]

    def tiene(self, categoria: str) -> bool:
        return any(h.categoria == categoria and h.bloqueante for h in self.hallazgos)

    @property
    def alucinacion(self) -> bool:
        return self.tiene(ALUCINACION)

    @property
    def fuga(self) -> bool:
        return self.tiene(FUGA)

    @property
    def principal(self) -> Hallazgo | None:
        """El hallazgo bloqueante más grave (es el que se registra como alerta)."""
        bloq = [h for h in self.hallazgos if h.bloqueante]
        if not bloq:
            return None
        return min(bloq, key=lambda h: PRIORIDAD.index(h.categoria))


# ------------------------------------------------------------------ normalización
_INVISIBLES = re.compile(r"[​-‏‪-‮⁠-⁩﻿­\U000E0000-\U000E007F]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ETIQUETA = re.compile(r"\[(?:RUT|NOMBRE|CORREO|TEL|DIRECCION|DATO_CODIFICADO)_ANON\]")
_COMILLAS = str.maketrans({"“": '"', "”": '"', "„": '"', "«": '"', "»": '"', "‘": "'", "’": "'"})
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def _sin_tildes(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _tokens(t: str) -> list[str]:
    """Palabras normalizadas. Las etiquetas de anonimización se vuelven un token comodín "§"."""
    t = _ETIQUETA.sub(" § ", t or "")
    return re.findall(r"§|[a-z0-9ñ]+", _sin_tildes(t))


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", t)


@dataclass
class _Corpus:
    """Todo lo que el modelo recibió y puede citar con respaldo."""
    texto: str
    tokens: list[str]
    unido: str = ""
    bigramas: set = field(default_factory=set)
    numeros: set = field(default_factory=set)
    fechas: set = field(default_factory=set)
    articulos: set = field(default_factory=set)
    codigos: set = field(default_factory=set)
    urls: set = field(default_factory=set)

    @classmethod
    def de(cls, partes: Iterable[str | None], referencias: Iterable[str | None] = ()) -> "_Corpus":
        """`referencias`: textos cuyos números son artículos válidos (el artículo/cláusula del control)."""
        texto = "\n".join(p for p in partes if p)
        toks = [t for t in _tokens(texto) if t != "§"]
        c = cls(texto=texto, tokens=toks)
        c.unido = " " + " ".join(toks) + " "
        c.bigramas = {(a, b) for a, b in zip(toks, toks[1:])}
        c.numeros = {_digitos(m) for m in re.findall(r"\d[\d.,]*", texto)}
        c.numeros |= {d for m in re.findall(r"\d[\d.,]*", texto) for d in re.split(r"[.,]", m) if d}
        c.fechas = _fechas(texto)
        c.articulos = set(_RE_ARTICULO.findall(_sin_tildes(texto)))
        for ref in referencias:
            c.articulos |= set(re.findall(r"\d+(?:\.\d+)*", ref or ""))
        c.codigos = set(_RE_CODIGO.findall(texto))
        c.urls = {_url_base(u) for u in _RE_URL.findall(texto)}
        return c


def _fechas(texto: str) -> set[tuple[int, int, int | None]]:
    """(año, mes, día) de las fechas del texto: 15/03/2025, 2025-03-15, 15 de marzo de 2025, marzo de 2025."""
    salida: set[tuple[int, int, int | None]] = set()
    t = _sin_tildes(texto)
    for d, m, a in re.findall(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", t):
        if 1 <= int(m) <= 12:
            salida.add((int(a), int(m), int(d)))
    for a, m, d in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        if 1 <= int(m) <= 12:
            salida.add((int(a), int(m), int(d)))
    for d, mes, a in re.findall(r"\b(?:(\d{1,2})\s+de\s+)?(" + "|".join(_MESES) + r")\s+(?:de|del)\s+(\d{4})\b", t):
        salida.add((int(a), _MESES[mes], int(d) if d else None))
    return salida


def _fecha_respaldada(f: tuple[int, int, int | None], corpus: set) -> bool:
    a, m, d = f
    return any(ca == a and cm == m and (d is None or cd is None or cd == d) for ca, cm, cd in corpus)


# ------------------------------------------------------------------ patrones
_RE_CITA = re.compile(r'"([^"\n]{8,400})"|\'([^\'\n]{8,400})\'')
_RE_ARTICULO = re.compile(r"\b(?:articulo|art\.|arts\.|clausula|seccion|sec\.|numeral|inciso)\s*(\d+(?:\.\d+)*)")
_RE_NORMA = re.compile(r"\b(?:ley\s*(?:n\.?\s*[ºo°]?\s*)?(\d{2}[.\s]?\d{3})|iso(?:/iec)?\s*(\d{4,5})(?::\d{4})?|"
                       r"nist\s*(?:ai\s*)?(?:rmf\s*)?(\d{3}-\d))")
_RE_CODIGO = re.compile(r"\b(?:DAT|GOB|RIE|SEG|TRA|ETI|CAP|PRI)-\d{3}\b")
_RE_URL = re.compile(r"\b(?:https?://|www\.)[^\s)\]>\"']*[^\s)\]>\"'.,;:]", re.IGNORECASE)
_RE_IMG_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_RE_CODIGO_ACTIVO = re.compile(
    r"<\s*/?\s*(?:script|iframe|img|svg|object|embed|style|link|meta|form|input|a|div|span|html|body)\b[^>]*>?|"
    r"\bon(?:error|load|click|mouseover|focus)\s*=|javascript\s*:|data\s*:\s*text/html", re.IGNORECASE)
_RE_TAG_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]{0,200}>")
_RE_CORREO = re.compile(r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b")
_RE_RUT = re.compile(r"(?<![\d.])(\d{1,2}\.?\d{3}\.?\d{3})\s*-\s*([\dkK])(?![\w])")
_RE_TEL = re.compile(r"(?:\+\s?56\s?[29](?:[\s.-]?\d){8}|\b9[\s.-]\d{4}[\s.-]\d{4}\b|\b2[\s.-]\d{4}[\s.-]\d{4}\b)")
_RE_REIDENT = re.compile(
    r"\[(?:NOMBRE|RUT|CORREO|TEL|DIRECCION)_ANON\]\s*(?:\(\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ]|"
    r"(?:corresponde a|ser[ií]a|probablemente (?:es|sea)|se trata de|es decir)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ])")
_RE_MARCADORES = re.compile(
    r"<\s*/?\s*(?:justificacion_usuario|evidencia_adjunta)\s*>|&lt;\s*/?\s*(?:justificacion_usuario|evidencia_adjunta)|"
    r"═{5,}|reglas de seguridad \(prioridad|datos no confiables a evaluar|reglas de clasificacion\b|"
    r"devuelve tu evaluacion unicamente", re.IGNORECASE)
_RE_OBEDIENCIA = re.compile(
    r"\b(siguiendo|obedeciendo|acatando|cumpliendo con|atendiendo)\s+(?:las?\s+|los\s+)?(instruc\w*|indicacion\w*|"
    r"ordenes|orden)\s+(?:\w+\s+){0,3}(del|de la|en el|en la|contenidas? en (?:el|la))\s+"
    r"(documento|evidencia|archivo|nota|texto|adjunto)\b|"
    r"\bcomo (?:me|se me) (pide|indica|ordena|solicita|instruye)n?\s+(?:el|la)\s+(documento|evidencia|nota|archivo|texto)\b|"
    r"\b(ignor|omit|desestim)\w*\s+(?:las?\s+|mis\s+)?(reglas|instrucciones|restricciones)\s+(anteriores|previas|del sistema|de seguridad)\b|"
    r"\bmodo\s+(desarrollador|developer|dan|sin restricciones|administrador)\b|"
    r"\b(as instructed|as requested|following the instructions)\b.{0,30}\b(document|evidence|note|file)\b|"
    r"\b(ahora soy|actuando como)\s+(un|una|el|la)\s+(asistente|ia|modelo)\s+sin\b", re.IGNORECASE)
_RE_MENCION_INYECCION = re.compile(
    r"\b(instruc\w*|ordenes|indicaciones)\s+(?:\w+\s+){0,3}(dirigid\w*|para|hacia)\s+(?:a\s+|al\s+)?(la ia|ti|el modelo|"
    r"modelo|el evaluador|evaluador|el asistente|asistente|la inteligencia artificial|el sistema de evaluacion)\b|"
    r"\b(intento|intenta|busca|pretende)\w*\s+(de\s+)?(manipular|influir en|forzar|alterar)\s+(esta|la|el)\s+"
    r"(evaluacion|clasificacion|resultado|validacion)\b")

# Normas que el system prompt menciona (el modelo puede nombrarlas sin que estén en la evidencia)
_NORMAS_PROMPT = {"21719", "42001", "1001"}


def _url_base(u: str) -> str:
    return re.sub(r"^(https?://)?(www\.)?", "", u.lower()).rstrip("/.,;")


def _textos_salida(r: Any) -> list[str]:
    salida = [str(getattr(r, "justificacion", "") or ""), str(getattr(r, "divergencia_explicada", "") or "")]
    errores = getattr(r, "errores", None) or []
    if isinstance(errores, (list, tuple)):
        salida += [str(e) for e in errores]
    return salida


def _valores_datos(r: Any) -> list[str]:
    datos = getattr(r, "datos_extraidos", None) or {}
    if not isinstance(datos, dict):
        return []
    valores = []
    for v in datos.values():
        if isinstance(v, (list, tuple)):
            valores += [str(x) for x in v if isinstance(x, (str, int, float)) and not isinstance(x, bool)]
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            valores.append(str(v))
    return valores


# ------------------------------------------------------------------ comprobaciones de respaldo
def _cita_respaldada(cita: str, corpus: _Corpus) -> bool:
    toks = _tokens(cita)
    palabras = [t for t in toks if t != "§"]
    if len(palabras) < 3:
        return True  # demasiado corta para afirmar que es una cita textual
    # Cada tramo entre etiquetas anonimizadas debe aparecer tal cual (en orden de palabras)
    tramos, actual = [], []
    for t in toks:
        if t == "§":
            if actual:
                tramos.append(actual)
            actual = []
        else:
            actual.append(t)
    if actual:
        tramos.append(actual)
    if all(f" {' '.join(tr)} " in corpus.unido for tr in tramos):
        return True
    # Tolerancia a reformateos menores (saltos de línea, guiones de PDF): 85 % de los bigramas
    bigr = [(a, b) for a, b in zip(palabras, palabras[1:])]
    return bool(bigr) and sum(1 for b in bigr if b in corpus.bigramas) / len(bigr) >= 0.85


def _dato_respaldado(valor: str, corpus: _Corpus) -> bool:
    if re.search(r"\d", valor):
        nums = [n for n in (_digitos(x) for x in re.findall(r"\d[\d.,]*", valor)) if len(n) >= 2]
        return all(n in corpus.numeros for n in nums)
    palabras = [t for t in _tokens(valor) if t != "§" and len(t) > 3]
    if len(palabras) < 3:
        return True  # valores cortos ("sí", "vigente", "Gerencia") no se pueden verificar con seguridad
    presentes = sum(1 for p in palabras if f" {p} " in corpus.unido)
    return presentes / len(palabras) >= 0.6


def _cifras_sin_respaldo(texto: str, corpus: _Corpus) -> int:
    t = _RE_CORREO.sub(" ", texto or "")
    t = _RE_TEL.sub(" ", _RE_RUT.sub(" ", t))   # los datos personales se revisan aparte (fuga)
    t = _sin_tildes(t)
    t = _RE_NORMA.sub(" ", t)          # las normas se revisan aparte
    t = _RE_ARTICULO.sub(" ", t)       # y los artículos también
    t = re.sub(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b", " ", t)  # fechas: aparte
    t = re.sub(r"\b(?:\d{1,2}\s+de\s+)?(?:" + "|".join(_MESES) + r")\s+(?:de|del)\s+\d{4}\b", " ", t)
    t = re.sub(r"\b[a-z]{3}-\d{3}\b", " ", t)      # códigos de control: aparte
    n = 0
    for m in re.finditer(r"(?<![\w.,])(\d[\d.,]*\d|\d)(\s*%)?", t):
        bruto, pct = m.group(1), m.group(2)
        if re.match(r"0[.,]\d", bruto):
            continue  # decimales bajo 1 (p. ej. la confianza)
        dig = _digitos(bruto)
        if len(dig) < 3 and not (pct and len(dig) >= 2):
            continue  # conteos pequeños ("2 de los 3 elementos") son razonamiento, no datos
        partes = [p for p in re.split(r"[.,]", bruto) if p]
        if dig in corpus.numeros or all(p in corpus.numeros for p in partes):
            continue
        n += 1
    return n


def _fechas_sin_respaldo(texto: str, corpus: _Corpus) -> int:
    return sum(1 for f in _fechas(texto) if not _fecha_respaldada(f, corpus.fechas))


def _articulos_sin_respaldo(texto: str, corpus: _Corpus) -> int:
    n = 0
    for num in _RE_ARTICULO.findall(_sin_tildes(texto)):
        if num in corpus.articulos:
            continue
        if any(v.startswith(num + ".") or num.startswith(v + ".") for v in corpus.articulos):
            continue
        n += 1
    return n


def _normas_sin_respaldo(texto: str, corpus: _Corpus) -> int:
    n = 0
    for ley, iso, nist in _RE_NORMA.findall(_sin_tildes(texto)):
        num = _digitos(ley or iso or nist)
        if num and num not in corpus.numeros and num not in _NORMAS_PROMPT:
            n += 1
    return n


def _ruts(texto: str) -> list[str]:
    salida = []
    for cuerpo, dv in _RE_RUT.findall(texto or ""):
        c = _digitos(cuerpo)
        if len(c) >= 7 and digito_verificador(c) == dv.upper():
            salida.append(f"{c}-{dv}")
    return salida


def _pii(texto: str) -> int:
    return len(_RE_CORREO.findall(texto or "")) + len(_ruts(texto)) + len(_RE_TEL.findall(texto or ""))


def _palabras_utiles(texto: str) -> int:
    return sum(1 for t in _tokens(texto) if t != "§" and re.search(r"[a-zñ]{3,}", t))


_CACHE_PROMPT: dict[int, set[str]] = {}


def _ventanas(texto: str, n: int = 8) -> set[str]:
    toks = [t for t in _tokens(texto) if t != "§"]
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def _ventanas_prompt(system: str) -> set[str]:
    clave = hash(system)
    if clave not in _CACHE_PROMPT:
        _CACHE_PROMPT[clave] = _ventanas(system)
    return _CACHE_PROMPT[clave]


_CACHE_CORPUS_PROMPT: dict[int, "_Corpus"] = {}


def _corpus_prompt(system: str) -> "_Corpus":
    clave = hash(system)
    if clave not in _CACHE_CORPUS_PROMPT:
        _CACHE_CORPUS_PROMPT[clave] = _Corpus.de([system])
    return _CACHE_CORPUS_PROMPT[clave]


def _system_por_defecto() -> str:
    from app.application.ai.prompts.validar_evidencia import SYSTEM
    return SYSTEM


def _campo(obj: Any, nombre: str) -> str | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        v = obj.get(nombre)
    else:
        v = getattr(obj, nombre, None)
    return str(v) if v not in (None, "") else None


# ------------------------------------------------------------------ verificación
def verificar_evidencia(
    resultado: Any,
    *,
    evidencia: str | None,
    justificacion: str | None = None,
    control: Any = None,
    brecha: Any = None,
    declarado: str | None = None,
    system_prompt: str | None = None,
) -> VerificacionSalida:
    """
    Revisa una salida de VALIDAR_EVIDENCIA. `evidencia` y `justificacion` son los textos que
    recibió el modelo (sirven en claro o anonimizados: las etiquetas [X_ANON] son comodines).
    `control` y `brecha` pueden ser modelos de SQLAlchemy, SimpleNamespace o dict.
    """
    h: list[Hallazgo] = []

    def agregar(codigo: str, categoria: str, bloqueante: bool, cantidad: int = 1) -> None:
        if cantidad > 0:
            h.append(Hallazgo(codigo, categoria, bloqueante, cantidad))

    campos_control = [_campo(control, c) for c in (
        "codigo_control", "framework_fuente", "articulo_referencia", "obligacion", "pregunta_evaluacion",
        "evidencia_esperada", "tipo_fuente", "aplicabilidad")]
    campos_brecha = [_campo(brecha, c) for c in ("categoria", "comportamiento_detectado")]
    corpus = _Corpus.de([evidencia, justificacion, *campos_control, *campos_brecha],
                        referencias=[_campo(control, "articulo_referencia")])
    codigo_propio = _campo(control, "codigo_control")

    # 1. Verificación sintáctica ---------------------------------------------------------
    clasificacion = getattr(resultado, "clasificacion", None)
    if clasificacion not in CLASIFICACIONES:
        agregar("sintaxis.clasificacion_invalida", SINTAXIS, True)
    confianza = getattr(resultado, "confianza", None)
    if isinstance(confianza, bool) or not isinstance(confianza, (int, float)) or not 0 <= confianza <= 1 \
            or confianza != confianza:
        agregar("sintaxis.confianza_invalida", SINTAXIS, True)
    textos = _textos_salida(resultado)
    datos = _valores_datos(resultado)
    todo = "\n".join(textos + datos)
    if _RE_CODIGO_ACTIVO.search(todo):
        agregar("sintaxis.codigo_activo", SINTAXIS, True)
    enlaces = [u for u in _RE_URL.findall(todo) if _url_base(u) not in corpus.urls]
    agregar("sintaxis.enlace_externo", SINTAXIS, True, len(enlaces) + len(_RE_IMG_MD.findall(todo)))
    if _INVISIBLES.search(todo) or _CONTROL.search(todo):
        agregar("sintaxis.caracteres_ocultos", SINTAXIS, False)
    if len(textos[0]) > MAX_JUSTIFICACION or any(len(e) > MAX_ERROR for e in textos[2:]) \
            or len(textos) - 2 > MAX_ERRORES:
        agregar("sintaxis.longitud_excesiva", SINTAXIS, False)

    # 2. Fuga de contexto -----------------------------------------------------------------
    agregar("fuga.datos_personales", FUGA, True, _pii(todo))
    agregar("fuga.reidentificacion", FUGA, True, len(_RE_REIDENT.findall(todo)))
    system = system_prompt if system_prompt is not None else _system_por_defecto()
    if _RE_MARCADORES.search(_sin_tildes(todo)) or len(_ventanas(todo) & _ventanas_prompt(system)) >= 4:
        agregar("fuga.prompt_sistema", FUGA, True)

    # 3. Inyección que llegó al modelo ------------------------------------------------------
    texto_norm = _sin_tildes(todo)
    if _RE_OBEDIENCIA.search(texto_norm):
        agregar("inyeccion.obediencia", INYECCION, True)
    if clasificacion in FAVORABLES and _RE_MENCION_INYECCION.search(texto_norm):
        agregar("inyeccion.no_degradada", INYECCION, True)

    # 4. Alucinación ----------------------------------------------------------------------
    suficiente = getattr(resultado, "evidencia_suficiente", None)
    vacia = evidencia is not None and _palabras_utiles(evidencia) == 0
    if clasificacion in FAVORABLES and (suficiente is False or vacia):
        agregar("alucinacion.cumplimiento_sin_evidencia", ALUCINACION, True)
    explicacion = "\n".join(textos[:2])
    citas = [a or b for a, b in _RE_CITA.findall(explicacion.translate(_COMILLAS))]
    # Citar el propio system prompt no es una alucinación (si lo reproduce, lo detecta fuga.prompt_sistema)
    corpus_sistema = _corpus_prompt(system)
    agregar("alucinacion.cita_inexistente", ALUCINACION, True,
            sum(1 for c in citas if not (_cita_respaldada(c, corpus) or _cita_respaldada(c, corpus_sistema))))
    agregar("alucinacion.dato_inexistente", ALUCINACION, True,
            sum(1 for v in datos if not _dato_respaldado(v, corpus)))
    agregar("alucinacion.cifra_inexistente", ALUCINACION, True, _cifras_sin_respaldo(explicacion, corpus))
    agregar("alucinacion.fecha_inexistente", ALUCINACION, True,
            _fechas_sin_respaldo(explicacion + "\n" + "\n".join(datos), corpus))
    agregar("alucinacion.articulo_inexistente", ALUCINACION, True, _articulos_sin_respaldo(explicacion, corpus))
    ajenos = {c for c in _RE_CODIGO.findall(todo) if c != codigo_propio and c not in corpus.codigos}
    agregar("alucinacion.control_ajeno", ALUCINACION, True, len(ajenos))
    agregar("alucinacion.norma_no_verificada", ALUCINACION, False, _normas_sin_respaldo(explicacion, corpus))

    # 5. Coherencia (advertencias; los dos primeros códigos son los de siempre) -------------
    respalda = getattr(resultado, "respalda_clasificacion_usuario", None)
    if respalda is False and not str(getattr(resultado, "divergencia_explicada", "") or "").strip():
        agregar("divergencia_sin_explicar", COHERENCIA, False)
    if not textos[0].strip():
        agregar("justificacion_vacia", COHERENCIA, False)
    if declarado in CLASIFICACIONES and clasificacion in CLASIFICACIONES and isinstance(respalda, bool):
        if (clasificacion == declarado) != respalda:
            agregar("coherencia.respaldo_contradictorio", COHERENCIA, False)
    elif declarado == "requiere_revision" and respalda is False:
        agregar("coherencia.respaldo_contradictorio", COHERENCIA, False)

    v = VerificacionSalida(tuple(h))
    return VerificacionSalida(v.hallazgos, sanear(resultado, v, corpus))


# ------------------------------------------------------------------ saneamiento de la salida
def _limpiar(texto: str, corpus: _Corpus | None, maximo: int) -> str:
    t = _INVISIBLES.sub("", texto or "")
    t = _CONTROL.sub("", t)
    t = _RE_IMG_MD.sub("[imagen omitida]", t)
    t = _RE_TAG_HTML.sub("", t)
    t = re.sub(r"javascript\s*:", "", t, flags=re.IGNORECASE)
    t = _RE_URL.sub(lambda m: m.group(0) if corpus and _url_base(m.group(0)) in corpus.urls else "[enlace omitido]", t)
    t = _RE_CORREO.sub("[CORREO_ANON]", t)
    for rut in set(_RE_RUT.findall(t)):
        cuerpo, dv = rut
        if len(_digitos(cuerpo)) >= 7 and digito_verificador(_digitos(cuerpo)) == dv.upper():
            t = re.sub(re.escape(cuerpo) + r"\s*-\s*" + re.escape(dv), "[RUT_ANON]", t)
    t = _RE_TEL.sub("[TEL_ANON]", t)
    if len(t) > maximo:
        t = t[: maximo - 1].rstrip() + "…"
    return t


def sanear(resultado: Any, verificacion: VerificacionSalida | None = None, corpus: _Corpus | None = None) -> Any:
    """Copia de la salida segura de guardar y mostrar. No cambia la clasificación ni la confianza."""
    fuga_prompt = bool(verificacion and "fuga.prompt_sistema" in verificacion.codigos)
    justificacion = TEXTO_FUGA if fuga_prompt else _limpiar(
        str(getattr(resultado, "justificacion", "") or ""), corpus, MAX_JUSTIFICACION)
    divergencia = getattr(resultado, "divergencia_explicada", None)
    if divergencia is not None:
        divergencia = None if fuga_prompt else _limpiar(str(divergencia), corpus, MAX_JUSTIFICACION)
    errores = getattr(resultado, "errores", None) or []
    if not isinstance(errores, (list, tuple)):
        errores = [str(errores)]
    errores = [] if fuga_prompt else [_limpiar(str(e), corpus, MAX_ERROR) for e in list(errores)[:MAX_ERRORES]]
    cambios = {"justificacion": justificacion, "divergencia_explicada": divergencia, "errores": errores}
    if hasattr(resultado, "model_copy"):
        presentes = {k: v for k, v in cambios.items() if k in type(resultado).model_fields}
        return resultado.model_copy(update=presentes)
    copia = copy.copy(resultado)
    for k, v in cambios.items():
        if hasattr(copia, k):
            try:
                setattr(copia, k, v)
            except Exception:  # noqa: BLE001 - objetos inmutables: se devuelve tal cual
                return resultado
    return copia
