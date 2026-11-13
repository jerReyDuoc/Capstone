"""
HU-38 · El registro de actividades alimenta el resto del cumplimiento (lógica PURA: sin BD).

Criterio 3 — el RAT como evidencia de los controles de protección de datos de la matriz:
  Un registro VIGENTE Y COMPLETO (al menos una actividad; todas las no archivadas vigentes, sin
  cambios del mapa pendientes de revisar y con los 13 campos completos; y ningún flujo del mapa sin
  actividad) aporta, para cada control de APORTES, el estado que demuestra. El caso de uso
  (app/application/use_cases/cumplimiento_rat.py) lo aplica SOLO si es mejor que el estado vigente
  del control: el registro nunca baja un control (misma regla que una evidencia de remediación).

  Control   Qué demuestra el registro                                         Estado que aporta
  DAT-005   Registro de actividades actualizado                               cumplido
  DAT-001   Base de licitud documentada en cada actividad                     cumplido
  DAT-003   Finalidades explícitas por actividad (falta informarlas: aviso)   parcialmente cumplido
  DAT-008   Toda transferencia internacional con una garantía válida          cumplido (si hay transferencias)
  DAT-007   Contrato confirmado con todos los terceros que lo requieren       cumplido o parcial (si hay terceros)
  DAT-009   Medidas clave en las actividades con datos sensibles o de NNA     parcialmente cumplido (si las hay)

  Los códigos son internos (nunca se muestran): el panel muestra la obligación del control.

Criterio 4 — brechas que genera el registro (lo que la empresa ve en su espacio):
  sin_base_licitud            una actividad no tiene base de licitud (o le falta la de los datos sensibles
                              o la descripción del interés legítimo)          → control DAT-001
  sin_plazo                   una categoría de datos sin plazo de conservación  → control DAT-005
  transferencia_sin_garantia  un envío fuera de Chile sin garantía válida       → control DAT-008
  flujo_sin_actividad         un flujo del mapa que ninguna actividad registra   → control DAT-005
Cada brecha trae el paso del formulario donde se corrige; el caso de uso le agrega su ruta de
remediación (módulo formativo del plan y su avance, y el control a re-evaluar).

PROPUESTA PARA VALIDAR CON EL PO: qué control cubre el registro y con qué estado vive en APORTES.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat

CUMPLIDO = "cumplido"
PARCIAL = "parcialmente_cumplido"
RANGO = {"no_cumplido": 0, "requiere_revision": 0, "parcialmente_cumplido": 1, "cumplido": 2}

# Medidas mínimas esperadas cuando la actividad trata datos sensibles o de NNA (como riesgos.py)
MEDIDAS_REFORZADAS = ("cifrado_reposo", "cifrado_transito", "control_acceso")


@dataclass(frozen=True)
class ActividadRegistro:
    """Lo que el caso de uso lee de cada actividad NO archivada (copia de trabajo y lo que toma del mapa)."""
    id: int
    nombre: str
    estado: str
    contenido: dict                  # rat.modelo.completar()
    derivados: dict                  # rat.analisis.derivados()
    completitud: dict                # rat.analisis.completitud()
    motivos_revision: tuple = ()


@dataclass(frozen=True)
class EstadoRegistro:
    activas: int
    vigentes: int
    completas: int
    en_revision: int
    borradores: int
    por_revisar: int                 # en revisión por un cambio en el mapa
    flujos_sin_actividad: int
    mapa_iniciado: bool

    @property
    def vigente_completo(self) -> bool:
        return (self.activas > 0 and self.vigentes == self.activas and self.completas == self.activas
                and self.por_revisar == 0 and self.flujos_sin_actividad == 0)

    def faltantes(self) -> list[str]:
        """Qué falta para que el registro cuente como evidencia (textos para la empresa)."""
        if not self.mapa_iniciado:
            return ["Registra tu mapa de datos: el registro de actividades se construye sobre él."]
        if self.activas == 0:
            return ["Registra al menos una actividad de tratamiento."]
        salida = []
        if self.vigentes < self.activas:
            n = self.activas - self.vigentes
            salida.append(f"Deja vigente{'s' if n > 1 else ''} {n} actividad{'es' if n > 1 else ''} "
                          f"(hoy {self.vigentes} de {self.activas} lo están).")
        if self.completas < self.activas:
            n = self.activas - self.completas
            salida.append(f"Completa los datos obligatorios de {n} actividad{'es' if n > 1 else ''}.")
        if self.por_revisar:
            salida.append(f"Revisa {self.por_revisar} actividad{'es' if self.por_revisar > 1 else ''} que cambiaron "
                          "por un cambio en el mapa de datos.")
        if self.flujos_sin_actividad:
            n = self.flujos_sin_actividad
            salida.append(f"Registra la actividad de {n} envío{'s' if n > 1 else ''} del mapa que no "
                          f"pertenece{'n' if n > 1 else ''} a ninguna actividad.")
        return salida


def estado_registro(actividades: list[ActividadRegistro], flujos_sin_actividad: int,
                    mapa_iniciado: bool) -> EstadoRegistro:
    return EstadoRegistro(
        activas=len(actividades),
        vigentes=sum(1 for a in actividades if a.estado == cat.VIGENTE),
        completas=sum(1 for a in actividades if a.completitud.get("puede_quedar_vigente")),
        en_revision=sum(1 for a in actividades if a.estado == cat.EN_REVISION),
        borradores=sum(1 for a in actividades if a.estado == cat.BORRADOR),
        por_revisar=sum(1 for a in actividades if a.estado == cat.EN_REVISION and a.motivos_revision),
        flujos_sin_actividad=flujos_sin_actividad,
        mapa_iniciado=mapa_iniciado,
    )


# ============================================================ criterio 3 · aportes del registro
@dataclass(frozen=True)
class Aporte:
    control: str                     # código interno de la matriz (no se muestra)
    estado: str                      # cumplido | parcialmente_cumplido
    motivo: str                      # qué demuestra el registro (texto para la empresa)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def aportes(estado: EstadoRegistro, actividades: list[ActividadRegistro]) -> list[Aporte]:
    """Lo que el registro demuestra, control por control. Vacío si no está vigente y completo."""
    if not estado.vigente_completo:
        return []
    n = _plural(len(actividades), "actividad vigente", "actividades vigentes")
    salida = [
        Aporte("DAT-005", CUMPLIDO, f"El registro de actividades está vigente y completo ({n}) y cubre todos los "
                                    "envíos del mapa de datos."),
        Aporte("DAT-001", CUMPLIDO, "Cada actividad del registro documenta su base de licitud y, cuando trata datos "
                                    "sensibles, la base que permite tratarlos."),
        Aporte("DAT-003", PARCIAL, "Cada actividad del registro documenta sus finalidades. Para cumplirlo por "
                                   "completo, infórmalas a las personas (aviso de privacidad)."),
    ]
    transferencias = {t.get("flujo_id"): t for a in actividades for t in a.derivados.get("transferencias") or []}
    if transferencias and all(t.get("garantia_valida") for t in transferencias.values()):
        salida.append(Aporte("DAT-008", CUMPLIDO,
                             f"Las {_plural(len(transferencias), 'transferencia', 'transferencias')} internacionales "
                             "del registro tienen una garantía válida."))
    terceros = {t["id"]: t for a in actividades for t in a.derivados.get("terceros") or []
                if t.get("rol_tercero") in cat_mapa.ROLES_CON_CONTRATO}
    if terceros:
        con_contrato = sum(1 for t in terceros.values() if t.get("contrato_firmado") is True)
        if con_contrato == len(terceros):
            salida.append(Aporte("DAT-007", CUMPLIDO, "Todos los terceros que tratan datos por cuenta de tu empresa "
                                                      "tienen su contrato confirmado en el mapa."))
        elif con_contrato:
            salida.append(Aporte("DAT-007", PARCIAL, f"{con_contrato} de {len(terceros)} terceros que tratan datos por "
                                                     "cuenta de tu empresa tienen su contrato confirmado."))
    especiales = [a for a in actividades if a.derivados.get("hay_sensibles") or a.derivados.get("incluye_nna")]
    if especiales and all(set(MEDIDAS_REFORZADAS) <= set((a.contenido.get("medidas") or {}).get("codigos") or [])
                          for a in especiales):
        salida.append(Aporte("DAT-009", PARCIAL, "Las actividades con datos sensibles o de niños, niñas y adolescentes "
                                                 "registran cifrado y control de accesos."))
    return salida


def mejora(actual: str | None, aportado: str) -> bool:
    """El registro solo puede MEJORAR un control (nunca lo baja ni toca un "no aplica")."""
    if actual not in RANGO:
        return False
    return RANGO[aportado] > RANGO[actual]


# ============================================================ criterio 4 · brechas del registro
SEVERIDAD = {"sin_base_licitud": "Alta", "transferencia_sin_garantia": "Alta", "sin_plazo": "Media",
             "flujo_sin_actividad": "Media"}
CONTROL_DE = {"sin_base_licitud": "DAT-001", "sin_plazo": "DAT-005", "transferencia_sin_garantia": "DAT-008",
              "flujo_sin_actividad": "DAT-005"}
TITULO = {"sin_base_licitud": "Actividad sin base de licitud", "sin_plazo": "Datos sin plazo de conservación",
          "transferencia_sin_garantia": "Transferencia internacional sin garantía",
          "flujo_sin_actividad": "Envío del mapa sin actividad"}
CODIGOS_BRECHA = tuple(SEVERIDAD)
_ORDEN_SEVERIDAD = {"Crítica": 0, "Alta": 1, "Media": 2, "Baja": 3}


def _brecha(codigo: str, texto: str, actividad: ActividadRegistro | None = None, paso: int | None = None,
            severidad: str | None = None, flujo_id: int | None = None) -> dict:
    return {
        "codigo": codigo, "titulo": TITULO[codigo], "texto": texto, "severidad": severidad or SEVERIDAD[codigo],
        "control": CONTROL_DE[codigo], "paso": paso,
        "actividad": {"id": actividad.id, "nombre": actividad.nombre} if actividad else None,
        "flujo_id": flujo_id,
    }


def brechas(actividades: list[ActividadRegistro], flujos_sin_actividad: list[dict] | None = None) -> list[dict]:
    """
    Brechas del registro ACTUAL. `flujos_sin_actividad`: [{id, nombre}] (rat.cobertura + nombres del mapa).
    Ordenadas de la más grave a la más leve.
    """
    salida: list[dict] = []
    for a in actividades:
        campos = a.completitud.get("campos") or {}
        especial = bool(a.derivados.get("hay_sensibles") or a.derivados.get("incluye_nna"))
        base = campos.get("base_licitud") or {}
        if not base.get("completo", True):
            salida.append(_brecha("sin_base_licitud", f"«{a.nombre}»: {base.get('faltante') or 'falta la base de licitud.'}",
                                  a, cat.CAMPOS_POR_CODIGO["base_licitud"].paso, "Crítica" if especial else None))
        conservacion = campos.get("conservacion") or {}
        if a.derivados.get("tipos_datos") and not conservacion.get("completo", True):
            salida.append(_brecha("sin_plazo", f"«{a.nombre}»: {conservacion.get('faltante') or 'falta el plazo.'}",
                                  a, cat.CAMPOS_POR_CODIGO["conservacion"].paso))
        sin_garantia = [t for t in a.derivados.get("transferencias") or [] if not t.get("garantia_valida")]
        if sin_garantia:
            paises = ", ".join(sorted({t.get("pais_nombre") or cat_mapa.nombre_pais(t.get("pais_destino"))
                                       for t in sin_garantia}))
            salida.append(_brecha("transferencia_sin_garantia",
                                  f"«{a.nombre}» envía datos fuera de Chile ({paises}) sin una garantía válida. "
                                  "Regístrala en el envío del mapa de datos.",
                                  a, cat.CAMPOS_POR_CODIGO["transferencias"].paso, "Crítica" if especial else None,
                                  flujo_id=sin_garantia[0].get("flujo_id")))
    for f in flujos_sin_actividad or []:
        salida.append(_brecha("flujo_sin_actividad",
                              f"El envío «{f.get('nombre', '?')}» del mapa no pertenece a ninguna actividad del registro.",
                              flujo_id=f.get("id")))
    return sorted(salida, key=lambda b: (_ORDEN_SEVERIDAD.get(b["severidad"], 9), CODIGOS_BRECHA.index(b["codigo"]),
                                         (b["actividad"] or {}).get("nombre", "").lower()))
