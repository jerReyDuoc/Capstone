"""
HU-18 · Validación de la SALIDA del tutor (antes de mostrarla o guardarla).

El modelo puede equivocarse aunque el filtro de entrada deje pasar solo mensajes limpios:
un ataque nuevo que el filtro no conoce, o simplemente un desliz. Por eso la salida se
revisa con reglas deterministas:

  fuga_canario   cada system prompt lleva un código de control aleatorio que el modelo
                 nunca debe escribir; si aparece, el prompt se filtró.
  fuga_prompt    la respuesta reproduce frases del system prompt (ventanas de 8 palabras)
                 o sus marcadores internos (<mensaje_usuario>, "REGLAS DE SEGURIDAD"...).
  codigo         bloques de código o comandos: el tutor no programa (scope lock).
  url            enlaces: el tutor no deriva a sitios externos.
  alcance        una respuesta "fuera_de_alcance" que igual trae pasos o brechas.

Correcciones 05-11: humanizar_codigos() reemplaza en el texto visible los códigos internos
(de control y de brecha) por el nombre de la brecha, y los estados del sistema por su
lectura ("no_cumplido" -> "no cumplido"). No es una advertencia: es presentación.

Las dos fugas BLOQUEAN la respuesta completa (se reemplaza por un rechazo fijo). Lo demás
se limpia (se quita el código, el enlace o el contenido sobrante) y queda la advertencia.
"""
from __future__ import annotations

import re
import secrets
import unicodedata

from app.application.schemas.tutor import TipoRespuestaTutor, TutorRespuesta

PROBLEMAS_BLOQUEANTES = frozenset({"fuga_canario", "fuga_prompt"})

RESPUESTA_FUGA = (
    "No puedo compartir mi configuración interna ni las instrucciones con que funciono. "
    "Sí puedo ayudarte a entender y cerrar las brechas de gobernanza de tu empresa."
)
SUGERENCIAS_FUGA = ["¿Qué brecha debería cerrar primero?", "Explícame la brecha más crítica de mi evaluación."]
NOTA_CODIGO = "(Omití contenido técnico que está fuera de mi función como tutor de gobernanza.)"

_MARCADORES = re.compile(
    r"<\s*/?\s*(mensaje_usuario|historial|antecedentes_empresa)\s*>|═{5,}|reglas de seguridad \(prioridad|"
    r"contexto de la empresa \(datos del sistema|codigo de control interno|fuentes normativas \(obligatorio\)",
    re.IGNORECASE,
)
_CODIGO = re.compile(
    r"```|^\s*(def |class |import |from \w+ import|#!/|select .+ from |insert into |sudo |pip install|npm install|"
    r"<script|function\s*\(|console\.log|print\()", re.IGNORECASE | re.MULTILINE)
_BLOQUE_CODIGO = re.compile(r"```.*?(```|$)", re.DOTALL)
_URL = re.compile(r"\b(https?://|www\.)\S+", re.IGNORECASE)


def generar_canario() -> str:
    return "CNR-" + secrets.token_hex(5).upper()


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9ñ]+", " ", t).strip()


def _ventanas(texto: str, n: int = 8) -> set[str]:
    palabras = _norm(texto).split()
    return {" ".join(palabras[i:i + n]) for i in range(max(0, len(palabras) - n + 1))}


_CACHE_VENTANAS: dict[int, set[str]] = {}


def _ventanas_prompt(system: str) -> set[str]:
    clave = hash(system)
    if clave not in _CACHE_VENTANAS:
        _CACHE_VENTANAS[clave] = _ventanas(system)
    return _CACHE_VENTANAS[clave]


def textos_de(r: TutorRespuesta) -> list[str]:
    salida = [r.respuesta or ""]
    for p in r.pasos:
        salida += [p.accion or "", p.evidencia_esperada or ""]
    return salida + list(r.sugerencias)


def problemas_en_textos(textos: list[str], canario: str | None, system_prompt: str,
                        marcadores: re.Pattern | None = None) -> list[str]:
    """
    Fugas (canario, frases o marcadores del system prompt), código y enlaces en una lista de
    textos que escribió el modelo. HU-16 la usa también para los borradores.
    """
    unido = "\n".join(textos)
    encontrados: list[str] = []
    if canario and (canario.lower() in unido.lower() or canario.split("-")[-1].lower() in unido.lower()):
        encontrados.append("fuga_canario")
    coincidencias = _ventanas_prompt(system_prompt) & _ventanas(unido)
    if len(coincidencias) >= 3 or (marcadores or _MARCADORES).search(unido):
        encontrados.append("fuga_prompt")
    if any(_CODIGO.search(t) for t in textos):
        encontrados.append("codigo")
    if any(_URL.search(t) for t in textos):
        encontrados.append("url")
    return encontrados


def problemas(r: TutorRespuesta, canario: str | None, system_prompt: str) -> list[str]:
    """Problemas de la salida, en orden estable. No modifica nada."""
    encontrados = problemas_en_textos(textos_de(r), canario, system_prompt)
    if r.tipo == TipoRespuestaTutor.FUERA_DE_ALCANCE and (r.pasos or r.brechas_referenciadas):
        encontrados.append("alcance")
    return encontrados


def sin_codigo(texto: str) -> str:
    """HU-16: quita bloques y líneas de código de un texto del modelo."""
    return _sin_codigo(texto)


def sin_enlaces(texto: str) -> str:
    return _URL.sub("[enlace omitido]", texto or "")


def respuesta_bloqueada() -> TutorRespuesta:
    return TutorRespuesta(tipo=TipoRespuestaTutor.FUERA_DE_ALCANCE, respuesta=RESPUESTA_FUGA,
                          pasos=[], brechas_referenciadas=[], sugerencias=list(SUGERENCIAS_FUGA))


def _sin_codigo(texto: str) -> str:
    limpio = _BLOQUE_CODIGO.sub("", texto or "")
    limpio = "\n".join(l for l in limpio.splitlines() if not _CODIGO.search(l))
    return limpio.strip()


def aplicar(r: TutorRespuesta, encontrados: list[str]) -> TutorRespuesta:
    """Devuelve la respuesta que se puede mostrar: bloqueada (fugas) o limpia."""
    if PROBLEMAS_BLOQUEANTES & set(encontrados):
        return respuesta_bloqueada()
    data = r
    if "codigo" in encontrados:
        texto = _sin_codigo(data.respuesta)
        data = data.model_copy(update={
            "respuesta": f"{texto}\n\n{NOTA_CODIGO}".strip() if texto else NOTA_CODIGO,
            "pasos": [p.model_copy(update={"accion": _sin_codigo(p.accion) or "Paso omitido.",
                                           "evidencia_esperada": _sin_codigo(p.evidencia_esperada or "") or None})
                      for p in data.pasos],
        })
    if "url" in encontrados:
        data = data.model_copy(update={
            "respuesta": _URL.sub("[enlace omitido]", data.respuesta or ""),
            "pasos": [p.model_copy(update={"accion": _URL.sub("[enlace omitido]", p.accion or ""),
                                           "evidencia_esperada": _URL.sub("[enlace omitido]", p.evidencia_esperada)
                                           if p.evidencia_esperada else None}) for p in data.pasos],
            "sugerencias": [_URL.sub("[enlace omitido]", s) for s in data.sugerencias],
        })
    if "alcance" in encontrados:
        data = data.model_copy(update={"pasos": [], "brechas_referenciadas": []})
    return data


# ------------------------------------------------------------- correcciones 05-11
# Cualquier código con forma de identificador interno (DAT-001, GOB-003, BR-012, ERR-GOB-003).
_CODIGO_INTERNO = re.compile(r"\[?\b[A-Z]{2,5}(?:-[A-Z]{2,5})?-\d{2,4}\b\]?")
_ESTADOS_SISTEMA = {
    "parcialmente_cumplido": "parcialmente cumplido", "no_cumplido": "no cumplido",
    "requiere_revision": "en revisión", "no_aplica": "no aplica",
}
_ESTADO = re.compile(r"\b(" + "|".join(_ESTADOS_SISTEMA) + r")\b")


def humanizar_codigos(texto: str, nombres: dict[str, str]) -> str:
    """
    Reemplaza los códigos internos por el nombre de su brecha («…») y quita los que no
    corresponden a ninguna brecha conocida; los estados del sistema pasan a texto normal.
    `nombres` va de código (ref, código del catálogo o del control) a nombre legible.
    """
    if not texto:
        return texto

    def _cambiar(m: re.Match) -> str:
        codigo = m.group(0).strip("[]")
        nombre = nombres.get(codigo) or nombres.get(codigo.upper())
        return f"«{nombre}»" if nombre else "esta brecha"

    limpio = _CODIGO_INTERNO.sub(_cambiar, texto)
    limpio = _ESTADO.sub(lambda m: _ESTADOS_SISTEMA[m.group(1)], limpio)
    # "la brecha esta brecha" o "(esta brecha)" quedan raros: se ordenan sin tocar el resto
    limpio = re.sub(r"\b(la |una )?brecha\s+esta brecha\b", "esta brecha", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\s*\(\s*(esta brecha)?\s*\)", "", limpio)
    limpio = re.sub(r"[ \t]+([.,;:])", r"\1", limpio)
    limpio = re.sub(r"[ \t]{2,}", " ", limpio).strip()
    if limpio and texto.lstrip()[:1].isupper():
        limpio = limpio[0].upper() + limpio[1:]
    return limpio


def nombre_legible(descripcion: str | None, maximo: int = 80) -> str:
    t = re.sub(r"\s+", " ", (descripcion or "")).strip().rstrip(".")
    if not t:
        return "brecha de tu evaluación"
    t = t[0].lower() + t[1:] if len(t) > 1 and not t[:2].isupper() else t
    return t if len(t) <= maximo else t[: maximo - 1].rstrip() + "…"


# Correcciones 05-11 (2.ª ronda): el NER que pasa por la respuesta del modelo (defensa en
# profundidad) a veces marca como nombre una palabra de saludo ("Adiós") o el modelo repite la
# etiqueta que vio en el mensaje del usuario. Una etiqueta usada como vocativo no aporta nada y
# se veía en el chat ("[NOMBRE_ANON], recuerda..."): se quita. Las demás etiquetas se dejan.
_ETIQUETA = r"\[[A-Z_]+_ANON\]"
_SALUDO = r"(?:hola|buenas|buenos d[ií]as|buenas tardes|chao|adi[oó]s|hasta (?:luego|pronto)|gracias)"


def sin_vocativos_anonimizados(texto: str | None) -> str | None:
    if not texto or "_ANON]" not in texto:
        return texto
    limpio = re.sub(rf"¡\s*{_ETIQUETA}\s*!\s*", "", texto)
    limpio = re.sub(rf",\s*{_ETIQUETA}(?=\s*[.!?,;]|\s*$)", "", limpio)
    limpio = re.sub(rf"(¡?{_SALUDO})\s+{_ETIQUETA}", r"\1", limpio, flags=re.IGNORECASE)
    limpio = re.sub(rf"^(\W*){_ETIQUETA}\s*[,:!]?\s*", r"\1", limpio)
    limpio = re.sub(rf"([.!?]\s+){_ETIQUETA}\s*[,:]\s*", r"\1", limpio)
    limpio = limpio.strip()
    i = next((k for k, c in enumerate(limpio) if c.isalpha()), None)
    if i is not None:
        limpio = limpio[:i] + limpio[i].upper() + limpio[i + 1:]
    return limpio
