"""
Adaptadores de los informes: filtros de URL -> FiltrosBrechas y plan -> JSON.

La lógica pura (severidad, brechas, plan formativo) vive en app/domain/evaluacion/analisis_brechas.py.
"""
from __future__ import annotations

from app.domain.evaluacion.analisis_brechas import (
    ESTADOS_BRECHA,
    SEVERIDADES,
    BrechaCubierta,
    FiltrosBrechas,
    PlanFormativo,
    RutaCatalogo,
)


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
