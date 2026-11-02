"""
HU-21 · Arma el informe de una evaluación a partir de lo que cargó carga.py.

Antes había dos copias de este armado (la descarga en routes/informes.py y "Mis documentos"
en documentos_empresa.py). Ahora hay una sola, así la descarga, el adjunto del correo, el
PDF archivado y la ficha que muestra el panel salen del mismo cálculo y llevan el mismo
código, la misma versión de matriz y la misma huella.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.application.informes.analisis import (
    SEVERIDADES,
    FiltrosBrechas,
    construir_brechas,
    construir_plan,
    contar_por_severidad,
    filtrar_brechas,
)
from app.application.informes.ficha import (
    AVISO_INFORME,
    FichaInforme,
    cinco_puntajes,
    codigo_evaluacion,
    huella_datos,
    huella_legible,
)
from app.application.informes.pdf_informe import DatosInforme, nombre_archivo

if TYPE_CHECKING:  # carga.py importa SQLAlchemy; aquí solo se leen sus atributos (lógica pura)
    from app.application.informes.carga import DatosEvaluacion


def construir_informe(datos: "DatosEvaluacion", filtros: FiltrosBrechas,
                      generado: datetime | None = None) -> DatosInforme:
    generado = generado or datetime.now(timezone.utc)
    puntajes_dom = {d.nombre: d.puntaje for d in datos.dominios if d.puntaje is not None}
    brechas = construir_brechas(datos.respuestas, puntajes_dom)
    plan = construir_plan(brechas, datos.dominios, datos.rutas)

    anio = (datos.fecha_inicio or (datos.fecha_completado.date() if datos.fecha_completado else None)
            or generado.date()).year
    codigo = codigo_evaluacion(datos.evaluacion_id, anio)
    registrada = bool(datos.version_matriz)
    version = datos.version_matriz or datos.version_matriz_actual or "sin registro"
    puntajes = cinco_puntajes(datos.puntaje_general, datos.controles_evaluados, datos.dominios,
                              datos.dimensiones_catalogo)
    ficha = FichaInforme(
        codigo=codigo, fecha_evaluacion=datos.fecha_inicio, fecha_completado=datos.fecha_completado,
        version_matriz=version, version_matriz_registrada=registrada, aviso=AVISO_INFORME,
        aviso_aceptado_version=datos.aviso_aceptado_version, aviso_aceptado_fecha=datos.aviso_aceptado_fecha,
        puntajes=puntajes, huella=huella_datos(codigo, version, puntajes, brechas, plan),
    )
    return DatosInforme(
        evaluacion_id=datos.evaluacion_id, rubro=datos.rubro, puntaje_general=datos.puntaje_general,
        controles_evaluados=datos.controles_evaluados, en_revision=datos.en_revision,
        comparativa=datos.comparativa, brechas_total=len(brechas),
        brechas=filtrar_brechas(brechas, filtros), filtros=filtros,
        plan=plan, generado=generado, ficha=ficha, brechas_completas=tuple(brechas),
    )


def _iso(v) -> str | None:
    return v.isoformat(timespec="seconds") if isinstance(v, datetime) else (v.isoformat() if v else None)


def ficha_a_dict(informe: DatosInforme) -> dict:
    """
    GET …/informe/ficha: lo que el PDF dice en su portada, en JSON. La página del panel lo
    muestra antes de descargar, y un auditor puede comparar la huella con la del papel.
    Sin códigos internos de controles ni de brechas (regla de interfaz del 29-10).
    """
    f = informe.ficha
    assert f is not None
    completas = list(informe.brechas_completas)
    por_sev = contar_por_severidad(completas)
    plan = informe.plan
    return {
        "evaluacion_id": informe.evaluacion_id,
        "codigo": f.codigo,
        "rubro": informe.rubro,
        "fecha_evaluacion": _iso(f.fecha_evaluacion),
        "fecha_completado": _iso(f.fecha_completado),
        "version_matriz": f.version_matriz,
        "version_matriz_registrada": f.version_matriz_registrada,
        "aviso_legal": {
            "version": f.aviso.version,
            "titulo": f.aviso.titulo,
            "parrafos": list(f.aviso.texto),
            "pie": f.aviso.pie,
            "aceptado_version": f.aviso_aceptado_version,
            "aceptado_fecha": _iso(f.aviso_aceptado_fecha),
        },
        "puntajes": [
            {"nombre": p.nombre, "puntaje": p.puntaje, "nivel": p.nivel, "preguntas": p.preguntas,
             "global": p.es_global}
            for p in f.puntajes
        ],
        "meta": informe.comparativa[0].meta if informe.comparativa else None,
        "brechas": {
            "total": len(completas),
            "por_severidad": {s: por_sev[s] for s in SEVERIDADES},
            # Las 3 más urgentes, para la vista previa (descripción, no el código interno)
            "principales": [
                {"prioridad": b.prioridad, "severidad": b.severidad, "dimension": b.dominio,
                 "descripcion": b.descripcion}
                for b in completas[:3]
            ],
        },
        "rutas": {
            "modulos": plan.modulos,
            "horas": plan.horas,
            "dimensiones": [
                {"dimension": d.dominio, "nivel": d.nivel_asignado, "modulos": len(d.modulos), "horas": d.horas}
                for d in plan.dimensiones
            ],
        },
        "en_revision": informe.en_revision,
        "huella": f.huella,
        "huella_corta": huella_legible(f.huella),
        "archivo": nombre_archivo(informe.evaluacion_id, informe.generado),
    }
