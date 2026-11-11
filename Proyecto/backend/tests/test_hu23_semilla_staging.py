"""
HU-23 · Datos semilla del ambiente de staging (scripts/sembrar_staging.py).

Corre contra SQLite en memoria con los mismos catálogos mínimos que el resto de la suite
(_api_harness._sembrar). Verifica que la semilla:
  - crea el administrador sin pedir nada por teclado y no lo pisa en la segunda ejecución;
  - crea evaluaciones completadas, con resumen, sin datos personales;
  - deja el benchmark con k = evaluaciones por rubro (la comparativa se puede publicar);
  - es idempotente y se puede borrar con --eliminar.
"""
import asyncio

import pytest
from sqlalchemy import func, select

import _api_harness as h
from scripts import sembrar_staging as semilla


def _bd():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    import app.domain.models  # noqa: F401
    from app.core.database import Base

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})

    async def preparar():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        await h._sembrar(Session)
        from app.domain.models import Rubro
        async with Session() as s:
            s.add(Rubro(id=2, nombre_rubro="Salud"))
            await s.commit()
        return Session

    return engine, preparar


def _correr(coro_fn):
    async def _envoltura():
        from app.infrastructure.cache import arbol_aplicabilidad
        arbol_aplicabilidad.invalidar()
        engine, preparar = _bd()
        try:
            Session = await preparar()
            return await coro_fn(Session)
        finally:
            await engine.dispose()
    return asyncio.run(_envoltura())


async def _ejecutar(Session, **kw):
    params = dict(admin_email="Piloto@Therionlabs.cl", admin_password="clave-larga-del-piloto",
                  rubros=2, por_rubro=5, iteraciones_hash=1000)
    params.update(kw)
    return await semilla.ejecutar(Session, **params)


def test_crea_admin_evaluaciones_y_benchmark():
    async def caso(Session):
        from app.core.autenticacion import verificar_password
        from app.domain.models import Benchmark, Evaluacion, Resumen, UsuarioAdmin, UsuarioTemporal

        r = await _ejecutar(Session)
        assert r.evaluaciones_creadas == 10 and r.evaluaciones_existentes == 0
        assert "creado" in r.admin
        async with Session() as s:
            admin = (await s.execute(
                select(UsuarioAdmin).where(UsuarioAdmin.email == "piloto@therionlabs.cl")
            )).scalar_one()
            assert admin.activo and verificar_password("clave-larga-del-piloto", admin.password_hash)

            evals = (await s.execute(
                select(Evaluacion).where(Evaluacion.id > semilla.ID_BASE)
            )).scalars().all()
            assert len(evals) == 10
            assert all(e.estado_progreso == "completada" and not e.es_prueba for e in evals)
            assert all(e.fecha_completado is not None and e.version_matriz for e in evals)
            con_resumen = (await s.execute(
                select(func.count(func.distinct(Resumen.evaluacion_id)))
                .where(Resumen.evaluacion_id > semilla.ID_BASE)
            )).scalar()
            assert con_resumen == 10
            # Sin datos personales: los usuarios temporales de ejemplo no tienen correo
            temporales = (await s.execute(
                select(UsuarioTemporal).where(UsuarioTemporal.id > semilla.ID_BASE)
            )).scalars().all()
            assert len(temporales) == 10 and all(t.email is None for t in temporales)

            generales = (await s.execute(
                select(Benchmark).where(Benchmark.dominio_id.is_(None))
            )).scalars().all()
            assert {b.rubro_id for b in generales} == {1, 2}
            assert all(b.total_empresas == 5 for b in generales)
    _correr(caso)


def test_es_idempotente_y_no_pisa_la_clave():
    async def caso(Session):
        from app.core.autenticacion import verificar_password
        from app.domain.models import Evaluacion, Respuesta, UsuarioAdmin

        await _ejecutar(Session)
        async with Session() as s:
            respuestas_1 = (await s.execute(select(func.count()).select_from(Respuesta))).scalar()
        r2 = await _ejecutar(Session, admin_password="otra-clave-distinta-123")
        assert r2.evaluaciones_creadas == 0 and r2.evaluaciones_existentes == 10
        assert "sin cambios" in r2.admin
        async with Session() as s:
            assert (await s.execute(
                select(func.count()).select_from(Evaluacion).where(Evaluacion.id > semilla.ID_BASE)
            )).scalar() == 10
            assert (await s.execute(select(func.count()).select_from(Respuesta))).scalar() == respuestas_1
            admin = (await s.execute(select(UsuarioAdmin).where(
                UsuarioAdmin.email == "piloto@therionlabs.cl"))).scalar_one()
            assert verificar_password("clave-larga-del-piloto", admin.password_hash)

        r3 = await _ejecutar(Session, admin_password="otra-clave-distinta-123", actualizar_clave=True)
        assert "actualizada" in r3.admin
    _correr(caso)


def test_eliminar_borra_solo_los_datos_de_ejemplo():
    async def caso(Session):
        from app.domain.models import Benchmark, Evaluacion, UsuarioTemporal

        await _ejecutar(Session)
        r = await _ejecutar(Session, eliminar=True)
        assert r.evaluaciones_eliminadas == 10
        async with Session() as s:
            assert (await s.execute(
                select(func.count()).select_from(Evaluacion).where(Evaluacion.id > semilla.ID_BASE)
            )).scalar() == 0
            assert (await s.execute(
                select(func.count()).select_from(UsuarioTemporal).where(UsuarioTemporal.id > semilla.ID_BASE)
            )).scalar() == 0
            # Las evaluaciones del arnés (ids 1 y 2) siguen ahí
            assert (await s.execute(select(func.count()).select_from(Evaluacion))).scalar() == 2
            assert (await s.execute(select(func.count()).select_from(Benchmark))).scalar() == 0
    _correr(caso)


def test_clave_corta_se_rechaza_con_mensaje_claro():
    async def caso(Session):
        with pytest.raises(semilla.SemillaError, match="al menos 12"):
            await _ejecutar(Session, admin_password="corta")
    _correr(caso)


def test_sin_catalogos_pide_ejecutar_las_migraciones():
    async def caso(_Session):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import StaticPool

        from app.core.database import Base

        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                     connect_args={"check_same_thread": False})
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            vacia = async_sessionmaker(engine, expire_on_commit=False)
            with pytest.raises(semilla.SemillaError, match="migraciones"):
                await semilla.ejecutar(vacia, admin_email=None, admin_password=None,
                                       rubros=1, por_rubro=1)
        finally:
            await engine.dispose()
    _correr(caso)
