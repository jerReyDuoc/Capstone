"""
HU-21 · Ficha de identificación del informe (lógica PURA: sin BD, sin red, sin reportlab).

El informe que se presenta al directorio o a un auditor tiene que poder identificarse y
reproducirse. Aquí vive todo lo que lo identifica, en un solo lugar, para que el PDF y la
página del panel (GET …/informe/ficha) muestren exactamente lo mismo:

  codigo_evaluacion()   CIA-2026-000123-7: año + número de la evaluación + dígito
                        verificador módulo 11 (el mismo algoritmo del RUT), para que un
                        auditor detecte un código mal transcrito.
  huella_matriz()       SHA-256 del contenido de la matriz de controles. La versión de la
  version_matriz()      matriz es "<etiqueta>+<8 primeros hex>": la etiqueta la fija el
                        equipo (MATRIZ_VERSION) y la huella cambia sola si alguien edita una
                        pregunta, su criticidad o su dominio sin subir la etiqueta.
  cinco_puntajes()      HU-03: siempre los 5 valores (Global, Gobernanza de IA, Gestión de
                        Riesgos, Protección de Datos, Uso Responsable). Una dimensión sin
                        preguntas aplicables se informa como tal, no desaparece (T-SM-12).
  huella_datos()        SHA-256 de los resultados (puntajes, brechas y rutas) sin la fecha
                        de emisión: dos descargas de la misma evaluación dan la misma huella,
                        y el auditor la puede comparar con la que entrega la API.
  AVISO_INFORME         HU-04 criterio 2 y 3: texto del aviso legal de la primera página y
                        del pie de cada página (delimitación de responsabilidad, Ley 21.719).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from app.application.informes.analisis import (
    ETIQUETA_MADUREZ,
    Brecha,
    DominioResultado,
    PlanFormativo,
    nivel_madurez,
    sin_tildes,
)

PREFIJO_CODIGO = "CIA"

# HU-03 criterio 2: los 5 valores, en este orden.
GLOBAL = "Global"
DIMENSIONES_OFICIALES = ("Gobernanza de IA", "Gestión de Riesgos", "Protección de Datos", "Uso Responsable")


# =====================================================================
# Aviso legal del informe (HU-04)
# =====================================================================
@dataclass(frozen=True)
class AvisoInforme:
    version: str
    titulo: str
    texto: tuple[str, ...]   # párrafos de la primera página
    pie: str                 # una línea, en el pie de TODAS las páginas


# BORRADOR TÉCNICO (T-SM-14): el texto lo valida el Product Owner con Therion Labs y el
# docente. Si cambia, sube la versión: queda impresa en cada informe para saber cuál se usó.
AVISO_INFORME = AvisoInforme(
    version="2026-11-v1",
    titulo="Aviso legal",
    texto=(
        "Este informe resume un autodiagnóstico que respondió la propia organización en la plataforma "
        "ComplianceIA de Therion Labs. Es un instrumento orientativo: no es una auditoría, no certifica el "
        "cumplimiento de la Ley N.º 21.719 sobre protección de datos personales ni de otra norma, y no "
        "constituye asesoría legal.",
        "Los puntajes, las brechas y las rutas se calculan solo con las respuestas y evidencias que entregó "
        "la organización, que responde por su veracidad y completitud. El cumplimiento de la Ley N.º 21.719 "
        "es responsabilidad de la organización como responsable del tratamiento; Therion Labs no asume las "
        "obligaciones que deriven de las decisiones que se adopten con este documento.",
        "Para una opinión jurídica o una certificación, consulte a un abogado o a un auditor independiente.",
    ),
    pie="Autodiagnóstico orientativo: no certifica el cumplimiento de la Ley N.º 21.719 ni constituye asesoría legal.",
)


# =====================================================================
# Código de evaluación
# =====================================================================
def digito_verificador(numero: int) -> str:
    """Módulo 11 con la serie 2..7 (como el RUT chileno): 0-9 o K."""
    if numero < 0:
        raise ValueError("El número de evaluación no puede ser negativo.")
    suma, factor = 0, 2
    for d in reversed(str(numero)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


def codigo_evaluacion(evaluacion_id: int, anio: int) -> str:
    """CIA-2026-000123-7. El año es el de inicio de la evaluación (estable entre descargas)."""
    return f"{PREFIJO_CODIGO}-{anio:04d}-{evaluacion_id:06d}-{digito_verificador(evaluacion_id)}"


def leer_codigo(codigo: str) -> tuple[int, int] | None:
    """(año, evaluacion_id) si el código está bien formado y el dígito cuadra; si no, None."""
    partes = (codigo or "").strip().upper().split("-")
    if len(partes) != 4 or partes[0] != PREFIJO_CODIGO:
        return None
    _, anio, numero, dv = partes
    if not (anio.isdigit() and len(anio) == 4 and numero.isdigit() and len(numero) >= 6):
        return None
    if digito_verificador(int(numero)) != dv:
        return None
    return int(anio), int(numero)


# =====================================================================
# Versión de la matriz
# =====================================================================
def huella_matriz(filas: Iterable[tuple]) -> str:
    """
    SHA-256 de las filas de la matriz de controles. Cada fila es una tupla con lo que define
    el control (id, código, dominio, pregunta, aplicabilidad, criticidad, obligación, brecha).
    El orden de llegada no importa: se ordenan antes de calcular.
    """
    normalizadas = sorted(json.dumps([("" if v is None else str(v)) for v in f], ensure_ascii=False)
                          for f in filas)
    return hashlib.sha256("\n".join(normalizadas).encode("utf-8")).hexdigest()


def version_matriz(etiqueta: str, huella: str) -> str:
    return f"{(etiqueta or 'sin-etiqueta').strip()}+{huella[:8]}"


# =====================================================================
# Los 5 puntajes (HU-03)
# =====================================================================
@dataclass(frozen=True)
class PuntajeInforme:
    nombre: str
    puntaje: float | None     # None = sin preguntas aplicables
    nivel: str                # etiqueta legible ("Gestionado") o "Sin preguntas aplicables"
    preguntas: int            # preguntas evaluadas (las N/A no cuentan)
    es_global: bool = False

    @property
    def aplicable(self) -> bool:
        return self.puntaje is not None


SIN_APLICABLES = "Sin preguntas aplicables"


def _clave(nombre: str | None) -> str:
    return sin_tildes(nombre or "").strip()


def cinco_puntajes(puntaje_general: float, preguntas_total: int, dominios: list[DominioResultado],
                   catalogo: Iterable[str] = ()) -> list[PuntajeInforme]:
    """
    Global + cada dimensión del catálogo (tabla dominio), siempre todas: una dimensión sin
    resumen (todas sus preguntas N/A) aparece con puntaje None en vez de desaparecer. Con la
    semilla real son las 4 de HU-03, en el orden de DIMENSIONES_OFICIALES; otra dimensión que
    exista en la BD va después, por nombre. Sin catálogo (pruebas que arman el informe a
    mano) se usan las 4 oficiales.

    El catálogo de la BD manda: no se inventan dimensiones que no existen en esa instalación.
    """
    por_clave = {_clave(d.nombre): d for d in dominios}
    base = [n for n in catalogo if n] or list(DIMENSIONES_OFICIALES)
    nombres: list[str] = []
    for nombre in [*base, *(d.nombre for d in dominios)]:
        if nombre and _clave(nombre) not in {_clave(n) for n in nombres}:
            nombres.append(nombre)
    orden = {_clave(n): i for i, n in enumerate(DIMENSIONES_OFICIALES)}
    nombres.sort(key=lambda n: (orden.get(_clave(n), len(orden)), _clave(n)))

    filas = [PuntajeInforme(
        nombre=GLOBAL,
        puntaje=round(puntaje_general, 1) if preguntas_total else None,
        nivel=ETIQUETA_MADUREZ[nivel_madurez(puntaje_general)] if preguntas_total else SIN_APLICABLES,
        preguntas=preguntas_total, es_global=True,
    )]
    for nombre in nombres:
        d = por_clave.get(_clave(nombre))
        if d is None or d.puntaje is None or d.controles == 0:
            filas.append(PuntajeInforme(nombre=d.nombre if d else nombre, puntaje=None,
                                        nivel=SIN_APLICABLES, preguntas=0))
        else:
            filas.append(PuntajeInforme(nombre=d.nombre, puntaje=round(d.puntaje, 1),
                                        nivel=ETIQUETA_MADUREZ[nivel_madurez(d.puntaje)],
                                        preguntas=d.controles or 0))
    return filas


# =====================================================================
# Huella de los datos del informe
# =====================================================================
def huella_datos(codigo: str, version: str, puntajes: list[PuntajeInforme],
                 brechas: list[Brecha], plan: PlanFormativo) -> str:
    """
    SHA-256 de lo que el informe AFIRMA (no de cómo se ve): puntajes, brechas completas
    (no las filtradas) y rutas del plan. No incluye la fecha de emisión.
    """
    contenido = {
        "codigo": codigo,
        "matriz": version,
        "puntajes": [[p.nombre, p.puntaje, p.preguntas] for p in puntajes],
        "brechas": sorted([b.prioridad, b.respuesta_id, b.severidad, b.estado] for b in brechas),
        "rutas": sorted({m.ruta.id for dim in plan.dimensiones for m in dim.modulos}),
    }
    texto = json.dumps(contenido, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def huella_legible(huella: str, grupos: int = 4) -> str:
    """Los primeros 16 hex en grupos de 4 (fáciles de dictar o comparar a ojo)."""
    h = huella[: grupos * 4].upper()
    return " ".join(h[i:i + 4] for i in range(0, len(h), 4))


# =====================================================================
# Ficha completa
# =====================================================================
@dataclass(frozen=True)
class FichaInforme:
    codigo: str
    fecha_evaluacion: date | None          # inicio de la evaluación
    fecha_completado: datetime | None      # cierre (UTC); None en evaluaciones anteriores a HU-29
    version_matriz: str
    # False = la evaluación es anterior a HU-21 y no guardó su versión: se imprime la
    # vigente al emitir el informe, con una nota.
    version_matriz_registrada: bool
    aviso: AvisoInforme
    aviso_aceptado_version: str | None     # HU-04/HU-19: lo que aceptó el encuestado
    aviso_aceptado_fecha: datetime | None
    puntajes: list[PuntajeInforme]
    huella: str
