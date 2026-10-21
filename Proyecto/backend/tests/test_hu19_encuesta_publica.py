"""
QA - HU-19: autodiagnóstico desde la landing, sin invitación.

  C1  aviso legal + rubro (+ CAPTCHA) -> usuario temporal anónimo + evaluación por API
  C2  token del encuestado: retoma con su clave y SOLO ve su evaluación; email opcional
  C3  abuso: intentos y evaluaciones por IP, CAPTCHA, evidencias y cuota diaria de IA
  C4  benchmark: solo evaluaciones completadas y que no sean de prueba

Solo en proceso (SQLite en memoria): los tokens dependen del AUTH_SECRET del servidor.
"""
import asyncio

import pytest

from _api_harness import DOMINIOS, MODO, TODOS_LOS_CONTROLES, body_filtro, cliente_api  # noqa: E402
from app.core import autenticacion as auth  # noqa: E402
from app.core.config import settings  # noqa: E402

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

pytestmark = pytest.mark.skipif(MODO == "live", reason="HU-19: solo en proceso")

SECRETO = "secreto-de-pruebas-hu19-0123456789abcdef"
ID_CONTROL = {codigo: i + 1 for i, codigo in enumerate(TODOS_LOS_CONTROLES)}
JUST = "Contamos con una política de IA aprobada por el directorio."
EVIDENCIA = b"Politica de uso responsable de IA v2. Aprobada por el directorio."


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", SECRETO)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    limitador = LimitadorMemoria()  # contadores nuevos en cada prueba
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield
    app.dependency_overrides.pop(obtener_limitador, None)


def _correr(escenario):
    async def _main():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_main())


def _body(**cambios):
    body = {"rubro_id": 1, "aviso_legal": {"version": settings.AVISO_LEGAL_VERSION, "aceptado": True},
            "captcha_token": "token-de-prueba"}
    body.update(cambios)
    return body


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _codigo(r):
    return r.json()["detail"]["codigo"]


async def _iniciar(c, **cambios):
    r = await c.post("/api/encuesta-publica/iniciar", json=_body(**cambios))
    assert r.status_code == 201, r.text
    return r.json()


# ===================================================================== C1
def test_inicia_sin_invitacion_y_crea_usuario_y_evaluacion_publica():
    async def esc(c):
        r = await c.post("/api/encuesta-publica/iniciar", json=_body())
        assert r.status_code == 201, r.text
        assert r.headers["cache-control"] == "no-store"
        datos = r.json()
        assert set(datos) == {"evaluacion_id", "clave_acceso", "access_token", "token_type", "expira_en"}
        assert len(datos["clave_acceso"]) == 14  # XXXX-XXXX-XXXX

        ev = await c.get(f"/api/evaluaciones/{datos['evaluacion_id']}", headers=_bearer(datos["access_token"]))
        assert ev.status_code == 200, ev.text
        assert ev.json()["estado_progreso"] == "en_progreso"

        from app.core.database import get_db
        from app.domain.models import Evaluacion, UsuarioTemporal
        from app.main import app
        gen = app.dependency_overrides[get_db]()
        s = await gen.__anext__()
        try:
            e = await s.get(Evaluacion, datos["evaluacion_id"])
            u = await s.get(UsuarioTemporal, e.usuario_temporal_id)
            assert e.origen == "publica" and e.es_prueba is False and e.clave_acceso_hash
            assert u.email is None and u.rubro_id == 1
            assert u.aviso_legal_version == settings.AVISO_LEGAL_VERSION and u.fecha_aceptacion_aviso
        finally:
            await gen.aclose()
    _correr(esc)


def test_aviso_no_aceptado_desactualizado_y_rubro_invalido():
    async def esc(c):
        r = await c.post("/api/encuesta-publica/iniciar",
                         json=_body(aviso_legal={"version": settings.AVISO_LEGAL_VERSION, "aceptado": False}))
        assert r.status_code == 422 and _codigo(r) == "AVISO_NO_ACEPTADO"
        r = await c.post("/api/encuesta-publica/iniciar",
                         json=_body(aviso_legal={"version": "1999-01", "aceptado": True}))
        assert r.status_code == 409 and _codigo(r) == "AVISO_DESACTUALIZADO"
        assert r.json()["detail"]["version_vigente"] == settings.AVISO_LEGAL_VERSION
        r = await c.post("/api/encuesta-publica/iniciar", json=_body(rubro_id=999))
        assert r.status_code == 422 and _codigo(r) == "RUBRO_INVALIDO"
        r = await c.get("/api/encuesta-publica/aviso-legal")
        assert r.json() == {"version": settings.AVISO_LEGAL_VERSION}
    _correr(esc)


def test_los_rechazos_no_gastan_el_cupo_diario(monkeypatch):
    monkeypatch.setattr(settings, "ENCUESTA_EVALUACIONES_IP_DIA", 1)

    async def esc(c):
        r = await c.post("/api/encuesta-publica/iniciar", json=_body(rubro_id=999))
        assert r.status_code == 422
        await _iniciar(c)  # el rubro inválido devolvió su cupo
    _correr(esc)


# ===================================================================== C2
def test_token_solo_da_acceso_a_su_propia_evaluacion():
    async def esc(c):
        a = await _iniciar(c)
        b = await _iniciar(c)
        ha, hb = _bearer(a["access_token"]), _bearer(b["access_token"])
        ia, ib = a["evaluacion_id"], b["evaluacion_id"]

        assert (await c.get(f"/api/evaluaciones/{ia}/progreso", headers=ha)).status_code == 200
        for ruta in (f"/api/evaluaciones/{ib}", f"/api/evaluaciones/{ib}/progreso",
                     f"/api/evaluaciones/{ib}/respuestas", f"/api/evaluaciones/{ib}/filtro"):
            r = await c.get(ruta, headers=ha)
            assert r.status_code == 404, (ruta, r.text)
        # Sin token, una evaluación pública no se ve (ni se lista)
        r = await c.get(f"/api/evaluaciones/{ia}")
        assert r.status_code == 401
        lista = (await c.get("/api/evaluaciones?page=1&size=100")).json()["items"]
        assert {ia, ib}.isdisjoint({e["id"] for e in lista})
        # El encuestado solo se lista a sí mismo
        propia = (await c.get("/api/evaluaciones?page=1&size=100", headers=hb)).json()
        assert [e["id"] for e in propia["items"]] == [ib] and propia["total"] == 1
        # No puede responder en la evaluación de otro
        r = await c.post("/api/respuestas/", headers=ha, json={
            "evaluacion_id": ib, "matriz_control_id": 1, "estado_clasificacion": "cumplido", "justificacion": JUST})
        assert r.status_code == 404
        # Token manipulado -> 401 (no se trata como anónimo)
        r = await c.get(f"/api/evaluaciones/{ia}", headers=_bearer(a["access_token"] + "x"))
        assert r.status_code == 401
    _correr(esc)


def test_las_evaluaciones_por_invitacion_siguen_igual_sin_token():
    async def esc(c):
        assert (await c.get("/api/evaluaciones/1")).status_code == 200
        a = await _iniciar(c)
        r = await c.get("/api/evaluaciones/1", headers=_bearer(a["access_token"]))
        assert r.status_code == 404  # el encuestado no ve evaluaciones ajenas por invitación
    _correr(esc)


def test_retoma_con_su_clave_desde_otro_dispositivo():
    async def esc(c):
        a = await _iniciar(c)
        clave = a["clave_acceso"].lower().replace("-", " ")  # tolera formato
        r = await c.post("/api/auth/encuestado", json={"evaluacion_id": a["evaluacion_id"], "clave": clave})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        assert (await c.get(f"/api/evaluaciones/{a['evaluacion_id']}", headers=_bearer(token))).status_code == 200
        r = await c.post("/api/auth/encuestado", json={"evaluacion_id": a["evaluacion_id"], "clave": "AAAA-BBBB-CCCC"})
        assert r.status_code == 401
    _correr(esc)


def test_email_opcional_no_bloquea_y_no_habilita_login_de_referente():
    async def esc(c):
        a = await _iniciar(c)
        h = _bearer(a["access_token"])
        r = await c.patch("/api/encuesta-publica/email", json={"email": "no-es-correo"}, headers=h)
        assert r.status_code == 422 and _codigo(r) == "EMAIL_INVALIDO"
        r = await c.patch("/api/encuesta-publica/email", json={"email": "Ana@Empresa.cl"}, headers=h)
        assert r.status_code == 204
        assert (await c.patch("/api/encuesta-publica/email", json={"email": "x@y.cl"})).status_code == 401

        from app.core.database import get_db
        from app.domain.models import Evaluacion
        from app.main import app
        gen = app.dependency_overrides[get_db]()
        s = await gen.__anext__()
        try:
            usuario_id = (await s.get(Evaluacion, a["evaluacion_id"])).usuario_temporal_id
        finally:
            await gen.aclose()
        r = await c.post("/api/auth/titular", json={"usuario_temporal_id": usuario_id, "email": "ana@empresa.cl"})
        assert r.status_code == 401
        # Borrar el email también es posible
        assert (await c.patch("/api/encuesta-publica/email", json={"email": None}, headers=h)).status_code == 204
    _correr(esc)


def test_encuestado_no_puede_hacer_la_revision_humana():
    async def esc(c):
        a = await _iniciar(c)
        h = _bearer(a["access_token"])
        ev = a["evaluacion_id"]
        assert (await c.post(f"/api/evaluaciones/{ev}/filtro", json=body_filtro(True), headers=h)).status_code == 200
        r = await c.post("/api/respuestas/", headers=h, json={
            "evaluacion_id": ev, "matriz_control_id": ID_CONTROL["GOB-001"],
            "estado_clasificacion": "cumplido", "justificacion": JUST})
        assert r.status_code == 201, r.text
        rid = r.json()["id_respuesta"]
        r = await c.patch(f"/api/respuestas/{rid}/revision", json={"clasificacion_revisada": "cumplido"}, headers=h)
        assert r.status_code == 403
    _correr(esc)


# ===================================================================== C3
def test_limite_de_intentos_por_ip(monkeypatch):
    monkeypatch.setattr(settings, "ENCUESTA_INTENTOS_IP_10MIN", 2)

    async def esc(c):
        await _iniciar(c)
        await _iniciar(c)
        r = await c.post("/api/encuesta-publica/iniciar", json=_body())
        assert r.status_code == 429 and _codigo(r) == "DEMASIADOS_INTENTOS"
        assert int(r.headers["retry-after"]) > 0
    _correr(esc)


def test_limite_de_evaluaciones_por_ip_y_dia(monkeypatch):
    monkeypatch.setattr(settings, "ENCUESTA_EVALUACIONES_IP_DIA", 1)

    async def esc(c):
        await _iniciar(c)
        r = await c.post("/api/encuesta-publica/iniciar", json=_body())
        assert r.status_code == 429 and _codigo(r) == "LIMITE_EVALUACIONES"
    _correr(esc)


def test_captcha_rechazado(monkeypatch):
    from app.api.routes import encuesta_publica
    from app.infrastructure.security.captcha import ResultadoCaptcha

    async def falso(token, ip, accion="iniciar_encuesta"):
        return ResultadoCaptcha(False, "invalid-input-response")

    monkeypatch.setattr(encuesta_publica, "verificar_captcha", falso)

    async def esc(c):
        r = await c.post("/api/encuesta-publica/iniciar", json=_body())
        assert r.status_code == 403 and _codigo(r) == "CAPTCHA_INVALIDO"
    _correr(esc)


def test_solo_el_bff_puede_iniciar_cuando_hay_secreto_compartido(monkeypatch):
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", "bff-" + "x" * 40)

    async def esc(c):
        r = await c.post("/api/encuesta-publica/iniciar", json=_body())
        assert r.status_code == 403 and _codigo(r) == "ORIGEN_NO_PERMITIDO"
        r = await c.post("/api/encuesta-publica/iniciar", json=_body(),
                         headers={"X-BFF-Secret": "bff-" + "x" * 40, "X-Cliente-IP": "203.0.113.7"})
        assert r.status_code == 201, r.text
    _correr(esc)


def test_la_ip_reenviada_solo_cuenta_si_viene_del_bff(monkeypatch):
    monkeypatch.setattr(settings, "ENCUESTA_EVALUACIONES_IP_DIA", 1)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", "bff-" + "y" * 40)
    bff = {"X-BFF-Secret": "bff-" + "y" * 40}

    async def esc(c):
        await _iniciar_con(c, {**bff, "X-Cliente-IP": "203.0.113.1"})
        await _iniciar_con(c, {**bff, "X-Cliente-IP": "203.0.113.2"})  # otra IP: otro cupo
        r = await c.post("/api/encuesta-publica/iniciar", json=_body(),
                         headers={**bff, "X-Cliente-IP": "203.0.113.1"})
        assert r.status_code == 429
    _correr(esc)


async def _iniciar_con(c, headers):
    r = await c.post("/api/encuesta-publica/iniciar", json=_body(), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _respuesta_con_evidencia_posible(c, h, ev):
    assert (await c.post(f"/api/evaluaciones/{ev}/filtro", json=body_filtro(True), headers=h)).status_code == 200
    r = await c.post("/api/respuestas/", headers=h, json={
        "evaluacion_id": ev, "matriz_control_id": ID_CONTROL["GOB-001"],
        "estado_clasificacion": "cumplido", "justificacion": JUST})
    assert r.status_code == 201, r.text
    return r.json()["id_respuesta"]


def _subir(c, rid, h):
    return c.post(f"/api/respuestas/{rid}/evidencias", headers=h,
                  files={"file": ("politica.txt", EVIDENCIA, "text/plain")})


def test_cuota_diaria_de_ia_por_evaluacion_y_estado_en_limites(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CUOTA_DIARIA_EVALUACION", 1)

    async def esc(c):
        a = await _iniciar(c)
        h = _bearer(a["access_token"])
        rid = await _respuesta_con_evidencia_posible(c, h, a["evaluacion_id"])
        assert (await _subir(c, rid, h)).status_code == 202
        r = await _subir(c, rid, h)
        assert r.status_code == 429 and _codigo(r) == "CUOTA_LLM_AGOTADA"
        assert r.json()["detail"]["reinicia_en"].endswith("Z")

        lim = (await c.get("/api/encuesta-publica/limites", headers=h)).json()
        assert lim["validaciones_ia"]["restantes"] == 0
        assert lim["evidencias"]["usadas"] == 1
    _correr(esc)


def test_un_archivo_rechazado_no_gasta_cuota(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CUOTA_DIARIA_EVALUACION", 1)

    async def esc(c):
        a = await _iniciar(c)
        h = _bearer(a["access_token"])
        rid = await _respuesta_con_evidencia_posible(c, h, a["evaluacion_id"])
        r = await c.post(f"/api/respuestas/{rid}/evidencias", headers=h,
                         files={"file": ("vacio.txt", b"", "text/plain")})
        assert r.status_code == 400
        assert (await _subir(c, rid, h)).status_code == 202
    _correr(esc)


def test_limite_de_evidencias_por_evaluacion(monkeypatch):
    monkeypatch.setattr(settings, "ENCUESTA_MAX_EVIDENCIAS_EVALUACION", 1)

    async def esc(c):
        a = await _iniciar(c)
        h = _bearer(a["access_token"])
        rid = await _respuesta_con_evidencia_posible(c, h, a["evaluacion_id"])
        assert (await _subir(c, rid, h)).status_code == 202
        r = await _subir(c, rid, h)
        assert r.status_code == 429 and _codigo(r) == "LIMITE_EVIDENCIAS"
    _correr(esc)


def test_las_evaluaciones_por_invitacion_no_tienen_cuota(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CUOTA_DIARIA_EVALUACION", 1)

    async def esc(c):
        assert (await c.post("/api/evaluaciones/1/filtro", json=body_filtro(True))).status_code == 200
        r = await c.post("/api/respuestas/", json={
            "evaluacion_id": 1, "matriz_control_id": ID_CONTROL["GOB-001"],
            "estado_clasificacion": "cumplido", "justificacion": JUST})
        rid = r.json()["id_respuesta"]
        for _ in range(2):
            assert (await _subir(c, rid, {})).status_code == 202
    _correr(esc)


# ===================================================================== C4
def test_benchmark_excluye_abandonadas_y_de_prueba():
    async def esc(c):
        from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase
        from app.core.database import get_db
        from app.domain.models import Evaluacion, UsuarioTemporal
        from app.domain.models.benchmark import Benchmark
        from app.domain.models.resumen import Resumen
        from app.main import app
        from sqlalchemy import select

        dominio_id = next(iter(DOMINIOS.values()))[0]
        gen = app.dependency_overrides[get_db]()
        s = await gen.__anext__()
        try:
            s.add(UsuarioTemporal(id=50, rubro_id=1))
            s.add_all([
                Evaluacion(id=501, estado_progreso="completada", usuario_temporal_id=50, origen="publica"),
                Evaluacion(id=502, estado_progreso="completada", usuario_temporal_id=50, origen="publica",
                           es_prueba=True),
                Evaluacion(id=503, estado_progreso="en_progreso", usuario_temporal_id=50, origen="publica"),
            ])
            await s.flush()
            s.add_all([
                Resumen(evaluacion_id=501, dominio_id=dominio_id, puntaje_obtenido=80.0, total_controles_evaluados=5),
                Resumen(evaluacion_id=502, dominio_id=dominio_id, puntaje_obtenido=10.0, total_controles_evaluados=5),
                Resumen(evaluacion_id=503, dominio_id=dominio_id, puntaje_obtenido=10.0, total_controles_evaluados=5),
            ])
            await s.commit()
            await UpdateBenchmarkUseCase(s).execute()
            b = (await s.execute(select(Benchmark).where(Benchmark.dominio_id == dominio_id))).scalar_one()
            assert b.total_evaluaciones == 1 and b.promedio_puntaje == 80.0
        finally:
            await gen.aclose()

        # Marcar como prueba es solo de admin
        r = await c.patch("/api/evaluaciones/501/prueba", json={"es_prueba": True})
        assert r.status_code == 401
        admin = {"Authorization": f"Bearer {auth.emitir_token(1, 'admin_therion', secreto=SECRETO)}"}
        r = await c.patch("/api/evaluaciones/501/prueba", json={"es_prueba": True}, headers=admin)
        assert r.status_code == 200 and r.json()["es_prueba"] is True
    _correr(esc)


def test_retomar_con_clave_limita_los_intentos_por_evaluacion():
    async def esc(c):
        a = await _iniciar(c)
        body = {"evaluacion_id": a["evaluacion_id"], "clave": "AAAA-BBBB-CCCC"}
        for _ in range(10):
            assert (await c.post("/api/auth/encuestado", json=body)).status_code == 401
        r = await c.post("/api/auth/encuestado", json={**body, "clave": a["clave_acceso"]})
        assert r.status_code == 429 and _codigo(r) == "DEMASIADOS_INTENTOS"
    _correr(esc)
