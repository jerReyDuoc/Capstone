"""
Lee de la BD todo lo que necesitan los informes y lo entrega como las dataclasses de
analisis.py (la lógica no toca la BD).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.application.informes.analisis import (
    BrechaCatalogo,
    ComparativaDominio,
    DominioResultado,
    RespuestaFila,
    RutaCatalogo,
)
from app.core.config import settings
from app.domain.models.benchmark import Benchmark
from app.domain.models.catalogo_brechas import CatalogoBrechas
from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.usuario_temporal import UsuarioTemporal


class SinResultadosError(Exception):
    """La evaluación no existe o todavía no tiene resumen (no se ha completado)."""


@dataclass(frozen=True)
class DatosEvaluacion:
    evaluacion_id: int
    fecha_inicio: date | None
    estado: str | None
    rubro: str | None
    puntaje_general: float
    controles_evaluados: int
    en_revision: int
    dominios: list[DominioResultado]
    respuestas: list[RespuestaFila]
    rutas: list[RutaCatalogo]
    comparativa: list[ComparativaDominio]
    email_registrado: str | None
    # HU-21: identificación del informe (con valores por defecto para no romper a quien ya
    # construye DatosEvaluacion a mano, p. ej. las pruebas del tutor)
    fecha_completado: datetime | None = None
    version_matriz: str | None = None          # la que quedó registrada al completar
    version_matriz_actual: str | None = None   # la de hoy (respaldo de las evaluaciones antiguas)
    aviso_aceptado_version: str | None = None
    aviso_aceptado_fecha: datetime | None = None
    dimensiones_catalogo: tuple[str, ...] = ()


async def version_matriz_vigente(db: AsyncSession) -> str:
    """
    HU-21 · "<MATRIZ_VERSION>+<huella>" de la matriz de controles tal como está ahora en la BD.
    POST /completar la guarda en la evaluación, así el informe dice con qué matriz se calculó.

    HU-24: si hay una versión publicada (mantenedor de la matriz), es su version_texto
    ("<etiqueta del admin>+<huella>"). Sin versiones guardadas, el cálculo de HU-21.
    """
    from app.application.informes.ficha import huella_matriz, version_matriz
    from app.domain.models.matriz_version import ESTADO_PUBLICADA, MatrizVersion

    texto = (await db.execute(
        select(MatrizVersion.version_texto).where(MatrizVersion.estado == ESTADO_PUBLICADA)
    )).scalar_one_or_none()
    if texto:
        return texto

    filas = (await db.execute(select(
        MatrizControl.id_control, MatrizControl.codigo_control, MatrizControl.dominio_id,
        MatrizControl.pregunta_evaluacion, MatrizControl.aplicabilidad, MatrizControl.criticidad,
        MatrizControl.obligacion, MatrizControl.catalogo_brechas_id_brecha,
    ))).all()
    return version_matriz(settings.MATRIZ_VERSION, huella_matriz(tuple(f) for f in filas))


def _ruta(r: RutaFormativa | None, dominios: dict[int, str]) -> RutaCatalogo | None:
    if r is None:
        return None
    return RutaCatalogo(
        id=r.id, nombre=r.nombre or f"Ruta {r.id}",
        dominio=dominios.get(r.dominio_id) if r.dominio_id else None,
        nivel=r.nivel, objetivo=r.objetivo,
        objetivos_especificos=r.lista_objetivos, contenidos=r.lista_contenidos,
        horas=r.horas, modalidad=r.modalidad, publico_objetivo=r.publico_objetivo,
    )


def _ruta_de_version(r: dict, dominios: dict[int, str]) -> RutaCatalogo:
    """HU-24: la misma ruta, leída del contenido de la versión de la matriz."""
    from app.domain.models.ruta_formativa import _lineas

    return RutaCatalogo(
        id=int(r["id"]), nombre=r.get("nombre") or f"Ruta {r['id']}",
        dominio=dominios.get(r["dominio_id"]) if r.get("dominio_id") else None,
        nivel=r.get("nivel"), objetivo=r.get("objetivo"),
        objetivos_especificos=_lineas(r.get("objetivos_especificos")), contenidos=_lineas(r.get("contenidos")),
        horas=r.get("horas"), modalidad=r.get("modalidad"), publico_objetivo=r.get("publico_objetivo"),
    )


def _brecha_de_version(b: dict, rutas: dict[int, RutaCatalogo]) -> BrechaCatalogo:
    return BrechaCatalogo(
        id=int(b["id"]), codigo=b.get("codigo_brecha"), categoria=b.get("categoria"),
        comportamiento=b.get("comportamiento_detectado"), criticidad=b.get("criticidad"),
        accion=b.get("accion_sistema"),
        ruta=rutas.get(b["ruta_formativa_id"]) if b.get("ruta_formativa_id") else None,
    )


def _control_de_version(c: dict, dominios: dict[int, str]) -> SimpleNamespace:
    """Objeto con los atributos que lee cargar_evaluacion() de un MatrizControl."""
    dominio_id = c.get("dominio_id")
    return SimpleNamespace(
        id_control=int(c["id"]), codigo_control=c.get("codigo_control"), obligacion=c.get("obligacion"),
        criticidad=c.get("criticidad"), recomendacion=c.get("recomendacion"),
        catalogo_brechas_id_brecha=c.get("brecha_id"), dominio_id=dominio_id,
        dominio=SimpleNamespace(nombre_dominio=dominios.get(dominio_id)) if dominio_id else None,
    )


def _brecha(b: CatalogoBrechas | None, rutas: dict[int, RutaCatalogo]) -> BrechaCatalogo | None:
    if b is None:
        return None
    return BrechaCatalogo(
        id=b.id_brecha, codigo=b.codigo_brecha, categoria=b.categoria,
        comportamiento=b.comportamiento_detectado, criticidad=b.criticidad, accion=b.accion_sistema,
        ruta=rutas.get(b.ruta_formativa_id) if b.ruta_formativa_id else None,
    )


async def cargar_evaluacion(db: AsyncSession, evaluacion_id: int) -> DatosEvaluacion:
    evaluacion = await db.get(Evaluacion, evaluacion_id)
    if evaluacion is None:
        raise SinResultadosError("Evaluación no encontrada")

    filas_resumen = (await db.execute(
        select(Resumen, Dominio).join(Dominio, Resumen.dominio_id == Dominio.id)
        .where(Resumen.evaluacion_id == evaluacion_id)
    )).all()
    if not filas_resumen:
        raise SinResultadosError("La evaluación todavía no tiene resultados: complétala primero.")

    nombres_dominio = {d.id: d.nombre_dominio or f"Dominio {d.id}"
                       for d in (await db.execute(select(Dominio))).scalars().all()}

    dominios = [
        DominioResultado(dominio_id=d.id, nombre=d.nombre_dominio or f"Dominio {d.id}",
                         puntaje=r.puntaje_obtenido, nivel_madurez=r.nivel_madurez,
                         controles=r.total_controles_evaluados)
        for r, d in filas_resumen
    ]
    total = sum(d.controles or 0 for d in dominios)
    puntaje_general = (
        round(sum((d.puntaje or 0) * (d.controles or 0) for d in dominios) / total, 2) if total else 0.0
    )

    # Catálogo vigente en las tablas (respaldo para ids que la versión no tenga)
    rutas_orm = (await db.execute(select(RutaFormativa).order_by(RutaFormativa.id))).scalars().all()
    rutas = {r.id: _ruta(r, nombres_dominio) for r in rutas_orm}
    rutas_activas = {r.id for r in rutas_orm if getattr(r, "activo", True) is not False}
    brechas = {
        b.id_brecha: _brecha(b, rutas)
        for b in (await db.execute(select(CatalogoBrechas))).scalars().all()
    }
    controles = {
        c.id_control: c
        for c in (await db.execute(
            select(MatrizControl).options(selectinload(MatrizControl.dominio))
        )).scalars().all()
    }
    # HU-24 criterio 2: una evaluación respondida con una versión de la matriz se informa con
    # los textos, brechas y rutas de ESA versión, aunque el admin haya publicado otra después.
    if evaluacion.matriz_version_id:
        from app.infrastructure.cache.versiones_matriz import contenido_de_version

        contenido = await contenido_de_version(db, evaluacion.matriz_version_id)
        if contenido:
            for r in contenido.get("rutas", []):
                rutas[int(r["id"])] = _ruta_de_version(r, nombres_dominio)
            rutas_activas = {int(r["id"]) for r in contenido.get("rutas", []) if r.get("activo", True)}
            for b in contenido.get("brechas", []):
                brechas[int(b["id"])] = _brecha_de_version(b, rutas)
            for c in contenido.get("controles", []):
                controles[int(c["id"])] = _control_de_version(c, nombres_dominio)

    respuestas_orm = (await db.execute(
        select(Respuesta).where(Respuesta.evaluacion_id == evaluacion_id).order_by(Respuesta.id)
    )).scalars().all()
    respuestas: list[RespuestaFila] = []
    en_revision = 0
    for r in respuestas_orm:
        estado = r.estado_clasificacion_final or r.estado_clasificacion
        if estado == "requiere_revision":
            en_revision += 1
        c = controles.get(r.matriz_controles_id_control) if r.matriz_controles_id_control else None
        respuestas.append(RespuestaFila(
            id=r.id, estado=estado,
            control_id=c.id_control if c else None,
            control_codigo=c.codigo_control if c else None,
            control_obligacion=c.obligacion if c else None,
            control_criticidad=c.criticidad if c else None,
            control_recomendacion=c.recomendacion if c else None,
            control_dominio=(c.dominio.nombre_dominio if c and c.dominio else None),
            brecha_respuesta=brechas.get(r.catalogo_brechas_id_brecha) if r.catalogo_brechas_id_brecha else None,
            brecha_control=brechas.get(c.catalogo_brechas_id_brecha) if c and c.catalogo_brechas_id_brecha else None,
        ))

    usuario = await db.get(UsuarioTemporal, evaluacion.usuario_temporal_id) if evaluacion.usuario_temporal_id else None
    # HU-29: el rubro de la empresa cliente manda (la reevaluación no tiene usuario temporal)
    from app.application.use_cases.historial_empresa import rubro_id_de_evaluacion

    rubro_id = await rubro_id_de_evaluacion(db, evaluacion)
    rubro = await db.get(Rubro, rubro_id) if rubro_id else None
    # HU-10: el promedio del rubro sale con la supresión k-anónima (cohortes < k ocultas)
    from app.application.benchmark.sector import filas_del_rubro, publicar_fila

    bench = await filas_del_rubro(db, rubro_id)
    general_ok = publicar_fila(bench.get(None)).suficiente
    comparativa = []
    for d in dominios:
        pub = publicar_fila(bench.get(d.dominio_id)) if general_ok else publicar_fila(None)
        comparativa.append(ComparativaDominio(
            dominio=d.nombre, tu_puntaje=d.puntaje,
            promedio_industria=pub.promedio,
            muestras=pub.empresas or 0,
            meta=settings.META_CUMPLIMIENTO_PUNTAJE,
            cohorte_suficiente=pub.suficiente,
        ))

    return DatosEvaluacion(
        evaluacion_id=evaluacion_id, fecha_inicio=evaluacion.fecha_inicio, estado=evaluacion.estado_progreso,
        rubro=rubro.nombre_rubro if rubro else None,
        puntaje_general=puntaje_general, controles_evaluados=total, en_revision=en_revision,
        dominios=sorted(dominios, key=lambda d: d.nombre), respuestas=respuestas,
        # HU-24: el catálogo de rutas para el plan son las activas (de la versión, si la hay)
        rutas=[r for rid, r in sorted(rutas.items()) if r is not None and rid in rutas_activas],
        comparativa=sorted(comparativa, key=lambda c: c.dominio),
        email_registrado=usuario.email if usuario else None,
        fecha_completado=evaluacion.fecha_completado,
        version_matriz=evaluacion.version_matriz,
        version_matriz_actual=None if evaluacion.version_matriz else await version_matriz_vigente(db),
        aviso_aceptado_version=usuario.aviso_legal_version if usuario else None,
        aviso_aceptado_fecha=usuario.fecha_aceptacion_aviso if usuario else None,
        dimensiones_catalogo=tuple(sorted(nombres_dominio.values())),
    )


def referencia_suficiente(bm: Benchmark | None) -> bool:
    """HU-10: el promedio del rubro solo se muestra con K_ANONIMATO_MINIMO empresas o más."""
    from app.application.benchmark.sector import publicar_fila

    return publicar_fila(bm).suficiente
