"""
HU-36 (base de HU-38) · Matriz de riesgos de las actividades del registro.

Cada actividad recibe un riesgo INHERENTE en una matriz de 5 × 5 (probabilidad × impacto), calculado
solo con lo que ya dice el registro (sin preguntar nada nuevo). Es determinista: la misma actividad
da siempre el mismo resultado, así el PDF, la planilla y el panel dicen lo mismo.

  Impacto (1–5)       qué tan grave sería para las personas un incidente o un uso indebido:
                      datos sensibles, de niños, niñas y adolescentes, decisiones automatizadas o
                      perfilamiento y cuántos grupos de personas abarca.
  Probabilidad (1–5)  qué tan expuesta está la actividad: transferencias internacionales (con o sin
                      garantía), terceros que tratan datos sin contrato, pocas medidas de seguridad,
                      decisiones automatizadas sin revisión humana, información incompleta y
                      fuentes de terceros o de acceso público.

  nivel = probabilidad × impacto     1–4 Bajo · 5–9 Medio · 10–14 Alto · 15–25 Crítico

Metodología ORIENTATIVA (inspirada en ISO 31000 e ISO/IEC 27005, y en los criterios de alto riesgo de
la Ley N.º 21.719). Los pesos viven en este archivo para que HU-38 (matriz de riesgos editable) los
ajuste o permita que la empresa registre su propia valoración y el riesgo residual sin tocar el
resto del informe. Cada factor trae su explicación y un tratamiento sugerido.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat

ESCALA = (1, 2, 3, 4, 5)
NIVELES = ("Bajo", "Medio", "Alto", "Crítico")
_UMBRALES = ((4, "Bajo"), (9, "Medio"), (14, "Alto"), (25, "Crítico"))

ETIQUETA_PROBABILIDAD = {1: "Muy baja", 2: "Baja", 3: "Media", 4: "Alta", 5: "Muy alta"}
ETIQUETA_IMPACTO = {1: "Muy bajo", 2: "Bajo", 3: "Moderado", 4: "Alto", 5: "Muy alto"}

METODOLOGIA = (
    "Riesgo inherente = probabilidad × impacto, en una escala de 1 a 5 cada uno. El impacto sube con los datos "
    "sensibles, los de niños, niñas y adolescentes, las decisiones automatizadas y la cantidad de grupos de "
    "personas. La probabilidad sube con las transferencias internacionales, los terceros sin contrato, las pocas "
    "medidas de seguridad, las decisiones sin revisión humana y la información incompleta. Es una valoración "
    "orientativa calculada con lo que registró la empresa: no reemplaza una evaluación de impacto en protección "
    "de datos cuando la ley la exige."
)

# Medidas que se esperan como mínimo cuando hay datos sensibles
_MEDIDAS_CLAVE_SENSIBLES = ("cifrado_reposo", "cifrado_transito", "control_acceso")
MIN_MEDIDAS = 3


@dataclass(frozen=True)
class Factor:
    eje: str            # "probabilidad" | "impacto"
    puntos: int
    titulo: str
    detalle: str
    tratamiento: str

    def como_dict(self) -> dict:
        return {"eje": self.eje, "puntos": self.puntos, "titulo": self.titulo, "detalle": self.detalle,
                "tratamiento": self.tratamiento}


@dataclass(frozen=True)
class RiesgoActividad:
    actividad_id: int
    nombre: str
    probabilidad: int
    impacto: int
    factores: tuple[Factor, ...] = field(default_factory=tuple)

    @property
    def puntaje(self) -> int:
        return self.probabilidad * self.impacto

    @property
    def nivel(self) -> str:
        return nivel_de(self.puntaje)

    @property
    def tratamientos(self) -> list[str]:
        vistos: list[str] = []
        for f in sorted(self.factores, key=lambda x: -x.puntos):
            if f.tratamiento and f.tratamiento not in vistos:
                vistos.append(f.tratamiento)
        return vistos

    def como_dict(self) -> dict:
        return {
            "actividad_id": self.actividad_id, "nombre": self.nombre, "probabilidad": self.probabilidad,
            "probabilidad_nombre": ETIQUETA_PROBABILIDAD[self.probabilidad], "impacto": self.impacto,
            "impacto_nombre": ETIQUETA_IMPACTO[self.impacto], "puntaje": self.puntaje, "nivel": self.nivel,
            "factores": [f.como_dict() for f in self.factores], "tratamientos": self.tratamientos,
        }


def nivel_de(puntaje: int) -> str:
    for tope, nombre in _UMBRALES:
        if puntaje <= tope:
            return nombre
    return NIVELES[-1]


def _acotar(v: int) -> int:
    return max(1, min(5, v))


def evaluar(actividad_id: int, nombre: str, contenido: dict, mapa: dict, faltantes: int = 0) -> RiesgoActividad:
    """
    `contenido`: lo que escribió la empresa (rat.modelo.completar). `mapa`: lo que la actividad toma del
    mapa (las listas de rat.analisis.derivados o de la instantánea de una versión vigente).
    `faltantes`: campos obligatorios vacíos (0 en una versión vigente).
    """
    factores: list[Factor] = []
    tipos = mapa.get("tipos_datos") or []
    titulares = mapa.get("titulares") or []
    sensibles = [t for t in tipos if t.get("sensible") or cat_mapa.es_sensible(t.get("codigo", ""))]
    nna = any(t.get("nna") or t.get("codigo") in cat_mapa.CODIGOS_TITULARES_NNA for t in titulares)
    decisiones = contenido.get("decisiones") or {}
    medidas = set((contenido.get("medidas") or {}).get("codigos") or [])
    otras_medidas = bool((contenido.get("medidas") or {}).get("otras"))
    transferencias = mapa.get("transferencias") or []
    terceros = mapa.get("terceros") or []

    # ------------------------------------------------------------ impacto
    if sensibles:
        factores.append(Factor(
            "impacto", 2, "Datos sensibles",
            "Usa " + ", ".join(t.get("nombre") or cat_mapa.nombre_dato(t["codigo"]) for t in sensibles[:4])
            + ("…" if len(sensibles) > 4 else "") + ": su exposición puede causar discriminación o un daño grave.",
            "Limita el acceso a quien lo necesite, cifra estos datos y verifica la base que permite tratarlos."))
    if nna:
        factores.append(Factor(
            "impacto", 1, "Niños, niñas y adolescentes",
            "Incluye datos de menores de 18 años, que la ley protege de forma reforzada.",
            "Aplica el interés superior del niño, minimiza los datos y verifica la autorización de sus representantes."))
    if decisiones.get("existe"):
        factores.append(Factor(
            "impacto", 1 + int(bool(decisiones.get("perfilamiento"))),
            "Decisiones automatizadas" + (" y perfilamiento" if decisiones.get("perfilamiento") else ""),
            "La actividad decide o arma perfiles de las personas sin intervención humana directa.",
            "Documenta la lógica, evalúa sesgos y ofrece a las personas una vía para pedir revisión humana."))
    if len(titulares) >= 4:
        factores.append(Factor(
            "impacto", 1, "Muchos grupos de personas",
            f"Abarca {len(titulares)} categorías de titulares: un incidente afectaría a muchas personas.",
            "Revisa si todos los grupos son necesarios para la finalidad (minimización)."))

    # ------------------------------------------------------------ probabilidad
    sin_garantia = [t for t in transferencias if not t.get("garantia_valida")]
    if sin_garantia:
        factores.append(Factor(
            "probabilidad", 2, "Transferencias internacionales sin garantía",
            f"{len(sin_garantia)} envío(s) fuera de Chile sin una garantía válida registrada "
            f"({', '.join(sorted({t.get('pais_nombre') or cat_mapa.nombre_pais(t.get('pais_destino')) for t in sin_garantia}))}).",
            "Registra una garantía para cada transferencia (país adecuado, cláusulas contractuales tipo o normas "
            "corporativas vinculantes) o deja de enviar esos datos."))
    elif transferencias:
        factores.append(Factor(
            "probabilidad", 1, "Transferencias internacionales",
            f"Los datos salen de Chile en {len(transferencias)} envío(s), aunque con garantía registrada.",
            "Revisa periódicamente que la garantía siga vigente y que el destinatario cumpla lo pactado."))
    sin_contrato = [t for t in terceros if t.get("rol_tercero") in cat_mapa.ROLES_CON_CONTRATO
                    and t.get("contrato_firmado") is not True]
    if sin_contrato:
        factores.append(Factor(
            "probabilidad", 1, "Terceros sin contrato de tratamiento",
            "Tratan datos por cuenta de tu empresa sin un contrato confirmado: "
            + ", ".join(t.get("nombre", "?") for t in sin_contrato[:4]) + ("…" if len(sin_contrato) > 4 else "") + ".",
            "Firma un contrato de tratamiento que fije finalidad, seguridad, confidencialidad y devolución de los datos."))
    total_medidas = len(medidas) + int(otras_medidas)
    faltan_clave = [m for m in _MEDIDAS_CLAVE_SENSIBLES if m not in medidas] if sensibles else []
    if total_medidas < MIN_MEDIDAS or faltan_clave:
        detalle = (f"Registra {total_medidas} medida(s) de seguridad" if total_medidas < MIN_MEDIDAS
                   else "Con datos sensibles faltan medidas básicas")
        if faltan_clave:
            detalle += " (faltan: " + ", ".join(cat.nombre(cat.MEDIDAS_POR_CODIGO, m).lower() for m in faltan_clave) + ")"
        factores.append(Factor(
            "probabilidad", 1, "Medidas de seguridad insuficientes", detalle + ".",
            "Refuerza las medidas técnicas (cifrado, control de accesos, respaldos) y organizativas (políticas, "
            "capacitación, procedimiento ante incidentes)."))
    if decisiones.get("existe") and decisiones.get("intervencion_humana") is not True:
        factores.append(Factor(
            "probabilidad", 1, "Sin revisión humana confirmada",
            "No está confirmado que una persona pueda revisar las decisiones automatizadas.",
            "Define quién revisa las decisiones cuando una persona lo pide y en qué plazo."))
    if faltantes:
        factores.append(Factor(
            "probabilidad", 1, "Información incompleta",
            f"Faltan {faltantes} dato(s) obligatorio(s) del registro: lo que no está documentado no se controla.",
            "Completa la actividad y déjala vigente."))
    fuentes = {f.get("tipo") for f in contenido.get("fuentes") or []}
    if fuentes & {"terceros", "acceso_publico"}:
        factores.append(Factor(
            "probabilidad", 1, "Datos que vienen de otras fuentes",
            "Parte de los datos no los entrega la propia persona (otra organización o una fuente de acceso público).",
            "Verifica que la fuente sea lícita e informa a las personas de dónde obtuviste sus datos."))

    impacto = _acotar(1 + sum(f.puntos for f in factores if f.eje == "impacto"))
    probabilidad = _acotar(1 + sum(f.puntos for f in factores if f.eje == "probabilidad"))
    return RiesgoActividad(actividad_id, nombre, probabilidad, impacto, tuple(factores))


# ============================================================ agregados
def mapa_calor(riesgos: list[RiesgoActividad]) -> list[list[int]]:
    """Conteo por celda: filas = probabilidad 5→1 (de arriba abajo), columnas = impacto 1→5."""
    celdas = [[0] * 5 for _ in range(5)]
    for r in riesgos:
        celdas[5 - r.probabilidad][r.impacto - 1] += 1
    return celdas


def conteo_niveles(riesgos: list[RiesgoActividad]) -> dict[str, int]:
    salida = {n: 0 for n in NIVELES}
    for r in riesgos:
        salida[r.nivel] += 1
    return salida


def ordenar(riesgos: list[RiesgoActividad]) -> list[RiesgoActividad]:
    """Del más grave al más leve (a igual puntaje, el de mayor impacto primero)."""
    return sorted(riesgos, key=lambda r: (-r.puntaje, -r.impacto, r.nombre.lower()))
