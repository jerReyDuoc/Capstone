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
  - plazos legales (30 días corridos, prórroga única, bloqueo en 2 días hábiles)
  - código de seguimiento único y consulta pública sin datos personales
  - acceso del encuestado anónimo de la encuesta pública (clave de la evaluación)
  - máquina de estados (TRANSICIONES_ARCOP)
  - aislamiento entre titulares, permisos por rol, validaciones y trazabilidad
"""
import asyncio
import os
import re
import time
from datetime import datetime, timedelta

import pytest

pytest.importorskip("httpx")

from _api_harness import (  # noqa: E402
    ADMIN_EMAIL, ADMIN_PASSWORD, EVAL_NA_ID, MODO, body_filtro, cliente_api,
)

from app.core import autenticacion as auth  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.domain.models.solicitud_arcop import (  # noqa: E402
    TRANSICIONES_ARCOP, EstadoSolicitudARCOP, transicion_permitida,
)
from app.application.use_cases.gestionar_solicitud_arcop import (  # noqa: E402
    _sumar_dias_habiles, normalizar_codigo, nuevo_codigo_seguimiento,
)
from app.application.use_cases.clave_acceso_encuestado import (  # noqa: E402
    hash_clave, normalizar_clave, nueva_clave, verificar_clave,
)

SECRETO = "secreto-solo-para-pytest-0123456789abcdef"
TITULAR_ID = 1       # usuarios sembrados por el arnés (_api_harness._sembrar)
OTRO_TITULAR_ID = 2
ADMIN_ID = 1
DESCRIPCION = "Solicito acceso a todos mis datos personales tratados por la plataforma."


@pytest.fixture(autouse=True)
def _auth_secret(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SECRET", SECRETO)
    # Plazos legales por defecto (Ley 21.719), aunque el .env del equipo los cambie
    monkeypatch.setattr(settings, "ARCOP_PLAZO_RESPUESTA_DIAS", 30)
    monkeypatch.setattr(settings, "ARCOP_PLAZO_PRORROGA_DIAS", 30)
    monkeypatch.setattr(settings, "ARCOP_PLAZO_BLOQUEO_DIAS_HABILES", 2)
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
        async with cliente_api(rol=None) as c:
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
    # HU-20: los datos y su verificación los maneja un admin (el titular pierde el acceso)
    async def esc(c):
        # Datos personales del titular 1: una respuesta con justificación y una evidencia
        # (HU-01: antes de responder hay que completar el filtro de aplicabilidad)
        r = await c.post("/api/evaluaciones/1/filtro", json=body_filtro(True), headers=ADMIN())
        assert r.status_code == 200, r.text
        r = await c.post("/api/respuestas/", headers=ADMIN(), json={
            "evaluacion_id": 1, "matriz_control_id": 1, "estado_clasificacion": "cumplido",
            "justificacion": "Política aprobada por Juan Pérez, gerente de TI.",
        })
        assert r.status_code == 201, r.text
        rid = r.json()["id_respuesta"]
        nombre = "evidencia_supresion_arcop_qa.txt"
        antes = set(os.listdir(settings.STORAGE_DIR))
        r = await c.post(f"/api/respuestas/{rid}/evidencias",
                         files={"file": (nombre, b"Politica firmada por Juan Perez", "text/plain")}, headers=ADMIN())
        assert r.status_code == 202, r.text
        # HU-06: en disco el nombre es un UUID (sin el nombre original) y el contenido va cifrado
        nuevos = set(os.listdir(settings.STORAGE_DIR)) - antes
        assert len(nuevos) == 1 and not any(nombre in f for f in nuevos)

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
        resp = (await c.get(f"/api/respuestas/{rid}", headers=ADMIN())).json()
        assert resp["justificacion_usuario"] is None
        assert resp["estado_clasificacion"] == "cumplido"
        assert resp["evidencias"][0]["nombre_archivo"] == "[anonimizado]"
        assert not (nuevos & set(os.listdir(settings.STORAGE_DIR)))   # archivo borrado

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
def test_plazos_desactivados_no_hay_fechas_limite(monkeypatch):
    async def esc(c):
        monkeypatch.setattr(settings, "ARCOP_PLAZO_RESPUESTA_DIAS", None)
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
        vencida = await _crear(c, "acceso")
        assert vencida["plazo_vencido"] is True
        r = await c.get("/api/arcop/solicitudes?vencidas=true", headers=ADMIN())
        assert [x["id_solicitud"] for x in r.json()["items"]] == [vencida["id_solicitud"]]
    _correr(esc)


# ================================================================ HU-08 v3
# ---------------------------------------------------------------- unitarias
_PATRON_CODIGO = re.compile(r"^ARC-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$")


def _iso(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", ""))


def test_codigo_formato_y_normalizacion():
    codigos = {nuevo_codigo_seguimiento() for _ in range(500)}
    assert len(codigos) == 500 and all(_PATRON_CODIGO.match(c) for c in codigos)
    assert normalizar_codigo("arc-7k3f-9qx2") == "ARC-7K3F-9QX2"
    assert normalizar_codigo(" ARC 7K3F 9QX2 ") == "ARC-7K3F-9QX2"
    assert normalizar_codigo("7k3f9qx2") == "ARC-7K3F-9QX2"
    assert normalizar_codigo("ARC-OOII-LL00") == "ARC-0011-1100"   # O->0, I/L->1
    assert normalizar_codigo("ARC-123") == ""


def test_dias_habiles_saltan_fin_de_semana():
    viernes = datetime(2026, 10, 16, 10, 0)
    assert _sumar_dias_habiles(viernes, 2) == datetime(2026, 10, 20, 10, 0)   # martes
    lunes = datetime(2026, 10, 19, 10, 0)
    assert _sumar_dias_habiles(lunes, 2) == datetime(2026, 10, 21, 10, 0)     # miércoles
    sabado = datetime(2026, 10, 17, 10, 0)
    assert _sumar_dias_habiles(sabado, 2) == datetime(2026, 10, 20, 10, 0)    # martes
    assert _sumar_dias_habiles(lunes, None) is None


def test_clave_encuestado_normalizada_y_hasheada():
    clave = nueva_clave()
    assert re.match(r"^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$", clave)
    h = hash_clave(clave)
    assert clave not in h and normalizar_clave(clave) not in h
    assert verificar_clave(clave.lower().replace("-", " "), h)
    assert not verificar_clave(nueva_clave(), h)
    assert not verificar_clave(clave, None)


# ---------------------------------------------------------------- código de seguimiento
def test_cada_solicitud_tiene_codigo_unico():
    async def esc(c):
        a, b = await _crear(c), await _crear(c)
        assert _PATRON_CODIGO.match(a["codigo_seguimiento"])
        assert a["codigo_seguimiento"] != b["codigo_seguimiento"]
        r = await c.get("/api/arcop/solicitudes", headers=ADMIN())
        assert {x["codigo_seguimiento"] for x in r.json()["items"]} >= {a["codigo_seguimiento"], b["codigo_seguimiento"]}
    _correr(esc)


def test_seguimiento_publico_sin_login_y_sin_datos_personales():
    async def esc(c):
        s = await _crear(c, "rectificacion")
        codigo = s["codigo_seguimiento"]
        r = await c.get(f"/api/arcop/seguimiento/{codigo.lower().replace('-', '')}")   # sin token
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["codigo_seguimiento"] == codigo and body["estado"] == "recibida"
        assert body["tipo"] == "rectificacion" and body["prorrogada"] is False
        for prohibido in ("descripcion", "respuesta", "id_solicitud", "usuario_temporal_id",
                          "evaluacion_id", "historial"):
            assert prohibido not in body
        assert (await c.get("/api/arcop/seguimiento/ARC-0000-0000")).status_code == 404
        assert (await c.get("/api/arcop/seguimiento/basura")).status_code == 404
    _correr(esc)


# ---------------------------------------------------------------- plazos legales
def test_plazo_legal_por_defecto_30_dias_corridos():
    async def esc(c):
        s = await _crear(c, "acceso")
        dif = _iso(s["fecha_limite_respuesta"]) - _iso(s["fecha_creacion"])
        assert dif == timedelta(days=30)
        cat = (await c.get("/api/arcop/catalogo")).json()
        assert cat["plazo_respuesta_dias"] == 30 and cat["plazo_respuesta_tipo"] == "corridos"
        assert cat["plazo_prorroga_dias"] == 30 and cat["plazo_bloqueo_dias_habiles"] == 2
    _correr(esc)


def test_bloqueo_se_responde_en_2_dias_habiles():
    async def esc(c):
        s = await _crear(c, "bloqueo")
        creada, limite = _iso(s["fecha_creacion"]), _iso(s["fecha_limite_respuesta"])
        assert limite == _sumar_dias_habiles(creada, 2)
        assert limite.weekday() < 5 and timedelta(days=2) <= limite - creada <= timedelta(days=4)
    _correr(esc)


def test_prorroga_unica_con_motivo(monkeypatch):
    async def esc(c):
        s = await _crear(c, "portabilidad")
        sid, limite = s["id_solicitud"], _iso(s["fecha_limite_respuesta"])
        url = f"/api/arcop/solicitudes/{sid}/prorroga"
        motivo = {"motivo": "Requiere reunir datos de varios sistemas."}

        assert (await c.post(url, json=motivo, headers=TITULAR())).status_code == 403
        assert (await c.post(url, json={"motivo": "corto"}, headers=ADMIN())).status_code == 400

        r = await c.post(url, json=motivo, headers=ADMIN())
        assert r.status_code == 200, r.text
        p = r.json()
        assert _iso(p["fecha_limite_respuesta"]) - limite == timedelta(days=30)
        assert p["fecha_prorroga"] is not None and p["estado"] == "recibida"
        assert p["historial"][-1]["tipo_evento"] == "prorroga"
        assert "varios sistemas" in p["historial"][-1]["comentario"]

        r = await c.post(url, json=motivo, headers=ADMIN())                 # segunda vez
        assert r.status_code == 409 and "una" in r.json()["detail"]["mensaje"]
        seg = (await c.get(f"/api/arcop/seguimiento/{s['codigo_seguimiento']}")).json()
        assert seg["prorrogada"] is True

        b = await _crear(c, "bloqueo")                                       # no aplica al bloqueo
        assert (await c.post(f"/api/arcop/solicitudes/{b['id_solicitud']}/prorroga",
                             json=motivo, headers=ADMIN())).status_code == 400

        monkeypatch.setattr(settings, "ARCOP_PLAZO_RESPUESTA_DIAS", -1)      # ya vencida
        v = await _crear(c, "acceso")
        r = await c.post(f"/api/arcop/solicitudes/{v['id_solicitud']}/prorroga", json=motivo, headers=ADMIN())
        assert r.status_code == 409 and "venció" in r.json()["detail"]["mensaje"]
    _correr(esc)


def test_no_se_prorroga_una_solicitud_cerrada():
    async def esc(c):
        sid = (await _crear(c))["id_solicitud"]
        await c.post(f"/api/arcop/solicitudes/{sid}/cancelacion", json={}, headers=TITULAR())
        r = await c.post(f"/api/arcop/solicitudes/{sid}/prorroga",
                         json={"motivo": "Motivo suficientemente largo."}, headers=ADMIN())
        assert r.status_code == 409
    _correr(esc)


# ---------------------------------------------------------------- encuestado anónimo
async def _clave_de(c, evaluacion_id: int) -> str:
    r = await c.post("/api/auth/encuestado/clave", json={"evaluacion_id": evaluacion_id}, headers=ADMIN())
    assert r.status_code == 201, r.text
    return r.json()["clave"]


async def _token_encuestado(c, evaluacion_id: int, clave: str) -> dict:
    r = await c.post("/api/auth/encuestado", json={"evaluacion_id": evaluacion_id, "clave": clave})
    assert r.status_code == 200, r.text
    assert r.json()["rol"] == "encuestado" and r.json()["usuario_id"] == evaluacion_id
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_solo_admin_genera_la_clave_de_una_evaluacion():
    async def esc(c):
        body = {"evaluacion_id": EVAL_NA_ID}
        assert (await c.post("/api/auth/encuestado/clave", json=body, headers=TITULAR())).status_code == 403
        assert (await c.post("/api/auth/encuestado/clave", json=body)).status_code == 401
        r = await c.post("/api/auth/encuestado/clave", json={"evaluacion_id": 999}, headers=ADMIN())
        assert r.status_code == 404
    _correr(esc)


def test_acceso_del_encuestado_con_la_clave_de_su_evaluacion():
    async def esc(c):
        clave = await _clave_de(c, EVAL_NA_ID)
        # minúsculas y espacios se aceptan
        await _token_encuestado(c, EVAL_NA_ID, clave.lower().replace("-", " "))
        # clave equivocada, otra evaluación o evaluación sin clave: mismo error genérico
        r1 = await c.post("/api/auth/encuestado", json={"evaluacion_id": EVAL_NA_ID, "clave": "AAAA-BBBB-CCCC"})
        r2 = await c.post("/api/auth/encuestado", json={"evaluacion_id": 1, "clave": clave})
        r3 = await c.post("/api/auth/encuestado", json={"evaluacion_id": 999, "clave": clave})
        assert r1.status_code == r2.status_code == r3.status_code == 401
        assert r1.json() == r2.json() == r3.json()
        # regenerar invalida la clave anterior
        nueva = await _clave_de(c, EVAL_NA_ID)
        r = await c.post("/api/auth/encuestado", json={"evaluacion_id": EVAL_NA_ID, "clave": clave})
        assert r.status_code == 401
        await _token_encuestado(c, EVAL_NA_ID, nueva)
    _correr(esc)


def test_encuestado_gestiona_solo_sus_solicitudes():
    async def esc(c):
        ENC = await _token_encuestado(c, EVAL_NA_ID, await _clave_de(c, EVAL_NA_ID))
        r = await c.post("/api/arcop/solicitudes", json={"tipo": "acceso", "descripcion": DESCRIPCION}, headers=ENC)
        assert r.status_code == 201, r.text
        s = r.json()
        assert s["evaluacion_id"] == EVAL_NA_ID and s["usuario_temporal_id"] is None
        assert _PATRON_CODIGO.match(s["codigo_seguimiento"])
        sid = s["id_solicitud"]

        propia = await _crear(c)                       # solicitud del invitado 1
        lista = (await c.get("/api/arcop/solicitudes", headers=ENC)).json()
        assert [x["id_solicitud"] for x in lista["items"]] == [sid]
        assert (await c.get(f"/api/arcop/solicitudes/{propia['id_solicitud']}", headers=ENC)).status_code == 404
        # y el invitado no ve la del encuestado
        assert (await c.get(f"/api/arcop/solicitudes/{sid}", headers=TITULAR())).status_code == 404
        lista_inv = (await c.get("/api/arcop/solicitudes", headers=TITULAR())).json()
        assert sid not in [x["id_solicitud"] for x in lista_inv["items"]]

        # el encuestado no puede gestionar
        assert (await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": "en_revision"},
                              headers=ENC)).status_code == 403
        # el admin filtra por evaluación
        r = await c.get(f"/api/arcop/solicitudes?evaluacion_id={EVAL_NA_ID}", headers=ADMIN())
        assert [x["id_solicitud"] for x in r.json()["items"]] == [sid]
        # ciclo con pedido de información y cancelación por el encuestado
        await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": "en_revision"}, headers=ADMIN())
        await c.patch(f"/api/arcop/solicitudes/{sid}/estado",
                      json={"estado": "pendiente_informacion", "comentario": "Indique qué datos."}, headers=ADMIN())
        r = await c.post(f"/api/arcop/solicitudes/{sid}/informacion",
                         json={"informacion": "Mis respuestas de la encuesta."}, headers=ENC)
        assert r.status_code == 200 and r.json()["estado"] == "en_revision"
        r = await c.post(f"/api/arcop/solicitudes/{sid}/cancelacion", json={}, headers=ENC)
        assert r.json()["estado"] == "cancelada"
    _correr(esc)


def test_supresion_del_encuestado_anonimiza_solo_su_evaluacion():
    async def esc(c):
        # datos personales en las dos evaluaciones
        for ev in (1, EVAL_NA_ID):
            assert (await c.post(f"/api/evaluaciones/{ev}/filtro", json=body_filtro(True), headers=ADMIN())).status_code == 200
            r = await c.post("/api/respuestas/", headers=ADMIN(), json={
                "evaluacion_id": ev, "matriz_control_id": 1, "estado_clasificacion": "no_cumplido",
                "justificacion": "Responsable: Juan Pérez, encargado de TI.",
            })
            assert r.status_code == 201, r.text
        resp_por_eval = {
            ev: (await c.get(f"/api/evaluaciones/{ev}/respuestas", headers=ADMIN())).json()["items"][0]["id_respuesta"]
            for ev in (1, EVAL_NA_ID)
        }

        clave = await _clave_de(c, EVAL_NA_ID)
        ENC = await _token_encuestado(c, EVAL_NA_ID, clave)
        r = await c.post("/api/arcop/solicitudes", json={"tipo": "supresion", "descripcion": DESCRIPCION}, headers=ENC)
        sid = r.json()["id_solicitud"]
        for estado in ("en_revision", "en_proceso"):
            await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": estado}, headers=ADMIN())
        r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion",
                         json={"resultado": "resuelta", "respuesta": "Se anonimizaron sus datos."}, headers=ADMIN())
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["descripcion"] == "[anonimizado]" and s["historial"][-1]["tipo_evento"] == "anonimizacion"
        assert "claves_evaluacion=1" in s["historial"][-1]["comentario"]
        assert "usuario_temporal" not in s["historial"][-1]["comentario"]

        # textos de SU evaluación borrados; la otra evaluación intacta
        r_enc = (await c.get(f"/api/respuestas/{resp_por_eval[EVAL_NA_ID]}", headers=ADMIN())).json()
        r_otra = (await c.get(f"/api/respuestas/{resp_por_eval[1]}", headers=ADMIN())).json()
        assert r_enc["justificacion_usuario"] is None and r_enc["estado_clasificacion"] == "no_cumplido"
        assert r_otra["justificacion_usuario"] is not None

        # el encuestado pierde el acceso; el invitado 1 sigue igual
        assert (await c.get("/api/arcop/solicitudes", headers=ENC)).status_code == 401
        r = await c.post("/api/auth/encuestado", json={"evaluacion_id": EVAL_NA_ID, "clave": clave})
        assert r.status_code == 401
        assert (await c.get("/api/arcop/solicitudes", headers=TITULAR())).status_code == 200
        # el código de seguimiento sigue respondiendo (sin datos personales)
        seg = await c.get(f"/api/arcop/seguimiento/{s['codigo_seguimiento']}")
        assert seg.status_code == 200 and seg.json()["estado"] == "resuelta"
    _correr(esc)
