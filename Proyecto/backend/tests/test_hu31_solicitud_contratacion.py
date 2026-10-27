"""
QA - HU-31: el encuestado solicita desde sus resultados que Therion Labs lo contacte para
contratar el servicio.

  C1  en los resultados (sin cuenta) hay un formulario con nombre, cargo, empresa, email y
      teléfono OPCIONAL.
  C2  el envío exige DOS consentimientos separados, cada uno con su versión y fecha: contacto
      comercial y asociar la evaluación a la empresa si contrata. Sin el segundo, HU-27 no migra.
  C3  las solicitudes llegan a la bandeja del admin (HU-28) con la evaluación vinculada y un
      estado (nueva, contactada, contratada o descartada); Therion recibe un aviso por correo y
      el formulario tiene el mismo límite contra abuso que la encuesta pública (HU-19).

El formulario del frontend (CTA "Contratar la plataforma" en /panel) se prueba en
frontend-next/tests/hu31_contratacion.test.ts. Solo en proceso (SQLite en memoria).
"""
import email
import email.header
from pathlib import Path

import pytest
from sqlalchemy import select

from _api_harness import MODO  # noqa: E402
from app.core.config import settings  # noqa: E402
from test_hu27_empresa_cliente import (  # noqa: E402  (mismo arnés: encuestado con evaluación completada)
    SECRETO, _alta, _bd, _bearer, _codigo, _correr, _evaluacion_completada, admin, cuerpo_solicitud,
)

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

pytestmark = pytest.mark.skipif(MODO == "live", reason="HU-31: solo en proceso")

AVISO = "comercial@therionlabs.cl"


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", SECRETO)
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "CONTRATACION_AVISO_EMAIL", AVISO)
    monkeypatch.setattr(settings, "CONTRATACION_SOLICITUDES_IP_DIA", None)
    limitador = LimitadorMemoria()
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield
    app.dependency_overrides.pop(obtener_limitador, None)


async def _enviar(c, e, **cambios):
    return await c.post("/api/contratacion/solicitudes", headers=e["h"], json=cuerpo_solicitud(e["ev"], **cambios))


async def _fila(sid: int):
    async def leer(s):
        from app.domain.models import SolicitudContratacion
        return await s.get(SolicitudContratacion, sid)
    return await _bd(leer)


async def _cuantas() -> int:
    async def contar(s):
        from sqlalchemy import func
        from app.domain.models import SolicitudContratacion
        return (await s.execute(select(func.count()).select_from(SolicitudContratacion))).scalar_one()
    return await _bd(contar)


def _correos_a(destino: str) -> list[email.message.Message]:
    carpeta = Path(settings.STORAGE_DIR) / "correos"
    if not carpeta.exists():
        return []
    msgs = [email.message_from_bytes(p.read_bytes()) for p in carpeta.glob("*.eml")]
    return [m for m in msgs if m["To"] == destino]


def _texto(msg) -> str:
    return next(p for p in msg.walk() if p.get_content_type() == "text/plain").get_payload(decode=True).decode()


async def _acciones_bitacora(c, accion: str) -> list[dict]:
    r = await c.get(f"/api/admin/bitacora?accion={accion}&size=200", headers=admin())
    assert r.status_code == 200
    return r.json()["items"]


# ===================================================================== C1: formulario
def test_c1_formulario_con_nombre_cargo_empresa_email_y_telefono_opcional():
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        # Sin teléfono: es opcional
        r = await _enviar(c, e, telefono=None)
        assert r.status_code == 201, r.text
        publica = r.json()
        assert publica["estado"] == "nueva" and publica["evaluacion_id"] == e["ev"]
        # Lo que ve el encuestado no expone datos de gestión ni su propio contacto
        assert set(publica) == {"id", "evaluacion_id", "estado", "autoriza_migracion", "fecha_creacion"}

        fila = await _fila(publica["id"])
        assert (fila.nombre_contacto, fila.cargo_contacto, fila.razon_social_declarada, fila.email_contacto,
                fila.telefono_contacto) == ("Ana Pérez", "Gerenta de Cumplimiento", "ACME SpA",
                                            "ana.perez@acme.cl", None)

        # Puede consultar su solicitud (el frontend no vuelve a ofrecer el formulario)
        r = await c.get(f"/api/contratacion/evaluaciones/{e['ev']}/solicitud", headers=e["h"])
        assert r.status_code == 200 and r.json()["id"] == publica["id"]
        # Una sola por evaluación
        r = await _enviar(c, e)
        assert r.status_code == 409 and _codigo(r) == "SOLICITUD_EXISTENTE"
    _correr(esc)


@pytest.mark.parametrize("cambios, campo", [
    ({"nombre": "  "}, "nombre"),
    ({"cargo": ""}, "cargo"),
    ({"empresa": " "}, "empresa"),
    ({"email": "ana@"}, "email"),
    ({"telefono": "llámame"}, "telefono"),
    ({"cargo": "x" * 81}, "cargo"),
])
def test_c1_campos_obligatorios_y_formato(cambios, campo):
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        r = await _enviar(c, e, **cambios)
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["campo"] == campo
        assert await _cuantas() == 0
    _correr(esc)


def test_c1_solo_con_la_evaluacion_terminada_y_propia():
    async def esc(c):
        r = await c.post("/api/encuesta-publica/iniciar", json={
            "rubro_id": 1, "aviso_legal": {"version": settings.AVISO_LEGAL_VERSION, "aceptado": True},
            "captcha_token": "t"})
        sin_terminar = {"ev": r.json()["evaluacion_id"], "h": _bearer(r.json()["access_token"])}
        r = await _enviar(c, sin_terminar)
        assert r.status_code == 409 and _codigo(r) == "EVALUACION_NO_COMPLETADA"
        otra = await _evaluacion_completada(c, con_evidencia=False)
        r = await c.post("/api/contratacion/solicitudes", headers=sin_terminar["h"], json=cuerpo_solicitud(otra["ev"]))
        assert r.status_code == 404  # ajena: no confirma que exista
        r = await c.post("/api/contratacion/solicitudes", json=cuerpo_solicitud(otra["ev"]))
        assert r.status_code == 401  # sin sesión de encuestado
    _correr(esc)


# ===================================================================== C2: dos consentimientos
def test_c2_los_textos_son_dos_y_cada_uno_trae_su_version():
    async def esc(c):
        r = await c.get("/api/contratacion/consentimiento")
        assert r.status_code == 200
        datos = r.json()
        assert set(datos) == {"contacto", "migracion"}
        assert datos["contacto"]["version"] == settings.CONSENTIMIENTO_CONTACTO_VERSION
        assert datos["migracion"]["version"] == settings.CONSENTIMIENTO_CONTRATACION_VERSION
        assert datos["contacto"]["texto"] != datos["migracion"]["texto"]
        assert "contact" in datos["contacto"]["texto"] and "evaluación" in datos["migracion"]["texto"]
    _correr(esc)


@pytest.mark.parametrize("clave", ["consentimiento_contacto", "consentimiento_migracion"])
def test_c2_sin_cualquiera_de_los_dos_no_se_envia(clave):
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        version = (settings.CONSENTIMIENTO_CONTACTO_VERSION if clave == "consentimiento_contacto"
                   else settings.CONSENTIMIENTO_CONTRATACION_VERSION)
        r = await _enviar(c, e, **{clave: {"version": version, "aceptado": False}})
        assert r.status_code == 422 and _codigo(r) == "CONSENTIMIENTO_REQUERIDO"
        assert r.json()["detail"]["consentimiento"] == clave.removeprefix("consentimiento_")
        # Faltando el objeto completo, lo rechaza la validación del esquema
        cuerpo = cuerpo_solicitud(e["ev"])
        cuerpo.pop(clave)
        r = await c.post("/api/contratacion/solicitudes", headers=e["h"], json=cuerpo)
        assert r.status_code == 422
        # Versión vieja de ESE texto: 409 con la vigente, para que el formulario lo vuelva a mostrar
        r = await _enviar(c, e, **{clave: {"version": "2020-01-v0", "aceptado": True}})
        assert r.status_code == 409 and _codigo(r) == "CONSENTIMIENTO_DESACTUALIZADO"
        assert r.json()["detail"]["version_vigente"] == version
        assert await _cuantas() == 0
    _correr(esc)


def test_c2_cada_consentimiento_queda_con_su_version_y_fecha_y_el_admin_los_ve_separados():
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        sid = (await _enviar(c, e)).json()["id"]
        fila = await _fila(sid)
        assert fila.consentimiento_contacto_version == settings.CONSENTIMIENTO_CONTACTO_VERSION
        assert fila.consentimiento_version == settings.CONSENTIMIENTO_CONTRATACION_VERSION
        assert fila.autoriza_migracion is True
        assert fila.fecha_consentimiento_contacto is not None and fila.fecha_autorizacion is not None

        sol = (await c.get(f"/api/admin/contrataciones/{sid}", headers=admin())).json()
        cons = sol["consentimientos"]
        assert cons["contacto"]["aceptado"] and cons["contacto"]["version"] == settings.CONSENTIMIENTO_CONTACTO_VERSION
        assert cons["migracion"]["aceptado"] and cons["migracion"]["version"] == settings.CONSENTIMIENTO_CONTRATACION_VERSION
        assert cons["contacto"]["fecha"] and cons["migracion"]["fecha"]
    _correr(esc)


def test_c2_sin_el_segundo_consentimiento_hu27_no_migra():
    """Una fila sin autorización (anterior a HU-31) no se puede migrar aunque esté contratada."""
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        sid = (await _enviar(c, e)).json()["id"]

        async def quitar(s):
            from app.domain.models import SolicitudContratacion
            fila = await s.get(SolicitudContratacion, sid)
            fila.autoriza_migracion = False
            await s.commit()
        await _bd(quitar)
        assert (await c.patch(f"/api/admin/contrataciones/{sid}", json={"estado": "contratada"},
                              headers=admin())).status_code == 200
        r = await c.post("/api/admin/empresas", json=_alta([sid]), headers=admin())
        assert r.status_code == 409 and _codigo(r) == "MIGRACION_NO_AUTORIZADA"
    _correr(esc)


# ===================================================================== C3: bandeja del admin
def test_c3_bandeja_con_evaluacion_vinculada_estados_y_conteo():
    async def esc(c):
        a = await _evaluacion_completada(c)
        b = await _evaluacion_completada(c, con_evidencia=False)
        sa = (await _enviar(c, a)).json()["id"]
        sb = (await _enviar(c, b, email_contacto="b@acme.cl")).json()["id"]

        r = await c.get("/api/admin/contrataciones", headers=admin())
        assert r.status_code == 200
        bandeja = r.json()
        assert bandeja["total"] == 2
        assert bandeja["conteo_por_estado"] == {"nueva": 2, "contactada": 0, "contratada": 0, "migrada": 0,
                                                "descartada": 0}
        item = next(i for i in bandeja["items"] if i["id"] == sa)
        assert item["estado"] == "nueva"
        assert item["contacto"] == {"nombre": "Ana Pérez", "cargo": "Gerenta de Cumplimiento",
                                    "email": "ana.perez@acme.cl", "telefono": "+56 9 1234 5678"}
        assert item["razon_social_declarada"] == "ACME SpA"
        # Evaluación vinculada: id, rubro, puntaje y que está completada
        ev = item["evaluacion"]
        assert ev["id"] == a["ev"] and ev["completada"] is True and ev["puntaje_general"] is not None
        assert ev["rubro"]

        # nueva -> contactada (filtro por estado) -> contratada
        r = await c.patch(f"/api/admin/contrataciones/{sa}", json={"estado": "contactada"}, headers=admin())
        assert r.status_code == 200 and r.json()["estado"] == "contactada"
        r = await c.get("/api/admin/contrataciones?estado=contactada", headers=admin())
        assert [i["id"] for i in r.json()["items"]] == [sa]
        assert r.json()["conteo_por_estado"]["contactada"] == 1 and r.json()["conteo_por_estado"]["nueva"] == 1
        # 'contactada' todavía no habilita la migración
        r = await c.post("/api/admin/empresas", json=_alta([sa]), headers=admin())
        assert r.status_code == 409 and _codigo(r) == "SOLICITUD_NO_CONTRATADA"
        assert (await c.patch(f"/api/admin/contrataciones/{sa}", json={"estado": "contratada"},
                              headers=admin())).status_code == 200
        # contratada -> contactada corrige un error; luego se vuelve a contratar y se migra (HU-27)
        assert (await c.patch(f"/api/admin/contrataciones/{sa}", json={"estado": "contactada"},
                              headers=admin())).status_code == 200
        assert (await c.patch(f"/api/admin/contrataciones/{sa}", json={"estado": "contratada"},
                              headers=admin())).status_code == 200
        r = await c.post("/api/admin/empresas", json=_alta([sa]), headers=admin())
        assert r.status_code == 201, r.text
        # Para el encuestado, la migrada se ve como contratada
        # (su token ya no sirve tras migrar; lo comprueba el admin)
        assert (await c.get(f"/api/admin/contrataciones/{sa}", headers=admin())).json()["estado"] == "migrada"

        # descartar borra el contacto (también el cargo) y es final
        r = await c.patch(f"/api/admin/contrataciones/{sb}", json={"estado": "descartada"}, headers=admin())
        assert r.status_code == 200
        assert r.json()["contacto"] == {"nombre": None, "cargo": None, "email": None, "telefono": None}
        assert r.json()["razon_social_declarada"] == "ACME SpA"  # la empresa no es dato personal
        for estado in ("nueva", "contactada", "contratada"):
            r = await c.patch(f"/api/admin/contrataciones/{sb}", json={"estado": estado}, headers=admin())
            assert r.status_code == 409 and _codigo(r) == "TRANSICION_INVALIDA"
        # el estado técnico 'migrada' solo lo fija HU-27, y 'pendiente' ya no existe
        b2 = await _evaluacion_completada(c, con_evidencia=False)
        s3 = (await _enviar(c, b2, email_contacto="c@acme.cl")).json()["id"]
        for estado in ("migrada", "pendiente", "nueva"):
            r = await c.patch(f"/api/admin/contrataciones/{s3}", json={"estado": estado}, headers=admin())
            assert r.status_code == 409, estado
        r = await c.get("/api/admin/contrataciones?estado=pendiente", headers=admin())
        assert r.status_code == 422

        cambios = await _acciones_bitacora(c, "solicitud_contratacion.estado_cambiado")
        assert {(i["detalle"]["estado_anterior"], i["detalle"]["estado_nuevo"]) for i in cambios} >= {
            ("nueva", "contactada"), ("contactada", "contratada"), ("contratada", "contactada"),
            ("nueva", "descartada")}
    _correr(esc)


def test_c3_aviso_por_correo_a_therion_sin_datos_de_contacto():
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        sid = (await _enviar(c, e)).json()["id"]
        (msg,) = _correos_a(AVISO)
        texto = _texto(msg)
        asunto = str(email.header.make_header(email.header.decode_header(msg["Subject"])))
        assert f"#{sid}" in asunto and "ACME SpA" in asunto
        assert f"#{e['ev']}" in texto and "Gerenta de Cumplimiento" in texto and "/admin/clientes" in texto
        # Minimización: ni nombre, ni correo, ni teléfono de la persona
        crudo = msg.as_string()
        for dato in ("Ana Pérez", "Ana P=C3=A9rez", "ana.perez@acme.cl", "1234 5678"):
            assert dato not in crudo and dato not in texto
        (fila,) = await _acciones_bitacora(c, "solicitud_contratacion.aviso_comercial")
        assert fila["resultado"] == "ok" and fila["entidad_id"] == sid and "@" not in str(fila["detalle"])
    _correr(esc)


def test_c3_sin_destinatario_o_con_el_correo_caido_la_solicitud_igual_queda(monkeypatch):
    async def esc(c):
        from app.application.informes import correo

        monkeypatch.setattr(settings, "CONTRATACION_AVISO_EMAIL", None)
        a = await _evaluacion_completada(c, con_evidencia=False)
        assert (await _enviar(c, a)).status_code == 201

        monkeypatch.setattr(settings, "CONTRATACION_AVISO_EMAIL", AVISO)

        async def caido(*_a, **_k):
            raise correo.CorreoFallidoError("smtp caído")
        monkeypatch.setattr(correo, "enviar", caido)
        b = await _evaluacion_completada(c, con_evidencia=False)
        assert (await _enviar(c, b, email_contacto="b@acme.cl")).status_code == 201

        avisos = await _acciones_bitacora(c, "solicitud_contratacion.aviso_comercial")
        assert sorted(i["resultado"] for i in avisos) == ["fallido", "omitido"]
        assert (await c.get("/api/admin/contrataciones", headers=admin())).json()["total"] == 2
    _correr(esc)


# ===================================================================== C3: límite contra abuso (HU-19)
def test_c3_limite_de_intentos_por_ip_igual_que_la_encuesta_publica(monkeypatch):
    async def esc(c):
        a = await _evaluacion_completada(c, con_evidencia=False)
        monkeypatch.setattr(settings, "ENCUESTA_INTENTOS_IP_10MIN", 3)
        # Los intentos fallidos también cuentan
        for _ in range(3):
            r = await _enviar(c, a, email_contacto="mal")
            assert r.status_code == 422
        r = await _enviar(c, a)
        assert r.status_code == 429 and _codigo(r) == "DEMASIADOS_INTENTOS"
        assert int(r.headers["Retry-After"]) > 0
        assert await _cuantas() == 0
    _correr(esc)


def test_c3_limite_diario_por_ip_y_un_rechazo_no_gasta_cupo(monkeypatch):
    async def esc(c):
        monkeypatch.setattr(settings, "CONTRATACION_SOLICITUDES_IP_DIA", 1)
        a = await _evaluacion_completada(c, con_evidencia=False)
        b = await _evaluacion_completada(c, con_evidencia=False)
        assert (await _enviar(c, a, empresa="")).status_code == 422  # rechazada: devuelve el cupo
        assert (await _enviar(c, a)).status_code == 201
        r = await _enviar(c, b, email_contacto="b@acme.cl")
        assert r.status_code == 429 and _codigo(r) == "LIMITE_SOLICITUDES"
        assert await _cuantas() == 1
    _correr(esc)


def test_c3_limite_diario_por_defecto_es_el_de_la_encuesta_publica():
    assert settings.CONTRATACION_SOLICITUDES_IP_DIA is None
    assert settings.contratacion_solicitudes_ip_dia == settings.ENCUESTA_EVALUACIONES_IP_DIA


def test_c3_captcha_en_el_servidor_con_su_propia_accion(monkeypatch):
    async def esc(c):
        import app.api.routes.contratacion as ruta
        from app.infrastructure.security.captcha import ResultadoCaptcha

        vistos = []

        async def captcha_falso(token, ip, accion="iniciar_encuesta"):
            vistos.append(accion)
            return ResultadoCaptcha(token == "ok", None if token == "ok" else "rechazado")

        a = await _evaluacion_completada(c, con_evidencia=False)
        monkeypatch.setattr(ruta, "verificar_captcha", captcha_falso)
        r = await _enviar(c, a, captcha_token="")
        assert r.status_code == 403 and _codigo(r) == "CAPTCHA_INVALIDO"
        assert await _cuantas() == 0
        assert (await _enviar(c, a, captcha_token="ok")).status_code == 201
        assert set(vistos) == {"solicitar_contratacion"}  # un token de /comenzar no sirve aquí
    _correr(esc)


def test_c3_con_secreto_del_bff_solo_se_acepta_desde_el_sitio(monkeypatch):
    async def esc(c):
        a = await _evaluacion_completada(c, con_evidencia=False)
        monkeypatch.setattr(settings, "BFF_SHARED_SECRET", "s" * 40)
        r = await _enviar(c, a)
        assert r.status_code == 403 and _codigo(r) == "ORIGEN_NO_PERMITIDO"
        r = await c.post("/api/contratacion/solicitudes", json=cuerpo_solicitud(a["ev"]),
                         headers={**a["h"], "X-BFF-Secret": "s" * 40, "X-Cliente-IP": "200.1.2.3"})
        assert r.status_code == 201, r.text
    _correr(esc)


# ===================================================================== Ley 21.719: retiro del consentimiento
def test_suprimir_los_datos_retira_el_contacto_y_descarta_la_solicitud():
    async def esc(c):
        from datetime import datetime, timezone
        from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository

        e = await _evaluacion_completada(c, con_evidencia=False)
        sid = (await _enviar(c, e)).json()["id"]

        async def suprimir(s):
            conteo, _ = await AnonimizacionRepository(s).anonimizar_encuestado(e["ev"], datetime.now(timezone.utc).replace(tzinfo=None))
            await s.commit()
            return conteo
        conteo = await _bd(suprimir)
        assert conteo["solicitudes_contratacion"] == 1
        fila = await _fila(sid)
        assert fila.estado == "descartada"
        assert (fila.nombre_contacto, fila.cargo_contacto, fila.email_contacto, fila.telefono_contacto) == (
            None, None, None, None)
        # y ya no se puede volver a contratar con esa solicitud
        r = await c.patch(f"/api/admin/contrataciones/{sid}", json={"estado": "contratada"}, headers=admin())
        assert r.status_code == 409
    _correr(esc)

