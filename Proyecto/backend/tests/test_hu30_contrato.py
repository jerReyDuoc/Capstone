"""
QA - HU-30: vigencia del contrato de la empresa cliente.

  C1  Desde el panel interno el admin renueva, suspende (y reactiva) o termina el contrato
      de una empresa, y cada cambio queda en la bitácora (HU-09).
  C2  Sin contrato vigente el servidor responde 403 CONTRATO_NO_VIGENTE en cursos, tutor IA,
      borradores y espacio de la empresa. Lo gratuito (evaluación, resultados, informe PDF y
      plan formativo) no cambia.
  C3  Al terminar el contrato el usuario descarga sus documentos durante un plazo de gracia;
      después los datos quedan para la retención (HU-25). ARCOP sigue disponible siempre.

Parte 1: reglas puras (app/domain/contrato.py); corre en cualquier entorno, sin BD.
Parte 2: API en proceso (SQLite), reutiliza la preparación de test_hu27_empresa_cliente.py
y de test_hu26_formacion.py; necesita FastAPI, SQLAlchemy y aiosqlite (Docker).

El tutor IA y los borradores aún no existen como rutas: cuando se agreguen deben depender
de app.core.servicio_pagado.empresa_con_servicio (y la descarga de borradores, de
empresa_con_documentos); test_rutas_del_servicio_pagado_usan_la_guarda lo vigila.
"""
import asyncio
from datetime import date, datetime, timedelta

import pytest

from app.domain.contrato import (
    PERMITIDAS, EstadoContrato, Operacion, SituacionContrato as S, evaluar, fin_de_gracia,
)

HOY = date(2026, 10, 28)
INICIO, TERMINO = date(2026, 1, 1), date(2026, 12, 31)


def _v(estado="activo", inicio=INICIO, termino=TERMINO, terminacion=None, hoy=HOY, gracia=30):
    return evaluar(estado=estado, inicio=inicio, termino=termino, fecha_terminacion=terminacion,
                   hoy=hoy, gracia_dias=gracia)


# ===================================================================== parte 1: reglas puras
@pytest.mark.parametrize("kwargs,situacion", [
    ({"hoy": date(2025, 12, 31)}, S.PENDIENTE),
    ({"hoy": INICIO}, S.VIGENTE),
    ({}, S.VIGENTE),
    ({"hoy": TERMINO}, S.VIGENTE),                         # el último día aún rige
    ({"hoy": TERMINO + timedelta(days=1)}, S.VENCIDO),
    ({"hoy": TERMINO + timedelta(days=30)}, S.VENCIDO),    # último día de gracia
    ({"hoy": TERMINO + timedelta(days=31)}, S.FINALIZADO),
    ({"estado": "suspendido"}, S.SUSPENDIDO),
    ({"estado": "suspendido", "hoy": TERMINO + timedelta(days=5)}, S.VENCIDO),  # vence igual
    ({"estado": "suspendido", "hoy": TERMINO + timedelta(days=31)}, S.FINALIZADO),
    ({"estado": "terminado", "terminacion": HOY}, S.TERMINADO),
    ({"estado": "terminado", "terminacion": HOY, "hoy": HOY + timedelta(days=30)}, S.TERMINADO),
    ({"estado": "terminado", "terminacion": HOY, "hoy": HOY + timedelta(days=31)}, S.FINALIZADO),
    ({"estado": "terminado", "terminacion": HOY, "gracia": 0, "hoy": HOY + timedelta(days=1)}, S.FINALIZADO),
])
def test_situacion_del_contrato(kwargs, situacion):
    assert _v(**kwargs).situacion is situacion


def test_que_permite_cada_situacion():
    vigente, suspendido = _v(), _v(estado="suspendido")
    terminado = _v(estado="terminado", terminacion=HOY)
    finalizado = _v(estado="terminado", terminacion=HOY, hoy=HOY + timedelta(days=60))
    assert vigente.servicio_habilitado and vigente.documentos_disponibles and not vigente.en_gracia
    assert not suspendido.servicio_habilitado and suspendido.documentos_disponibles
    assert not terminado.servicio_habilitado and terminado.documentos_disponibles and terminado.en_gracia
    assert not finalizado.servicio_habilitado and not finalizado.documentos_disponibles
    assert terminado.como_dict()["documentos_disponibles_hasta"] == (HOY + timedelta(days=30)).isoformat()
    assert finalizado.como_dict()["documentos_disponibles_hasta"] is None
    assert "27-11-2026" in terminado.mensaje() and "ARCOP" in finalizado.mensaje()


def test_terminar_un_contrato_ya_vencido_no_reinicia_el_plazo_de_gracia():
    vencio = date(2026, 9, 30)
    assert fin_de_gracia(vencio, date(2026, 10, 28), 30) == vencio + timedelta(days=30)
    assert fin_de_gracia(TERMINO, HOY, 30) == HOY + timedelta(days=30)   # terminación anticipada
    v = _v(estado="terminado", termino=vencio, terminacion=HOY, hoy=vencio + timedelta(days=31))
    assert v.situacion is S.FINALIZADO


def test_operaciones_permitidas_por_situacion():
    assert S.FINALIZADO not in set().union(*PERMITIDAS.values())   # nada después de la gracia
    assert PERMITIDAS[Operacion.REACTIVAR] == {S.SUSPENDIDO}
    assert S.TERMINADO in PERMITIDAS[Operacion.RENOVAR] and S.TERMINADO not in PERMITIDAS[Operacion.TERMINAR]
    assert S.VENCIDO not in PERMITIDAS[Operacion.SUSPENDER]
    assert EstadoContrato.valores() == ["activo", "suspendido", "terminado"]


# ===================================================================== parte 2: API
def _hay_api() -> bool:
    try:
        import aiosqlite  # noqa: F401
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
        return True
    except ImportError:
        return False


api = pytest.mark.skipif(not _hay_api(), reason="Pruebas de API: requieren FastAPI, SQLAlchemy y aiosqlite (Docker)")


@pytest.fixture
def hu27(monkeypatch, tmp_path):
    if not _hay_api():
        pytest.skip("sin FastAPI/SQLAlchemy")
    import test_hu27_empresa_cliente as m
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("HU-30: solo en proceso")
    from app.core.config import settings
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", m.SECRETO)
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ACTIVACION_URL_BASE", "http://localhost:3000/activar")
    monkeypatch.setattr(settings, "CONTRATO_GRACIA_DIAS", 30)
    limitador = LimitadorMemoria()
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield m
    app.dependency_overrides.pop(obtener_limitador, None)


def _correr(escenario):
    from _api_harness import cliente_api

    async def _main():
        async with cliente_api(rol=None) as c:
            await escenario(c)
    asyncio.run(_main())


def _base(hu27, empresa_id: int) -> str:
    return f"/api/admin/empresas/{empresa_id}/contrato"


async def _cliente(hu27, c) -> dict:
    x = await hu27._empresa_creada(c)
    return {**x, "hc": await hu27._activar_y_entrar(c)}


async def _mover_fechas(hu27, empresa_id: int, **cambios):
    async def f(s):
        from app.domain.models import Empresa
        e = await s.get(Empresa, empresa_id)
        for k, v in cambios.items():
            setattr(e, k, v)
        await s.commit()
    await hu27._bd(f)


async def _completar_modulo(c, h):
    import test_hu26_formacion as hu26
    ids = await hu26._ids_preguntas(c, h)
    for orden in (1, 2):
        assert (await c.post(f"/api/formacion/modulos/1/lecciones/{orden}/vista", headers=h)).status_code == 200
    r = await c.post("/api/formacion/modulos/1/verificacion", headers=h,
                     json={"respuestas": {ids["¿Uno?"]: 2, ids["¿Dos?"]: 0}})
    assert r.status_code == 200 and r.json()["aprobado"] is True, r.text


# --------------------------------------------------------------------- C1
@api
def test_api_admin_renueva_suspende_reactiva_y_termina_y_cada_cambio_queda_en_la_bitacora(hu27):
    async def esc(c):
        x = await _cliente(hu27, c)
        base, adm, eid = _base(hu27, x["empresa_id"]), hu27.admin(), x["empresa_id"]
        termino = date.fromisoformat(x["alta"]["empresa"]["fecha_termino_contrato"])
        assert x["alta"]["empresa"]["contrato"]["situacion"] == "vigente"

        # Suspender: motivo de una lista cerrada (sin texto libre que pueda traer datos personales)
        r = await c.post(f"{base}/suspension", json={"motivo": "porque sí"}, headers=adm)
        assert r.status_code == 422 and hu27._codigo(r) == "MOTIVO_INVALIDO"
        r = await c.post(f"{base}/suspension", json={"motivo": "no_pago"}, headers=adm)
        assert r.status_code == 200, r.text
        assert r.json()["contrato"]["situacion"] == "suspendido" and r.json()["contrato_vigente"] is False
        assert r.json()["contrato"]["motivo_suspension"] == "no_pago"
        # No se suspende dos veces: 409 con las operaciones posibles
        r = await c.post(f"{base}/suspension", json={"motivo": "no_pago"}, headers=adm)
        assert r.status_code == 409 and hu27._codigo(r) == "TRANSICION_CONTRATO_INVALIDA"
        assert r.json()["detail"]["permitidas"] == ["reactivar", "renovar", "terminar"]

        r = await c.post(f"{base}/reactivacion", headers=adm)
        assert r.status_code == 200 and r.json()["contrato"]["situacion"] == "vigente"
        assert (await c.post(f"{base}/reactivacion", headers=adm)).status_code == 409

        # Renovar: la nueva fecha debe ser posterior a la actual
        r = await c.post(f"{base}/renovacion", json={"fecha_termino_contrato": termino.isoformat()}, headers=adm)
        assert r.status_code == 422 and hu27._codigo(r) == "FECHA_RENOVACION_INVALIDA"
        r = await c.post(f"{base}/renovacion", json={"fecha_termino_contrato": "2206-01-01"}, headers=adm)
        assert r.status_code == 422
        nueva = termino + timedelta(days=365)
        r = await c.post(f"{base}/renovacion", json={"fecha_termino_contrato": nueva.isoformat()}, headers=adm)
        assert r.status_code == 200 and r.json()["fecha_termino_contrato"] == nueva.isoformat()

        r = await c.post(f"{base}/terminacion", json={"motivo": "solicitud_cliente"}, headers=adm)
        assert r.status_code == 200, r.text
        contrato = r.json()["contrato"]
        assert contrato["situacion"] == "terminado" and contrato["en_plazo_de_gracia"] is True
        assert contrato["documentos_disponibles_hasta"] == (date.today() + timedelta(days=30)).isoformat()
        assert (await c.post(f"{base}/terminacion", json={"motivo": "otro"}, headers=adm)).status_code == 409

        # Renovar dentro del plazo de gracia deshace la terminación (el cliente vuelve)
        r = await c.post(f"{base}/renovacion", json={"fecha_termino_contrato": (nueva + timedelta(days=1)).isoformat()},
                         headers=adm)
        assert r.status_code == 200 and r.json()["contrato"]["situacion"] == "vigente"
        assert r.json()["contrato"]["fecha_terminacion"] is None

        # Bitácora: una fila por cambio, con el antes y el después y sin datos personales
        r = await c.get(f"/api/admin/bitacora?entidad=empresa&entidad_id={eid}&size=50", headers=adm)
        filas = [f for f in r.json()["items"] if f["accion"].startswith("contrato.")]
        assert [f["accion"] for f in reversed(filas)] == [
            "contrato.suspendido", "contrato.reactivado", "contrato.renovado", "contrato.terminado",
            "contrato.renovado"]
        suspension = filas[-1]
        assert suspension["actor_rol"] == "admin_therion" and suspension["detalle"]["motivo"] == "no_pago"
        assert suspension["detalle"]["antes"]["situacion"] == "vigente"
        assert suspension["detalle"]["despues"]["situacion"] == "suspendido"
        assert "@" not in str(filas)

        # Solo el admin (401 sin token, 403 con otro rol); 404 para una empresa inexistente
        rutas = [("renovacion", {"fecha_termino_contrato": (nueva + timedelta(days=9)).isoformat()}),
                 ("suspension", {"motivo": "no_pago"}), ("reactivacion", None), ("terminacion", {"motivo": "otro"})]
        for ruta, cuerpo in rutas:
            assert (await c.post(f"{base}/{ruta}", json=cuerpo)).status_code == 401, ruta
            for h in (x["hc"], hu27._h(1, "referente")):
                assert (await c.post(f"{base}/{ruta}", json=cuerpo, headers=h)).status_code == 403, ruta
        r = await c.post("/api/admin/empresas/999/contrato/suspension", json={"motivo": "no_pago"}, headers=adm)
        assert r.status_code == 404
    _correr(esc)


# --------------------------------------------------------------------- C2
@api
def test_api_sin_contrato_vigente_el_servicio_pagado_responde_403_y_lo_gratuito_no_cambia(hu27):
    async def esc(c):
        x = await _cliente(hu27, c)
        h, ev, adm = x["hc"], x["ev"], hu27.admin()
        pagadas = ["/api/cliente/empresa", "/api/formacion/avance", "/api/formacion/modulos/1",
                   f"/api/remediacion/evaluaciones/{ev}"]
        gratuitas = [f"/api/evaluaciones/{ev}", f"/api/evaluaciones/{ev}/resumen",
                     f"/api/evaluaciones/{ev}/plan-formativo", f"/api/evaluaciones/{ev}/informe/pdf"]
        assert (await c.get("/api/cliente/empresa", headers=h)).status_code == 200

        async def comprobar(situacion: str):
            for url in pagadas:
                r = await c.get(url, headers=h)
                assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE", (url, r.text)
                assert r.json()["detail"]["situacion"] == situacion
            r = await c.post("/api/formacion/modulos/1/lecciones/1/vista", headers=h)
            assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE"
            for url in gratuitas:
                assert (await c.get(url, headers=h)).status_code == 200, url
            r = await c.get("/api/cliente/contrato", headers=h)
            assert r.status_code == 200 and r.json()["contrato"]["situacion"] == situacion
            assert r.json()["contrato"]["servicio_habilitado"] is False
            assert r.json()["documentos"]["evaluaciones"][0]["informe_pdf"] == f"/api/evaluaciones/{ev}/informe/pdf"
            r = await c.post("/api/auth/cliente", json={"email": "gerencia@acme.cl", "password": hu27.PASSWORD})
            assert r.status_code == 200 and r.json()["contrato"]["situacion"] == situacion

        # suspendido
        assert (await c.post(f"{_base(hu27, x['empresa_id'])}/suspension", json={"motivo": "no_pago"},
                             headers=adm)).status_code == 200
        await comprobar("suspendido")
        # aún no comienza
        await c.post(f"{_base(hu27, x['empresa_id'])}/reactivacion", headers=adm)
        await _mover_fechas(hu27, x["empresa_id"], fecha_inicio_contrato=date.today() + timedelta(days=5))
        await comprobar("pendiente")
        # venció por fecha (sin que nadie haga nada: se calcula en cada petición)
        await _mover_fechas(hu27, x["empresa_id"], fecha_inicio_contrato=date.today() - timedelta(days=90),
                            fecha_termino_contrato=date.today() - timedelta(days=1))
        await comprobar("vencido")

        # /api/cliente/contrato es solo del cliente
        assert (await c.get("/api/cliente/contrato")).status_code == 401
        assert (await c.get("/api/cliente/contrato", headers=adm)).status_code == 403
    _correr(esc)


def test_rutas_del_servicio_pagado_usan_la_guarda():
    """Cursos, remediación y espacio de la empresa dependen de empresa_con_servicio."""
    if not _hay_api():
        pytest.skip("sin FastAPI")
    from fastapi.routing import APIRoute

    from app.core.servicio_pagado import empresa_con_documentos, empresa_con_servicio
    from app.main import app

    def deps(route):
        pila, vistos = list(route.dependant.dependencies), set()
        while pila:
            d = pila.pop()
            vistos.add(d.call)
            pila.extend(d.dependencies)
        return vistos

    pagadas = [r for r in app.routes if isinstance(r, APIRoute) and (
        r.path.startswith(("/api/formacion", "/api/remediacion", "/api/tutor", "/api/borradores"))
        or r.path == "/api/cliente/empresa")]
    assert pagadas
    for r in pagadas:
        guardas = deps(r) & {empresa_con_servicio, empresa_con_documentos}
        assert guardas, f"{r.path} no exige contrato (app/core/servicio_pagado.py)"
        if not r.path.endswith("/constancia"):
            assert empresa_con_servicio in guardas, r.path


# --------------------------------------------------------------------- C3
@api
def test_api_plazo_de_gracia_para_documentos_y_despues_retencion(hu27):
    async def esc(c):
        from app.application.use_cases.gestionar_contrato import empresas_con_gracia_vencida
        import test_hu26_formacion as hu26

        x = await _cliente(hu27, c)
        h, eid, adm = x["hc"], x["empresa_id"], hu27.admin()
        await hu26._sembrar_curso(hu27)
        await _completar_modulo(c, h)

        r = await c.post(f"{_base(hu27, eid)}/terminacion", json={"motivo": "fin_acuerdo"}, headers=adm)
        assert r.status_code == 200
        # Durante la gracia: descarga sus documentos, pero no usa los cursos
        assert (await c.get("/api/formacion/avance", headers=h)).status_code == 403
        r = await c.get("/api/formacion/modulos/1/constancia", headers=h)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        r = await c.get("/api/cliente/contrato", headers=h)
        d = r.json()
        assert d["contrato"]["situacion"] == "terminado" and d["contrato"]["documentos_disponibles"] is True
        assert d["contrato"]["documentos_disponibles_hasta"] == (date.today() + timedelta(days=30)).isoformat()
        assert [k["url"] for k in d["documentos"]["constancias"]] == ["/api/formacion/modulos/1/constancia"]
        assert await hu27._bd(lambda s: empresas_con_gracia_vencida(s)) == []

        # Vencido el plazo: ya no descarga; sus datos quedan para la retención (HU-25)
        await _mover_fechas(hu27, eid, fecha_terminacion=datetime.now() - timedelta(days=31))
        r = await c.get("/api/formacion/modulos/1/constancia", headers=h)
        assert r.status_code == 403 and hu27._codigo(r) == "PLAZO_GRACIA_VENCIDO"
        d = (await c.get("/api/cliente/contrato", headers=h)).json()
        assert d["contrato"]["situacion"] == "finalizado" and d["documentos"]["constancias"] == []
        assert await hu27._bd(lambda s: empresas_con_gracia_vencida(s)) == [eid]
        r = await c.post(f"{_base(hu27, eid)}/renovacion",
                         json={"fecha_termino_contrato": (date.today() + timedelta(days=365)).isoformat()}, headers=adm)
        assert r.status_code == 409 and hu27._codigo(r) == "CONTRATO_FINALIZADO"

        # ARCOP sigue disponible
        r = await c.post("/api/arcop/solicitudes", headers=h,
                         json={"tipo": "acceso", "descripcion": "Quiero saber qué datos míos conservan."})
        assert r.status_code == 201, r.text
        assert r.json()["usuario_definitivo_id"] == x["alta"]["usuario"]["id"]
        assert r.json()["usuario_temporal_id"] is None and r.json()["evaluacion_id"] is None
        lista = (await c.get("/api/arcop/solicitudes", headers=h)).json()
        assert [s["id_solicitud"] for s in lista["items"]] == [r.json()["id_solicitud"]]
    _correr(esc)


@api
def test_api_supresion_arcop_del_cliente_borra_sus_datos_y_no_toca_la_empresa(hu27):
    async def esc(c):
        x = await _cliente(hu27, c)
        h, adm, ev = x["hc"], hu27.admin(), x["ev"]
        r = await c.post("/api/arcop/solicitudes", headers=h,
                         json={"tipo": "supresion", "descripcion": "Solicito suprimir mis datos personales."})
        assert r.status_code == 201, r.text
        sid, codigo = r.json()["id_solicitud"], r.json()["codigo_seguimiento"]
        # Un encuestado no ve la solicitud del cliente
        assert (await c.get(f"/api/arcop/solicitudes/{sid}", headers=x["h"])).status_code in (401, 404)

        for estado in ("en_revision", "en_proceso"):
            assert (await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": estado},
                                  headers=adm)).status_code == 200
        r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion", headers=adm,
                         json={"resultado": "resuelta", "respuesta": "Datos suprimidos según la Ley 21.719."})
        assert r.status_code == 200, r.text
        assert any(e["tipo_evento"] == "anonimizacion" for e in r.json()["historial"])

        # La cuenta quedó cerrada: el token deja de servir y no puede volver a entrar
        assert (await c.get("/api/cliente/contrato", headers=h)).status_code == 401
        r = await c.post("/api/auth/cliente", json={"email": "gerencia@acme.cl", "password": hu27.PASSWORD})
        assert r.status_code == 401
        # Puede seguir su solicitud con el código público
        assert (await c.get(f"/api/arcop/seguimiento/{codigo}")).status_code == 200

        d = (await c.get(f"/api/admin/empresas/{x['empresa_id']}", headers=adm)).json()
        assert d["usuario"]["nombre"] == "[anonimizado]" and "acme.cl" not in d["usuario"]["email"]
        assert d["usuario"]["estado"] == "bloqueado"
        # La empresa y su evaluación migrada no se tocan (persona jurídica; HU-25 decide su retención)
        assert d["razon_social"] == "ACME Servicios SpA" and [e["id"] for e in d["evaluaciones"]] == [ev]
    _correr(esc)
