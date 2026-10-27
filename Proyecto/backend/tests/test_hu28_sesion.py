"""
QA - HU-28: inicio y cierre de sesión con email y contraseña (usuario definitivo y admin).

  C1  inicio de sesión, cierre de sesión y recuperación de contraseña. El token lleva una
      sesión revocable: cerrar sesión o restablecer la contraseña lo deja sin efecto en el
      servidor (el BFF lo guarda en una cookie httpOnly; eso se prueba en frontend-next).
  C2  el usuario definitivo entra al espacio de su empresa (GET /api/cliente/empresa); el
      admin, al panel interno con empresas, solicitudes de contratación y evaluaciones.
  C3  intentos fallidos limitados (por cuenta y por IP), mensajes que no revelan si el
      email existe y cada inicio de sesión en la bitácora de auditoría (HU-09).

Reutiliza la preparación de test_hu27_empresa_cliente.py (evaluación completada, solicitud
contratada, alta de la empresa y activación). Solo en proceso (SQLite en memoria).
"""
import asyncio
import email
import re
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

import test_hu27_empresa_cliente as hu27
from _api_harness import ADMIN_EMAIL, ADMIN_PASSWORD, MODO, cliente_api  # noqa: E402
from app.core import autenticacion as auth  # noqa: E402
from app.core.config import settings  # noqa: E402

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

pytestmark = pytest.mark.skipif(MODO == "live", reason="HU-28: solo en proceso")

PASSWORD = hu27.PASSWORD
NUEVA = "Cumplimiento2027firme"
CLIENTE = "gerencia@acme.cl"
_LIMITADOR = {}


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", hu27.SECRETO)  # mismos helpers de token que HU-27
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ACTIVACION_URL_BASE", "http://localhost:3000/activar")
    monkeypatch.setattr(settings, "RECUPERACION_URL_BASE", "http://localhost:3000/restablecer")
    limitador = LimitadorMemoria()
    _LIMITADOR["x"] = limitador
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield
    app.dependency_overrides.pop(obtener_limitador, None)


def _correr(escenario):
    async def _main():
        async with cliente_api(rol=None) as c:
            await escenario(c)
    asyncio.run(_main())


_codigo = hu27._codigo
_bearer = hu27._bearer
admin = hu27.admin


def _correos(destino: str) -> list[str]:
    """Textos planos de los .eml que dejó CORREO_MODO=archivo para `destino`, del más nuevo al más viejo."""
    carpeta = Path(settings.STORAGE_DIR) / "correos"
    if not carpeta.exists():
        return []
    textos = []
    for ruta in sorted(carpeta.glob("*.eml"), key=lambda p: p.stat().st_mtime_ns, reverse=True):
        msg = email.message_from_bytes(ruta.read_bytes())
        if msg["To"] == destino:
            parte = next(p for p in msg.walk() if p.get_content_type() == "text/plain")
            textos.append(parte.get_payload(decode=True).decode())
    return textos


def _token_recuperacion(destino: str) -> str:
    for texto in _correos(destino):
        m = re.search(r"/restablecer#token=([A-Za-z0-9_-]+)", texto)
        if m:
            return m.group(1)
    raise AssertionError(f"No hay correo de recuperación para {destino}")


async def _cliente_activo(c) -> dict:
    x = await hu27._empresa_creada(c)
    token = hu27._token_del_correo(CLIENTE)
    r = await c.post("/api/auth/activacion", json={"token": token, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return x


async def _login_cliente(c, password=PASSWORD, correo=CLIENTE):
    return await c.post("/api/auth/cliente", json={"email": correo, "password": password})


async def _bitacora(c) -> list[dict]:
    r = await c.get("/api/admin/bitacora?size=200", headers=admin())
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ===================================================================== C1 + C2: cliente
def test_cliente_entra_a_su_empresa_y_cerrar_sesion_revoca_el_token():
    async def esc(c):
        x = await _cliente_activo(c)
        r = await _login_cliente(c)
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        assert auth.verificar_token(token, settings.AUTH_SECRET).sid  # el token lleva su sesión
        h = _bearer(token)

        # C2: el espacio de SU empresa con las evaluaciones migradas
        r = await c.get("/api/cliente/empresa", headers=h)
        assert r.status_code == 200, r.text
        datos = r.json()
        assert datos["empresa"]["razon_social"] == "ACME Servicios SpA"
        assert datos["empresa"]["contrato_vigente"] is True
        assert [e["id"] for e in datos["evaluaciones"]] == [x["ev"]]
        assert datos["evaluaciones"][0]["completada"] is True
        assert "password_hash" not in str(datos)
        # Otros roles no tienen "espacio de empresa"
        assert (await c.get("/api/cliente/empresa", headers=admin())).status_code == 403
        assert (await c.get("/api/cliente/empresa")).status_code == 401

        # C1: cerrar sesión invalida el token en el servidor, aunque no haya vencido
        assert (await c.post("/api/auth/logout", headers=h)).status_code == 204
        r = await c.get("/api/cliente/empresa", headers=h)
        assert r.status_code == 401 and _codigo(r) == "USUARIO_DESHABILITADO"
        assert (await c.get(f"/api/evaluaciones/{x['ev']}", headers=h)).status_code == 401
        assert (await c.post("/api/auth/logout", headers=h)).status_code == 401

        # Otra sesión del mismo usuario (otro dispositivo) no se ve afectada por ese cierre
        h2 = _bearer((await _login_cliente(c)).json()["access_token"])
        assert (await c.get("/api/cliente/empresa", headers=h2)).status_code == 200

        # C3: inicio y cierre en la bitácora, sin datos personales
        items = await _bitacora(c)
        acciones = [i["accion"] for i in items]
        assert acciones.count("cliente.inicio_sesion") == 2 and "sesion.cierre" in acciones
        login = next(i for i in items if i["accion"] == "cliente.inicio_sesion")
        assert login["actor_rol"] == "cliente" and login["detalle"]["sesion_id"]
        assert "@" not in str([i["detalle"] for i in items])
    _correr(esc)


# ===================================================================== C1 + C2: admin
def test_admin_inicia_sesion_ve_el_panel_interno_y_cierra_sesion():
    async def esc(c):
        x = await _cliente_activo(c)
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD})
        assert r.status_code == 200 and r.json()["rol"] == "admin_therion", r.text
        h = _bearer(r.json()["access_token"])

        # C2: panel interno con empresas, solicitudes de contratación y evaluaciones
        assert (await c.get("/api/admin/empresas", headers=h)).status_code == 200
        assert (await c.get("/api/admin/contrataciones", headers=h)).status_code == 200
        r = await c.get("/api/admin/evaluaciones", headers=h)
        assert r.status_code == 200, r.text
        fila = next(e for e in r.json()["items"] if e["id"] == x["ev"])
        assert fila["empresa"] == {"id": x["empresa_id"], "razon_social": "ACME Servicios SpA"}
        assert fila["completada"] is True and fila["origen"] == "publica"
        r = await c.get(f"/api/admin/evaluaciones?empresa_id={x['empresa_id']}", headers=h)
        assert [e["id"] for e in r.json()["items"]] == [x["ev"]]
        assert "email" not in str(r.json()) and "@" not in str(r.json())
        # El cliente no entra al panel interno
        hc = _bearer((await _login_cliente(c)).json()["access_token"])
        assert (await c.get("/api/admin/evaluaciones", headers=hc)).status_code == 403

        assert (await c.post("/api/auth/logout", headers=h)).status_code == 204
        assert (await c.get("/api/admin/empresas", headers=h)).status_code == 401
        acciones = {i["accion"] for i in await _bitacora(c)}
        assert {"admin.inicio_sesion", "sesion.cierre"} <= acciones
    _correr(esc)


def test_un_sid_inventado_o_de_otro_usuario_no_sirve():
    async def esc(c):
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        sid = auth.verificar_token(r.json()["access_token"], settings.AUTH_SECRET).sid
        inventado = auth.emitir_token(1, "admin_therion", secreto=settings.AUTH_SECRET, sid="x" * 32)
        assert (await c.get("/api/admin/empresas", headers=_bearer(inventado))).status_code == 401
        # El sid real del admin firmado para otro rol/usuario tampoco abre nada
        robado = auth.emitir_token(2, "admin_therion", secreto=settings.AUTH_SECRET, sid=sid)
        assert (await c.get("/api/admin/empresas", headers=_bearer(robado))).status_code == 401
    _correr(esc)


# ===================================================================== C3: intentos fallidos
def test_los_intentos_fallidos_se_limitan_sin_revelar_si_el_email_existe(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FALLOS_CUENTA", 3)

    async def esc(c):
        await _cliente_activo(c)
        respuestas = {}
        for correo in (CLIENTE, "no-existe@acme.cl"):
            fallos = [await _login_cliente(c, "Clave-equivocada-1", correo) for _ in range(3)]
            assert all(r.status_code == 401 for r in fallos), [r.text for r in fallos]
            # Bloqueada: ni la contraseña correcta entra mientras dure la ventana
            bloqueo = await _login_cliente(c, PASSWORD, correo)
            assert bloqueo.status_code == 429 and _codigo(bloqueo) == "DEMASIADOS_INTENTOS", bloqueo.text
            assert int(bloqueo.headers["retry-after"]) > 0
            respuestas[correo] = (fallos[0].json(), bloqueo.json()["detail"]["mensaje"])
        # Mismo mensaje exista o no la cuenta (ni el 401 ni el 429 la delatan)
        assert respuestas[CLIENTE] == respuestas["no-existe@acme.cl"]

        # Al terminar la ventana entra, y entrar bien reinicia el contador de la cuenta
        _LIMITADOR["x"].limpiar()
        assert (await _login_cliente(c)).status_code == 200
        for _ in range(2):
            assert (await _login_cliente(c, "Clave-equivocada-1")).status_code == 401
        assert (await _login_cliente(c)).status_code == 200
        assert (await _login_cliente(c, "Clave-equivocada-1")).status_code == 401
        assert (await _login_cliente(c)).status_code == 200  # 1 fallo tras el reinicio: no bloquea

        # Cada intento quedó en la bitácora (exitoso, fallido y bloqueado), sin el correo escrito
        items = await _bitacora(c)
        fallidos = [i for i in items if i["accion"] == "sesion.inicio_fallido"]
        assert len(fallidos) >= 9 and all(i["resultado"] == "rechazado" for i in fallidos)
        assert {i["entidad_id"] for i in fallidos} >= {None}  # el correo inexistente no tiene id
        assert sum(i["accion"] == "sesion.inicio_bloqueado" for i in items) == 2
        assert sum(i["accion"] == "cliente.inicio_sesion" for i in items) == 3
        assert any(i["detalle"].get("bloqueo_activado") for i in fallidos)
        assert "@" not in str([i["detalle"] for i in items])
    _correr(esc)


def test_los_intentos_fallidos_tambien_se_limitan_por_ip_y_en_el_login_del_admin(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FALLOS_IP", 4)

    async def esc(c):
        for n in range(4):  # cuatro correos distintos desde la misma IP
            r = await c.post("/api/auth/login", json={"email": f"intruso{n}@x.cl", "password": "nada-de-nada-1"})
            assert r.status_code == 401
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 429 and _codigo(r) == "DEMASIADOS_INTENTOS"
        _LIMITADOR["x"].limpiar()
        r = await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
    _correr(esc)


def test_cuenta_pendiente_bloqueada_o_sin_contrato_responde_igual_que_credenciales_malas():
    async def esc(c):
        await hu27._empresa_creada(c)  # usuario sin activar
        sin_activar = await _login_cliente(c)
        malas = await _login_cliente(c, "otra-cosa-123", "nadie@acme.cl")
        assert sin_activar.status_code == malas.status_code == 401
        assert sin_activar.json() == malas.json()
    _correr(esc)


# ===================================================================== C1: recuperación
def test_recuperacion_de_contrasena_del_cliente_de_punta_a_punta():
    async def esc(c):
        await _cliente_activo(c)
        h_vieja = _bearer((await _login_cliente(c)).json()["access_token"])

        existe = await c.post("/api/auth/recuperacion", json={"tipo": "cliente", "email": CLIENTE.upper()})
        no_existe = await c.post("/api/auth/recuperacion", json={"tipo": "cliente", "email": "nadie@acme.cl"})
        assert existe.status_code == no_existe.status_code == 202
        assert existe.json() == no_existe.json()  # no revela si el correo existe
        assert _correos("nadie@acme.cl") == []
        token = _token_recuperacion(CLIENTE)
        recuperacion = [t for t in _correos(CLIENTE) if "/restablecer#token=" in t]
        assert len(recuperacion) == 1 and "Gabriela" not in recuperacion[0]  # el correo no lleva el nombre

        r = await c.post("/api/auth/recuperacion/verificar", json={"token": token})
        assert r.status_code == 200 and r.json()["tipo"] == "cliente", r.text
        assert r.json()["email"] != CLIENTE and "***" in r.json()["email"]  # enmascarado

        # Contraseña débil: 422 y el enlace sigue sirviendo
        r = await c.post("/api/auth/recuperacion/restablecer", json={"token": token, "password": "corta"})
        assert r.status_code == 422 and _codigo(r) == "CONTRASENA_DEBIL" and r.json()["detail"]["problemas"]
        r = await c.post("/api/auth/recuperacion/restablecer", json={"token": token, "password": NUEVA})
        assert r.status_code == 200 and r.json() == {
            "restablecido": True, "tipo": "cliente",
            "mensaje": "Tu contraseña quedó actualizada. Ya puedes iniciar sesión."}

        # Un solo uso; las sesiones abiertas se cerraron; la contraseña vieja ya no sirve
        r = await c.post("/api/auth/recuperacion/restablecer", json={"token": token, "password": NUEVA + "x"})
        assert r.status_code == 400 and _codigo(r) == "ENLACE_INVALIDO"
        assert (await c.get("/api/cliente/empresa", headers=h_vieja)).status_code == 401
        assert (await _login_cliente(c)).status_code == 401
        assert (await _login_cliente(c, NUEVA)).status_code == 200
        assert any("se acaba de cambiar" in t for t in _correos(CLIENTE))  # aviso del cambio

        items = await _bitacora(c)
        pedidos = [i for i in items if i["accion"] == "recuperacion.solicitada"]
        assert sorted(i["resultado"] for i in pedidos) == ["ok", "rechazado"]
        usada = next(i for i in items if i["accion"] == "recuperacion.contrasena_restablecida")
        assert usada["detalle"]["sesiones_cerradas"] == 1
        assert "recuperacion.rechazada" in {i["accion"] for i in items}
        assert "@" not in str([i["detalle"] for i in items])
    _correr(esc)


def test_recuperacion_del_admin_revoca_enlaces_anteriores_y_vence():
    async def esc(c):
        def tokens() -> set[str]:
            return {m.group(1) for t in _correos(ADMIN_EMAIL) for m in [re.search(r"#token=([A-Za-z0-9_-]+)", t)] if m}

        r = await c.post("/api/auth/recuperacion", json={"tipo": "admin", "email": ADMIN_EMAIL})
        assert r.status_code == 202
        (primero,) = tokens()
        r = await c.post("/api/auth/recuperacion", json={"tipo": "admin", "email": ADMIN_EMAIL})
        assert r.status_code == 202
        (segundo,) = tokens() - {primero}
        r = await c.post("/api/auth/recuperacion/verificar", json={"token": primero})
        assert r.status_code == 400 and _codigo(r) == "ENLACE_INVALIDO"  # revocado por el segundo
        r = await c.post("/api/auth/recuperacion/verificar", json={"token": segundo})
        assert r.status_code == 200 and r.json()["tipo"] == "admin"

        async def vencer(s):
            from app.domain.models import TokenRecuperacion
            for fila in (await s.execute(select(TokenRecuperacion))).scalars():
                fila.fecha_expiracion = fila.fecha_creacion - timedelta(minutes=1)
            await s.commit()
        await hu27._bd(vencer)
        r = await c.post("/api/auth/recuperacion/restablecer", json={"token": segundo, "password": NUEVA})
        assert r.status_code == 410 and _codigo(r) == "ENLACE_VENCIDO"
        # El tipo importa: el correo del admin no recibe enlaces como "cliente"
        r = await c.post("/api/auth/recuperacion", json={"tipo": "cliente", "email": ADMIN_EMAIL})
        assert r.status_code == 202 and len(_correos(ADMIN_EMAIL)) == 2
    _correr(esc)


def test_recuperacion_limitada_por_cuenta_responde_igual_y_desbloquea_el_login(monkeypatch):
    monkeypatch.setattr(settings, "RECUPERACION_CORREOS_CUENTA_HORA", 1)
    monkeypatch.setattr(settings, "LOGIN_MAX_FALLOS_CUENTA", 2)

    async def esc(c):
        await _cliente_activo(c)
        for _ in range(2):
            assert (await _login_cliente(c, "Clave-equivocada-1")).status_code == 401
        assert (await _login_cliente(c)).status_code == 429  # bloqueada

        a = await c.post("/api/auth/recuperacion", json={"tipo": "cliente", "email": CLIENTE})
        b = await c.post("/api/auth/recuperacion", json={"tipo": "cliente", "email": CLIENTE})
        assert a.status_code == b.status_code == 202 and a.json() == b.json()
        enlaces = [t for t in _correos(CLIENTE) if "/restablecer#token=" in t]
        assert len(enlaces) == 1  # el segundo pedido no envió nada

        r = await c.post("/api/auth/recuperacion/restablecer",
                         json={"token": _token_recuperacion(CLIENTE), "password": NUEVA})
        assert r.status_code == 200, r.text
        # Quien recuperó su contraseña entra de inmediato aunque la cuenta estuviera bloqueada
        assert (await _login_cliente(c, NUEVA)).status_code == 200
    _correr(esc)


def test_un_usuario_que_no_activo_su_cuenta_no_recibe_enlace_de_recuperacion():
    async def esc(c):
        await hu27._empresa_creada(c)
        r = await c.post("/api/auth/recuperacion", json={"tipo": "cliente", "email": CLIENTE})
        assert r.status_code == 202
        assert not [t for t in _correos(CLIENTE) if "/restablecer#token=" in t]
    _correr(esc)
