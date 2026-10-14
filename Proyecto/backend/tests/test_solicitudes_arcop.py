"""
QA - Solicitudes de derechos ARCOP (historia de usuario del Titular de Datos Personales).

Ejecutar desde Proyecto/backend/:
  pytest tests/test_solicitudes_arcop.py -v

Usa el arnés en proceso (_api_harness.py): app FastAPI real + SQLite en memoria.
No requiere PostgreSQL, Redis ni Groq. En modo live (LATENCIA_BASE_URL) se omite,
porque los tokens se firman con el AUTH_SECRET del servidor.

Cubre:
  - login de administrador y acceso del titular (app/api/routes/auth.py)
  - firma/expiración de tokens, roles y revocación (app/core/autenticacion.py)
  - anonimización al aprobar una supresión
  - plazos configurables (ARCOP_PLAZO_*_DIAS)
  - máquina de estados (TRANSICIONES_ARCOP)
  - aislamiento entre titulares, permisos por rol, validaciones y trazabilidad
"""
import asyncio
import os
import time

import pytest

pytest.importorskip("httpx")

from _api_harness import ADMIN_EMAIL, ADMIN_PASSWORD, MODO, cliente_api  # noqa: E402

from app.core import autenticacion as auth  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.domain.models.solicitud_arcop import (  # noqa: E402
    TRANSICIONES_ARCOP, EstadoSolicitudARCOP, transicion_permitida,
)

SECRETO = "secreto-solo-para-pytest-0123456789abcdef"
TITULAR_ID = 1       # usuarios sembrados por el arnés (_api_harness._sembrar)
OTRO_TITULAR_ID = 2
ADMIN_ID = 1
DESCRIPCION = "Solicito acceso a todos mis datos personales tratados por la plataforma."


@pytest.fixture(autouse=True)
def _auth_secret(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SECRET", SECRETO)
    monkeypatch.setattr(settings, "ARCOP_PLAZO_RESPUESTA_DIAS", None)
    monkeypatch.setattr(settings, "ARCOP_PLAZO_INFORMACION_DIAS", None)


def _h(usuario_id: int, rol: str) -> dict:
    return {"Authorization": f"Bearer {auth.emitir_token(usuario_id, rol, secreto=SECRETO)}"}


TITULAR = lambda: _h(TITULAR_ID, "referente")  # noqa: E731
OTRO = lambda: _h(OTRO_TITULAR_ID, "referente")  # noqa: E731
ADMIN = lambda: _h(ADMIN_ID, "admin_therion")  # noqa: E731


def _correr(escenario):
    if MODO == "live":
        pytest.skip("Pruebas ARCOP solo en proceso (los tokens dependen del AUTH_SECRET del servidor).")
    pytest.importorskip("aiosqlite")

    async def _f():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_f())


async def _crear(c, tipo="acceso", descripcion=DESCRIPCION):
    r = await c.post("/api/arcop/solicitudes", json={"tipo": tipo, "descripcion": descripcion}, headers=TITULAR())
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- unitarias
def test_token_valido_y_manipulado():
    tok = auth.emitir_token(5, "referente", secreto=SECRETO)
    assert auth.verificar_token(tok, SECRETO) == auth.Actor(id=5, rol="referente")
    with pytest.raises(auth.TokenInvalidoError):
        auth.verificar_token(tok, "otro-secreto")
    cuerpo, firma = tok.split(".")
    falso = auth._b64(b'{"sub":6,"rol":"admin_therion","exp":9999999999}')
    with pytest.raises(auth.TokenInvalidoError):
        auth.verificar_token(f"{falso}.{firma}", SECRETO)


def test_token_expirado(monkeypatch):
    tok = auth.emitir_token(5, "referente", ttl_min=1, secreto=SECRETO)
    monkeypatch.setattr(time, "time", lambda: 10**12)
    with pytest.raises(auth.TokenInvalidoError, match="expirado"):
        auth.verificar_token(tok, SECRETO)


def test_maquina_de_estados():
    E = EstadoSolicitudARCOP
    assert transicion_permitida("recibida", "en_revision")
    assert transicion_permitida("en_proceso", "resuelta")
    assert not transicion_permitida("recibida", "resuelta")       # no se resuelve sin procesar
    assert not transicion_permitida("en_proceso", "cancelada")    # el titular ya no desiste
    for final in E.finales():
        assert TRANSICIONES_ARCOP[final] == set()
    assert set(TRANSICIONES_ARCOP) == set(E.valores())


# ---------------------------------------------------------------- autenticación
def test_sin_token_401_y_token_invalido_401():
    async def esc(c):
        assert (await c.get("/api/arcop/solicitudes")).status_code == 401
        r = await c.get("/api/arcop/solicitudes", headers={"Authorization": "Bearer abc.def"})
        assert r.status_code == 401
        assert r.json()["detail"]["codigo"] == "TOKEN_INVALIDO"
    _correr(esc)


def test_sin_auth_secret_responde_503(monkeypatch):
    async def esc(c):
        monkeypatch.setattr(settings, "AUTH_SECRET", None)
        r = await c.get("/api/arcop/solicitudes", headers=TITULAR())
        assert r.status_code == 503
    _correr(esc)


# ---------------------------------------------------------------- creación y validaciones
def test_crear_solicitud_queda_recibida_con_historial():
    async def esc(c):
        s = await _crear(c, "rectificacion")
        assert s["estado"] == "recibida"
        assert s["tipo"] == "rectificacion"
        assert s["usuario_temporal_id"] == TITULAR_ID
        assert s["fecha_cierre"] is None
        assert [e["tipo_evento"] for e in s["historial"]] == ["creada"]
        assert s["historial"][0]["actor_id"] is None   # el titular no ve ids de actores
        assert set(s["transiciones_posibles"]) == {"en_revision", "rechazada", "cancelada"}
    _correr(esc)


@pytest.mark.parametrize("tipo", ["acceso", "rectificacion", "supresion", "oposicion", "portabilidad", "bloqueo"])
def test_crear_los_seis_tipos(tipo):
    async def esc(c):
        assert (await _crear(c, tipo))["tipo"] == tipo
    _correr(esc)


@pytest.mark.parametrize("body,fragmento", [
    ({"tipo": "olvido", "descripcion": DESCRIPCION}, "Tipo de solicitud inválido"),
    ({"tipo": "acceso", "descripcion": "   "}, "obligatorio"),
    ({"tipo": "acceso", "descripcion": "corto"}, "al menos"),
    ({"tipo": "acceso", "descripcion": "x" * 5001}, "no puede superar"),
])
def test_crear_invalida_400(body, fragmento):
    async def esc(c):
        r = await c.post("/api/arcop/solicitudes", json=body, headers=TITULAR())
        assert r.status_code == 400 and fragmento in r.text
    _correr(esc)


def test_admin_no_crea_y_token_de_usuario_inexistente_401():
    async def esc(c):
        body = {"tipo": "acceso", "descripcion": DESCRIPCION}
        assert (await c.post("/api/arcop/solicitudes", json=body, headers=ADMIN())).status_code == 403
        r = await c.post("/api/arcop/solicitudes", json=body, headers=_h(999, "referente"))
        assert r.status_code == 401 and r.json()["detail"]["codigo"] == "USUARIO_DESHABILITADO"
        r = await c.get("/api/arcop/solicitudes", headers=_h(999, "admin_therion"))
        assert r.status_code == 401
    _correr(esc)


# ---------------------------------------------------------------- aislamiento entre titulares
def test_titular_no_ve_ni_modifica_solicitudes_ajenas():
    async def esc(c):
        s = await _crear(c)
        sid = s["id_solicitud"]
        assert (await c.get(f"/api/arcop/solicitudes/{sid}", headers=OTRO())).status_code == 404
        assert (await c.post(f"/api/arcop/solicitudes/{sid}/cancelacion", json={}, headers=OTRO())).status_code == 404
        r = await c.get("/api/arcop/solicitudes", headers=OTRO())
        assert r.json()["total"] == 0
        # aunque intente filtrar por el id del otro titular
        r = await c.get(f"/api/arcop/solicitudes?usuario_temporal_id={TITULAR_ID}", headers=OTRO())
        assert r.json()["total"] == 0
        # el dueño y el admin sí la ven
        assert (await c.get(f"/api/arcop/solicitudes/{sid}", headers=TITULAR())).status_code == 200
        assert (await c.get(f"/api/arcop/solicitudes/{sid}", headers=ADMIN())).status_code == 200
    _correr(esc)


def test_listado_no_expone_texto_libre_y_pagina():
    async def esc(c):
        for _ in range(3):
            await _crear(c)
        r = await c.get("/api/arcop/solicitudes?size=2", headers=TITULAR())
        body = r.json()
        assert body["total"] == 3 and body["pages"] == 2 and len(body["items"]) == 2
        assert "descripcion" not in body["items"][0] and "respuesta" not in body["items"][0]
        assert (await c.get("/api/arcop/solicitudes?estado=xx", headers=TITULAR())).status_code == 400
    _correr(esc)


# ---------------------------------------------------------------- permisos por rol
def test_titular_no_cambia_estado_ni_resuelve():
    async def esc(c):
        sid = (await _crear(c))["id_solicitud"]
        r = await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": "en_revision"}, headers=TITULAR())
        assert r.status_code == 403
        r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion",
                         json={"resultado": "resuelta", "respuesta": "Se entregan los datos."}, headers=TITULAR())
        assert r.status_code == 403
    _correr(esc)


def test_admin_no_cancela_por_el_titular():
    async def esc(c):
        sid = (await _crear(c))["id_solicitud"]
        assert (await c.post(f"/api/arcop/solicitudes/{sid}/cancelacion", json={}, headers=ADMIN())).status_code == 403
    _correr(esc)


# ---------------------------------------------------------------- ciclo de vida
def test_ciclo_completo_con_pedido_de_informacion_y_resolucion():
    async def esc(c):
        sid = (await _crear(c, "rectificacion"))["id_solicitud"]
        base = f"/api/arcop/solicitudes/{sid}"

        r = await c.patch(f"{base}/estado", json={"estado": "en_revision"}, headers=ADMIN())
        assert r.status_code == 200 and r.json()["estado"] == "en_revision"

        # pedir información exige comentario
        r = await c.patch(f"{base}/estado", json={"estado": "pendiente_informacion"}, headers=ADMIN())
        assert r.status_code == 400
        r = await c.patch(f"{base}/estado",
                          json={"estado": "pendiente_informacion", "comentario": "Indique qué datos desea suprimir."},
                          headers=ADMIN())
        assert r.json()["estado"] == "pendiente_informacion"

        r = await c.post(f"{base}/informacion", json={"informacion": "Mi correo y mi cargo registrados."},
                         headers=TITULAR())
        assert r.status_code == 200 and r.json()["estado"] == "en_revision"

        await c.patch(f"{base}/estado", json={"estado": "en_proceso"}, headers=ADMIN())
        r = await c.post(f"{base}/resolucion",
                         json={"resultado": "resuelta", "respuesta": "Se suprimieron los datos indicados."},
                         headers=ADMIN())
        s = r.json()
        assert r.status_code == 200 and s["estado"] == "resuelta"
        assert s["respuesta"] == "Se suprimieron los datos indicados."
        assert s["fecha_cierre"] is not None and s["transiciones_posibles"] == []
        assert [e["estado_nuevo"] for e in s["historial"]] == [
            "recibida", "en_revision", "pendiente_informacion", "en_revision", "en_proceso", "resuelta",
        ]
        assert all(e["actor_id"] is not None for e in s["historial"])  # admin ve actores

        # estado final: nada más es posible
        r = await c.patch(f"{base}/estado", json={"estado": "en_revision"}, headers=ADMIN())
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "TRANSICION_INVALIDA"
        assert (await c.post(f"{base}/cancelacion", json={}, headers=TITULAR())).status_code == 409
    _correr(esc)


def test_transiciones_invalidas():
    async def esc(c):
        sid = (await _crear(c))["id_solicitud"]
        base = f"/api/arcop/solicitudes/{sid}"
        # no se resuelve sin pasar por en_proceso
        r = await c.post(f"{base}/resolucion", json={"resultado": "resuelta", "respuesta": "Datos entregados."},
                         headers=ADMIN())
        assert r.status_code == 409
        assert r.json()["detail"]["permitidas"] == ["cancelada", "en_revision", "rechazada"]
        # los estados finales no van por PATCH /estado
        r = await c.patch(f"{base}/estado", json={"estado": "resuelta"}, headers=ADMIN())
        assert r.status_code == 400
        # aportar información solo en pendiente_informacion
        r = await c.post(f"{base}/informacion", json={"informacion": "Información adicional."}, headers=TITULAR())
        assert r.status_code == 409
        # resolución sin texto
        r = await c.post(f"{base}/resolucion", json={"resultado": "rechazada", "respuesta": ""}, headers=ADMIN())
        assert r.status_code == 400
    _correr(esc)


def test_rechazo_y_cancelacion():
    async def esc(c):
        s1 = (await _crear(c))["id_solicitud"]
        r = await c.post(f"/api/arcop/solicitudes/{s1}/resolucion",
                         json={"resultado": "rechazada", "respuesta": "No se pudo verificar la solicitud."},
                         headers=ADMIN())
        assert r.json()["estado"] == "rechazada" and r.json()["fecha_cierre"]

        s2 = (await _crear(c))["id_solicitud"]
        r = await c.post(f"/api/arcop/solicitudes/{s2}/cancelacion", json={"motivo": "Ya no la necesito."},
                         headers=TITULAR())
        s = r.json()
        assert s["estado"] == "cancelada" and s["historial"][-1]["comentario"] == "Ya no la necesito."

        r = await c.get("/api/arcop/solicitudes?estado=cancelada", headers=ADMIN())
        assert r.json()["total"] == 1
    _correr(esc)


def test_catalogo():
    async def esc(c):
        r = await c.get("/api/arcop/catalogo")
        assert r.status_code == 200
        assert len(r.json()["tipos"]) == 6
    _correr(esc)


# ---------------------------------------------------------------- login y acceso
def test_password_hash():
    h = auth.hash_password("una-clave-larga", iteraciones=1000)
    assert h.startswith("pbkdf2_sha256$1000$") and "una-clave-larga" not in h
    assert auth.verificar_password("una-clave-larga", h)
    assert not auth.verificar_password("otra", h)
    assert not auth.verificar_password("x", "basura")


def test_login_admin_y_gestion():
    async def esc(c):
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        assert r.json()["rol"] == "admin_therion"
        r = await c.get("/api/arcop/solicitudes", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        me = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json() == {"usuario_id": ADMIN_ID, "rol": "admin_therion"}
        # errores genéricos: no revelan si el email existe
        r1 = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "mala"})
        r2 = await c.post("/api/auth/login", json={"email": "nadie@example.com", "password": "mala"})
        assert r1.status_code == r2.status_code == 401
        assert r1.json() == r2.json()
    _correr(esc)


def test_acceso_titular_con_invitacion():
    async def esc(c):
        r = await c.post("/api/auth/titular", json={"usuario_temporal_id": TITULAR_ID, "email": " QA@example.com "})
        assert r.status_code == 200 and r.json()["rol"] == "referente"
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = await c.post("/api/arcop/solicitudes", json={"tipo": "acceso", "descripcion": DESCRIPCION}, headers=h)
        assert r.status_code == 201
        # email que no corresponde a ese id
        r = await c.post("/api/auth/titular", json={"usuario_temporal_id": TITULAR_ID, "email": "qa2@example.com"})
        assert r.status_code == 401
        r = await c.post("/api/auth/titular", json={"usuario_temporal_id": 999, "email": "qa@example.com"})
        assert r.status_code == 401
    _correr(esc)


# ---------------------------------------------------------------- anonimización
async def _llevar_a_en_proceso(c, sid):
    for estado in ("en_revision", "en_proceso"):
        r = await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": estado}, headers=ADMIN())
        assert r.status_code == 200, r.text


def test_supresion_resuelta_anonimiza_datos_del_titular():
    async def esc(c):
        # Datos personales del titular 1: una respuesta con justificación y una evidencia
        r = await c.post("/api/respuestas/", json={
            "evaluacion_id": 1, "matriz_control_id": 1, "estado_clasificacion": "cumplido",
            "justificacion": "Política aprobada por Juan Pérez, gerente de TI.",
        })
        assert r.status_code == 201, r.text
        rid = r.json()["id_respuesta"]
        nombre = "evidencia_supresion_arcop_qa.txt"
        r = await c.post(f"/api/respuestas/{rid}/evidencias",
                         files={"file": (nombre, b"Politica firmada por Juan Perez", "text/plain")})
        assert r.status_code == 202, r.text
        assert any(f.endswith(nombre) for f in os.listdir(settings.STORAGE_DIR))

        otra = await _crear(c, "acceso")   # otra solicitud del mismo titular
        sid = (await _crear(c, "supresion"))["id_solicitud"]
        await _llevar_a_en_proceso(c, sid)
        r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion",
                         json={"resultado": "resuelta", "respuesta": "Se anonimizaron sus datos personales."},
                         headers=ADMIN())
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["estado"] == "resuelta" and s["descripcion"] == "[anonimizado]"
        assert [e["tipo_evento"] for e in s["historial"]][-2:] == ["resolucion", "anonimizacion"]
        assert "respuestas=1" in s["historial"][-1]["comentario"]
        assert "evidencias=1" in s["historial"][-1]["comentario"]

        # textos y archivos borrados; clasificaciones conservadas
        resp = (await c.get(f"/api/respuestas/{rid}")).json()
        assert resp["justificacion_usuario"] is None
        assert resp["estado_clasificacion"] == "cumplido"
        assert resp["evidencias"][0]["nombre_archivo"] == "[anonimizado]"
        assert not any(f.endswith(nombre) for f in os.listdir(settings.STORAGE_DIR))

        # la otra solicitud del titular también queda anonimizada
        r = await c.get(f"/api/arcop/solicitudes/{otra['id_solicitud']}", headers=ADMIN())
        assert r.json()["descripcion"] == "[anonimizado]"

        # el titular pierde el acceso
        assert (await c.get("/api/arcop/solicitudes", headers=TITULAR())).status_code == 401
        r = await c.post("/api/auth/titular", json={"usuario_temporal_id": TITULAR_ID, "email": "qa@example.com"})
        assert r.status_code == 401
        # otros titulares no se ven afectados
        assert (await c.get("/api/arcop/solicitudes", headers=OTRO())).status_code == 200
    _correr(esc)


@pytest.mark.parametrize("tipo,resultado", [("supresion", "rechazada"), ("acceso", "resuelta")])
def test_sin_anonimizacion_si_no_es_supresion_aprobada(tipo, resultado):
    async def esc(c):
        sid = (await _crear(c, tipo))["id_solicitud"]
        await _llevar_a_en_proceso(c, sid)
        r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion",
                         json={"resultado": resultado, "respuesta": "Respuesta al titular de la solicitud."},
                         headers=ADMIN())
        assert r.status_code == 200
        assert r.json()["descripcion"] == DESCRIPCION
        assert "anonimizacion" not in [e["tipo_evento"] for e in r.json()["historial"]]
        assert (await c.get("/api/arcop/solicitudes", headers=TITULAR())).status_code == 200
    _correr(esc)


# ---------------------------------------------------------------- plazos
def test_sin_plazos_configurados_no_hay_fechas_limite():
    async def esc(c):
        s = await _crear(c)
        assert s["fecha_limite_respuesta"] is None and s["plazo_vencido"] is False
        cat = (await c.get("/api/arcop/catalogo")).json()
        assert cat["plazo_respuesta_dias"] is None
    _correr(esc)


def test_plazos_configurados_y_vencidas(monkeypatch):
    async def esc(c):
        monkeypatch.setattr(settings, "ARCOP_PLAZO_RESPUESTA_DIAS", 10)
        monkeypatch.setattr(settings, "ARCOP_PLAZO_INFORMACION_DIAS", 5)
        s = await _crear(c)
        assert s["fecha_limite_respuesta"] is not None and s["plazo_vencido"] is False
        sid = s["id_solicitud"]
        await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": "en_revision"}, headers=ADMIN())
        r = await c.patch(f"/api/arcop/solicitudes/{sid}/estado",
                          json={"estado": "pendiente_informacion", "comentario": "Indique el periodo."},
                          headers=ADMIN())
        assert r.json()["fecha_limite_informacion"] is not None
        r = await c.post(f"/api/arcop/solicitudes/{sid}/informacion",
                         json={"informacion": "Periodo 2025 completo."}, headers=TITULAR())
        assert r.json()["fecha_limite_informacion"] is None   # se limpia al salir de pendiente

        # una solicitud con plazo ya vencido aparece en ?vencidas=true
        monkeypatch.setattr(settings, "ARCOP_PLAZO_RESPUESTA_DIAS", -1)
        vencida = await _crear(c, "bloqueo")
        assert vencida["plazo_vencido"] is True
        r = await c.get("/api/arcop/solicitudes?vencidas=true", headers=ADMIN())
        assert [x["id_solicitud"] for x in r.json()["items"]] == [vencida["id_solicitud"]]
    _correr(esc)
