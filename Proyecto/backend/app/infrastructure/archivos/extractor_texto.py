"""
HU-17 · Extracción de texto de archivos de evidencia (PDF con pypdf; DOCX con la librería
estándar: zipfile + XML; TXT tal cual). Implementa ExtractorTextoPort (A-14).

La detección de tipo (lista blanca por contenido) sigue en app/application/evidencias/archivos.py.
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from app.domain.ports.extractor_texto_port import ArchivoIlegibleError
from app.infrastructure.security.prompt_injection.seguridad import normalizar_vinetas

_MAX_DOCX_XML = 20 * 1024 * 1024  # bomba ZIP: no se descomprime más que esto


def _es_docx(contenido: bytes) -> bool:
    if not contenido.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            return "word/document.xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


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
    """Texto plano del archivo según su contenido real (sirve también para el .txt ya anonimizado).

    HU-33: las viñetas de PDF y Word (\\x7f y los caracteres del área privada de Symbol/Wingdings),
    el guion blando y el BOM se normalizan aquí, para que el detector de prompt injection no
    los confunda con caracteres de control. Los caracteres bidi y "tag" NO se tocan."""
    if contenido.startswith(b"%PDF-"):
        texto = _texto_pdf(contenido)
    elif _es_docx(contenido):
        texto = _texto_docx(contenido)
    else:
        # el texto plano llega tal cual (como antes de HU-17), salvo las viñetas
        return normalizar_vinetas(_texto_plano(contenido))
    texto = normalizar_vinetas(texto)
    # Espacios repetidos y líneas vacías de más (los PDF suelen traer muchos)
    texto = re.sub(r"[ \t\f\v]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


class ExtractorTexto:
    """Implementa ExtractorTextoPort."""

    def extraer_texto(self, contenido: bytes) -> str:
        return extraer_texto(contenido)
