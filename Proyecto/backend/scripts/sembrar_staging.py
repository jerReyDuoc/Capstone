"""
HU-23 · Datos semilla del ambiente de staging (piloto con usuarios reales, HU-14).

Deja la plataforma lista para que un usuario del piloto vea algo útil desde el primer día:

  1. Un ADMINISTRADOR (admin_therion) creado sin pedir nada por teclado: el correo y la
     contraseña vienen de las variables SEMILLA_ADMIN_EMAIL y SEMILLA_ADMIN_PASSWORD
     (secretos del job "seed" en Azure; nunca en el código ni en la imagen).
  2. Evaluaciones COMPLETADAS de ejemplo, 100 % sintéticas (sin correos, nombres ni textos
     personales), repartidas en los primeros rubros del catálogo. Sirven para que la
     comparativa sectorial se publique: HU-10 la oculta mientras un rubro tenga menos de
     K_ANONIMATO_MINIMO organizaciones (5 en production).
  3. Recalcula el benchmark (lo mismo que el cron diario del worker).

Es IDEMPOTENTE: ejecutarlo dos veces no duplica nada. Las evaluaciones de ejemplo usan un
rango de IDs propio (desde 990001) y las que ya existen se saltan; el administrador que ya
existe no se toca (salvo --actualizar-clave).

Los catálogos (dominios, rubros, controles, filtro F1-F7, formación) NO los crea este script:
vienen en las migraciones de Alembic. Si faltan, el script se detiene y lo dice.

Uso (Docker local, desde Proyecto/):
    docker compose exec -e SEMILLA_ADMIN_EMAIL=admin@therionlabs.cl \
        -e SEMILLA_ADMIN_PASSWORD='una-clave-larga-y-unica' api python scripts/sembrar_staging.py

En Azure lo ejecuta el job "seed" (ver Proyecto/docs/DESPLIEGUE_STAGING.md).

Opciones:
    --rubros N            rubros que reciben evaluaciones de ejemplo (defecto 2)
    --por-rubro N         evaluaciones por rubro (defecto 10: alcanza también para la
                          mediana y los percentiles, K_ANONIMATO_DISTRIBUCION)
    --sin-evaluaciones    solo el administrador
    --actualizar-clave    si el administrador ya existe, le pone la contraseña de la variable
    --eliminar            borra las evaluaciones de ejemplo y recalcula el benchmark (úsalo
                          antes de medir los resultados reales del piloto). En el job de
                          Azure se pide con la variable SEMILLA_ACCION=eliminar.

Variables: SEMILLA_ADMIN_EMAIL, SEMILLA_ADMIN_PASSWORD, SEMILLA_RUBROS, SEMILLA_POR_RUBRO,
SEMILLA_ACCION (sembrar | eliminar).
"""
import argparse
import asyncio
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

ID_BASE = 990_000          # primer ID de ejemplo = ID_BASE + 1
ID_TOPE = ID_BASE + 9_999  # rango reservado para la semilla
MIN_PASSWORD = 12          # igual que app/core/crear_admin.py

# Texto neutro, sin datos personales (HU-06): justificación de los "parcialmente cumplido"
JUSTIFICACION_EJEMPLO = (
    "Dato de ejemplo del ambiente de pruebas: el control está implementado solo en parte."
)


class SemillaError(Exception):
    """Error con un mensaje pensado para quien ejecuta el job."""


@dataclass
class ResultadoSemilla:
    admin: str = "sin cambios"
    evaluaciones_creadas: int = 0
    evaluaciones_existentes: int = 0
    evaluaciones_eliminadas: int = 0
    rubros: list[str] = field(default_factory=list)
    benchmark: dict | None = None

    def lineas(self) -> list[str]:
        out = [f"Administrador: {self.admin}"]
        if self.rubros:
            out.append(f"Rubros con datos de ejemplo: {', '.join(self.rubros)}")
        out.append(f"Evaluaciones de ejemplo creadas: {self.evaluaciones_creadas}"
                   f" (ya existían: {self.evaluaciones_existentes})")
        if self.evaluaciones_eliminadas:
            out.append(f"Evaluaciones de ejemplo eliminadas: {self.evaluaciones_eliminadas}")
        if self.benchmark is not None:
            out.append(f"Benchmark recalculado: {self.benchmark}")
        return out


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- administrador
async def sembrar_admin(session, email: str | None, password: str | None,
                        actualizar_clave: bool = False, iteraciones: int | None = None) -> str:
    from app.core.autenticacion import hash_password
    from app.domain.models.usuario_admin import UsuarioAdmin

    if not email:
        return "no se pidió (SEMILLA_ADMIN_EMAIL vacía)"
    email = email.strip().lower()
    admin = (await session.execute(
        select(UsuarioAdmin).where(func.lower(UsuarioAdmin.email) == email)
    )).scalar_one_or_none()
    if admin is not None and not actualizar_clave:
        return f"{email} ya existe (sin cambios)"
    if not password or len(password) < MIN_PASSWORD:
        raise SemillaError(
            f"SEMILLA_ADMIN_PASSWORD debe tener al menos {MIN_PASSWORD} caracteres."
        )
    kwargs = {"iteraciones": iteraciones} if iteraciones else {}
    if admin is None:
        session.add(UsuarioAdmin(email=email, password_hash=hash_password(password, **kwargs),
                                 activo=True, fecha_creacion=_ahora()))
        accion = "creado"
    else:
        admin.password_hash = hash_password(password, **kwargs)
        admin.activo = True
        accion = "contraseña actualizada"
    await session.commit()
    return f"{email} {accion}"


# ---------------------------------------------------------------- evaluaciones de ejemplo
def _estado_para(rng: random.Random, madurez: float) -> str:
    """Estado declarado de un control según la 'madurez' de la organización ficticia."""
    r = rng.random()
    if r < 0.05:
        return "no_aplica"
    r = rng.random()
    if r < madurez * 0.75:
        return "cumplido"
    if r < madurez:
        return "parcialmente_cumplido"
    return "no_cumplido"


async def _verificar_catalogos(session) -> None:
    from app.domain.models.matriz_control import MatrizControl
    from app.domain.models.pregunta_filtro import PreguntaFiltro
    from app.domain.models.rubro import Rubro

    controles = (await session.execute(select(func.count()).select_from(MatrizControl))).scalar() or 0
    preguntas = (await session.execute(
        select(func.count()).select_from(PreguntaFiltro).where(PreguntaFiltro.activa.is_(True))
    )).scalar() or 0
    rubros = (await session.execute(select(func.count()).select_from(Rubro))).scalar() or 0
    if not (controles and preguntas and rubros):
        raise SemillaError(
            "La base de datos no tiene los catálogos (controles, preguntas del filtro o rubros). "
            "Ejecuta primero las migraciones: alembic upgrade head (job 'migrate')."
        )


async def _crear_evaluacion(session, ev_id: int, rubro_id: int) -> None:
    from app.application.filters.control_tree import get_controles_aplicables
    from app.application.informes.carga import version_matriz_vigente
    from app.application.use_cases.generate_resumen import GenerateResumenUseCase
    from app.core.config import settings
    from app.domain.models.evaluacion import ORIGEN_PUBLICA, Evaluacion
    from app.domain.models.matriz_control import MatrizControl
    from app.domain.models.matriz_version import ESTADO_PUBLICADA, MatrizVersion
    from app.domain.models.pregunta_filtro import PreguntaFiltro
    from app.domain.models.respuesta import EstadoClasificacion, FuenteClasificacion, Respuesta
    from app.domain.models.respuesta_filtro import RespuestaFiltro
    from app.domain.models.usuario_temporal import UsuarioTemporal
    from app.infrastructure.cache.arbol_aplicabilidad import arbol_vigente

    rng = random.Random(ev_id)  # determinista: misma semilla, mismos datos
    hoy = date.today()
    inicio = hoy - timedelta(days=rng.randint(3, 60))

    session.add(UsuarioTemporal(
        id=ev_id, email=None, rubro_id=rubro_id,
        fecha_expiracion=hoy + timedelta(days=365),
        aviso_legal_version=settings.AVISO_LEGAL_VERSION,
        fecha_aceptacion_aviso=_ahora(),
    ))
    await session.flush()
    evaluacion = Evaluacion(
        id=ev_id, fecha_inicio=inicio, estado_progreso="en_progreso",
        usuario_temporal_id=ev_id, filtro_completado=True, fecha_filtro=inicio,
        origen=ORIGEN_PUBLICA, es_prueba=False,
    )
    session.add(evaluacion)
    await session.flush()

    # Filtro F1-F7: las compuertas (F1 por defecto, HU-24) en SÍ y el resto al azar
    preguntas = (await session.execute(
        select(PreguntaFiltro).where(PreguntaFiltro.activa.is_(True)).order_by(PreguntaFiltro.orden)
    )).scalars().all()
    respuestas_filtro = {
        p.codigo: bool(getattr(p, "es_compuerta", False) or p.codigo == "F1" or rng.random() < 0.4)
        for p in preguntas
    }
    session.add_all([
        RespuestaFiltro(evaluacion_id=ev_id, pregunta_id=p.id_pregunta,
                        respuesta=respuestas_filtro[p.codigo], fecha_respuesta=inicio)
        for p in preguntas
    ])

    codigos = get_controles_aplicables(respuestas_filtro, await arbol_vigente(session))
    controles = (await session.execute(
        select(MatrizControl).where(MatrizControl.codigo_control.in_(codigos))
    )).scalars().all() if codigos else []
    madurez = rng.uniform(0.25, 0.9)
    for control in controles:
        estado = _estado_para(rng, madurez)
        r = Respuesta(
            evaluacion_id=ev_id,
            matriz_controles_id_control=control.id_control,
            estado_clasificacion=estado,
            estado_clasificacion_final=estado,
            fuente_clasificacion=FuenteClasificacion.USUARIO.value,
            justificacion_usuario=(
                JUSTIFICACION_EJEMPLO
                if EstadoClasificacion.requiere_justificacion(estado) else None
            ),
        )
        r.sincronizar_brecha(control)
        session.add(r)

    # Cierre igual que POST /completar: estado, fecha y versión de la matriz
    evaluacion.estado_progreso = "completada"
    evaluacion.fecha_completado = _ahora()
    vigente = (await session.execute(
        select(MatrizVersion.id, MatrizVersion.version_texto).where(MatrizVersion.estado == ESTADO_PUBLICADA)
    )).first()
    if vigente is not None:
        evaluacion.matriz_version_id, evaluacion.version_matriz = vigente
    else:
        evaluacion.version_matriz = await version_matriz_vigente(session)
    await session.flush()
    await GenerateResumenUseCase(session).execute(ev_id)  # hace el commit


async def sembrar_evaluaciones(session, rubros: int, por_rubro: int, resultado: ResultadoSemilla) -> None:
    from app.domain.models.evaluacion import Evaluacion
    from app.domain.models.rubro import Rubro

    if rubros < 1 or por_rubro < 1:
        return
    if rubros * por_rubro > ID_TOPE - ID_BASE:
        raise SemillaError("Demasiadas evaluaciones de ejemplo para el rango reservado.")
    await _verificar_catalogos(session)
    lista = (await session.execute(select(Rubro).order_by(Rubro.id).limit(rubros))).scalars().all()
    existentes = set((await session.execute(
        select(Evaluacion.id).where(Evaluacion.id.between(ID_BASE + 1, ID_TOPE))
    )).scalars().all())
    n = 0
    for rubro in lista:
        resultado.rubros.append(rubro.nombre_rubro or f"rubro {rubro.id}")
        for _ in range(por_rubro):
            n += 1
            ev_id = ID_BASE + n
            if ev_id in existentes:
                resultado.evaluaciones_existentes += 1
                continue
            await _crear_evaluacion(session, ev_id, rubro.id)
            resultado.evaluaciones_creadas += 1


async def eliminar_evaluaciones(session) -> int:
    from app.domain.models.evaluacion import Evaluacion
    from app.domain.models.respuesta import Respuesta
    from app.domain.models.respuesta_filtro import RespuestaFiltro
    from app.domain.models.resumen import Resumen
    from app.domain.models.usuario_temporal import UsuarioTemporal

    rango = (ID_BASE + 1, ID_TOPE)
    ids = list((await session.execute(
        select(Evaluacion.id).where(Evaluacion.id.between(*rango))
    )).scalars().all())
    if not ids:
        return 0
    # Orden de las claves foráneas. La semilla no crea evidencias, eventos ni solicitudes.
    await session.execute(delete(Resumen).where(Resumen.evaluacion_id.in_(ids)))
    await session.execute(delete(Respuesta).where(Respuesta.evaluacion_id.in_(ids)))
    await session.execute(delete(RespuestaFiltro).where(RespuestaFiltro.evaluacion_id.in_(ids)))
    await session.execute(delete(Evaluacion).where(Evaluacion.id.in_(ids)))
    await session.execute(delete(UsuarioTemporal).where(UsuarioTemporal.id.between(*rango)))
    await session.commit()
    return len(ids)


# ---------------------------------------------------------------- orquestación
async def ejecutar(session_factory, *, admin_email: str | None, admin_password: str | None,
                   rubros: int = 2, por_rubro: int = 10, actualizar_clave: bool = False,
                   eliminar: bool = False, iteraciones_hash: int | None = None) -> ResultadoSemilla:
    from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase

    resultado = ResultadoSemilla()
    async with session_factory() as session:
        if eliminar:
            resultado.evaluaciones_eliminadas = await eliminar_evaluaciones(session)
        else:
            resultado.admin = await sembrar_admin(session, admin_email, admin_password,
                                                  actualizar_clave, iteraciones_hash)
            await sembrar_evaluaciones(session, rubros, por_rubro, resultado)
    async with session_factory() as session:
        resultado.benchmark = await UpdateBenchmarkUseCase(session).execute()
    return resultado


async def _main(args) -> int:
    from app.core.database import AsyncSessionLocal, engine

    try:
        resultado = await ejecutar(
            AsyncSessionLocal,
            admin_email=os.getenv("SEMILLA_ADMIN_EMAIL") or None,
            admin_password=os.getenv("SEMILLA_ADMIN_PASSWORD") or None,
            rubros=0 if args.sin_evaluaciones else args.rubros,
            por_rubro=args.por_rubro,
            actualizar_clave=args.actualizar_clave,
            eliminar=args.eliminar,
        )
    except SemillaError as e:
        print(f"[semilla] ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    for linea in resultado.lineas():
        print(f"[semilla] {linea}")
    return 0


def _argumentos(argv=None):
    p = argparse.ArgumentParser(description="Datos semilla del ambiente de staging (HU-23).")
    p.add_argument("--rubros", type=int, default=int(os.getenv("SEMILLA_RUBROS", "2")))
    p.add_argument("--por-rubro", type=int, default=int(os.getenv("SEMILLA_POR_RUBRO", "10")))
    p.add_argument("--sin-evaluaciones", action="store_true")
    p.add_argument("--actualizar-clave", action="store_true")
    p.add_argument("--eliminar", action="store_true",
                   default=os.getenv("SEMILLA_ACCION", "sembrar").strip().lower() == "eliminar")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_argumentos())))
