"""
HU-17 · Archivos de evidencia: tipos admitidos, extracción de texto y términos del control.

Antes de esta HU el worker leía toda evidencia como texto UTF-8: un PDF o un DOCX llegaba
ilegible al NER y al LLM (hallazgo de la revisión del backlog, T-SM-54). Ahora:

  - detectar_tipo()     lista blanca por CONTENIDO (no solo por extensión): PDF (%PDF-),
                        DOCX (ZIP con word/document.xml) y TXT (UTF-8 legible). Cualquier
                        otro archivo se rechaza en la API antes de guardarlo (T-SM-55).
  - extraer_texto()     texto plano del archivo para el NER y el LLM. PDF con pypdf; DOCX
                        con la librería estándar (zipfile + XML); TXT tal cual.
  - terminos_control()  HU-17 C2: verificación LOCAL (sin LLM) de qué términos del control
                        aparecen en el texto, para mostrarlos y no gastar cuota del LLM en
                        archivos que no tienen nada que ver.

Sin dependencias de FastAPI ni de la BD (se prueba sola en tests/test_hu17_remediacion.py).
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from xml.etree import ElementTree

PDF, DOCX, TXT = "pdf", "docx", "txt"
MIME = {PDF: "application/pdf",
        DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        TXT: "text/plain"}
EXTENSIONES = {".pdf": PDF, ".docx": DOCX, ".txt": TXT, ".md": TXT, ".csv": TXT}
_MAX_DOCX_XML = 20 * 1024 * 1024  # bomba ZIP: no se descomprime más que esto


class ArchivoNoAdmitidoError(ValueError):
    codigo = "TIPO_NO_ADMITIDO"


class ArchivoIlegibleError(ValueError):
    codigo = "ARCHIVO_ILEGIBLE"


def _extension(nombre: str | None) -> str:
    m = re.search(r"(\.[A-Za-z0-9]{1,5})$", (nombre or "").strip())
    return m.group(1).lower() if m else ""


def _es_docx(contenido: bytes) -> bool:
    if not contenido.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            return "word/document.xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


def _es_texto(contenido: bytes) -> bool:
    muestra = contenido[:4096]
    if b"\x00" in muestra:
        return False
    try:
        muestra.decode("utf-8")
    except UnicodeDecodeError as e:
        # Un corte a mitad de un carácter multibyte al final de la muestra no cuenta
        if e.start < len(muestra) - 3:
            try:
                muestra.decode("latin-1")
                return not re.search(rb"[\x00-\x08\x0e-\x1f]", muestra)
            except UnicodeDecodeError:  # pragma: no cover - latin-1 decodifica todo
                return False
    return True


def detectar_tipo(nombre: str | None, contenido: bytes) -> str:
    """El tipo real del archivo o ArchivoNoAdmitidoError. La extensión debe coincidir con el contenido."""
    ext = _extension(nombre)
    declarado = EXTENSIONES.get(ext)
    if contenido.startswith(b"%PDF-"):
        real = PDF
    elif _es_docx(contenido):
        real = DOCX
    elif _es_texto(contenido):
        real = TXT
    else:
        real = None
    if real is None or declarado is None or (declarado != real):
        raise ArchivoNoAdmitidoError(
            "Solo se aceptan evidencias en PDF, Word (.docx) o texto (.txt), y la extensión del "
            "archivo debe coincidir con su contenido."
        )
    return real


def _texto_pdf(contenido: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise ArchivoIlegibleError("El servidor no puede leer PDF (falta pypdf: pip install -r requirements.txt).") from e
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted:
            try:
                lector.decrypt("")
            except Exception as e:  # noqa: BLE001
                raise ArchivoIlegibleError("El PDF está protegido con contraseña. Súbelo sin protección.") from e
        return "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    except ArchivoIlegibleError:
        raise
    except Exception as e:  # noqa: BLE001 - PDF dañado
        raise ArchivoIlegibleError("No pudimos leer el PDF. Revisa que no esté dañado.") from e


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _texto_docx(contenido: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > _MAX_DOCX_XML:
                raise ArchivoIlegibleError("El documento Word es demasiado grande para analizarlo.")
            raiz = ElementTree.fromstring(z.read(info))
    except ArchivoIlegibleError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ArchivoIlegibleError("No pudimos leer el documento Word. Revisa que no esté dañado.") from e
    parrafos = []
    for p in raiz.iter(f"{_W}p"):
        partes = []
        for nodo in p.iter():
            if nodo.tag == f"{_W}t" and nodo.text:
                partes.append(nodo.text)
            elif nodo.tag == f"{_W}tab":
                partes.append("\t")
            elif nodo.tag in (f"{_W}br", f"{_W}cr"):
                partes.append("\n")
        parrafos.append("".join(partes))
    return "\n".join(parrafos)


def _texto_plano(contenido: bytes) -> str:
    # Igual que antes de HU-17: lo que no es UTF-8 válido se descarta (no se inventan caracteres)
    return contenido.decode("utf-8", errors="ignore")


def extraer_texto(contenido: bytes) -> str:
    """Texto plano del archivo según su contenido real (sirve también para el .txt ya anonimizado)."""
    if contenido.startswith(b"%PDF-"):
        texto = _texto_pdf(contenido)
    elif _es_docx(contenido):
        texto = _texto_docx(contenido)
    else:
        return _texto_plano(contenido)  # el texto plano llega tal cual (como antes de HU-17)
    # Espacios repetidos y líneas vacías de más (los PDF suelen traer muchos)
    texto = re.sub(r"[ \t\f\v]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


# --------------------------------------------------------------------- términos del control
_VACIAS = frozenset("""
a al ante bajo cabe con contra de del desde durante en entre hacia hasta mediante para por segun sin
so sobre tras el la los las un una unos unas lo y o u e ni que se su sus es son ser esta este estos
estas ese esa esos esas como cual cuales donde cuando mas muy ya no si sea han ha hay tiene tienen
debe deben cada todo toda todos todas otro otra otros otras sus organizacion empresa existe existen
cuenta cuentan mediante caso asi tambien forma manera parte uso usar
""".split())


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _raiz(palabra: str) -> str:
    """Raíz tosca para el español: plurales y algunos sufijos frecuentes."""
    for sufijo in ("aciones", "acion", "mente", "es", "s"):
        if len(palabra) > len(sufijo) + 4 and palabra.endswith(sufijo):
            return palabra[: -len(sufijo)]
    return palabra


def terminos_del_control(*textos: str | None, maximo: int = 12) -> list[str]:
    """Palabras clave del control (obligación, evidencia esperada, pregunta), sin repetir."""
    vistos, salida = set(), []
    for texto in textos:
        for palabra in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]{5,}", texto or ""):
            n = _normalizar(palabra)
            r = _raiz(n)
            if n in _VACIAS or r in vistos or n.isdigit():
                continue
            vistos.add(r)
            salida.append(palabra.lower())
            if len(salida) >= maximo:
                return salida
    return salida


def terminos_control(texto: str, control) -> dict:
    """HU-17 C2: {terminos, encontrados, faltantes, cobertura} del control sobre el texto."""
    terminos = terminos_del_control(
        getattr(control, "evidencia_esperada", None), getattr(control, "obligacion", None),
        getattr(control, "pregunta_evaluacion", None),
    )
    raices_texto = {_raiz(_normalizar(p)) for p in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]{4,}", texto or "")}
    encontrados = [t for t in terminos if _raiz(_normalizar(t)) in raices_texto]
    faltantes = [t for t in terminos if t not in encontrados]
    return {
        "terminos": terminos,
        "encontrados": encontrados,
        "faltantes": faltantes,
        "cobertura": round(100 * len(encontrados) / len(terminos), 1) if terminos else None,
    }


# --------------------------------------------------------------------- RAG local (HU-17 C2)
_SEPARADOR_RAG = "\n[…]\n"


def _pasajes(texto: str, objetivo: int = 900) -> list[str]:
    """Divide el texto en pasajes de ~`objetivo` caracteres respetando los párrafos."""
    pasajes, actual = [], ""
    for parrafo in re.split(r"\n\s*\n|\n", texto):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        while len(parrafo) > objetivo * 2:          # párrafo enorme (PDF sin saltos): se corta por frases
            corte = parrafo.rfind(". ", 0, objetivo) + 1 or objetivo
            pasajes.append(parrafo[:corte].strip())
            parrafo = parrafo[corte:].strip()
        if actual and len(actual) + len(parrafo) > objetivo:
            pasajes.append(actual)
            actual = ""
        actual = f"{actual}\n{parrafo}".strip()
    if actual:
        pasajes.append(actual)
    return pasajes


def recuperar_fragmentos(texto: str, control, max_chars: int) -> tuple[str, dict]:
    """
    HU-17 C2 · RAG local: cuando la evidencia no cabe completa en el prompt, en vez de mandar
    solo el comienzo del documento se RECUPERAN los pasajes que más hablan de lo que pide el
    control (BM25 sobre los términos del control, calculado en el servidor, sin servicios
    externos) y esos pasajes, en su orden original, son el contexto del LLM.

    Devuelve (texto para el LLM, metadatos). Si el texto cabe, va completo.
    """
    if len(texto) <= max_chars:
        return texto, {"aplicado": False, "pasajes_total": None, "pasajes_usados": None}
    import math

    consulta = {_raiz(_normalizar(t)) for t in terminos_del_control(
        getattr(control, "evidencia_esperada", None), getattr(control, "obligacion", None),
        getattr(control, "pregunta_evaluacion", None), maximo=20,
    )}
    pasajes = _pasajes(texto)
    tokens = [[_raiz(_normalizar(p)) for p in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]{4,}", x)] for x in pasajes]
    n = len(pasajes)
    largo_medio = sum(len(t) for t in tokens) / n if n else 1
    df = {q: sum(1 for t in tokens if q in t) for q in consulta}
    k1, b = 1.5, 0.75

    def bm25(t: list[str]) -> float:
        total = 0.0
        for q in consulta:
            f = t.count(q)
            if f:
                idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
                total += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(t) / (largo_medio or 1)))
        return total

    puntajes = [bm25(t) for t in tokens]
    orden = sorted(range(n), key=lambda i: (-puntajes[i], i))
    elegidos, usados = [], 0
    for i in orden:
        costo = len(pasajes[i]) + len(_SEPARADOR_RAG)
        if usados + costo > max_chars:
            continue
        elegidos.append(i)
        usados += costo
    if not elegidos:  # un solo pasaje gigante: su comienzo
        return texto[:max_chars], {"aplicado": True, "pasajes_total": n, "pasajes_usados": 1}
    elegidos.sort()
    return _SEPARADOR_RAG.join(pasajes[i] for i in elegidos), {
        "aplicado": True, "pasajes_total": n, "pasajes_usados": len(elegidos),
        "pasajes_con_terminos": sum(1 for i in elegidos if puntajes[i] > 0),
    }
