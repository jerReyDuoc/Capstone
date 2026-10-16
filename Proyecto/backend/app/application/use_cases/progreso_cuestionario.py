"""
HU-01 — Progreso del cuestionario (controles respondidos / aplicables) para que el
Oficial de Cumplimiento pueda reanudarlo donde lo dejó.

Función pura: recibe el contexto de la evaluación, el catálogo de controles y las
filas (id_respuesta, id_control, estado, estado_final) de sus respuestas.
"""
from app.application.schemas.api_schemas import ProgresoCuestionarioResponse


def _pct(parte: int, total: int) -> float:
    return round(parte * 100 / total, 2) if total else 0.0


def _base(control) -> dict:
    return {
        "id_control": control.id_control,
        "codigo_control": control.codigo_control,
        "dominio_id": control.dominio_id,
        "dominio": control.dominio,
    }


def calcular_progreso(contexto, catalogo, filas) -> ProgresoCuestionarioResponse:
    aplicables = [catalogo.por_codigo[c] for c in contexto.codigos_aplicables if c in catalogo.por_codigo]
    ids_aplicables = {c.id_control for c in aplicables}

    por_control = {}
    fuera_de_alcance = 0
    for fila in filas:
        id_respuesta, id_control, estado, estado_final = tuple(fila)
        if id_control in ids_aplicables:
            por_control[id_control] = (id_respuesta, estado, estado_final)
        else:
            fuera_de_alcance += 1

    respondidos, pendientes = [], []
    dimensiones: dict[int | None, dict] = {}
    for control in aplicables:                       # orden: código de control
        dim = dimensiones.setdefault(control.dominio_id, {
            "dominio_id": control.dominio_id, "dominio": control.dominio,
            "aplicables": 0, "respondidos": 0,
        })
        dim["aplicables"] += 1
        if control.id_control in por_control:
            id_respuesta, estado, estado_final = por_control[control.id_control]
            dim["respondidos"] += 1
            respondidos.append({
                **_base(control), "id_respuesta": id_respuesta,
                "estado_clasificacion": estado, "estado_clasificacion_final": estado_final,
            })
        else:
            pendientes.append(_base(control))

    total, hechos = len(aplicables), len(respondidos)
    if contexto.cerrada:
        etapa = "cerrada"
    elif not contexto.filtro_completado:
        etapa = "filtro"
    elif pendientes:
        etapa = "cuestionario"
    else:
        etapa = "completo"

    return ProgresoCuestionarioResponse(
        evaluacion_id=contexto.id,
        estado_progreso=contexto.estado_progreso,
        cerrada=contexto.cerrada,
        filtro_completado=contexto.filtro_completado,
        etapa=etapa,
        controles_aplicables=total,
        controles_respondidos=hechos,
        controles_pendientes=total - hechos,
        porcentaje=_pct(hechos, total),
        respuestas_fuera_de_alcance=fuera_de_alcance,
        por_dimension=[
            {**d, "porcentaje": _pct(d["respondidos"], d["aplicables"])}
            for d in sorted(dimensiones.values(), key=lambda d: (d["dominio_id"] is None, d["dominio_id"] or 0))
        ],
        siguiente_control=pendientes[0] if pendientes and not contexto.cerrada else None,
        pendientes=pendientes,
        respondidos=respondidos,
    )
