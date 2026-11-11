"""
HU-25 · Anonimización automática de usuarios temporales vencidos tras un plazo de retención
(Ley 21.719, principio de limitación de la conservación).

Ejecutar desde Proyecto/backend/ (en Docker):
    docker compose exec api pytest tests/test_hu25_retencion.py -v

  Criterio 1 — plazo configurable:
    - el plazo del panel manda sobre RETENCION_DATOS_TITULAR_DIAS; "entorno" vuelve a la
      variable y "desactivada" apaga la regla; límites y validaciones; cada cambio en el log.
  Criterio 2 — tarea programada que reutiliza la anonimización de ARCOP y conserva puntajes:
    - el worker registra la tarea en el cron (hora configurable) y como función encolable;
    - R1 llama a AnonimizacionRepository (la misma rutina de la supresión ARCOP);
    - el benchmark recalculado después de anonimizar es idéntico al de antes.
  Criterio 3 — cada ejecución queda en el audit log:
    - también sin nada que anonimizar, en simulación, omitida por otra en curso y con fallos.
  API del panel (/api/admin/retencion): solo admin, vista previa, simulación y ejecución encolada.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

import app.domain.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.autenticacion import Actor, Rol
from app.core.config import settings
from app.core.database import Base
from app.domain.models import AuditLog
from app.domain.models.benchmark import Benchmark
from app.domain.models.configuracion_retencion import ConfiguracionRetencion
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import EstadoValidacion, Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.usuario_temporal import UsuarioTemporal

HOY = date.today()
ADMIN = Actor(id=1, rol=Rol.ADMIN_THERION.value)


# ------------------------------------------------------------------ utilidades
def _con_bd(escenario):
    pytest.importorskip("aiosqlite")
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    async def _f():
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                     connect_args={"check_same_thread": False})
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as s:
            s.add(Rubro(id=1, nombre_rubro="Rubro"))
            await s.commit()
        try:
            await escenario(Session)
        finally:
            await engine.dispose()
    asyncio.run(_f())


async def _titular(s, uid, *, vence, email=None, puntaje=60.0):
    s.add(UsuarioTemporal(id=uid, email=email or f"titular{uid}@demo.cl", rubro_id=1,
                          fecha_expiracion=vence, validacion_invitacion="S"))
    s.add(Evaluacion(id=uid, usuario_temporal_id=uid, fecha_inicio=vence, estado_progreso="completada",
                     filtro_completado=True, origen="invitacion", es_prueba=False))
    s.add(Respuesta(id=uid, evaluacion_id=uid, estado_clasificacion="cumplido",
                    estado_clasificacion_final="cumplido", justificacion_usuario="Texto [RUT_ANON]"))
    s.add(Evidencia(id_evidencia=uid, respuesta_id=uid, nombre_archivo="acta.txt",
                    storage_path=f"/tmp/no-existe-hu25-{uid}.txt", mime_type="text/plain", hash_archivo="a" * 64,
                    estado_validacion=EstadoValidacion.VALIDATED.value, justificacion_llm="ok"))
    s.add(Resumen(evaluacion_id=uid, dominio_id=1, puntaje_obtenido=puntaje, nivel_madurez="definido",
                  total_controles_evaluados=10))
    await s.commit()


def _uc(s, **kw):
    from app.application.use_cases.aplicar_retencion import AplicarRetencionUseCase
    return AplicarRetencionUseCase(s, **kw)


async def _log(s, accion):
    return list((await s.execute(select(AuditLog).where(AuditLog.accion == accion).order_by(AuditLog.id)))
                .scalars().all())


@pytest.fixture
def sin_plazos_entorno(monkeypatch):
    """Las demás reglas apagadas y el plazo de titulares sin valor en el entorno."""
    for nombre in ("RETENCION_DATOS_TITULAR_DIAS", "RETENCION_ARCOP_CERRADAS_DIAS",
                   "RETENCION_EVENTOS_SEGURIDAD_DIAS", "TUTOR_RETENCION_DIAS"):
        monkeypatch.setattr(settings, nombre, None)


# ------------------------------------------------------------------ criterio 1
def test_plazo_del_panel_manda_sobre_el_entorno_y_cada_cambio_queda_en_el_log(sin_plazos_entorno, monkeypatch):
    from app.application.use_cases.configurar_retencion import actualizar_plazo, plazo_titular_vigente

    async def esc(Session):
        async with Session() as s:
            await _titular(s, 1, vence=HOY - timedelta(days=400))
            await _titular(s, 2, vence=HOY - timedelta(days=100))

            # Sin plazo en el entorno ni en el panel: la regla no se aplica
            p = await plazo_titular_vigente(s)
            assert (p.modo, p.dias, p.activa) == ("entorno", None, False)
            r = await _uc(s).execute()
            assert "titulares" in r.reglas_desactivadas and r.titulares == 0

            # El Oficial de Privacidad fija 365 días desde el panel
            p = await actualizar_plazo(s, ADMIN, modo="plazo", dias=365)
            assert (p.modo, p.dias, p.fuente) == ("plazo", 365, "panel")
            r = await _uc(s).execute()
            assert r.fuente_plazo_titular == "panel" and r.plazo_titular_dias == 365
            assert r.titulares == 1  # solo el vencido hace más de 365 días
            async with Session() as s2:  # sesión nueva: R1 actualiza con UPDATE directo
                assert (await s2.get(UsuarioTemporal, 1)).email is None
                assert (await s2.get(UsuarioTemporal, 2)).email == "titular2@demo.cl"

            # Repetir el mismo valor no ensucia el log
            await actualizar_plazo(s, ADMIN, modo="plazo", dias=365)
            # El panel manda aunque el entorno tenga otro valor
            monkeypatch.setattr(settings, "RETENCION_DATOS_TITULAR_DIAS", 30)
            assert (await plazo_titular_vigente(s)).dias == 365
            # "entorno" vuelve a la variable; "desactivada" apaga la regla aunque la variable exista
            assert (await actualizar_plazo(s, ADMIN, modo="entorno", dias=None)).dias == 30
            p = await actualizar_plazo(s, ADMIN, modo="desactivada", dias=None)
            assert (p.modo, p.dias) == ("desactivada", None)
            assert "titulares" in (await _uc(s).execute()).reglas_desactivadas

            cambios = await _log(s, "retencion.configuracion_cambiada")
            assert len(cambios) == 3
            assert cambios[0].actor_rol == "admin_therion" and cambios[0].actor_id == 1
            assert cambios[0].detalle["antes"]["modo"] == "entorno"
            assert cambios[0].detalle["despues"] == {"modo": "plazo", "fuente": "panel",
                                                     "plazo_titular_dias": 365, "activa": True}
            assert cambios[2].detalle["despues"]["modo"] == "desactivada"
    _con_bd(esc)


@pytest.mark.parametrize("modo,dias,codigo", [
    ("plazo", None, "PLAZO_INVALIDO"),
    ("plazo", 1, "PLAZO_INVALIDO"),          # bajo RETENCION_TITULAR_MIN_DIAS (30)
    ("plazo", 99_999, "PLAZO_INVALIDO"),     # sobre RETENCION_TITULAR_MAX_DIAS (3650)
    ("plazo", True, "PLAZO_INVALIDO"),
    ("borrar_todo", 365, "MODO_INVALIDO"),
])
def test_validacion_del_plazo(modo, dias, codigo):
    from app.application.use_cases.configurar_retencion import RetencionError, validar_cambio
    with pytest.raises(RetencionError) as e:
        validar_cambio(modo, dias)
    assert e.value.status == 422 and e.value.codigo == codigo


def test_config_valida_limites_hora_y_timeout():
    from app.core.config import Settings
    base = dict(DATABASE_URL="x", DATABASE_URL_SYNC="x", REDIS_URL="x", GROQ_API_KEY="x")
    s = Settings(_env_file=None, **base)
    assert (s.RETENCION_TITULAR_MIN_DIAS, s.RETENCION_TITULAR_MAX_DIAS, s.RETENCION_HORA_UTC) == (30, 3650, 3)
    for malo in ({"RETENCION_TITULAR_MIN_DIAS": 0}, {"RETENCION_TITULAR_MIN_DIAS": 500, "RETENCION_TITULAR_MAX_DIAS": 100},
                 {"RETENCION_HORA_UTC": 24}, {"RETENCION_TIMEOUT_S": 30},
                 {"RETENCION_TIMEOUT_S": 7200, "RETENCION_BLOQUEO_MAX_MIN": 60}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **base, **malo)


# ------------------------------------------------------------------ criterio 2
def test_worker_programa_la_tarea_y_la_permite_encolar():
    pytest.importorskip("arq")
    from app.worker.tasks import WorkerSettings, aplicar_retencion_task

    crons = [c for c in WorkerSettings.cron_jobs if c.coroutine is aplicar_retencion_task]
    assert len(crons) == 1
    assert crons[0].hour == settings.RETENCION_HORA_UTC and crons[0].minute == 0
    assert crons[0].timeout_s == settings.RETENCION_TIMEOUT_S
    encolables = [f for f in WorkerSettings.functions if getattr(f, "coroutine", f) is aplicar_retencion_task]
    assert encolables and encolables[0].timeout_s == settings.RETENCION_TIMEOUT_S


def test_reutiliza_la_anonimizacion_de_arcop(sin_plazos_entorno, monkeypatch):
    from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository

    llamadas = []
    original = AnonimizacionRepository.anonimizar_titular

    async def espia(self, usuario_id, ahora):
        llamadas.append(usuario_id)
        return await original(self, usuario_id, ahora)

    monkeypatch.setattr(AnonimizacionRepository, "anonimizar_titular", espia)

    async def esc(Session):
        async with Session() as s:
            await _titular(s, 7, vence=HOY - timedelta(days=400))
            r = await _uc(s, plazos={"titulares": 365, "arcop": None, "eventos": None}).execute()
            assert r.titulares == 1 and llamadas == [7]
        async with Session() as s:  # sesión nueva: la anonimización usa UPDATE directo
            u = await s.get(UsuarioTemporal, 7)
            assert u.email is None and u.validacion_invitacion is None and u.fecha_anonimizacion is not None
            assert (await s.get(Respuesta, 7)).justificacion_usuario is None
            assert (await s.get(Evidencia, 7)).nombre_archivo == "[anonimizado]"
            # registro por titular (T-06) con la regla y el plazo
            fila = (await _log(s, "retencion.titular_anonimizado"))[0]
            assert fila.entidad_id == 7 and fila.detalle["regla"] == "R1" and fila.detalle["plazo_dias"] == 365
    _con_bd(esc)


def test_conserva_puntajes_y_el_benchmark_no_cambia(sin_plazos_entorno):
    from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase

    async def foto(s):
        await UpdateBenchmarkUseCase(s).execute()
        await s.commit()
        filas = (await s.execute(select(Benchmark).order_by(Benchmark.rubro_id, Benchmark.dominio_id))).scalars().all()
        return [(b.rubro_id, b.dominio_id, b.promedio_puntaje, b.total_empresas, b.total_evaluaciones) for b in filas]

    async def esc(Session):
        async with Session() as s:
            for uid, puntaje in ((1, 40.0), (2, 55.0), (3, 70.0), (4, 85.0), (5, 90.0)):
                await _titular(s, uid, vence=HOY - timedelta(days=500), puntaje=puntaje)
            antes = await foto(s)
            assert antes  # hay comparativa del rubro
            r = await _uc(s, plazos={"titulares": 365, "arcop": None, "eventos": None}).execute()
            assert r.titulares == 5
        async with Session() as s:
            for uid in range(1, 6):
                assert (await s.get(UsuarioTemporal, uid)).email is None
                assert (await s.get(Respuesta, uid)).estado_clasificacion_final == "cumplido"
                assert (await s.execute(select(Resumen.puntaje_obtenido).where(Resumen.evaluacion_id == uid))
                        ).scalar_one() is not None
            assert await foto(s) == antes
    _con_bd(esc)


# ------------------------------------------------------------------ criterio 3
def test_cada_ejecucion_queda_en_el_log_aunque_no_haya_nada(sin_plazos_entorno):
    async def esc(Session):
        async with Session() as s:
            r1 = await _uc(s).execute()                 # cron, nada que hacer
            r2 = await _uc(s).execute(aplicar=False)    # simulación
            filas = await _log(s, "retencion.ejecucion")
            assert [f.id for f in filas] == [r1.ejecucion_id, r2.ejecucion_id]
            real, simulada = filas
            assert real.actor_rol == "sistema" and real.actor_id is None and real.resultado == "ok"
            assert real.ip.startswith("sistema:")
            d = real.detalle
            assert d["origen"] == "cron" and d["simulacion"] is False
            assert d["plazos_dias"]["titulares"] is None and d["fuente_plazo_titulares"] == "entorno"
            assert d["conteos"]["titulares"] == 0 and d["error"] is None and d["duracion_ms"] >= 0
            assert set(d["reglas_desactivadas"]) == {"titulares", "arcop", "eventos", "tutor"}
            assert simulada.detalle["simulacion"] is True
            # categoría "supresion": el Auditor Externo la ve al filtrar supresiones
            from app.infrastructure.repositories.bitacora_repository import categoria
            assert categoria("retencion.ejecucion") == "supresion"
            assert categoria("retencion.configuracion_cambiada") == "modificacion"
    _con_bd(esc)


def test_ejecucion_manual_registra_al_admin_y_la_fecha_de_corte(sin_plazos_entorno):
    async def esc(Session):
        async with Session() as s:
            await _titular(s, 3, vence=HOY - timedelta(days=400))
            r = await _uc(s, plazos={"titulares": 365, "arcop": None, "eventos": None},
                          origen="manual", actor=ADMIN).execute()
            fila = (await _log(s, "retencion.ejecucion"))[-1]
            assert fila.id == r.ejecucion_id and fila.actor_rol == "admin_therion" and fila.actor_id == 1
            assert fila.detalle["origen"] == "manual" and fila.detalle["conteos"]["titulares"] == 1
            assert fila.detalle["fecha_corte_titulares"] == (HOY - timedelta(days=365)).isoformat()
            assert "@" not in str(fila.detalle)  # nunca datos personales
    _con_bd(esc)


def test_dos_ejecuciones_a_la_vez_la_segunda_se_omite_y_queda_registrada(sin_plazos_entorno):
    from app.application.use_cases.configurar_retencion import asegurar_fila

    async def esc(Session):
        async with Session() as s:
            await _titular(s, 4, vence=HOY - timedelta(days=400))
            await asegurar_fila(s)
            en_curso = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
            await s.execute(update(ConfiguracionRetencion).values(ejecucion_desde=en_curso))
            await s.commit()

            r = await _uc(s, plazos={"titulares": 365, "arcop": None, "eventos": None}).execute()
            assert r.omitida_por_ejecucion_en_curso and r.titulares == 0
            assert (await s.get(UsuarioTemporal, 4)).email == "titular4@demo.cl"
            fila = (await _log(s, "retencion.ejecucion"))[-1]
            assert fila.resultado == "omitido" and fila.detalle["omitida_por_ejecucion_en_curso"] is True

            # Una marca abandonada (worker caído) no bloquea para siempre
            vieja = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=settings.RETENCION_BLOQUEO_MAX_MIN + 1)
            await s.execute(update(ConfiguracionRetencion).values(ejecucion_desde=vieja))
            await s.commit()
            r = await _uc(s, plazos={"titulares": 365, "arcop": None, "eventos": None}).execute()
            assert not r.omitida_por_ejecucion_en_curso and r.titulares == 1
            # al terminar, la marca se libera
            assert (await s.execute(select(ConfiguracionRetencion.ejecucion_desde))).scalar_one() is None
    _con_bd(esc)


def test_un_titular_que_falla_no_detiene_al_resto_y_la_ejecucion_queda_con_error(sin_plazos_entorno, monkeypatch):
    from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository

    original = AnonimizacionRepository.anonimizar_titular

    async def falla_con_el_5(self, usuario_id, ahora):
        if usuario_id == 5:
            raise RuntimeError("fallo simulado")
        return await original(self, usuario_id, ahora)

    monkeypatch.setattr(AnonimizacionRepository, "anonimizar_titular", falla_con_el_5)

    async def esc(Session):
        async with Session() as s:
            await _titular(s, 5, vence=HOY - timedelta(days=400))
            await _titular(s, 6, vence=HOY - timedelta(days=400))
            r = await _uc(s, plazos={"titulares": 365, "arcop": None, "eventos": None}).execute()
            assert r.titulares == 1 and r.titulares_fallidos == 1
        async with Session() as s:
            assert (await s.get(UsuarioTemporal, 5)).fecha_anonimizacion is None  # se reintenta mañana
            assert (await s.get(UsuarioTemporal, 6)).fecha_anonimizacion is not None
            fila = (await _log(s, "retencion.ejecucion"))[-1]
            assert fila.resultado == "error" and fila.detalle["conteos"]["titulares_fallidos"] == 1
            assert (await s.execute(select(ConfiguracionRetencion.ejecucion_desde))).scalar_one() is None
    _con_bd(esc)


def test_una_ejecucion_que_se_cae_igual_queda_registrada_y_libera_la_marca(sin_plazos_entorno, monkeypatch):
    from app.application.use_cases.aplicar_retencion import AplicarRetencionUseCase

    async def revienta(self, limite, aplicar, r):
        raise ConnectionError("BD caída")

    monkeypatch.setattr(AplicarRetencionUseCase, "_titulares", revienta)

    async def esc(Session):
        async with Session() as s:
            with pytest.raises(ConnectionError):
                await _uc(s, plazos={"titulares": 365, "arcop": None, "eventos": None}).execute()
            fila = (await _log(s, "retencion.ejecucion"))[-1]
            assert fila.resultado == "error" and fila.detalle["error"] == "ConnectionError"
            assert (await s.execute(select(ConfiguracionRetencion.ejecucion_desde))).scalar_one() is None
    _con_bd(esc)


# ------------------------------------------------------------------ API del panel
def _api():
    pytest.importorskip("httpx")
    pytest.importorskip("aiosqlite")
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("cambia la configuración de retención; solo en proceso")


def _correr(escenario):
    from _api_harness import cliente_api

    async def _main():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_main())


B = "/api/admin/retencion"


def test_api_panel_configura_previsualiza_simula_y_encola(sin_plazos_entorno):
    _api()
    from app.main import app

    async def esc(c):
        r = await c.get(B)
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["modo"] == "entorno" and e["activa"] is False and e["pendientes"] is None
        assert e["limites"] == {"min_dias": 30, "max_dias": 3650}
        assert e["usuarios_sin_vencimiento"] == 2  # los titulares sembrados no tienen fecha de expiración
        assert e["proxima_ejecucion"] and e["ultima_ejecucion"] is None

        assert (await c.get(f"{B}/vista-previa?dias=365")).json()["pendientes"]["titulares"] == 0
        assert (await c.get(f"{B}/vista-previa?dias=5")).json()["detail"]["codigo"] == "PLAZO_INVALIDO"

        r = await c.patch(B, json={"modo": "plazo", "plazo_titular_dias": 10})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "PLAZO_INVALIDO"
        r = await c.patch(B, json={"modo": "plazo", "plazo_titular_dias": 365})
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["modo"] == "plazo" and e["plazo_titular_dias"] == 365
        assert e["pendientes"]["titulares"] == 0 and e["cambios_recientes"][0]["actor_rol"] == "admin_therion"

        r = await c.post(f"{B}/simulacion")
        assert r.status_code == 200 and r.json()["simulacion"] is True and r.json()["origen"] == "manual"

        r = await c.post(f"{B}/ejecuciones", json={})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "CONFIRMACION_REQUERIDA"
        r = await c.post(f"{B}/ejecuciones", json={"confirmar": True})
        assert r.status_code == 202 and r.json()["encolada"] is True
        assert ("aplicar_retencion_task", ("manual", 1)) in app.state.arq.jobs

        hist = (await c.get(f"{B}/ejecuciones")).json()
        assert hist["total"] == 1 and hist["items"][0]["detalle"]["simulacion"] is True
        assert (await c.get(B)).json()["ultima_ejecucion"]["id"] == hist["items"][0]["id"]
    _correr(esc)


def test_api_retencion_solo_admin():
    _api()
    from _api_harness import EVAL_ID, encabezados_qa
    from app.core.autenticacion import emitir_token

    async def esc(c):
        rutas = [("GET", B, {}), ("PATCH", B, {"json": {"modo": "entorno"}}),
                 ("GET", f"{B}/vista-previa?dias=365", {}), ("POST", f"{B}/simulacion", {}),
                 ("POST", f"{B}/ejecuciones", {"json": {"confirmar": True}}), ("GET", f"{B}/ejecuciones", {})]
        otros = [encabezados_qa("referente"),
                 {"Authorization": f"Bearer {emitir_token(EVAL_ID, Rol.ENCUESTADO.value)}"},
                 {"Authorization": f"Bearer {emitir_token(1, Rol.CLIENTE.value)}"}]
        for metodo, url, kw in rutas:
            assert (await c.request(metodo, url, headers={"Authorization": ""}, **kw)).status_code == 401
            for h in otros:
                assert (await c.request(metodo, url, headers=h, **kw)).status_code in (401, 403)
    _correr(esc)


def test_catalogo_de_datos_personales_incluye_la_tabla_nueva():
    from app.core.catalogo_datos_personales import CATALOGO
    assert set(CATALOGO["configuracion_retencion"]) == {c.name for c in ConfiguracionRetencion.__table__.columns}
    assert not any(d.es_personal for d in CATALOGO["configuracion_retencion"].values())
