"""
QA - HU-20: confidencialidad del diagnóstico (autorización por endpoint).

  C1  evaluaciones, respuestas, evidencias y reportes exigen el token del encuestado
      (HU-19), del referente dueño o de un admin; catálogos, controles y landing siguen
      públicos.
  C2  un encuestado solo accede a su evaluación (404 en las ajenas); métricas de IA,
      eventos de seguridad y revisión humana solo para admin.
  C3  pruebas automáticas de autorización POR ENDPOINT: cada ruta de la API está en una
      de las matrices de abajo (test_todas_las_rutas_estan_clasificadas falla si se
      agrega un endpoint sin decidir quién puede usarlo).

Actores de cada caso (BD SQLite nueva por caso, así un POST no afecta al siguiente):
  sin_token, encuestado (dueño de la evaluación pública A), encuestado_ajeno (dueño de
  B), referente (usuario temporal 1, dueño de la evaluación por invitación 1),
  referente_ajeno (usuario temporal 2, sin evaluaciones) y admin.

Solo en proceso: los tokens dependen del AUTH_SECRET del servidor.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import pytest

from _api_harness import (  # noqa: E402
    ADMIN_EMAIL, ADMIN_PASSWORD, MODO, TODOS_LOS_CONTROLES, body_filtro, cliente_api,
)
from app.core import autenticacion as auth  # noqa: E402
from app.core.config import settings  # noqa: E402

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

pytestmark = pytest.mark.skipif(MODO == "live", reason="HU-20: solo en proceso")

SECRETO = "secreto-de-pruebas-hu20-0123456789abcdef"
ID_CONTROL = {codigo: i + 1 for i, codigo in enumerate(TODOS_LOS_CONTROLES)}
JUST = "Contamos con una política de IA aprobada por el directorio."
EVIDENCIA = b"Politica de uso responsable de IA v2. Aprobada por el directorio."
INVITACION_ID = 1        # evaluación sembrada por el arnés (usuario temporal 1)
REFERENTE_ID = 1
REFERENTE_AJENO_ID = 2   # sembrado por el arnés, sin evaluaciones
ADMIN_ID = 1


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", SECRETO)
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)  # aunque el .env diga otra cosa
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "CORREO_MODO", "desactivado")  # el envío del informe no escribe nada
    limitador = LimitadorMemoria()
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield
    app.dependency_overrides.pop(obtener_limitador, None)


def _correr(escenario):
    async def _main():
        async with cliente_api(rol=None) as c:
            await escenario(c)
    asyncio.run(_main())


def _h(usuario_id: int, rol: str, ttl_min: int | None = None) -> dict:
    return {"Authorization": f"Bearer {auth.emitir_token(usuario_id, rol, ttl_min=ttl_min, secreto=SECRETO)}"}


def _codigo(r):
    detalle = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else None
    return detalle.get("codigo") if isinstance(detalle, dict) else None


# ===================================================================== mundo de prueba
@dataclass
class Mundo:
    cab: dict = field(default_factory=dict)       # actor -> headers
    ev: dict = field(default_factory=dict)        # "publica" | "invitacion" | "publica_ajena" -> id
    resp: dict = field(default_factory=dict)      # "publica" | "invitacion" -> id_respuesta
    evid: dict = field(default_factory=dict)      # "publica" | "invitacion" -> id_evidencia
    clave: dict = field(default_factory=dict)     # "publica" -> clave de acceso
    evento: int | None = None


async def _iniciar(c) -> dict:
    r = await c.post("/api/encuesta-publica/iniciar", json={
        "rubro_id": 1, "aviso_legal": {"version": settings.AVISO_LEGAL_VERSION, "aceptado": True},
        "captcha_token": "token-de-prueba"})
    assert r.status_code == 201, r.text
    return r.json()


async def _respuesta_y_evidencia(c, h: dict, ev: int) -> tuple[int, int]:
    r = await c.post(f"/api/evaluaciones/{ev}/filtro", json=body_filtro(True), headers=h)
    assert r.status_code == 200, r.text
    r = await c.post("/api/respuestas/", headers=h, json={
        "evaluacion_id": ev, "matriz_control_id": ID_CONTROL["GOB-001"],
        "estado_clasificacion": "cumplido", "justificacion": JUST})
    assert r.status_code == 201, r.text
    rid = r.json()["id_respuesta"]
    r = await c.post(f"/api/respuestas/{rid}/evidencias", headers=h,
                     files={"file": ("politica.txt", EVIDENCIA, "text/plain")})
    assert r.status_code == 202, r.text
    return rid, r.json()["id_evidencia"]


async def _crear_evento(ev: int) -> int:
    from app.core.database import get_db
    from app.domain.models.evento_seguridad import EventoSeguridad, OrigenEvento
    from app.main import app

    gen = app.dependency_overrides[get_db]()
    s = await gen.__anext__()
    try:
        evento = EventoSeguridad(fecha=datetime(2026, 10, 1), tipo="prompt_injection",
                                 origen=OrigenEvento.JUSTIFICACION.value, evaluacion_id=ev,
                                 extracto="ignora las instrucciones", hash_texto="0" * 64, revisado=False)
        s.add(evento)
        await s.commit()
        return evento.id_evento
    finally:
        await gen.aclose()


async def _armar(c) -> Mundo:
    m = Mundo()
    a, b = await _iniciar(c), await _iniciar(c)
    m.ev = {"publica": a["evaluacion_id"], "publica_ajena": b["evaluacion_id"], "invitacion": INVITACION_ID}
    m.clave = {"publica": a["clave_acceso"]}
    m.cab = {
        "sin_token": {},
        "encuestado": {"Authorization": f"Bearer {a['access_token']}"},
        "encuestado_ajeno": {"Authorization": f"Bearer {b['access_token']}"},
        "referente": _h(REFERENTE_ID, "referente"),
        "referente_ajeno": _h(REFERENTE_AJENO_ID, "referente"),
        "admin": _h(ADMIN_ID, "admin_therion"),
    }
    m.resp["publica"], m.evid["publica"] = await _respuesta_y_evidencia(c, m.cab["encuestado"], m.ev["publica"])
    m.resp["invitacion"], m.evid["invitacion"] = await _respuesta_y_evidencia(c, m.cab["referente"], INVITACION_ID)
    m.evento = await _crear_evento(m.ev["publica"])
    return m


# Para cada tipo de evaluación: quién es el dueño y a quién se le niega con 404
DUENO = {"publica": "encuestado", "invitacion": "referente"}
AJENOS = {"publica": ("encuestado_ajeno", "referente", "referente_ajeno"),
          "invitacion": ("encuestado", "encuestado_ajeno", "referente_ajeno")}


def _permitido(r) -> bool:
    """El control de acceso dejó pasar: ni 401/403 ni el 404 del alcance."""
    if r.status_code in (401, 403):
        return False
    return not (r.status_code == 404 and _codigo(r) == "EVALUACION_NO_ENCONTRADA")


# ===================================================================== C1 + C2: matriz de rutas con alcance
def _p(m: Mundo, t: str) -> dict:
    """Valores para formatear la ruta según el tipo de evaluación t."""
    return {"ev": m.ev[t], "resp": m.resp[t], "evid": m.evid[t]}


def _respuesta_nueva(m: Mundo, t: str) -> dict:
    return {"json": {"evaluacion_id": m.ev[t], "matriz_control_id": ID_CONTROL["GOB-002"],
                     "estado_clasificacion": "cumplido", "justificacion": JUST}}


# (método, ruta de FastAPI, función que arma los kwargs de httpx)
RUTAS_CON_ALCANCE = [
    ("GET", "/api/evaluaciones/{evaluacion_id}", None),
    ("GET", "/api/evaluaciones/{evaluacion_id}/respuestas", None),
    ("GET", "/api/evaluaciones/{evaluacion_id}/filtro", None),
    ("POST", "/api/evaluaciones/{evaluacion_id}/filtro", lambda m, t: {"json": body_filtro(True)}),
    ("GET", "/api/evaluaciones/{evaluacion_id}/controles-aplicables", None),
    ("GET", "/api/evaluaciones/{evaluacion_id}/progreso", None),
    ("POST", "/api/evaluaciones/{evaluacion_id}/cerrar", None),
    ("POST", "/api/evaluaciones/{evaluacion_id}/completar", None),
    ("GET", "/api/evaluaciones/{evaluacion_id}/resumen", None),
    ("GET", "/api/evaluaciones/{evaluacion_id}/comparativa", None),
    ("GET", "/api/evaluaciones/{evaluacion_id}/plan-formativo", None),
    ("GET", "/api/evaluaciones/{evaluacion_id}/informe/pdf", None),
    # HU-21: la portada del PDF en JSON (mismo alcance que el PDF)
    ("GET", "/api/evaluaciones/{evaluacion_id}/informe/ficha", None),
    ("POST", "/api/evaluaciones/{evaluacion_id}/informe/enviar",
     lambda m, t: {"json": {"email": "informe@example.com"}}),
    ("POST", "/api/respuestas/", _respuesta_nueva),
    ("GET", "/api/respuestas/{respuesta_id}", None),
    ("PUT", "/api/respuestas/{respuesta_id}",
     lambda m, t: {"json": {"estado_clasificacion": "no_cumplido", "justificacion": JUST}}),
    ("POST", "/api/respuestas/{respuesta_id}/evidencias",
     lambda m, t: {"files": {"file": ("otra.txt", EVIDENCIA, "text/plain")}}),
    ("GET", "/api/evidencias/{evidencia_id}", None),
]


def _url(ruta: str, m: Mundo, t: str) -> str:
    v = _p(m, t)
    return ruta.format(evaluacion_id=v["ev"], respuesta_id=v["resp"], evidencia_id=v["evid"])


@pytest.mark.parametrize("tipo", ["publica", "invitacion"])
@pytest.mark.parametrize("metodo,ruta,armar", RUTAS_CON_ALCANCE, ids=[f"{m} {r}" for m, r, _ in RUTAS_CON_ALCANCE])
def test_ruta_con_alcance(metodo, ruta, armar, tipo):
    async def esc(c):
        m = await _armar(c)
        url = _url(ruta, m, tipo)

        async def pedir(actor):
            kwargs = armar(m, tipo) if armar else {}
            return await c.request(metodo, url, headers=m.cab[actor], **kwargs)

        r = await pedir("sin_token")
        assert r.status_code == 401 and _codigo(r) == "NO_AUTENTICADO", (url, r.status_code, r.text)
        assert r.headers.get("www-authenticate") == "Bearer"
        for ajeno in AJENOS[tipo]:
            r = await pedir(ajeno)
            assert r.status_code == 404 and _codigo(r) == "EVALUACION_NO_ENCONTRADA", (ajeno, url, r.text)
        # El dueño y el admin pasan el control de acceso (la ruta puede responder 409, 422, etc.)
        for permitido in (DUENO[tipo], "admin"):
            r = await pedir(permitido)
            assert _permitido(r), (permitido, url, r.status_code, r.text)
    _correr(esc)


def test_las_respuestas_de_un_ajeno_no_revelan_datos():
    """El 404 de lo ajeno es idéntico al de un id inexistente (no confirma que exista)."""
    async def esc(c):
        m = await _armar(c)
        h = m.cab["encuestado"]
        ajena = await c.get(f"/api/evaluaciones/{m.ev['publica_ajena']}", headers=h)
        inexistente = await c.get("/api/evaluaciones/987654", headers=h)
        assert ajena.status_code == inexistente.status_code == 404
        assert ajena.json() == inexistente.json()
        assert JUST not in (await c.get(f"/api/respuestas/{m.resp['invitacion']}", headers=h)).text
    _correr(esc)


def test_sin_token_un_id_inexistente_tambien_es_401():
    async def esc(c):
        for url in ("/api/evaluaciones/987654", "/api/evaluaciones/987654/resumen",
                    "/api/respuestas/987654", "/api/evidencias/987654"):
            r = await c.get(url)
            assert r.status_code == 401, (url, r.text)
        r = await c.post("/api/respuestas/", json={"evaluacion_id": 987654, "matriz_control_id": 1,
                                                   "estado_clasificacion": "cumplido", "justificacion": JUST})
        assert r.status_code == 401
        # con token, lo inexistente es 404 (como lo ajeno)
        h = _h(ADMIN_ID, "admin_therion")
        assert (await c.get("/api/respuestas/987654", headers=_h(REFERENTE_ID, "referente"))).status_code == 404
        assert (await c.get("/api/evidencias/987654", headers=h)).status_code == 404
    _correr(esc)


def test_token_invalido_o_vencido_es_401():
    async def esc(c):
        m = await _armar(c)
        url = f"/api/evaluaciones/{m.ev['publica']}"
        vencido = _h(m.ev["publica"], "encuestado", ttl_min=-1)
        otra_firma = {"Authorization": "Bearer " + auth.emitir_token(m.ev["publica"], "encuestado",
                                                                      secreto="otro-secreto-" + "x" * 32)}
        for h in (vencido, otra_firma, {"Authorization": "Bearer basura"}):
            r = await c.get(url, headers=h)
            assert r.status_code == 401 and _codigo(r) == "TOKEN_INVALIDO", r.text
    _correr(esc)


# ===================================================================== listado y benchmark
def test_listado_de_evaluaciones_por_actor():
    async def esc(c):
        m = await _armar(c)

        async def ids(actor):
            r = await c.get("/api/evaluaciones?page=1&size=100", headers=m.cab[actor])
            assert r.status_code == 200, (actor, r.text)
            return {e["id"] for e in r.json()["items"]}

        assert (await c.get("/api/evaluaciones")).status_code == 401
        assert await ids("encuestado") == {m.ev["publica"]}
        assert await ids("encuestado_ajeno") == {m.ev["publica_ajena"]}
        assert await ids("referente") == {1, 2}            # las dos sembradas por invitación
        assert await ids("referente_ajeno") == set()
        assert {1, 2, m.ev["publica"], m.ev["publica_ajena"]} <= await ids("admin")
    _correr(esc)


def test_benchmark_exige_token_de_cualquier_rol():
    async def esc(c):
        m = await _armar(c)
        r = await c.get("/api/evaluaciones/benchmark")
        assert r.status_code == 401
        for actor in ("encuestado", "referente", "admin"):
            r = await c.get("/api/evaluaciones/benchmark", headers=m.cab[actor])
            assert r.status_code == 200, (actor, r.text)
    _correr(esc)


# ===================================================================== C2: solo admin
RUTAS_SOLO_ADMIN = [
    ("GET", "/api/ia/metricas", lambda m: ("/api/ia/metricas", {})),
    ("GET", "/api/seguridad/eventos", lambda m: ("/api/seguridad/eventos", {})),
    ("PATCH", "/api/seguridad/eventos/{evento_id}/revisado",
     lambda m: (f"/api/seguridad/eventos/{m.evento}/revisado", {})),
    ("PATCH", "/api/respuestas/{respuesta_id}/revision",
     lambda m: (f"/api/respuestas/{m.resp['publica']}/revision", {"json": {"clasificacion_revisada": "cumplido", "comentario": "Revisado por el Oficial de Cumplimiento."}})),
    ("PATCH", "/api/evaluaciones/{evaluacion_id}/prueba",
     lambda m: (f"/api/evaluaciones/{m.ev['publica']}/prueba", {"json": {"es_prueba": True}})),
    ("POST", "/api/auth/encuestado/clave",
     lambda m: ("/api/auth/encuestado/clave", {"json": {"evaluacion_id": INVITACION_ID}})),
    # HU-27: panel interno (listados; el resto de /api/admin está en RUTAS_ADMIN_HU27)
    ("GET", "/api/admin/contrataciones", lambda m: ("/api/admin/contrataciones", {})),
    ("GET", "/api/admin/empresas", lambda m: ("/api/admin/empresas", {})),
    ("GET", "/api/admin/bitacora", lambda m: ("/api/admin/bitacora", {})),
    ("GET", "/api/admin/bitacora/verificacion", lambda m: ("/api/admin/bitacora/verificacion", {})),  # HU-18
    # HU-28: evaluaciones del panel interno
    ("GET", "/api/admin/evaluaciones", lambda m: ("/api/admin/evaluaciones", {})),
    # HU-22: bandeja de revisión del Oficial de Cumplimiento
    ("GET", "/api/admin/revision/bandeja", lambda m: ("/api/admin/revision/bandeja", {})),
    ("GET", "/api/admin/revision/resumen", lambda m: ("/api/admin/revision/resumen", {})),
    ("GET", "/api/admin/revision/respuestas/{respuesta_id}",
     lambda m: (f"/api/admin/revision/respuestas/{m.resp['publica']}", {})),
    ("PATCH", "/api/seguridad/eventos/{evento_id}/revision",
     lambda m: (f"/api/seguridad/eventos/{m.evento}/revision",
                {"json": {"resolucion": "falso_positivo", "comentario": "Texto legítimo del encuestado."}})),
]

# HU-27: también solo admin, pero necesitan una solicitud o empresa creadas. Sus pruebas de
# 401 (sin token), 403 (encuestado, referente y cliente) y 2xx (admin) están en
# tests/test_hu27_empresa_cliente.py::test_rutas_admin_hu27_solo_admin.
RUTAS_ADMIN_HU27 = [
    ("GET", "/api/admin/contrataciones/{solicitud_id}"),
    ("PATCH", "/api/admin/contrataciones/{solicitud_id}"),
    ("POST", "/api/admin/empresas"),
    ("GET", "/api/admin/empresas/{empresa_id}"),
    ("POST", "/api/admin/empresas/{empresa_id}/evaluaciones"),
    ("POST", "/api/admin/empresas/{empresa_id}/usuario/activacion"),
    # HU-26: avance formativo de una empresa (prueba en tests/test_hu26_formacion.py)
    ("GET", "/api/admin/empresas/{empresa_id}/formacion"),
    # HU-30: vigencia del contrato (roles en tests/test_hu30_contrato.py)
    ("POST", "/api/admin/empresas/{empresa_id}/contrato/renovacion"),
    ("POST", "/api/admin/empresas/{empresa_id}/contrato/suspension"),
    ("POST", "/api/admin/empresas/{empresa_id}/contrato/reactivacion"),
    ("POST", "/api/admin/empresas/{empresa_id}/contrato/terminacion"),
]


@pytest.mark.parametrize("metodo,ruta,armar", RUTAS_SOLO_ADMIN, ids=[f"{m} {r}" for m, r, _ in RUTAS_SOLO_ADMIN])
def test_ruta_solo_admin(metodo, ruta, armar):
    async def esc(c):
        m = await _armar(c)
        url, kwargs = armar(m)
        r = await c.request(metodo, url, **kwargs)
        assert r.status_code == 401, (url, r.text)
        # Ni el dueño de los datos (encuestado/referente) puede: 403
        for actor in ("encuestado", "encuestado_ajeno", "referente", "referente_ajeno"):
            r = await c.request(metodo, url, headers=m.cab[actor], **kwargs)
            assert r.status_code == 403 and _codigo(r) == "NO_AUTORIZADO", (actor, url, r.text)
        r = await c.request(metodo, url, headers=m.cab["admin"], **kwargs)
        assert 200 <= r.status_code < 300, (url, r.status_code, r.text)
    _correr(esc)


def test_revision_humana_del_admin_cambia_la_clasificacion_final():
    async def esc(c):
        m = await _armar(c)
        rid = m.resp["publica"]
        r = await c.patch(f"/api/respuestas/{rid}/revision", json={"clasificacion_revisada": "no_cumplido", "comentario": "Revisado por el Oficial de Cumplimiento."},
                          headers=m.cab["encuestado"])
        assert r.status_code == 403
        r = await c.patch(f"/api/respuestas/{rid}/revision", json={"clasificacion_revisada": "no_cumplido", "comentario": "Revisado por el Oficial de Cumplimiento."},
                          headers=m.cab["admin"])
        assert r.status_code == 200 and r.json()["fuente_clasificacion"] == "revision"
        # el encuestado ve el resultado de la revisión en SU respuesta
        r = await c.get(f"/api/respuestas/{rid}", headers=m.cab["encuestado"])
        assert r.json()["estado_clasificacion_final"] == "no_cumplido"
        # inexistente: el admin recibe 404; sin token sigue siendo 401
        assert (await c.patch("/api/respuestas/987654/revision", json={"clasificacion_revisada": "cumplido", "comentario": "Revisado por el Oficial de Cumplimiento."},
                              headers=m.cab["admin"])).status_code == 404
    _correr(esc)


# ===================================================================== C1: lo público sigue público
RUTAS_PUBLICAS = [
    ("GET", "/health", "/health", {}),
    ("GET", "/api/dominios", "/api/dominios", {}),
    ("GET", "/api/rubros", "/api/rubros", {}),
    ("GET", "/api/rutas-formativas", "/api/rutas-formativas", {}),
    ("GET", "/api/brechas", "/api/brechas", {}),
    ("GET", "/api/controles", "/api/controles", {}),
    ("GET", "/api/controles/{control_id}", "/api/controles/1", {}),
    ("GET", "/api/encuesta-publica/aviso-legal", "/api/encuesta-publica/aviso-legal", {}),
    ("POST", "/api/encuesta-publica/iniciar", "/api/encuesta-publica/iniciar", None),  # body abajo
    ("GET", "/api/arcop/catalogo", "/api/arcop/catalogo", {}),
    ("GET", "/api/arcop/seguimiento/{codigo}", "/api/arcop/seguimiento/ARC-0000-0000", {}),
    ("GET", "/api/contratacion/consentimiento", "/api/contratacion/consentimiento", {}),  # HU-27/31
]


@pytest.mark.parametrize("metodo,ruta,url,kwargs", RUTAS_PUBLICAS, ids=[f"{m} {r}" for m, r, _, _ in RUTAS_PUBLICAS])
def test_ruta_publica_sin_token(metodo, ruta, url, kwargs):
    cuerpo = kwargs if kwargs is not None else {"json": {
        "rubro_id": 1, "captcha_token": "t",
        "aviso_legal": {"version": settings.AVISO_LEGAL_VERSION, "aceptado": True}}}

    async def esc(c):
        r = await c.request(metodo, url, **cuerpo)
        assert r.status_code not in (401, 403), (url, r.status_code, r.text)
        assert r.status_code < 500, (url, r.text)
    _correr(esc)


def test_los_catalogos_responden_igual_con_y_sin_token():
    async def esc(c):
        m = await _armar(c)
        for url in ("/api/controles", "/api/brechas", "/api/rubros"):
            sin = await c.get(url)
            con = await c.get(url, headers=m.cab["encuestado"])
            assert sin.status_code == con.status_code == 200 and sin.json() == con.json()
    _correr(esc)


# Rutas que entregan un token (se llaman sin uno, con credenciales en el cuerpo)
RUTAS_DE_ACCESO = [
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/titular"),
    ("POST", "/api/auth/encuestado"),
    # HU-27: login del cliente y enlace de activación (la prueba completa está en test_hu27)
    ("POST", "/api/auth/cliente"),
    ("POST", "/api/auth/activacion/verificar"),
    ("POST", "/api/auth/activacion"),
    # HU-09: login del Auditor Externo (la prueba completa está en test_hu09_audit_log.py)
    ("POST", "/api/auth/auditor"),
    # HU-28: recuperación de contraseña (la prueba completa está en test_hu28_sesion.py)
    ("POST", "/api/auth/recuperacion"),
    ("POST", "/api/auth/recuperacion/verificar"),
    ("POST", "/api/auth/recuperacion/restablecer"),
]


def test_rutas_de_acceso_entregan_tokens_sin_token_previo():
    async def esc(c):
        m = await _armar(c)
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        r = await c.post("/api/auth/titular", json={"usuario_temporal_id": REFERENTE_ID, "email": "qa@example.com"})
        assert r.status_code == 200, r.text
        r = await c.post("/api/auth/encuestado", json={"evaluacion_id": m.ev["publica"], "clave": m.clave["publica"]})
        assert r.status_code == 200, r.text
        # el token obtenido con la clave solo abre SU evaluación
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert (await c.get(f"/api/evaluaciones/{m.ev['publica']}", headers=h)).status_code == 200
        assert (await c.get(f"/api/evaluaciones/{m.ev['publica_ajena']}", headers=h)).status_code == 404
    _correr(esc)


# Rutas del propio titular/encuestado (sus roles se prueban en test_solicitudes_arcop.py y
# test_hu19_encuesta_publica.py); aquí: todas exigen token.
RUTAS_CON_TOKEN_PROPIO = [
    ("GET", "/api/auth/me", "/api/auth/me", {}),
    ("PATCH", "/api/encuesta-publica/email", "/api/encuesta-publica/email", {"json": {"email": None}}),
    ("GET", "/api/encuesta-publica/limites", "/api/encuesta-publica/limites", {}),
    ("POST", "/api/arcop/solicitudes", "/api/arcop/solicitudes", {"json": {"tipo": "acceso", "descripcion": "x" * 30}}),
    ("GET", "/api/arcop/solicitudes", "/api/arcop/solicitudes", {}),
    ("GET", "/api/arcop/solicitudes/{solicitud_id}", "/api/arcop/solicitudes/1", {}),
    ("PATCH", "/api/arcop/solicitudes/{solicitud_id}/estado", "/api/arcop/solicitudes/1/estado",
     {"json": {"estado": "en_revision"}}),
    ("POST", "/api/arcop/solicitudes/{solicitud_id}/prorroga", "/api/arcop/solicitudes/1/prorroga",
     {"json": {"motivo": "x" * 30}}),
    ("POST", "/api/arcop/solicitudes/{solicitud_id}/resolucion", "/api/arcop/solicitudes/1/resolucion",
     {"json": {"resultado": "resuelta", "respuesta": "x" * 30}}),
    ("POST", "/api/arcop/solicitudes/{solicitud_id}/cancelacion", "/api/arcop/solicitudes/1/cancelacion", {}),
    ("POST", "/api/arcop/solicitudes/{solicitud_id}/informacion", "/api/arcop/solicitudes/1/informacion",
     {"json": {"informacion": "x" * 30}}),
    # HU-32: descarga de los datos del titular (roles en test_hu32_exportacion_arcop.py)
    ("GET", "/api/arcop/solicitudes/{solicitud_id}/exportacion", "/api/arcop/solicitudes/1/exportacion", {}),
    # HU-27/31: el usuario temporal pide contratar (sus roles se prueban en test_hu27)
    ("POST", "/api/contratacion/solicitudes", "/api/contratacion/solicitudes",
     {"json": {"evaluacion_id": 1, "nombre": "Ana", "email": "a@b.cl", "autoriza_migracion": True}}),
    ("GET", "/api/contratacion/evaluaciones/{evaluacion_id}/solicitud",
     "/api/contratacion/evaluaciones/1/solicitud", {}),
    # HU-28: cerrar sesión y espacio de la empresa del cliente (roles en test_hu28_sesion.py)
    ("POST", "/api/auth/logout", "/api/auth/logout", {}),
    ("GET", "/api/cliente/empresa", "/api/cliente/empresa", {}),
    # HU-30: situación del contrato del cliente (roles en test_hu30_contrato.py)
    ("GET", "/api/cliente/contrato", "/api/cliente/contrato", {}),
    # HU-29: Mis evaluaciones y Mis documentos (roles en test_hu29_historial_documentos.py)
    ("GET", "/api/cliente/evaluaciones", "/api/cliente/evaluaciones", {}),
    ("POST", "/api/cliente/evaluaciones", "/api/cliente/evaluaciones", {}),
    ("GET", "/api/cliente/documentos", "/api/cliente/documentos", {}),
    ("POST", "/api/cliente/documentos/informes", "/api/cliente/documentos/informes", {"json": {"evaluacion_id": 1}}),
    ("GET", "/api/cliente/documentos/{documento_id}/descarga", "/api/cliente/documentos/1/descarga", {}),
    ("DELETE", "/api/cliente/documentos/{documento_id}", "/api/cliente/documentos/1", {}),
    ("GET", "/api/cliente/documentos/evidencias/{evidencia_id}/descarga",
     "/api/cliente/documentos/evidencias/1/descarga", {}),
    ("DELETE", "/api/cliente/documentos/evidencias/{evidencia_id}", "/api/cliente/documentos/evidencias/1", {}),
    ("DELETE", "/api/cliente/documentos/constancias/{ruta_id}", "/api/cliente/documentos/constancias/1", {}),
    # HU-26: recorrido de módulos (solo cliente con servicio activo; roles en test_hu26_formacion.py)
    ("GET", "/api/formacion/avance", "/api/formacion/avance", {}),
    ("GET", "/api/formacion/modulos/{ruta_id}", "/api/formacion/modulos/1", {}),
    ("POST", "/api/formacion/modulos/{ruta_id}/lecciones/{orden}/vista", "/api/formacion/modulos/1/lecciones/1/vista", {}),
    ("POST", "/api/formacion/modulos/{ruta_id}/verificacion", "/api/formacion/modulos/1/verificacion",
     {"json": {"respuestas": {}}}),
    ("GET", "/api/formacion/modulos/{ruta_id}/constancia", "/api/formacion/modulos/1/constancia", {}),
    # HU-17: remediación con evidencia (roles en test_hu17_remediacion.py)
    ("GET", "/api/remediacion/evaluaciones/{evaluacion_id}", "/api/remediacion/evaluaciones/1", {}),
    ("POST", "/api/remediacion/respuestas/{respuesta_id}/evidencias", "/api/remediacion/respuestas/1/evidencias",
     {"files": {"file": ("p.txt", EVIDENCIA, "text/plain")}, "data": {"estado_declarado": "cumplido"}}),
    ("GET", "/api/remediacion/evidencias/{evidencia_id}", "/api/remediacion/evidencias/1", {}),
    # HU-15: Agente IA Tutor (solo cliente con contrato vigente; roles en test_hu15_tutor.py)
    ("GET", "/api/tutor/contexto", "/api/tutor/contexto", {}),
    ("GET", "/api/tutor/conversaciones", "/api/tutor/conversaciones", {}),
    ("POST", "/api/tutor/conversaciones", "/api/tutor/conversaciones", {"json": {}}),
    ("GET", "/api/tutor/conversaciones/{conversacion_id}", "/api/tutor/conversaciones/1", {}),
    ("PATCH", "/api/tutor/conversaciones/{conversacion_id}", "/api/tutor/conversaciones/1",
     {"json": {"nivel": "Inicial"}}),
    ("DELETE", "/api/tutor/conversaciones/{conversacion_id}", "/api/tutor/conversaciones/1", {}),
    ("POST", "/api/tutor/conversaciones/{conversacion_id}/mensajes", "/api/tutor/conversaciones/1/mensajes",
     {"json": {"texto": "hola"}}),
    # HU-16: borradores de cumplimiento (solo cliente con contrato vigente; roles en test_hu16_borradores.py)
    ("GET", "/api/borradores/plantillas", "/api/borradores/plantillas", {}),
    ("GET", "/api/borradores", "/api/borradores", {}),
    ("POST", "/api/borradores", "/api/borradores", {"json": {"tipo": "politica_llm"}}),
    ("GET", "/api/borradores/{borrador_id}", "/api/borradores/1", {}),
    ("PATCH", "/api/borradores/{borrador_id}", "/api/borradores/1", {"json": {"contenido": "x", "version": 1}}),
    ("GET", "/api/borradores/{borrador_id}/descarga", "/api/borradores/1/descarga", {}),
    ("POST", "/api/borradores/{borrador_id}/consolidacion", "/api/borradores/1/consolidacion",
     {"json": {"version": 1}}),
    ("DELETE", "/api/borradores/{borrador_id}", "/api/borradores/1", {}),
    # HU-34: mapa de datos personales (solo cliente con contrato vigente; roles en test_hu34_mapa_datos.py)
    ("GET", "/api/mapa-datos/catalogo", "/api/mapa-datos/catalogo", {}),
    ("GET", "/api/mapa-datos", "/api/mapa-datos", {}),
    ("POST", "/api/mapa-datos/elementos", "/api/mapa-datos/elementos",
     {"json": {"version": 0, "tipo": "sistema", "nombre": "ERP"}}),
    ("PATCH", "/api/mapa-datos/elementos/{elemento_id}", "/api/mapa-datos/elementos/1", {"json": {"version": 0}}),
    ("DELETE", "/api/mapa-datos/elementos/{elemento_id}", "/api/mapa-datos/elementos/1?version=0", {}),
    ("POST", "/api/mapa-datos/flujos", "/api/mapa-datos/flujos",
     {"json": {"version": 0, "origen_id": 1, "destino_id": 2}}),
    ("PATCH", "/api/mapa-datos/flujos/{flujo_id}", "/api/mapa-datos/flujos/1", {"json": {"version": 0}}),
    ("DELETE", "/api/mapa-datos/flujos/{flujo_id}", "/api/mapa-datos/flujos/1?version=0", {}),
    ("POST", "/api/mapa-datos/revision", "/api/mapa-datos/revision", {"json": {"version": 0, "todo": True}}),
    ("GET", "/api/mapa-datos/plantillas", "/api/mapa-datos/plantillas", {}),
    ("POST", "/api/mapa-datos/plantillas/aplicar", "/api/mapa-datos/plantillas/aplicar",
     {"json": {"version": 0, "codigo": "general"}}),
    ("GET", "/api/mapa-datos/sugerencias", "/api/mapa-datos/sugerencias", {}),
    ("POST", "/api/mapa-datos/sugerencias/restablecer", "/api/mapa-datos/sugerencias/restablecer", {}),
    ("POST", "/api/mapa-datos/sugerencias/{clave}/aceptar", "/api/mapa-datos/sugerencias/llm_externo/aceptar",
     {"json": {"version": 0}}),
    ("POST", "/api/mapa-datos/sugerencias/{clave}/descartar", "/api/mapa-datos/sugerencias/llm_externo/descartar", {}),
    ("GET", "/api/mapa-datos/versiones", "/api/mapa-datos/versiones", {}),
    ("GET", "/api/mapa-datos/versiones/{numero}", "/api/mapa-datos/versiones/1", {}),
    ("POST", "/api/mapa-datos/versiones/{numero}/restaurar", "/api/mapa-datos/versiones/1/restaurar",
     {"json": {"version": 0}}),
    ("GET", "/api/mapa-datos/informe/pdf", "/api/mapa-datos/informe/pdf", {}),
    ("POST", "/api/mapa-datos/informe/enviar", "/api/mapa-datos/informe/enviar", {"json": {}}),
    # HU-35: registro de actividades de tratamiento (solo cliente con contrato vigente; roles en test_hu35_rat.py)
    ("GET", "/api/registro-actividades/catalogo", "/api/registro-actividades/catalogo", {}),
    ("GET", "/api/registro-actividades", "/api/registro-actividades", {}),
    ("POST", "/api/registro-actividades/actividades", "/api/registro-actividades/actividades",
     {"json": {"nombre": "Ventas en línea"}}),
    ("GET", "/api/registro-actividades/actividades/{actividad_id}", "/api/registro-actividades/actividades/1", {}),
    ("PATCH", "/api/registro-actividades/actividades/{actividad_id}", "/api/registro-actividades/actividades/1",
     {"json": {"revision": 1}}),
    ("POST", "/api/registro-actividades/actividades/{actividad_id}/estado",
     "/api/registro-actividades/actividades/1/estado", {"json": {"revision": 1, "accion": "enviar_revision"}}),
    ("GET", "/api/registro-actividades/actividades/{actividad_id}/versiones",
     "/api/registro-actividades/actividades/1/versiones", {}),
    ("GET", "/api/registro-actividades/actividades/{actividad_id}/versiones/{numero}",
     "/api/registro-actividades/actividades/1/versiones/1", {}),
    # HU-36: informe del registro de actividades (solo cliente con contrato vigente; roles en
    # test_hu36_informe_rat.py)
    ("GET", "/api/registro-actividades/informes", "/api/registro-actividades/informes", {}),
    ("POST", "/api/registro-actividades/informes", "/api/registro-actividades/informes", {"json": {}}),
    ("GET", "/api/registro-actividades/informes/verificacion",
     "/api/registro-actividades/informes/verificacion?codigo=CIA-REG-2026-000045-0", {}),
    ("GET", "/api/registro-actividades/informes/{informe_id}/descarga",
     "/api/registro-actividades/informes/1/descarga?formato=pdf", {}),
    ("POST", "/api/registro-actividades/informes/{informe_id}/enviar",
     "/api/registro-actividades/informes/1/enviar", {"json": {"formatos": ["pdf"]}}),
    # HU-37: informe RoPA (solo cliente con contrato vigente; roles en test_hu37_informe_ropa.py)
    ("GET", "/api/registro-actividades/ropa", "/api/registro-actividades/ropa", {}),
    ("PATCH", "/api/registro-actividades/ropa/datos", "/api/registro-actividades/ropa/datos",
     {"json": {"correo": "privacidad@empresa.cl"}}),
    ("POST", "/api/registro-actividades/ropa", "/api/registro-actividades/ropa", {"json": {}}),
    ("GET", "/api/registro-actividades/ropa/{informe_id}/descarga",
     "/api/registro-actividades/ropa/1/descarga?formato=pdf", {}),
    # HU-38: el registro conectado con la evaluación, las brechas y los borradores (solo cliente con contrato
    # vigente; flujo completo en test_hu38_integracion_rat.py)
    ("GET", "/api/registro-actividades/cumplimiento", "/api/registro-actividades/cumplimiento", {}),
    ("POST", "/api/registro-actividades/cumplimiento/evidencia", "/api/registro-actividades/cumplimiento/evidencia",
     {}),
    # HU-40: revisión interna del registro (solo cliente con contrato vigente: el mismo usuario, sin otra
    # cuenta; flujo completo en test_hu40_revision_interna.py)
    ("GET", "/api/registro-actividades/revision", "/api/registro-actividades/revision", {}),
    ("POST", "/api/registro-actividades/revision", "/api/registro-actividades/revision", {}),
    ("POST", "/api/registro-actividades/revision/verificaciones", "/api/registro-actividades/revision/verificaciones",
     {"json": {"clave": "actividad:1", "decision": "verificado"}}),
    ("POST", "/api/registro-actividades/revision/observaciones", "/api/registro-actividades/revision/observaciones",
     {"json": {"clave": "actividad:1", "prioridad": "media", "texto": "Revisar el plazo"}}),
    ("POST", "/api/registro-actividades/revision/observaciones/{observacion_id}/cerrar",
     "/api/registro-actividades/revision/observaciones/1/cerrar", {"json": {"nota": "Se corrigió"}}),
    ("POST", "/api/registro-actividades/revision/observaciones/{observacion_id}/reabrir",
     "/api/registro-actividades/revision/observaciones/1/reabrir", {}),
    ("POST", "/api/registro-actividades/revision/marcar", "/api/registro-actividades/revision/marcar",
     {"json": {"revisor_nombre": "Ana Pérez", "confirmo": True}}),
    ("GET", "/api/registro-actividades/revision/diferencias", "/api/registro-actividades/revision/diferencias", {}),
    ("PATCH", "/api/registro-actividades/revision/configuracion", "/api/registro-actividades/revision/configuracion",
     {"json": {"plazo_meses": 12, "aviso_dias": 30, "recordatorio_correo": True}}),
    ("GET", "/api/registro-actividades/revision/revisiones/{revision_id}",
     "/api/registro-actividades/revision/revisiones/1", {}),
    ("GET", "/api/registro-actividades/revision/revisiones/{revision_id}/constancia",
     "/api/registro-actividades/revision/revisiones/1/constancia", {}),
    ("GET", "/api/registro-actividades/revision/revisiones/{revision_id}/paquete",
     "/api/registro-actividades/revision/revisiones/1/paquete", {}),
    ("POST", "/api/registro-actividades/revision/revisiones/{revision_id}/enviar",
     "/api/registro-actividades/revision/revisiones/1/enviar", {"json": {}}),
    ("POST", "/api/registro-actividades/revision/paquetes/verificacion",
     "/api/registro-actividades/revision/paquetes/verificacion",
     {"files": {"file": ("paquete.zip", b"PK", "application/zip")}}),
    # HU-39: asistente de IA del mapa y del RAT (solo cliente con contrato vigente; roles y flujo
    # completo en test_hu39_asistente_rat.py)
    ("GET", "/api/asistente", "/api/asistente", {}),
    ("POST", "/api/asistente/sesiones", "/api/asistente/sesiones", {"json": {}}),
    ("POST", "/api/asistente/sesiones/{sesion_id}/area", "/api/asistente/sesiones/1/area",
     {"json": {"area": "clientes"}}),
    ("POST", "/api/asistente/sesiones/{sesion_id}/respuestas", "/api/asistente/sesiones/1/respuestas",
     {"json": {"texto": "Usamos un CRM"}}),
    ("POST", "/api/asistente/sesiones/{sesion_id}/cerrar", "/api/asistente/sesiones/1/cerrar", {}),
    ("POST", "/api/asistente/documentos", "/api/asistente/documentos",
     {"files": {"file": ("politica.txt", b"Politica de datos", "text/plain")}}),
    ("POST", "/api/asistente/propuestas/{propuesta_id}/aceptar", "/api/asistente/propuestas/1/aceptar",
     {"json": {}}),
    ("POST", "/api/asistente/propuestas/{propuesta_id}/descartar", "/api/asistente/propuestas/1/descartar",
     {"json": {}}),
]


@pytest.mark.parametrize("metodo,ruta,url,kwargs", RUTAS_CON_TOKEN_PROPIO,
                         ids=[f"{m} {r}" for m, r, _, _ in RUTAS_CON_TOKEN_PROPIO])
def test_ruta_con_token_propio_exige_token(metodo, ruta, url, kwargs):
    async def esc(c):
        r = await c.request(metodo, url, **kwargs)
        assert r.status_code == 401, (url, r.status_code, r.text)
    _correr(esc)


# HU-09: log inmutable. /api/auditoria/* es del Auditor Externo y del admin; /api/admin/auditores
# solo del admin. Sus pruebas de 401, 403 (encuestado, referente, cliente) y 2xx están en
# tests/test_hu09_audit_log.py::test_rutas_hu09_por_rol.
RUTAS_HU09 = [
    ("GET", "/api/auditoria/catalogo"),
    ("GET", "/api/auditoria/registros"),
    ("GET", "/api/auditoria/verificacion"),
    ("GET", "/api/auditoria/lotes"),
    ("GET", "/api/auditoria/exportacion"),
    ("GET", "/api/admin/auditores"),
    ("POST", "/api/admin/auditores"),
    ("PATCH", "/api/admin/auditores/{auditor_id}"),
]


# HU-24: mantenedor de la matriz normativa, solo admin. Sus pruebas de 401 (sin token), 403
# (encuestado, referente y cliente) y 2xx (admin) están en
# tests/test_hu24_matriz_versionada.py::test_rutas_hu24_solo_admin.
RUTAS_HU24 = [
    ("GET", "/api/admin/matriz"),
    ("GET", "/api/admin/matriz/versiones"),
    ("GET", "/api/admin/matriz/versiones/{version_id}"),
    ("POST", "/api/admin/matriz/borrador"),
    ("GET", "/api/admin/matriz/borrador"),
    ("GET", "/api/admin/matriz/borrador/validacion"),
    ("POST", "/api/admin/matriz/borrador/descartar"),
    ("POST", "/api/admin/matriz/borrador/publicar"),
    ("PATCH", "/api/admin/matriz/borrador/controles/{item_id}/aplicabilidad"),
    ("POST", "/api/admin/matriz/borrador/{entidad}"),
    ("PATCH", "/api/admin/matriz/borrador/{entidad}/{item_id}"),
    ("POST", "/api/admin/matriz/borrador/{entidad}/{item_id}/retirar"),
    ("POST", "/api/admin/matriz/borrador/{entidad}/{item_id}/restaurar"),
]


# Correcciones 05-11: rubros desde el panel interno, solo admin. Sus pruebas de 401, 403 y 2xx
# están en tests/test_admin_rubros.py.
RUTAS_RUBROS = [
    ("GET", "/api/admin/rubros"),
    ("POST", "/api/admin/rubros"),
    ("PATCH", "/api/admin/rubros/{rubro_id}"),
]


# HU-25: retención de usuarios temporales vencidos, solo admin. Sus pruebas de 401, 403 y 2xx
# están en tests/test_hu25_retencion.py::test_api_retencion_solo_admin.
RUTAS_RETENCION = [
    ("GET", "/api/admin/retencion"),
    ("PATCH", "/api/admin/retencion"),
    ("GET", "/api/admin/retencion/vista-previa"),
    ("POST", "/api/admin/retencion/simulacion"),
    ("POST", "/api/admin/retencion/ejecuciones"),
    ("GET", "/api/admin/retencion/ejecuciones"),
]


# HU-41: registro de tratamiento de la propia plataforma, solo admin. Sus pruebas de 401, 403 y 2xx
# están en tests/test_hu41_registro_plataforma.py::test_api_solo_admin.
RUTAS_PRIVACIDAD_PLATAFORMA = [
    ("GET", "/api/admin/privacidad-plataforma"),
    ("GET", "/api/admin/privacidad-plataforma/actividades/{clave}"),
    ("PATCH", "/api/admin/privacidad-plataforma/ropa-datos"),
    ("POST", "/api/admin/privacidad-plataforma/informes"),
    ("GET", "/api/admin/privacidad-plataforma/informes/verificacion"),
    ("GET", "/api/admin/privacidad-plataforma/informes/{informe_id}/descarga"),
    ("GET", "/api/admin/privacidad-plataforma/mapa/descarga"),
]


# ===================================================================== C3: cobertura de la matriz
def test_todas_las_rutas_estan_clasificadas():
    """
    Cada endpoint de la API debe estar en una matriz de este archivo. Si agregas una ruta,
    decide quién puede usarla y agrégala a la lista que corresponda (con su prueba).
    """
    from fastapi.routing import APIRoute
    from app.main import app

    existentes = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    clasificadas = (
        {(m, r) for m, r, _ in RUTAS_CON_ALCANCE}
        | {(m, r) for m, r, _ in RUTAS_SOLO_ADMIN}
        | {(m, r) for m, r, _, _ in RUTAS_PUBLICAS}
        | {(m, r) for m, r, _, _ in RUTAS_CON_TOKEN_PROPIO}
        | set(RUTAS_DE_ACCESO)
        | set(RUTAS_ADMIN_HU27)
        | set(RUTAS_HU09)
        | set(RUTAS_HU24)
        | set(RUTAS_RUBROS)
        | set(RUTAS_RETENCION)
        | set(RUTAS_PRIVACIDAD_PLATAFORMA)
        | {("GET", "/api/evaluaciones"), ("GET", "/api/evaluaciones/benchmark")}
    )
    assert existentes - clasificadas == set(), "Rutas sin clasificar en HU-20"
    assert clasificadas - existentes == set(), "La matriz de HU-20 nombra rutas que ya no existen"


# ===================================================================== interruptor y producción
def test_interruptor_solo_desarrollo_abre_invitaciones_pero_no_lo_demas(monkeypatch):
    async def esc(c):
        m = await _armar(c)
        monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", False)
        assert (await c.get(f"/api/evaluaciones/{INVITACION_ID}")).status_code == 200
        assert (await c.get("/api/evaluaciones")).status_code == 200
        # lo público y lo de admin siguen cerrados
        assert (await c.get(f"/api/evaluaciones/{m.ev['publica']}")).status_code == 401
        assert (await c.get(f"/api/respuestas/{m.resp['publica']}")).status_code == 401
        assert (await c.get("/api/ia/metricas")).status_code == 401
        assert (await c.get("/api/seguridad/eventos")).status_code == 401
        lista = (await c.get("/api/evaluaciones?page=1&size=100")).json()["items"]
        assert m.ev["publica"] not in {e["id"] for e in lista}
    _correr(esc)


def test_exigir_token_no_se_puede_apagar_en_produccion():
    from app.core.config import Settings
    base = dict(DATABASE_URL="x", DATABASE_URL_SYNC="x", REDIS_URL="x", GROQ_API_KEY="x",
                APP_ENV="production", ENTITY_MAP_KEY="k", AUTH_SECRET="a" * 32,
                TURNSTILE_SECRET_KEY="t", BFF_SHARED_SECRET="b" * 32, CORREO_MODO="desactivado",
                DB_APP_PASSWORD="p" * 20)  # HU-09: clave propia del rol de la app en producción
    assert Settings(_env_file=None, **base).EXIGIR_TOKEN_EVALUACIONES is True  # por defecto
    with pytest.raises(ValueError, match="EXIGIR_TOKEN_EVALUACIONES"):
        Settings(_env_file=None, EXIGIR_TOKEN_EVALUACIONES=False, **base)