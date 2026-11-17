"""
Corpus sintético y determinista para medir el rendimiento del motor NER (T-04).

Genera "páginas" de evidencia de cumplimiento en español con datos personales
repartidos (nombres, RUT, correos, teléfonos, direcciones, nombres en MAYÚSCULAS),
siglas del dominio (ISO, DPO, ARCOP) y referencias normativas (Ley 21.719), que
son las que más trabajo dan al motor.

Una página = CHARS_POR_PAGINA caracteres (por defecto 3.000, ~500 palabras: una
plana A4 de texto corrido). Se puede cambiar con la variable NER_CHARS_POR_PAGINA.
"""
from __future__ import annotations

import os
import random

CHARS_POR_PAGINA = int(os.getenv("NER_CHARS_POR_PAGINA", "3000"))

_NOMBRES = ["Juan", "María", "Pedro", "Camila", "Francisca", "Diego", "Valentina", "Felipe",
            "Javiera", "Matías", "Constanza", "Sebastián", "Catalina", "Tomás", "Fernanda"]
_APELLIDOS = ["Pérez", "González", "Muñoz", "Rojas", "Díaz", "Soto", "Contreras", "Silva",
              "Martínez", "Sepúlveda", "Morales", "Fuentes", "Valenzuela", "Araya", "Tapia"]
_CALLES = ["Av. Providencia", "Calle Los Aromos", "Pasaje El Roble", "Avenida Apoquindo",
           "Calle San Diego", "Av. Libertador Bernardo O'Higgins"]
_COMUNAS = ["Providencia", "Santiago", "Las Condes", "Ñuñoa", "Maipú", "San Bernardo"]
_CARGOS = ["Presidenta del Directorio", "Gerente General", "Encargado de Protección de Datos",
           "Oficial de Cumplimiento", "Jefa de Tecnologías de la Información"]

_FRASES = [
    "La organización mantiene un registro de actividades de tratamiento conforme a la Ley 21.719.",
    "El comité de seguridad revisó la política de control de acceso basada en ISO 27001.",
    "Se aplicó la evaluación de impacto (EIPD) a los sistemas que tratan datos sensibles.",
    "Las solicitudes ARCOP se responden mediante el portal del titular dentro del plazo definido.",
    "El DPO informó al directorio los incidentes de seguridad del trimestre.",
    "Los respaldos se cifran con AES-256 y se almacenan en un centro de datos certificado.",
    "El proveedor SAP firmó el acuerdo de encargo de tratamiento con cláusulas de confidencialidad.",
    "Se capacitó a 120 colaboradores en protección de datos personales durante 2025.",
    "El modelo de IA se evalúa trimestralmente para detectar sesgos y deriva de datos.",
    "La matriz de riesgos considera probabilidad, impacto y controles compensatorios.",
    "Según el artículo 14 de la Ley 19.628, el titular puede solicitar la rectificación de sus datos.",
    "El monto aprobado para el proyecto fue de $15000000 según el acta folio 20240315.",
]


def _nombre(r: random.Random) -> str:
    return f"{r.choice(_NOMBRES)} {r.choice(_APELLIDOS)} {r.choice(_APELLIDOS)}"


def _rut(r: random.Random) -> str:
    cuerpo = r.randint(5_000_000, 25_000_000)
    suma, factor = 0, 2
    for d in reversed(str(cuerpo)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    dv = {11: "0", 10: "K"}.get(11 - suma % 11, str(11 - suma % 11))
    return f"{cuerpo:,}".replace(",", ".") + f"-{dv}"


def _frase_con_pii(r: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """Frase con PII + las entidades que contiene (tipo, valor), para medir precisión."""
    n = _nombre(r)
    rut = _rut(r)
    correo = f"{n.split()[0].lower()}.{n.split()[1].lower()}@empresa.cl"
    tel = f"+56 9 {r.randint(1000, 9999)} {r.randint(1000, 9999)}"
    dire = f"{r.choice(_CALLES)} {r.randint(100, 9999)}, oficina {r.randint(1, 900)}, {r.choice(_COMUNAS)}"
    opciones = [
        (f"El documento fue firmado por {n}, RUT {rut}.", [("NOMBRE", n), ("RUT", rut)]),
        (f"Para consultas escribir a {correo} o llamar al {tel}.", [("CORREO", correo), ("TEL", tel)]),
        (f"La oficina se ubica en {dire}.", [("DIRECCION", dire)]),
        (f"La política fue aprobada por {n.upper()} en sesión del directorio.", [("NOMBRE", n.upper())]),
        (f"Asistió la {r.choice(_CARGOS)}, {n}, quien validó el procedimiento.", [("NOMBRE", n)]),
        (f"El responsable del inventario es {n} (cédula {rut}).", [("NOMBRE", n), ("RUT", rut)]),
    ]
    return r.choice(opciones)


def pagina_etiquetada(seed: int = 0, chars: int = CHARS_POR_PAGINA,
                      densidad_pii: float = 0.35) -> tuple[str, list[tuple[str, str]]]:
    """Una página de ~`chars` caracteres y sus entidades (las que quedan dentro del corte)."""
    r = random.Random(seed)
    partes: list[str] = []
    entidades: list[tuple[str, str]] = []
    largo = 0
    while largo < chars:
        if r.random() < densidad_pii:
            frase, ents = _frase_con_pii(r)
        else:
            frase, ents = r.choice(_FRASES), []
        if r.random() < 0.15:
            frase += "\n\n"
        if largo + len(frase) <= chars:  # solo se etiqueta lo que queda completo
            entidades += ents
        partes.append(frase)
        largo += len(frase) + 1
    return " ".join(partes)[:chars], entidades


def pagina(seed: int = 0, chars: int = CHARS_POR_PAGINA, densidad_pii: float = 0.35) -> str:
    """Una página de ~`chars` caracteres. `densidad_pii` = fracción de frases con PII."""
    return pagina_etiquetada(seed, chars, densidad_pii)[0]


def paginas(n: int, chars: int = CHARS_POR_PAGINA, densidad_pii: float = 0.35) -> list[str]:
    return [pagina(seed=i, chars=chars, densidad_pii=densidad_pii) for i in range(n)]
