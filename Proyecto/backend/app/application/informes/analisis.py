"""
Lógica pura de los informes: severidad de brechas (HU-11) y plan formativo (HU-12).

No importa SQLAlchemy ni FastAPI: recibe dataclasses y devuelve dataclasses, así se
prueba sola (tests/test_hu12_plan_formativo.py) y el PDF, el correo y la API usan
exactamente el mismo cálculo.

La severidad replica frontend-next/lib/severidad.ts y el orden replica
frontend-next/lib/adaptadores.ts (ordenarBrechas): lo que el panel muestra y lo que
el PDF imprime es la misma lista, en el mismo orden.

                 │ No cumplido │ Parcialmente cumplido
  ───────────────┼─────────────┼──────────────────────
  Impacto Alto   │  Crítica    │  Alta
  Impacto Medio  │  Alta       │  Media
  Impacto Bajo   │  Media      │  Baja
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace

# --------------------------------------------------------------------- constantes
NO_CUMPLIDO = "no_cumplido"
PARCIAL = "parcialmente_cumplido"
ESTADOS_BRECHA = (NO_CUMPLIDO, PARCIAL)

SEVERIDADES = ("Crítica", "Alta", "Media", "Baja", "Sin clasificar")
PESO_SEVERIDAD = {s: i for i, s in enumerate(SEVERIDADES)}
PESO_IMPACTO = {"Alta": 0, "Media": 1, "Baja": 2, "Sin clasificar": 3}

MATRIZ_SEVERIDAD = {
    "Alta": {NO_CUMPLIDO: "Crítica", PARCIAL: "Alta"},
    "Media": {NO_CUMPLIDO: "Alta", PARCIAL: "Media"},
    "Baja": {NO_CUMPLIDO: "Media", PARCIAL: "Baja"},
}

GUIA_SEVERIDAD = {
    "Crítica": "Atender de inmediato",
    "Alta": "Resolver en el corto plazo",
    "Media": "Planificar este trimestre",
    "Baja": "Mejora continua",
    "Sin clasificar": "Falta clasificar el control",
}

ETIQUETA_ESTADO = {NO_CUMPLIDO: "No cumplido", PARCIAL: "Parcialmente cumplido"}

# HU-12: niveles del catálogo formativo, en orden de aprendizaje.
NIVELES = ("Inicial", "Intermedio", "Avanzado")
PESO_NIVEL = {n: i for i, n in enumerate(NIVELES)}

# Corte de madurez -> nivel de capacitación que se asigna a la dimensión.
# Mismos cortes que generate_resumen.nivel_madurez:
#   inicial (≤25) y en desarrollo (≤50) -> Inicial: faltan las bases.
#   gestionado (≤75)                    -> Intermedio: hay controles, falta aplicarlos bien.
#   optimizado (>75)                    -> Avanzado: mejora continua y casos complejos.
OBJETIVO_NIVEL = {
    "Inicial": "Instalar las bases: que todo el personal conozca las obligaciones y aplique "
               "los controles mínimos.",
    "Intermedio": "Aplicar los controles de forma consistente, con responsables, registros y "
                  "evidencias que resistan una auditoría.",
    "Avanzado": "Sostener la mejora continua: medir, auditar y resolver los casos complejos "
                "de la dimensión.",
}


def normalizar_impacto(valor: str | None) -> str:
    v = (valor or "").strip().lower()
    if v.startswith(("alt", "crít", "crit")):
        return "Alta"
    if v.startswith("med"):
        return "Media"
    if v.startswith("baj"):
        return "Baja"
    return "Sin clasificar"


def calcular_severidad(impacto_catalogo: str | None, estado: str,
                       impacto_control: str | None = None) -> tuple[str, str]:
    """(severidad, impacto). El catálogo manda; si no trae, se usa el del control."""
    crudo = impacto_catalogo if (impacto_catalogo or "").strip() else impacto_control
    impacto = normalizar_impacto(crudo)
    if (crudo or "").strip().lower().startswith(("crít", "crit")):
        return "Crítica", impacto
    if impacto == "Sin clasificar":
        return "Sin clasificar", impacto
    return MATRIZ_SEVERIDAD[impacto][estado], impacto


def nivel_por_puntaje(puntaje: float | None) -> str:
    p = puntaje or 0
    if p <= 50:
        return "Inicial"
    if p <= 75:
        return "Intermedio"
    return "Avanzado"


def nivel_madurez(puntaje: float | None) -> str:
    p = puntaje or 0
    if p <= 25:
        return "inicial"
    if p <= 50:
        return "en_desarrollo"
    if p <= 75:
        return "gestionado"
    return "optimizado"


ETIQUETA_MADUREZ = {
    "inicial": "Inicial",
    "en_desarrollo": "En desarrollo",
    "gestionado": "Gestionado",
    "optimizado": "Optimizado",
}


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


# --------------------------------------------------------------------- entradas
@dataclass(frozen=True)
class RutaCatalogo:
    """Ruta del catálogo formativo (tabla ruta_formativa)."""
    id: int
    nombre: str
    dominio: str | None = None
    nivel: str | None = None
    objetivo: str | None = None
    objetivos_especificos: tuple[str, ...] = ()
    contenidos: tuple[str, ...] = ()
    horas: int | None = None
    modalidad: str | None = None
    publico_objetivo: str | None = None

    @property
    def nivel_efectivo(self) -> str | None:
        """La columna nivel o, si falta, el sufijo del nombre ("… - Intermedio")."""
        if self.nivel in NIVELES:
            return self.nivel
        m = re.search(r"(inicial|intermedio|avanzado)\s*$", sin_tildes(self.nombre or ""))
        return m.group(1).capitalize() if m else None

    @property
    def dominio_efectivo(self) -> str | None:
        """La columna dominio o, si falta, el prefijo del nombre ("Protección de Datos - …")."""
        if self.dominio:
            return self.dominio
        if " - " in (self.nombre or ""):
            return self.nombre.rsplit(" - ", 1)[0].strip() or None
        return None


@dataclass(frozen=True)
class BrechaCatalogo:
    id: int
    codigo: str | None
    categoria: str | None
    comportamiento: str | None
    criticidad: str | None
    accion: str | None
    ruta: RutaCatalogo | None = None


@dataclass(frozen=True)
class RespuestaFila:
    """Una respuesta con su control y las brechas de catálogo que le corresponden."""
    id: int
    estado: str | None                         # estado efectivo (final ?? declarado)
    control_id: int | None = None
    control_codigo: str | None = None
    control_obligacion: str | None = None
    control_criticidad: str | None = None
    control_recomendacion: str | None = None
    control_dominio: str | None = None
    brecha_respuesta: BrechaCatalogo | None = None   # asignada a la respuesta (solo no cumplido)
    brecha_control: BrechaCatalogo | None = None     # la del control (sirve también para parciales)


@dataclass(frozen=True)
class DominioResultado:
    dominio_id: int | None
    nombre: str
    puntaje: float | None
    nivel_madurez: str | None
    controles: int | None = None


@dataclass(frozen=True)
class ComparativaDominio:
    dominio: str
    tu_puntaje: float | None
    promedio_industria: float | None
    muestras: int
    meta: float
    # HU-10: false = cohorte del rubro < K_ANONIMATO_MINIMO empresas (promedio oculto)
    cohorte_suficiente: bool = False


# --------------------------------------------------------------------- brechas
@dataclass(frozen=True)
class Brecha:
    respuesta_id: int
    prioridad: int
    codigo: str
    control_codigo: str | None
    dominio: str
    descripcion: str
    impacto: str
    severidad: str
    estado: str
    accion: str | None
    ruta: RutaCatalogo | None
    puntaje_dominio: float | None


def construir_brechas(filas: list[RespuestaFila], puntajes: dict[str, float] | None = None) -> list[Brecha]:
    """Brecha = respuesta no cumplida o parcial. Lista priorizada y numerada (1 = más urgente)."""
    puntajes = puntajes or {}
    previas = []
    for r in filas:
        if r.estado not in ESTADOS_BRECHA:
            continue
        cat = r.brecha_respuesta
        severidad, impacto = calcular_severidad(cat.criticidad if cat else None, r.estado, r.control_criticidad)
        dominio = (cat.categoria if cat and cat.categoria else None) or r.control_dominio or "Sin dominio"
        # HU-12 · mapeo al catálogo formativo: la brecha de la respuesta o, en parciales
        # (que no llevan brecha asignada), la del control.
        ruta = (cat.ruta if cat else None) or (r.brecha_control.ruta if r.brecha_control else None)
        previas.append(Brecha(
            respuesta_id=r.id, prioridad=0,
            codigo=(cat.codigo if cat and cat.codigo else None) or r.control_codigo or f"RESP-{r.id}",
            control_codigo=r.control_codigo,
            dominio=dominio,
            descripcion=(cat.comportamiento if cat and cat.comportamiento else None)
            or r.control_obligacion
            or (r.brecha_control.comportamiento if r.brecha_control else None)
            or "Control no cumplido sin brecha de catálogo asociada.",
            impacto=impacto, severidad=severidad, estado=r.estado,
            accion=(cat.accion if cat and cat.accion else None) or r.control_recomendacion
            or (r.brecha_control.accion if r.brecha_control else None),
            ruta=ruta,
            puntaje_dominio=puntajes.get(dominio),
        ))

    def clave(b: Brecha):
        return (
            PESO_SEVERIDAD[b.severidad],
            0 if b.estado == NO_CUMPLIDO else 1,
            PESO_IMPACTO[b.impacto],
            b.puntaje_dominio if b.puntaje_dominio is not None else 101,
            sin_tildes(b.codigo),
        )

    ordenadas = sorted(previas, key=clave)
    return [replace(b, prioridad=i + 1) for i, b in enumerate(ordenadas)]


@dataclass(frozen=True)
class FiltrosBrechas:
    severidades: tuple[str, ...] = ()
    dominio: str | None = None
    estado: str | None = None
    texto: str = ""

    @property
    def activos(self) -> bool:
        return bool(self.severidades or self.dominio or self.estado or self.texto.strip())

    def describir(self) -> str:
        partes = []
        if self.severidades:
            partes.append(" + ".join(self.severidades))
        if self.dominio:
            partes.append(self.dominio)
        if self.estado:
            partes.append("No cumplidas" if self.estado == NO_CUMPLIDO else "Parciales")
        if self.texto.strip():
            partes.append(f"búsqueda «{self.texto.strip()}»")
        return " · ".join(partes) if partes else "Todas las brechas"


def parsear_filtros(severidad: str | None, dominio: str | None, estado: str | None,
                    q: str | None) -> FiltrosBrechas:
    """Mismos parámetros de URL que el panel (?severidad=Crítica,Alta&dominio=…&estado=…&q=…)."""
    pedidas = {s.strip() for s in (severidad or "").split(",")}
    return FiltrosBrechas(
        severidades=tuple(s for s in SEVERIDADES if s in pedidas),
        dominio=(dominio or "").strip()[:80] or None,
        estado=estado if estado in ESTADOS_BRECHA else None,
        texto=(q or "").strip()[:80],
    )


def filtrar_brechas(brechas: list[Brecha], f: FiltrosBrechas) -> list[Brecha]:
    q = sin_tildes(f.texto.strip())

    def coincide(b: Brecha) -> bool:
        texto = " ".join([b.codigo, b.descripcion, b.accion or "", b.ruta.nombre if b.ruta else "",
                          b.control_codigo or ""])
        return (
            (not f.severidades or b.severidad in f.severidades)
            and (not f.dominio or b.dominio == f.dominio)
            and (not f.estado or b.estado == f.estado)
            and (not q or q in sin_tildes(texto))
        )

    return [b for b in brechas if coincide(b)]


def contar_por_severidad(brechas: list[Brecha]) -> dict[str, int]:
    conteo = {s: 0 for s in SEVERIDADES}
    for b in brechas:
        conteo[b.severidad] += 1
    return conteo


# --------------------------------------------------------------------- HU-12 plan formativo
@dataclass
class BrechaCubierta:
    codigo: str
    control_codigo: str | None
    dominio: str
    severidad: str
    estado: str
    prioridad: int
    # HU-17/HU-26: respuesta de la brecha, para enlazarla con su remediación (subir evidencia)
    respuesta_id: int | None = None


@dataclass
class ModuloPlan:
    ruta: RutaCatalogo
    nivel: str
    motivo: str                    # "brechas" (lo activó una brecha) | "nivel" (base del nivel asignado)
    prioridad: str                 # peor severidad de sus brechas, o "Complementario"
    brechas: list[BrechaCubierta] = field(default_factory=list)


@dataclass
class DimensionPlan:
    dominio_id: int | None
    dominio: str
    puntaje: float | None
    nivel_madurez: str | None
    nivel_asignado: str
    objetivo_nivel: str
    brechas_dimension: int
    modulos: list[ModuloPlan] = field(default_factory=list)

    @property
    def horas(self) -> int:
        return sum(m.ruta.horas or 0 for m in self.modulos)


@dataclass
class PlanFormativo:
    dimensiones: list[DimensionPlan]
    brechas_total: int
    brechas_mapeadas: int
    brechas_sin_ruta: list[BrechaCubierta]

    @property
    def modulos(self) -> int:
        return sum(len(d.modulos) for d in self.dimensiones)

    @property
    def horas(self) -> int:
        return sum(d.horas for d in self.dimensiones)

    @property
    def cobertura(self) -> float:
        return round(100 * self.brechas_mapeadas / self.brechas_total, 1) if self.brechas_total else 100.0


def _clave_dominio(nombre: str | None) -> str:
    return sin_tildes((nombre or "").strip())


def construir_plan(brechas: list[Brecha], dominios: list[DominioResultado],
                   catalogo: list[RutaCatalogo]) -> PlanFormativo:
    """
    HU-12 · Plan de estudio recomendado por dimensión normativa.

    1. Mapeo automático: cada brecha activa la ruta formativa que el catálogo le asocia
       (catalogo_brechas.ruta_formativa_id). La ruta se agrupa en SU dimensión, que puede
       no ser la de la brecha (p. ej. ERR-DAT-002 -> Gestión de Riesgos - Intermedio).
    2. Nivel asignado por dimensión según su puntaje (nivel_por_puntaje). La ruta de ese
       nivel siempre entra como base ("nivel"), aunque ninguna brecha la haya activado.
    3. Orden: Inicial -> Intermedio -> Avanzado y, dentro del nivel, por severidad.
    """
    por_dominio = {_clave_dominio(d.nombre): d for d in dominios}
    dims: dict[str, DimensionPlan] = {}

    def dimension(nombre: str) -> DimensionPlan:
        k = _clave_dominio(nombre)
        if k not in dims:
            d = por_dominio.get(k)
            puntaje = d.puntaje if d else None
            nivel = nivel_por_puntaje(puntaje)
            dims[k] = DimensionPlan(
                dominio_id=d.dominio_id if d else None,
                dominio=d.nombre if d else nombre,
                puntaje=puntaje,
                nivel_madurez=(d.nivel_madurez or nivel_madurez(puntaje)) if d else None,
                nivel_asignado=nivel,
                objetivo_nivel=OBJETIVO_NIVEL[nivel],
                brechas_dimension=0,
            )
        return dims[k]

    for d in dominios:
        dimension(d.nombre)

    modulos: dict[int, tuple[DimensionPlan, ModuloPlan]] = {}
    sin_ruta: list[BrechaCubierta] = []
    mapeadas = 0
    for b in brechas:
        dimension(b.dominio).brechas_dimension += 1
        cubierta = BrechaCubierta(b.codigo, b.control_codigo, b.dominio, b.severidad, b.estado, b.prioridad,
                                  respuesta_id=b.respuesta_id)
        if b.ruta is None:
            sin_ruta.append(cubierta)
            continue
        mapeadas += 1
        if b.ruta.id not in modulos:
            dim = dimension(b.ruta.dominio_efectivo or b.dominio)
            nivel = b.ruta.nivel_efectivo or dim.nivel_asignado
            modulos[b.ruta.id] = (dim, ModuloPlan(ruta=b.ruta, nivel=nivel, motivo="brechas", prioridad=b.severidad))
        _, m = modulos[b.ruta.id]
        m.brechas.append(cubierta)
        if PESO_SEVERIDAD[b.severidad] < PESO_SEVERIDAD.get(m.prioridad, 99):
            m.prioridad = b.severidad

    # 2. Ruta base del nivel asignado en cada dimensión (si el catálogo la tiene)
    catalogo_por_dim_nivel = {
        (_clave_dominio(r.dominio_efectivo), r.nivel_efectivo): r for r in catalogo if r.nivel_efectivo
    }
    for k, dim in dims.items():
        base = catalogo_por_dim_nivel.get((k, dim.nivel_asignado))
        if base is not None and base.id not in modulos:
            modulos[base.id] = (dim, ModuloPlan(ruta=base, nivel=dim.nivel_asignado, motivo="nivel",
                                                prioridad="Complementario"))

    for dim, m in modulos.values():
        m.brechas.sort(key=lambda c: c.prioridad)
        dim.modulos.append(m)

    for dim in dims.values():
        dim.modulos.sort(key=lambda m: (PESO_NIVEL.get(m.nivel, 9), PESO_SEVERIDAD.get(m.prioridad, 9),
                                        sin_tildes(m.ruta.nombre)))

    # Dimensiones sin puntaje ni módulos (p. ej. la categoría "Sin dominio") no aportan nada
    visibles = [d for d in dims.values() if d.modulos or d.puntaje is not None]
    visibles.sort(key=lambda d: sin_tildes(d.dominio))
    return PlanFormativo(dimensiones=visibles, brechas_total=len(brechas), brechas_mapeadas=mapeadas,
                         brechas_sin_ruta=sin_ruta)


def plan_a_dict(plan: PlanFormativo) -> dict:
    """Respuesta JSON de GET /api/evaluaciones/{id}/plan-formativo."""
    def ruta(r: RutaCatalogo) -> dict:
        return {
            "id": r.id, "nombre": r.nombre, "dominio": r.dominio_efectivo, "nivel": r.nivel_efectivo,
            "objetivo": r.objetivo, "objetivos_especificos": list(r.objetivos_especificos),
            "contenidos": list(r.contenidos), "horas": r.horas, "modalidad": r.modalidad,
            "publico_objetivo": r.publico_objetivo,
        }

    def cubierta(c: BrechaCubierta) -> dict:
        return {"codigo": c.codigo, "control_codigo": c.control_codigo, "dominio": c.dominio,
                "severidad": c.severidad, "estado": c.estado, "prioridad": c.prioridad,
                "respuesta_id": c.respuesta_id}

    return {
        "resumen": {
            "dimensiones": len(plan.dimensiones),
            "modulos": plan.modulos,
            "horas": plan.horas,
            "brechas_total": plan.brechas_total,
            "brechas_mapeadas": plan.brechas_mapeadas,
            "cobertura_mapeo": plan.cobertura,
        },
        "brechas_sin_ruta": [cubierta(c) for c in plan.brechas_sin_ruta],
        "dimensiones": [
            {
                "dominio_id": d.dominio_id,
                "dominio": d.dominio,
                "puntaje": d.puntaje,
                "nivel_madurez": d.nivel_madurez,
                "nivel_asignado": d.nivel_asignado,
                "objetivo_nivel": d.objetivo_nivel,
                "brechas": d.brechas_dimension,
                "horas": d.horas,
                "modulos": [
                    {"nivel": m.nivel, "motivo": m.motivo, "prioridad": m.prioridad, "ruta": ruta(m.ruta),
                     "brechas": [cubierta(c) for c in m.brechas]}
                    for m in d.modulos
                ],
            }
            for d in plan.dimensiones
        ],
    }
