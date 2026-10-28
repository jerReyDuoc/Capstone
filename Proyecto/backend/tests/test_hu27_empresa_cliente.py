"""
QA - HU-27: alta de la empresa cliente, usuario definitivo y migración de la evaluación.

  C1  el admin crea la empresa (razón social, RUT, rubro, contrato) y su usuario definitivo
      (nombre, email) con el único rol 'cliente'.
  C2  asocia una o más evaluaciones autorizadas en una solicitud de contratación; en UNA
      transacción pasan respuestas, evidencias, resumen, plan formativo e informes; la clave
      temporal deja de funcionar y el usuario temporal queda cerrado sin duplicar el contacto.
  C3  el usuario definitivo recibe un enlace de un solo uso y con vencimiento para definir su
      contraseña (nunca se envía una); todo queda en la bitácora de auditoría.

Solo en proceso (SQLite en memoria): los tokens dependen del AUTH_SECRET del servidor.
"""
import asyncio
import email
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from _api_harness import MODO, TODOS_LOS_CONTROLES, cliente_api  # noqa: E402
from app.core import autenticacion as auth  # noqa: E402
from app.core.config import settings  # noqa: E402

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

pytestmark = pytest.mark.skipif(MODO == "live", reason="HU-27: solo en proceso")

SECRETO = "secreto-de-pruebas-hu27-0123456789abcdef"
ID_CONTROL = {codigo: i + 1 for i, codigo in enumerate(TODOS_LOS_CONTROLES)}
SOLO_BASE = {"respuestas": [{"codigo": f"F{i}", "respuesta": i == 1} for i in range(1, 8)]}
JUST = "Existe una política aprobada, pero aún no se aplica en todas las áreas."
RUT_OK = "76.086.428-5"           # RUT de empresa con DV válido (módulo 11)
RUT_OK_2 = "96.790.240-3"
PASSWORD = "Gobernanza2026segura"
HOY = date.today()


def _utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    monkeypatch.setattr(settings, "ACTIVACION_URL_BASE", "http://localhost:3000/activar")
    limitador = LimitadorMemoria()
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield
    app.dependency_overrides.pop(obtener_limitador, None)


def _correr(escenario):
    async def _main():
        async with cliente_api(rol=None) as c:
            await escenario(c)
    asyncio.run(_main())


def _h(usuario_id: int, rol: str) -> dict:
    return {"Authorization": f"Bearer {auth.emitir_token(usuario_id, rol, secreto=SECRETO)}"}


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _codigo(r):
    detalle = r.json().get("detail")
    return detalle.get("codigo") if isinstance(detalle, dict) else None



def admin() -> dict:
    return _h(1, "admin_therion")


async def _sesion():
    """Sesión de la BD SQLite de la prueba (la misma que usa la API)."""
    from app.core.database import get_db
    from app.main import app

    gen = app.dependency_overrides[get_db]()
    return gen, await gen.__anext__()


async def _bd(fn):
    gen, s = await _sesion()
    try:
        return await fn(s)
    finally:
        await gen.aclose()


# ------------------------------------------------------------------ preparación
async def _evaluacion_completada(c, con_evidencia: bool = True) -> dict:
    """Encuestado público con su evaluación COMPLETADA (respuestas, evidencia validada y resumen)."""
    from app.application.filters.control_tree import CONTROLES_BASE

    r = await c.post("/api/encuesta-publica/iniciar", json={
        "rubro_id": 1, "aviso_legal": {"version": settings.AVISO_LEGAL_VERSION, "aceptado": True},
        "captcha_token": "t"})
    assert r.status_code == 201, r.text
    datos = r.json()
    ev, h = datos["evaluacion_id"], _bearer(datos["access_token"])
    assert (await c.post(f"/api/evaluaciones/{ev}/filtro", json=SOLO_BASE, headers=h)).status_code == 200
    primera = None
    for n, codigo in enumerate(CONTROLES_BASE):
        estado = "cumplido" if n == 0 else ("no_cumplido" if n % 2 else "parcialmente_cumplido")
        r = await c.post("/api/respuestas/", headers=h, json={
            "evaluacion_id": ev, "matriz_control_id": ID_CONTROL[codigo], "estado_clasificacion": estado,
            "justificacion": JUST})
        assert r.status_code in (200, 201), r.text
        primera = primera or r.json()["id_respuesta"]
    if con_evidencia:
        r = await c.post(f"/api/respuestas/{primera}/evidencias", headers=h,
                         files={"file": ("politica.txt", b"Politica de IA aprobada por el directorio.", "text/plain")})
        assert r.status_code == 202, r.text
        evid = r.json()["id_evidencia"]

        async def validar(s):
            from app.domain.models.evidencia import Evidencia
            fila = await s.get(Evidencia, evid)
            fila.estado_validacion = "validated"
            await s.commit()
        await _bd(validar)
    r = await c.post(f"/api/evaluaciones/{ev}/completar", headers=h)
    assert r.status_code == 200, r.text
    return {"ev": ev, "h": h, "clave": datos["clave_acceso"]}


def cuerpo_solicitud(evaluacion_id: int, email_contacto: str = "ana.perez@acme.cl", **cambios) -> dict:
    """Formulario "Contratar la plataforma" (HU-31): datos de contacto y los DOS consentimientos."""
    cuerpo = {
        "evaluacion_id": evaluacion_id, "nombre": "Ana Pérez", "cargo": "Gerenta de Cumplimiento",
        "empresa": "ACME SpA", "email": email_contacto, "telefono": "+56 9 1234 5678",
        "consentimiento_contacto": {"version": settings.CONSENTIMIENTO_CONTACTO_VERSION, "aceptado": True},
        "consentimiento_migracion": {"version": settings.CONSENTIMIENTO_CONTRATACION_VERSION, "aceptado": True},
        "captcha_token": "t",
    }
    cuerpo.update(cambios)
    return cuerpo


async def _solicitar(c, e: dict, autoriza: bool = True, email_contacto: str = "ana.perez@acme.cl") -> int:
    r = await c.post("/api/contratacion/solicitudes", headers=e["h"],
                     json=cuerpo_solicitud(e["ev"], email_contacto))
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    if not autoriza:
        # HU-31 exige los dos consentimientos al enviar; una fila SIN autorización solo puede
        # venir de antes de HU-31 (base de HU-27). Se simula para probar que HU-27 no la migra.
        async def quitar(s):
            from app.domain.models import SolicitudContratacion
            fila = await s.get(SolicitudContratacion, sid)
            fila.autoriza_migracion, fila.consentimiento_version, fila.fecha_autorizacion = False, None, None
            await s.commit()
        await _bd(quitar)
    return sid


async def _contratar(c, solicitud_id: int):
    r = await c.patch(f"/api/admin/contrataciones/{solicitud_id}", json={"estado": "contratada"}, headers=admin())
    assert r.status_code == 200, r.text


def _alta(solicitudes, rut=RUT_OK, email_usuario="gerencia@acme.cl", **empresa):
    datos = {"razon_social": "ACME Servicios SpA", "rut": rut, "rubro_id": 1,
             "fecha_inicio_contrato": HOY.isoformat(),
             "fecha_termino_contrato": (HOY + timedelta(days=365)).isoformat()}
    datos.update(empresa)
    return {"empresa": datos, "usuario": {"nombre": "Gabriela Rojas", "email": email_usuario},
            "solicitudes_ids": solicitudes}


def _token_del_correo(destino: str) -> str:
    """Lee el .eml que dejó CORREO_MODO=archivo y saca el token del enlace."""
    carpeta = Path(settings.STORAGE_DIR) / "correos"
    for ruta in sorted(carpeta.glob("*.eml"), key=lambda p: p.stat().st_mtime, reverse=True):
        msg = email.message_from_bytes(ruta.read_bytes())
        if msg["To"] != destino:
            continue
        texto = next(p for p in msg.walk() if p.get_content_type() == "text/plain").get_payload(decode=True).decode()
        m = re.search(r"/activar#token=([A-Za-z0-9_-]+)", texto)
        assert m, texto
        return m.group(1)
    raise AssertionError(f"No hay correo para {destino}")


async def _empresa_creada(c) -> dict:
    e = await _evaluacion_completada(c)
    sid = await _solicitar(c, e)
    await _contratar(c, sid)
    r = await c.post("/api/admin/empresas", json=_alta([sid]), headers=admin())
    assert r.status_code == 201, r.text
    return {**e, "solicitud": sid, "alta": r.json(), "empresa_id": r.json()["empresa"]["id"]}


async def _activar_y_entrar(c, destino="gerencia@acme.cl") -> dict:
    token = _token_del_correo(destino)
    r = await c.post("/api/auth/activacion", json={"token": token, "password": PASSWORD})
    assert r.status_code == 200, r.text
    r = await c.post("/api/auth/cliente", json={"email": destino, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return _bearer(r.json()["access_token"])


# ===================================================================== utilidades puras
def test_rut_se_normaliza_y_valida_el_digito_verificador():
    from app.core.rut import RutInvalidoError, normalizar_rut, rut_valido

    assert normalizar_rut("76.086.428-5") == "76086428-5"
    assert normalizar_rut("760864285") == "76086428-5"
    assert normalizar_rut(" 96790240-3 ") == "96790240-3"
    assert rut_valido("76.086.428-K") is False
    assert rut_valido("12") is False
    with pytest.raises(RutInvalidoError):
        normalizar_rut("76.086.428-4")


def test_reglas_de_la_contrasena_del_cliente():
    from app.application.use_cases.activacion_cuenta import validar_contrasena

    assert validar_contrasena(PASSWORD, "gerencia@acme.cl", "Gabriela Rojas") == []
    assert any("12" in p for p in validar_contrasena("Corta1", "x@y.cl"))
    assert any("letras y números" in p for p in validar_contrasena("solamenteletrasaqui", "x@y.cl"))
    assert any("correo" in p for p in validar_contrasena("gerencia2026abc", "gerencia@acme.cl"))
    assert any("nombre" in p for p in validar_contrasena("gabriela2026xyz", "x@y.cl", "Gabriela Rojas"))


def test_la_bitacora_no_admite_datos_personales():
    from app.infrastructure.repositories.bitacora_repository import _validar_detalle

    _validar_detalle({"empresa_id": 1, "conteos": [1, 2], "estado": "ok"})
    for malo in ({"email": "x"}, {"datos": {"token": "abc"}}, {"nota": "escribir a ana@acme.cl"}):
        with pytest.raises(ValueError):
            _validar_detalle(malo)


# ===================================================================== flujo completo (C1 + C2 + C3)
def test_flujo_completo_alta_migracion_activacion_y_acceso_del_cliente():
    async def esc(c):
        e = await _evaluacion_completada(c)

        # HU-31: el encuestado pide contratar y autoriza el traspaso
        r = await c.get("/api/contratacion/consentimiento")
        assert r.status_code == 200
        assert r.json()["migracion"]["version"] == settings.CONSENTIMIENTO_CONTRATACION_VERSION
        sid = await _solicitar(c, e)
        r = await c.get(f"/api/contratacion/evaluaciones/{e['ev']}/solicitud", headers=e["h"])
        assert r.status_code == 200 and r.json()["estado"] == "nueva"

        async def foto(s):
            from app.domain.models import Evidencia, Respuesta, Resumen
            return {
                "respuestas": sorted((await s.execute(select(Respuesta.id).where(
                    Respuesta.evaluacion_id == e["ev"]))).scalars().all()),
                "evidencias": (await s.execute(select(func.count()).select_from(Evidencia))).scalar_one(),
                "resumen": (await s.execute(select(func.count()).select_from(Resumen).where(
                    Resumen.evaluacion_id == e["ev"]))).scalar_one(),
            }
        antes = await _bd(foto)
        plan_antes = (await c.get(f"/api/evaluaciones/{e['ev']}/plan-formativo", headers=e["h"])).json()

        # Nueva (sin contratar): todavía no se puede migrar (y no queda NADA creado)
        r = await c.post("/api/admin/empresas", json=_alta([sid]), headers=admin())
        assert r.status_code == 409 and _codigo(r) == "SOLICITUD_NO_CONTRATADA", r.text
        assert (await c.get("/api/admin/empresas", headers=admin())).json()["total"] == 0

        await _contratar(c, sid)
        r = await c.post("/api/admin/empresas", json=_alta([sid]), headers=admin())
        assert r.status_code == 201, r.text
        alta = r.json()

        # C1: empresa y usuario definitivo con el único rol cliente, sin contraseña
        assert alta["empresa"]["rut"] == "76086428-5" and alta["empresa"]["contrato_vigente"] is True
        assert alta["usuario"]["rol"] == "cliente" and alta["usuario"]["estado"] == "pendiente_activacion"
        assert "password_hash" not in alta["usuario"] and "token" not in str(alta).lower().replace(
            "token_activacion", "")
        # C2: lo que pasó a la empresa
        (m,) = alta["evaluaciones_migradas"]
        assert m["evaluacion_id"] == e["ev"] and m["respuestas"] == len(antes["respuestas"])
        assert m["evidencias"] == 1 and m["dimensiones_resumen"] == antes["resumen"] > 0
        assert m["plan_formativo"] is True and m["informe_pdf"] is True
        assert alta["activacion"]["enviado"] is True and alta["activacion"]["modo"] == "archivo"

        # C2: la clave temporal y el token del encuestado dejan de funcionar
        assert (await c.get(f"/api/evaluaciones/{e['ev']}", headers=e["h"])).status_code == 401
        r = await c.post("/api/auth/encuestado", json={"evaluacion_id": e["ev"], "clave": e["clave"]})
        assert r.status_code == 401

        # C2: nada se duplicó; usuario temporal cerrado; contacto solo en el usuario definitivo
        async def revisar(s):
            from app.domain.models import (
                Evaluacion, SolicitudContratacion, UsuarioDefinitivo, UsuarioTemporal,
            )
            ev = await s.get(Evaluacion, e["ev"])
            ut = await s.get(UsuarioTemporal, ev.usuario_temporal_id)
            sol = await s.get(SolicitudContratacion, sid)
            ud = (await s.execute(select(UsuarioDefinitivo))).scalar_one()
            return ev, ut, sol, ud
        ev, ut, sol, ud = await _bd(revisar)
        assert ev.empresa_id == alta["empresa"]["id"] and ev.clave_acceso_hash is None and ev.fecha_migracion
        assert ut.email is None and ut.fecha_anonimizacion is not None
        assert sol.estado == "migrada" and sol.empresa_id == ev.empresa_id
        assert (sol.nombre_contacto, sol.cargo_contacto, sol.email_contacto, sol.telefono_contacto) == (
            None, None, None, None)
        assert ud.email == "gerencia@acme.cl" and ud.password_hash is None
        assert await _bd(foto) == antes

        # C3: el correo trae un enlace (token en el fragmento) y NUNCA una contraseña
        token = _token_del_correo("gerencia@acme.cl")
        eml = next((Path(settings.STORAGE_DIR) / "correos").glob("*.eml")).read_bytes().decode("utf-8", "ignore")
        assert PASSWORD not in eml and "contraseña:" not in eml.lower()

        r = await c.post("/api/auth/activacion/verificar", json={"token": token})
        assert r.status_code == 200 and r.json()["email"] == "g***a@acme.cl" and r.json()["valido"]
        # Contraseña débil: 422 y el enlace NO se consume
        r = await c.post("/api/auth/activacion", json={"token": token, "password": "corta"})
        assert r.status_code == 422 and _codigo(r) == "CONTRASENA_DEBIL" and r.json()["detail"]["problemas"]
        assert (await c.post("/api/auth/activacion/verificar", json={"token": token})).status_code == 200
        r = await c.post("/api/auth/activacion", json={"token": token, "password": PASSWORD})
        assert r.status_code == 200 and r.json()["activado"] is True
        # Un solo uso
        r = await c.post("/api/auth/activacion", json={"token": token, "password": PASSWORD + "x"})
        assert r.status_code == 400 and _codigo(r) == "ENLACE_INVALIDO"

        # Login del cliente
        r = await c.post("/api/auth/cliente", json={"email": "GERENCIA@acme.cl", "password": "otra-clave-123"})
        assert r.status_code == 401
        r = await c.post("/api/auth/cliente", json={"email": "GERENCIA@acme.cl", "password": PASSWORD})
        assert r.status_code == 200 and r.json()["rol"] == "cliente", r.text
        hc = _bearer(r.json()["access_token"])

        # El cliente sigue con su historial, sin repetir el autodiagnóstico
        assert (await c.get(f"/api/evaluaciones/{e['ev']}", headers=hc)).status_code == 200
        assert (await c.get(f"/api/evaluaciones/{e['ev']}/comparativa", headers=hc)).status_code == 200
        r = await c.get(f"/api/evaluaciones/{e['ev']}/plan-formativo", headers=hc)
        assert r.status_code == 200 and r.json() == plan_antes
        r = await c.get(f"/api/evaluaciones/{e['ev']}/informe/pdf", headers=hc)
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
        lista = (await c.get("/api/evaluaciones", headers=hc)).json()
        assert [x["id"] for x in lista["items"]] == [e["ev"]]
        # ...pero no lo ajeno ni lo de Therion Labs
        assert (await c.get("/api/evaluaciones/1", headers=hc)).status_code == 404
        # HU-30: el cliente es titular ARCOP; solo ve SUS solicitudes (ninguna todavía)
        r = await c.get("/api/arcop/solicitudes", headers=hc)
        assert r.status_code == 200 and r.json()["items"] == []
        assert (await c.get("/api/admin/empresas", headers=hc)).status_code == 403
        r = await c.post("/api/respuestas/", headers=hc, json={
            "evaluacion_id": e["ev"], "matriz_control_id": 1, "estado_clasificacion": "cumplido", "justificacion": JUST})
        assert r.status_code == 409  # evaluación cerrada: el historial no se reescribe

        # C3: todo el proceso quedó en la bitácora, sin datos personales
        r = await c.get("/api/admin/bitacora?size=200", headers=admin())
        assert r.status_code == 200
        items = r.json()["items"]
        acciones = {i["accion"] for i in items}
        assert {
            "solicitud_contratacion.creada", "solicitud_contratacion.estado_cambiado", "empresa.creada",
            "usuario_definitivo.creado", "evaluacion.migrada_a_empresa", "usuario_temporal.cerrado_por_migracion",
            "activacion.enlace_emitido", "activacion.correo", "activacion.cuenta_activada",
            "activacion.rechazada", "cliente.inicio_sesion",
        } <= acciones
        assert "@" not in str([i["detalle"] for i in items])
        # el alta fallida (pendiente) no dejó rastro de empresa: se revirtió entera
        assert sum(i["accion"] == "empresa.creada" for i in items) == 1
    _correr(esc)


# ===================================================================== C2: atomicidad
def test_si_una_solicitud_no_es_valida_no_se_migra_nada():
    async def esc(c):
        a, b = await _evaluacion_completada(c), await _evaluacion_completada(c, con_evidencia=False)
        sa = await _solicitar(c, a)
        sb = await _solicitar(c, b, email_contacto="otro@acme.cl")
        await _contratar(c, sa)  # b queda nueva (sin contratar)
        r = await c.post("/api/admin/empresas", json=_alta([sa, sb]), headers=admin())
        assert r.status_code == 409 and _codigo(r) == "SOLICITUD_NO_CONTRATADA"
        assert r.json()["detail"]["solicitud_id"] == sb

        async def revisar(s):
            from app.domain.models import Empresa, Evaluacion, SolicitudContratacion, UsuarioDefinitivo
            return (
                (await s.execute(select(func.count()).select_from(Empresa))).scalar_one(),
                (await s.execute(select(func.count()).select_from(UsuarioDefinitivo))).scalar_one(),
                (await s.get(Evaluacion, a["ev"])).empresa_id,
                (await s.get(Evaluacion, a["ev"])).clave_acceso_hash is not None,
                (await s.get(SolicitudContratacion, sa)).email_contacto,
            )
        assert await _bd(revisar) == (0, 0, None, True, "ana.perez@acme.cl")
        # el encuestado de 'a' sigue entrando: no se cerró nada
        assert (await c.get(f"/api/evaluaciones/{a['ev']}", headers=a["h"])).status_code == 200
    _correr(esc)


def test_no_se_migra_sin_autorizacion_con_arcop_abierta_ni_dos_veces():
    async def esc(c):
        # sin autorización expresa
        a = await _evaluacion_completada(c, con_evidencia=False)
        sa = await _solicitar(c, a, autoriza=False)
        await _contratar(c, sa)
        r = await c.post("/api/admin/empresas", json=_alta([sa]), headers=admin())
        assert r.status_code == 409 and _codigo(r) == "MIGRACION_NO_AUTORIZADA"

        # con una solicitud ARCOP en curso
        b = await _evaluacion_completada(c, con_evidencia=False)
        r = await c.post("/api/arcop/solicitudes", headers=b["h"], json={
            "tipo": "acceso", "descripcion": "Quiero saber qué datos personales tienen de mí."})
        assert r.status_code == 201, r.text
        sb = await _solicitar(c, b, email_contacto="b@acme.cl")
        await _contratar(c, sb)
        r = await c.post("/api/admin/empresas", json=_alta([sb]), headers=admin())
        assert r.status_code == 409 and _codigo(r) == "ARCOP_PENDIENTE"

        # dos veces la misma: la segunda vez ya está migrada
        d = await _evaluacion_completada(c, con_evidencia=False)
        sd = await _solicitar(c, d, email_contacto="d@acme.cl")
        await _contratar(c, sd)
        r = await c.post("/api/admin/empresas", json=_alta([sd]), headers=admin())
        assert r.status_code == 201, r.text
        r = await c.post("/api/admin/empresas", json=_alta([sd], rut=RUT_OK_2, email_usuario="x@otra.cl"),
                         headers=admin())
        assert r.status_code == 409 and _codigo(r) == "EVALUACION_YA_MIGRADA"
    _correr(esc)


def test_la_solicitud_exige_evaluacion_propia_y_completada():
    async def esc(c):
        r = await c.post("/api/encuesta-publica/iniciar", json={
            "rubro_id": 1, "aviso_legal": {"version": settings.AVISO_LEGAL_VERSION, "aceptado": True},
            "captcha_token": "t"})
        nueva = r.json()
        h = _bearer(nueva["access_token"])
        cuerpo = cuerpo_solicitud(nueva["evaluacion_id"], "a@acme.cl")
        r = await c.post("/api/contratacion/solicitudes", json=cuerpo, headers=h)
        assert r.status_code == 409 and _codigo(r) == "EVALUACION_NO_COMPLETADA"
        # ajena -> 404 (no confirma que exista)
        otra = await _evaluacion_completada(c, con_evidencia=False)
        r = await c.post("/api/contratacion/solicitudes", json={**cuerpo, "evaluacion_id": otra["ev"]}, headers=h)
        assert r.status_code == 404
        # versión del consentimiento desactualizada
        r = await c.post("/api/contratacion/solicitudes", headers=otra["h"],
                         json={**cuerpo, "evaluacion_id": otra["ev"],
                               "consentimiento_migracion": {"version": "vieja", "aceptado": True}})
        assert r.status_code == 409 and _codigo(r) == "CONSENTIMIENTO_DESACTUALIZADO"
        # el admin no puede pedir contratar por nadie
        r = await c.post("/api/contratacion/solicitudes", json={**cuerpo, "evaluacion_id": otra["ev"]},
                         headers=admin())
        assert r.status_code == 403
    _correr(esc)


# ===================================================================== C1: validaciones del alta
def test_validaciones_del_alta_de_empresa():
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        sid = await _solicitar(c, e)
        await _contratar(c, sid)
        casos = [
            (_alta([sid], rut="76.086.428-4"), 422, "RUT_INVALIDO"),
            (_alta([sid], rubro_id=999), 422, "RUBRO_INVALIDO"),
            (_alta([sid], fecha_inicio_contrato=HOY.isoformat(),
                   fecha_termino_contrato=(HOY - timedelta(days=1)).isoformat()), 422, "FECHAS_CONTRATO_INVALIDAS"),
            (_alta([sid], fecha_inicio_contrato=(HOY - timedelta(days=30)).isoformat(),
                   fecha_termino_contrato=(HOY - timedelta(days=1)).isoformat()), 422, "CONTRATO_VENCIDO"),
            (_alta([sid], email_usuario="no-es-correo"), 422, "EMAIL_INVALIDO"),
            (_alta([sid], razon_social=" "), 422, "DATOS_INVALIDOS"),
        ]
        for cuerpo, status, codigo in casos:
            r = await c.post("/api/admin/empresas", json=cuerpo, headers=admin())
            assert r.status_code == status and _codigo(r) == codigo, (codigo, r.text)
        r = await c.post("/api/admin/empresas", json={**_alta([sid]), "solicitudes_ids": []}, headers=admin())
        assert r.status_code == 422

        assert (await c.post("/api/admin/empresas", json=_alta([sid]), headers=admin())).status_code == 201
        # RUT y email únicos
        otra = await _evaluacion_completada(c, con_evidencia=False)
        so = await _solicitar(c, otra, email_contacto="o@acme.cl")
        await _contratar(c, so)
        r = await c.post("/api/admin/empresas", json=_alta([so], rut="760864285", email_usuario="z@z.cl"),
                         headers=admin())
        assert r.status_code == 409 and _codigo(r) == "RUT_DUPLICADO"
        r = await c.post("/api/admin/empresas", json=_alta([so], rut=RUT_OK_2, email_usuario="Gerencia@ACME.cl"),
                         headers=admin())
        assert r.status_code == 409 and _codigo(r) == "EMAIL_DUPLICADO"
    _correr(esc)


# ===================================================================== C3: enlace con vencimiento y reenvío
def test_enlace_vencido_reenvio_revoca_el_anterior_y_no_se_reenvia_a_cuentas_activas():
    async def esc(c):
        x = await _empresa_creada(c)
        viejo = _token_del_correo("gerencia@acme.cl")

        async def vencer(s):
            from app.domain.models import TokenActivacion
            fila = (await s.execute(select(TokenActivacion))).scalar_one()
            fila.fecha_expiracion = _utc() - timedelta(minutes=1)
            await s.commit()
        await _bd(vencer)
        r = await c.post("/api/auth/activacion", json={"token": viejo, "password": PASSWORD})
        assert r.status_code == 410 and _codigo(r) == "ENLACE_VENCIDO"

        r = await c.post(f"/api/admin/empresas/{x['empresa_id']}/usuario/activacion", headers=admin())
        assert r.status_code == 200 and r.json()["activacion"]["enviado"] is True
        nuevo = _token_del_correo("gerencia@acme.cl")
        assert nuevo != viejo
        r = await c.post("/api/auth/activacion", json={"token": viejo, "password": PASSWORD})
        assert r.status_code in (400, 410)
        assert (await c.post("/api/auth/activacion", json={"token": nuevo, "password": PASSWORD})).status_code == 200

        r = await c.post(f"/api/admin/empresas/{x['empresa_id']}/usuario/activacion", headers=admin())
        assert r.status_code == 409 and _codigo(r) == "USUARIO_NO_PENDIENTE"
        # token inventado o mal formado: mismo 400 genérico
        for t in ("x" * 43, "no válido!"):
            r = await c.post("/api/auth/activacion", json={"token": t, "password": PASSWORD})
            assert r.status_code == 400 and _codigo(r) == "ENLACE_INVALIDO"
    _correr(esc)


def test_sin_servidor_de_correo_el_alta_queda_y_el_admin_reenvia(monkeypatch):
    async def esc(c):
        e = await _evaluacion_completada(c, con_evidencia=False)
        sid = await _solicitar(c, e)
        await _contratar(c, sid)
        monkeypatch.setattr(settings, "CORREO_MODO", "desactivado")
        r = await c.post("/api/admin/empresas", json=_alta([sid]), headers=admin())
        assert r.status_code == 201
        assert r.json()["activacion"]["enviado"] is False
        assert r.json()["activacion"]["motivo"] == "CORREO_NO_DISPONIBLE"
        monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
        r = await c.post(f"/api/admin/empresas/{r.json()['empresa']['id']}/usuario/activacion", headers=admin())
        assert r.json()["activacion"]["enviado"] is True
        await _activar_y_entrar(c)
    _correr(esc)


def test_contrato_vencido_corta_el_servicio_pero_no_lo_gratuito():
    """HU-30 reemplaza la regla de HU-27: sin contrato el cliente entra, pero sin servicio pagado."""
    async def esc(c):
        x = await _empresa_creada(c)
        hc = await _activar_y_entrar(c)
        assert (await c.get(f"/api/evaluaciones/{x['ev']}", headers=hc)).status_code == 200

        async def vencer(s):
            from app.domain.models import Empresa
            emp = await s.get(Empresa, x["empresa_id"])
            emp.fecha_inicio_contrato = HOY - timedelta(days=60)
            emp.fecha_termino_contrato = HOY - timedelta(days=1)
            await s.commit()
        await _bd(vencer)
        # lo gratuito sigue (mismo token)
        assert (await c.get(f"/api/evaluaciones/{x['ev']}", headers=hc)).status_code == 200
        # el servicio pagado no
        r = await c.get("/api/cliente/empresa", headers=hc)
        assert r.status_code == 403 and _codigo(r) == "CONTRATO_NO_VIGENTE"
        assert r.json()["detail"]["situacion"] == "vencido"
        # y el login responde 200 con la situación del contrato
        r = await c.post("/api/auth/cliente", json={"email": "gerencia@acme.cl", "password": PASSWORD})
        assert r.status_code == 200 and r.json()["contrato"]["situacion"] == "vencido"
    _correr(esc)


def test_cliente_sin_activar_no_puede_entrar():
    async def esc(c):
        await _empresa_creada(c)
        r = await c.post("/api/auth/cliente", json={"email": "gerencia@acme.cl", "password": PASSWORD})
        assert r.status_code == 401
        # un token emitido a mano para un usuario pendiente tampoco sirve
        r = await c.get("/api/evaluaciones", headers=_h(1, "cliente"))
        assert r.status_code == 401
    _correr(esc)


# ===================================================================== C2: una o más evaluaciones
def test_asociar_otra_evaluacion_autorizada_a_la_misma_empresa():
    async def esc(c):
        x = await _empresa_creada(c)
        hc = await _activar_y_entrar(c)
        otra = await _evaluacion_completada(c, con_evidencia=False)
        so = await _solicitar(c, otra, email_contacto="ana2@acme.cl")
        r = await c.post(f"/api/admin/empresas/{x['empresa_id']}/evaluaciones", json={"solicitudes_ids": [so]},
                         headers=admin())
        assert r.status_code == 409 and _codigo(r) == "SOLICITUD_NO_CONTRATADA"
        await _contratar(c, so)
        r = await c.post(f"/api/admin/empresas/{x['empresa_id']}/evaluaciones", json={"solicitudes_ids": [so]},
                         headers=admin())
        assert r.status_code == 200, r.text
        assert [m["evaluacion_id"] for m in r.json()["evaluaciones_migradas"]] == [otra["ev"]]
        ids = {e["id"] for e in (await c.get("/api/evaluaciones", headers=hc)).json()["items"]}
        assert ids == {x["ev"], otra["ev"]}
        det = (await c.get(f"/api/admin/empresas/{x['empresa_id']}", headers=admin())).json()
        assert {e["id"] for e in det["evaluaciones"]} == ids and det["usuario"]["estado"] == "activo"
        assert (await c.get(f"/api/evaluaciones/{otra['ev']}", headers=otra["h"])).status_code == 401
    _correr(esc)


def test_un_solo_usuario_por_empresa_y_rol_unico_en_la_bd():
    async def esc(c):
        x = await _empresa_creada(c)

        async def duplicar(s):
            from sqlalchemy.exc import IntegrityError
            from app.domain.models import UsuarioDefinitivo
            s.add(UsuarioDefinitivo(empresa_id=x["empresa_id"], nombre="Otro", email="otro@acme.cl",
                                    fecha_creacion=_utc()))
            with pytest.raises(IntegrityError):
                await s.commit()
            await s.rollback()
            s.add(UsuarioDefinitivo(empresa_id=x["empresa_id"] + 1, nombre="Otro", email="otro2@acme.cl",
                                    rol="admin", fecha_creacion=_utc()))
            with pytest.raises(IntegrityError):
                await s.commit()
        await _bd(duplicar)
    _correr(esc)


# ===================================================================== datos migrados protegidos
def test_supresion_o_retencion_del_temporal_no_borra_lo_migrado():
    async def esc(c):
        x = await _empresa_creada(c)

        async def anonimizar(s):
            from app.domain.models import Evaluacion, Respuesta
            from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository
            ev = await s.get(Evaluacion, x["ev"])
            repo = AnonimizacionRepository(s)
            await repo.anonimizar_encuestado(x["ev"], _utc())
            await repo.anonimizar_titular(ev.usuario_temporal_id, _utc())
            await s.commit()
            return (await s.execute(select(Respuesta.justificacion_usuario).where(
                Respuesta.evaluacion_id == x["ev"]))).scalars().all()
        justificaciones = await _bd(anonimizar)
        assert justificaciones and all(j for j in justificaciones)
    _correr(esc)


# ===================================================================== HU-20: rutas nuevas solo admin
def test_rutas_admin_hu27_solo_admin():
    async def esc(c):
        x = await _empresa_creada(c)
        hc = await _activar_y_entrar(c)
        otra = await _evaluacion_completada(c, con_evidencia=False)
        so = await _solicitar(c, otra, email_contacto="o@acme.cl")
        rutas = [
            ("GET", f"/api/admin/contrataciones/{so}", {}),
            ("PATCH", f"/api/admin/contrataciones/{so}", {"json": {"estado": "contratada"}}),
            ("POST", f"/api/admin/empresas/{x['empresa_id']}/evaluaciones", {"json": {"solicitudes_ids": [so]}}),
            ("GET", f"/api/admin/empresas/{x['empresa_id']}", {}),
            ("POST", "/api/admin/empresas", {"json": _alta([so], rut=RUT_OK_2, email_usuario="n@n.cl")}),
            ("POST", f"/api/admin/empresas/{x['empresa_id']}/usuario/activacion", {}),
            ("GET", "/api/admin/bitacora", {}),
            ("GET", "/api/admin/empresas", {}),
            ("GET", "/api/admin/contrataciones", {}),
        ]
        otros = {"encuestado": otra["h"], "referente": _h(1, "referente"), "cliente": hc}
        for metodo, url, kw in rutas:
            assert (await c.request(metodo, url, **kw)).status_code == 401, url
            for nombre, h in otros.items():
                r = await c.request(metodo, url, headers=h, **kw)
                assert r.status_code == 403, (nombre, url, r.text)
        # admin: 2xx en lo que tiene sentido ejecutar
        assert (await c.get(f"/api/admin/contrataciones/{so}", headers=admin())).status_code == 200
        assert (await c.patch(f"/api/admin/contrataciones/{so}", json={"estado": "descartada"},
                              headers=admin())).status_code == 200
        sol = (await c.get(f"/api/admin/contrataciones/{so}", headers=admin())).json()
        assert sol["estado"] == "descartada" and sol["contacto"] == {
            "nombre": None, "cargo": None, "email": None, "telefono": None}
        r = await c.patch(f"/api/admin/contrataciones/{so}", json={"estado": "contratada"}, headers=admin())
        assert r.status_code == 409 and _codigo(r) == "TRANSICION_INVALIDA"
        assert (await c.get(f"/api/admin/empresas/{x['empresa_id']}", headers=admin())).status_code == 200
        assert (await c.get("/api/admin/empresas/999", headers=admin())).status_code == 404
    _correr(esc)
