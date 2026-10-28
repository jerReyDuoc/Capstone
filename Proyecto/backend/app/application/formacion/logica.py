"""
HU-26 · Lógica pura del recorrido de módulos y del avance de la empresa.

No importa SQLAlchemy ni FastAPI (se prueba sola en tests/test_hu26_formacion.py):

  - lecciones_de_ruta()      lecciones del módulo (las de la BD o, si una ruta aún no las
                             tiene, una por línea de `contenidos`, como placeholder).
  - preguntas_publicas()     la actividad SIN la respuesta correcta y con las opciones en un
                             orden estable por empresa (que copiar la posición no sirva).
  - corregir()               nota de la actividad (la corrige siempre el servidor).
  - resumir_avance()         avance de la empresa por módulo, dimensión y nivel, y qué brechas
                             ya tienen la formación hecha.

Regla de negocio (criterio 3): completar un módulo marca sus brechas con "formación hecha",
pero NUNCA cambia el puntaje de madurez. El puntaje solo cambia con evidencia nueva (HU-17).
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime

from app.application.informes.analisis import NIVELES, PESO_NIVEL, PlanFormativo, RutaCatalogo, sin_tildes

NO_INICIADO = "no_iniciado"
EN_CURSO = "en_curso"
COMPLETADO = "completado"

MATERIAL_PLACEHOLDER = (
    {"tipo": "guia", "titulo": "Guía de la lección (PDF)",
     "descripcion": "Resumen descargable con los conceptos y ejemplos de la lección."},
    {"tipo": "video", "titulo": "Video explicativo", "descripcion": "Cápsula de 5 a 8 minutos con un caso práctico."},
    {"tipo": "plantilla", "titulo": "Plantilla de trabajo",
     "descripcion": "Formato editable para aplicar la lección en tu organización."},
)


# --------------------------------------------------------------------- lecciones
@dataclass(frozen=True)
class Leccion:
    orden: int
    titulo: str
    resumen: str | None = None
    contenido: tuple[str, ...] = ()
    material: tuple[dict, ...] = ()
    duracion_min: int | None = None


def lecciones_de_ruta(ruta: RutaCatalogo, guardadas: list[Leccion]) -> list[Leccion]:
    """Las lecciones de la BD en orden; si la ruta no tiene, una por cada contenido (placeholder)."""
    if guardadas:
        return sorted(guardadas, key=lambda x: x.orden)
    titulos = list(ruta.contenidos)
    minutos = max(10, round((ruta.horas or 1) * 60 / len(titulos))) if titulos else None
    return [
        Leccion(
            orden=i, titulo=t, resumen=f"Lección {i} de {len(titulos)} del módulo {ruta.nombre}.",
            contenido=(f"Esta lección trabaja «{t}».",
                       "Contenido en preparación por Therion Labs: aquí irá el desarrollo de la lección "
                       "con ejemplos aplicados a empresas chilenas y a la Ley 21.719."),
            material=MATERIAL_PLACEHOLDER, duracion_min=minutos,
        )
        for i, t in enumerate(titulos, start=1)
    ]


# --------------------------------------------------------------------- actividad de verificación
@dataclass(frozen=True)
class Pregunta:
    id: int
    orden: int
    enunciado: str
    opciones: tuple[str, ...]
    correcta: int
    explicacion: str | None = None


def _semilla(*partes) -> int:
    return int(hashlib.sha256(":".join(str(p) for p in partes).encode()).hexdigest()[:12], 16)


def preguntas_publicas(preguntas: list[Pregunta], empresa_id: int) -> list[dict]:
    """
    La actividad tal como la ve el navegador: sin `correcta` ni `explicacion`. Cada opción
    lleva su id (su posición original) y se muestran en un orden estable por empresa y
    pregunta, así la letra de la opción correcta no se repite de una empresa a otra.
    """
    salida = []
    for p in sorted(preguntas, key=lambda x: x.orden):
        opciones = [{"id": i, "texto": t} for i, t in enumerate(p.opciones)]
        random.Random(_semilla(empresa_id, p.id)).shuffle(opciones)
        salida.append({"id": p.id, "orden": p.orden, "enunciado": p.enunciado, "opciones": opciones})
    return salida


@dataclass
class Correccion:
    total: int
    correctas: int
    puntaje: float            # 0-100
    aprobado: bool
    detalle: list[dict] = field(default_factory=list)
    sin_responder: list[int] = field(default_factory=list)


def corregir(preguntas: list[Pregunta], respuestas: dict[int, int], umbral: float) -> Correccion:
    """
    Nota sobre 100. Aprueba con `umbral` o más. Una pregunta sin responder cuenta como
    incorrecta (y se informa en `sin_responder`). La explicación de cada pregunta solo se
    entrega si aprobó: antes revelaría la respuesta correcta.
    """
    if not preguntas:
        raise ValueError("El módulo no tiene actividad de verificación.")
    correctas = 0
    detalle, sin_responder = [], []
    for p in sorted(preguntas, key=lambda x: x.orden):
        elegida = respuestas.get(p.id)
        if elegida is None:
            sin_responder.append(p.id)
        ok = elegida is not None and int(elegida) == p.correcta
        correctas += ok
        detalle.append({"pregunta_id": p.id, "correcta": ok})
    puntaje = round(100 * correctas / len(preguntas), 1)
    aprobado = puntaje >= umbral
    if aprobado:
        por_id = {p.id: p for p in preguntas}
        for d in detalle:
            d["explicacion"] = por_id[d["pregunta_id"]].explicacion
    return Correccion(len(preguntas), correctas, puntaje, aprobado, detalle, sin_responder)


def codigo_constancia(rng: random.Random | None = None) -> str:
    """CF-XXXX-XXXX sin letras que se confundan (0/O, 1/I)."""
    alfabeto = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    rng = rng or random.SystemRandom()
    bloque = lambda: "".join(rng.choice(alfabeto) for _ in range(4))  # noqa: E731
    return f"CF-{bloque()}-{bloque()}"


# --------------------------------------------------------------------- avance de la empresa
@dataclass(frozen=True)
class AvanceModulo:
    ruta_id: int
    estado: str                         # en_curso | completado
    lecciones_vistas: frozenset[int] = frozenset()
    intentos: int = 0
    mejor_puntaje: float | None = None
    ultimo_puntaje: float | None = None
    fecha_inicio: datetime | None = None
    fecha_completado: datetime | None = None
    codigo_constancia: str | None = None


def _pct(parte: int, total: int) -> float:
    return round(100 * parte / total, 1) if total else 0.0


def _iso(f: datetime | None) -> str | None:
    return f.isoformat(timespec="seconds") if f else None


def resumir_avance(plan: PlanFormativo, avances: dict[int, AvanceModulo], lecciones_por_ruta: dict[int, int],
                   rutas_fuera_del_plan: list[RutaCatalogo] | None = None) -> dict:
    """
    Criterio 2: el avance de la empresa sobre el plan formativo de una evaluación.

    Los módulos son los del plan (HU-12) más los que la empresa ya completó o empezó y que
    hoy no están en el plan (p. ej. porque cerró sus brechas con evidencia, HU-17): así cerrar
    una brecha nunca baja el avance. El porcentaje de cada dimensión y nivel es la proporción
    de módulos completados; el de cada módulo, sus lecciones vistas.
    """
    modulos: list[dict] = []
    vistos: set[int] = set()
    brechas: list[dict] = []

    def fila(ruta: RutaCatalogo, dominio: str, nivel: str, motivo: str, prioridad: str, en_plan: bool,
             cubiertas: list) -> dict:
        a = avances.get(ruta.id)
        total_l = lecciones_por_ruta.get(ruta.id, len(ruta.contenidos))
        vistas = len([o for o in (a.lecciones_vistas if a else ()) if 1 <= o <= total_l]) if total_l else 0
        estado = a.estado if a else NO_INICIADO
        return {
            "ruta_id": ruta.id, "nombre": ruta.nombre, "dominio": dominio, "nivel": nivel,
            "horas": ruta.horas, "modalidad": ruta.modalidad, "motivo": motivo, "prioridad": prioridad,
            "en_plan": en_plan, "estado": estado,
            "lecciones_total": total_l, "lecciones_vistas": vistas,
            "porcentaje_lecciones": 100.0 if estado == COMPLETADO else _pct(vistas, total_l),
            "intentos": a.intentos if a else 0,
            "mejor_puntaje": a.mejor_puntaje if a else None,
            "fecha_inicio": _iso(a.fecha_inicio) if a else None,
            "fecha_completado": _iso(a.fecha_completado) if a else None,
            "codigo_constancia": a.codigo_constancia if a else None,
            "brechas": [c.codigo for c in cubiertas],
        }

    for d in plan.dimensiones:
        for m in d.modulos:
            if m.ruta.id in vistos:
                continue
            vistos.add(m.ruta.id)
            f = fila(m.ruta, d.dominio, m.nivel, m.motivo, m.prioridad, True, m.brechas)
            modulos.append(f)
            for c in m.brechas:
                brechas.append({
                    "codigo": c.codigo, "respuesta_id": c.respuesta_id, "control_codigo": c.control_codigo,
                    "dominio": c.dominio, "severidad": c.severidad, "estado": c.estado, "prioridad": c.prioridad,
                    "ruta_id": m.ruta.id, "modulo": m.ruta.nombre,
                    "formacion_completada": f["estado"] == COMPLETADO,
                })

    for r in rutas_fuera_del_plan or []:
        if r.id in vistos or r.id not in avances:
            continue
        vistos.add(r.id)
        modulos.append(fila(r, r.dominio_efectivo or "Sin dimensión", r.nivel_efectivo or "Inicial",
                            "historial", "Complementario", False, []))

    def agrupar(clave: str, orden) -> list[dict]:
        grupos: dict[str, list[dict]] = {}
        for m in modulos:
            grupos.setdefault(m[clave], []).append(m)
        salida = []
        for nombre in sorted(grupos, key=orden):
            ms = grupos[nombre]
            hechos = sum(m["estado"] == COMPLETADO for m in ms)
            salida.append({
                clave: nombre, "total": len(ms), "completados": hechos,
                "en_curso": sum(m["estado"] == EN_CURSO for m in ms),
                "porcentaje": _pct(hechos, len(ms)),
                "horas_total": sum(m["horas"] or 0 for m in ms),
                "horas_completadas": sum(m["horas"] or 0 for m in ms if m["estado"] == COMPLETADO),
            })
        return salida

    completados = sum(m["estado"] == COMPLETADO for m in modulos)
    en_curso = sum(m["estado"] == EN_CURSO for m in modulos)
    formadas = sum(b["formacion_completada"] for b in brechas)
    brechas.sort(key=lambda b: b["prioridad"])
    modulos.sort(key=lambda m: (not m["en_plan"], sin_tildes(m["dominio"]), PESO_NIVEL.get(m["nivel"], 9),
                                sin_tildes(m["nombre"])))
    return {
        "resumen": {
            "modulos_total": len(modulos),
            "iniciados": completados + en_curso,
            "en_curso": en_curso,
            "completados": completados,
            "porcentaje": _pct(completados, len(modulos)),
            "horas_total": sum(m["horas"] or 0 for m in modulos),
            "horas_completadas": sum(m["horas"] or 0 for m in modulos if m["estado"] == COMPLETADO),
            "brechas_total": len(brechas),
            "brechas_con_formacion": formadas,
            "porcentaje_brechas_con_formacion": _pct(formadas, len(brechas)),
        },
        "por_dimension": agrupar("dominio", sin_tildes),
        "por_nivel": agrupar("nivel", lambda n: PESO_NIVEL.get(n, 9)),
        "modulos": modulos,
        "brechas": brechas,
        "niveles": list(NIVELES),
    }
