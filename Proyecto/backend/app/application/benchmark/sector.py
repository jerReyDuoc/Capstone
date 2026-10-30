"""
HU-10 · Lectura de la tabla benchmark aplicando la supresión k-anónima.

Todo lo que sale hacia la API, la interfaz o el informe PDF pasa por aquí: nadie más debe
leer promedio_puntaje / percentiles de Benchmark para mostrarlos.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.benchmark.k_anonimato import SUPRIMIDA, Publicacion, diferencia, posicion, publicar
from app.core.config import settings
from app.domain.models.benchmark import Benchmark

# Códigos de la advertencia que la interfaz muestra (criterio 3)
SIN_RUBRO = "SIN_RUBRO"
COHORTE_INSUFICIENTE = "COHORTE_INSUFICIENTE"
COHORTE_PARCIAL = "COHORTE_PARCIAL"


def publicar_fila(bm: Benchmark | None) -> Publicacion:
    """La publicación (o la supresión) de una fila del benchmark según la configuración."""
    if bm is None:
        return SUPRIMIDA
    return publicar(
        bm.total_empresas, bm.promedio_puntaje, bm.mediana_puntaje, bm.percentil_25, bm.percentil_75,
        k_minimo=settings.K_ANONIMATO_MINIMO, k_distribucion=settings.K_ANONIMATO_DISTRIBUCION,
    )


async def filas_del_rubro(db: AsyncSession, rubro_id: int | None) -> dict[int | None, Benchmark]:
    """{dominio_id: fila}; la clave None es el puntaje general del rubro."""
    if rubro_id is None:
        return {}
    filas = (await db.execute(select(Benchmark).where(Benchmark.rubro_id == rubro_id))).scalars().all()
    return {b.dominio_id: b for b in filas}


def advertencia(rubro_id: int | None, general: Publicacion, suprimidas: int, total: int) -> dict | None:
    """
    Qué advertir en la interfaz. No incluye cuántas empresas hay: solo el umbral.
    """
    k = settings.K_ANONIMATO_MINIMO
    if rubro_id is None:
        return {
            "codigo": SIN_RUBRO,
            "mensaje": "Esta evaluación no tiene un sector asociado, así que se compara solo con la meta.",
        }
    if not general.suficiente:
        return {
            "codigo": COHORTE_INSUFICIENTE,
            "mensaje": (f"Tu sector tiene menos de {k} empresas evaluadas. Para que nadie pueda deducir "
                        "el resultado de una empresa en particular, ocultamos el promedio sectorial "
                        "hasta que haya más."),
        }
    if suprimidas:
        return {
            "codigo": COHORTE_PARCIAL,
            "mensaje": (f"En {suprimidas} de {total} dimensiones hay menos de {k} empresas con puntaje, "
                        "por eso esas comparaciones están ocultas."),
        }
    return None


def bloque_sector(rubro_id: int | None, rubro_nombre: str | None, general_bm: Benchmark | None,
                  tu_puntaje: float | None, suprimidas: int, total: int) -> dict:
    """Resumen sectorial de la comparativa (puntaje general frente al rubro)."""
    pub = publicar_fila(general_bm) if rubro_id is not None else SUPRIMIDA
    return {
        "rubro_id": rubro_id,
        "rubro": rubro_nombre,
        "k_minimo": settings.K_ANONIMATO_MINIMO,
        **pub.como_dict(),
        "tu_puntaje": tu_puntaje,
        "diferencia": diferencia(tu_puntaje, pub),
        "posicion": posicion(tu_puntaje, pub),
        "dimensiones_publicadas": total - suprimidas,
        "dimensiones_suprimidas": suprimidas,
        "advertencia": advertencia(rubro_id, pub, suprimidas, total),
    }
