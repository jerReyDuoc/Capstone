"""
QA - HU-09: Como Auditor Externo, quiero exportar un log inmutable con el historial de
modificaciones y supresiones de datos (Ley 21.719, art. 14 ter).

  C1  Tabla audit_log append-only sin permisos UPDATE/DELETE.
      - En proceso (SQLite): el modelo, la migración (permisos del rol de la app, triggers de
        UPDATE/DELETE/TRUNCATE) y que el código no tenga cómo modificar ni borrar filas.
      - En PostgreSQL real (HU09_PG_LIVE=1, dentro de Docker): el rol de la app recibe
        "permission denied" y el dueño choca con los triggers.
  C2  Registro obligatorio de timestamp, usuario/sistema, IP, acción y resultado.
  C3  Verificación de integridad por hash en lote (servidor y script independiente).
  +   Rol auditor_externo, exportación ZIP y cobertura de modificaciones y supresiones.

Solo en proceso (SQLite en memoria), salvo la prueba en vivo opcional de C1.
"""
import asyncio
import io
import json
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text

from _api_harness import MODO, cliente_api  # noqa: E402
from app.core import autenticacion as auth  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.domain import auditoria_hash  # noqa: E402

if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

pytestmark = pytest.mark.skipif(MODO == "live", reason="HU-09: solo en proceso")

SECRETO = "secreto-de-pruebas-hu09-0123456789abcdef"
RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "versions" / "d2f8a6c4e1b9_hu09_audit_log_inmutable.py"
PASSWORD_AUDITOR = "Auditoria-Externa-2026"
REFERENTE_ID = 1   # sembrado por el arnés (_api_harness._sembrar)


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", SECRETO)
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "AUDIT_LOTE_TAMANO", 10)
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


def admin() -> dict:
    return _h(1, "admin_therion")


async def _bd(fn):
    from app.core.database import get_db
    from app.main import app

    gen = app.dependency_overrides[get_db]()
    s = await gen.__anext__()
    try:
        return await fn(s)
    finally:
        await gen.aclose()


async def _filas(accion: str | None = None):
    from app.domain.models import AuditLog

    async def leer(s):
        q = select(AuditLog).order_by(AuditLog.id)
        if accion:
            q = q.where(AuditLog.accion == accion)
        return list((await s.execute(q)).scalars().all())
    return await _bd(leer)


async def _auditor(c, email="auditora@firma-externa.cl", dias=30) -> tuple[int, dict]:
    r = await c.post("/api/admin/auditores", headers=admin(), json={
        "email": email, "organizacion": "Firma Auditora Externa SpA", "password": PASSWORD_AUDITOR,
        "dias_vigencia": dias})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = await c.post("/api/auth/auditor", json={"email": email, "password": PASSWORD_AUDITOR})
    assert r.status_code == 200, r.text
    assert r.json()["rol"] == "auditor_externo"
    return aid, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _actividad(c, n: int = 3) -> None:
    """Genera registros reales en el log: logins de admin (éxito y fallidos)."""
    from _api_harness import ADMIN_EMAIL, ADMIN_PASSWORD
    for _ in range(n):
        assert (await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})).status_code == 200
    assert (await c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "mala"})).status_code == 401


# ===================================================================== C1: append-only
def test_c1_el_codigo_no_tiene_como_modificar_ni_borrar_el_log():
    from app.infrastructure.repositories.bitacora_repository import BitacoraRepository
    publicos = {n for n in dir(BitacoraRepository) if not n.startswith("_")}
    assert publicos == {"registrar", "listar"}
    # Ningún UPDATE/DELETE sobre audit_log en el código de la app
    for ruta in (RAIZ / "app").rglob("*.py"):
        contenido = ruta.read_text(encoding="utf-8").lower()
        for prohibido in ("update audit_log", "delete from audit_log", "truncate audit_log",
                          "update(auditlog", "delete(auditlog", "update(bitacoraauditoria", "delete(bitacoraauditoria"):
            assert prohibido not in contenido, f"{ruta}: {prohibido}"


def test_c1_la_migracion_quita_update_delete_truncate_y_agrega_triggers():
    m = MIGRACION.read_text(encoding="utf-8")
    assert "op.rename_table('bitacora_auditoria', 'audit_log')" in m
    assert "BEFORE UPDATE OR DELETE ON {tabla}" in m and "BEFORE TRUNCATE ON {tabla}" in m
    assert 'REVOKE ALL ON {tabla} FROM {rol}' in m and 'GRANT SELECT, INSERT ON {tabla} TO {rol}' in m
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON {tabla} FROM PUBLIC" in m
    assert '_TABLAS_INMUTABLES = ("audit_log", "audit_log_sello")' in m
    assert "NOSUPERUSER" in m  # el rol de la app no es superusuario (a él sí le aplican los permisos)


COMPOSE = RAIZ.parent / "docker-compose.yml"


@pytest.mark.skipif(not COMPOSE.is_file(),
                    reason="docker-compose.yml no está dentro del contenedor (solo se copia backend/); "
                           "esta prueba corre en el CI y fuera de Docker")
def test_c1_compose_conecta_api_y_worker_con_el_rol_limitado():
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "${DB_APP_USER:-complianceia_app}:${DB_APP_PASSWORD:-complianceia_app_dev}@db" in compose
    assert "${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-1234}@db" in compose   # migrate sigue como dueño


@pytest.mark.skipif(os.environ.get("HU09_PG_LIVE") != "1",
                    reason="C1 en PostgreSQL real: HU09_PG_LIVE=1 dentro del contenedor (ver CAMBIOS_HU09.md)")
def test_c1_en_postgresql_el_rol_de_la_app_no_puede_update_delete_truncate():
    import psycopg2
    from psycopg2 import errors

    url = settings.DATABASE_URL_SYNC.replace("postgresql+psycopg2://", "postgresql://")
    con = psycopg2.connect(url)
    try:
        cur = con.cursor()
        cur.execute("SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user")
        usuario, superusuario = cur.fetchone()
        assert not superusuario, f"La app se conecta como superusuario ({usuario}): revisa DB_APP_USER en el compose"
        # INSERT permitido (se revierte: no deja nada)
        cur.execute("INSERT INTO audit_log (fecha, actor_rol, accion, entidad, resultado, ip) "
                    "VALUES (now(), 'sistema', 'qa.hu09', 'qa', 'ok', 'sistema:qa') RETURNING id")
        assert cur.fetchone()[0] > 0
        con.rollback()
        for sql in ("UPDATE audit_log SET resultado = 'error'", "DELETE FROM audit_log",
                    "TRUNCATE audit_log", "UPDATE audit_log_sello SET cantidad = 1", "DELETE FROM audit_log_sello"):
            with pytest.raises(errors.InsufficientPrivilege):
                cur.execute(sql)
            con.rollback()
        with pytest.raises(errors.CheckViolation):   # C2 en la BD: sin IP no entra
            cur.execute("INSERT INTO audit_log (fecha, actor_rol, accion, entidad, resultado) "
                        "VALUES (now(), 'sistema', 'qa.hu09', 'qa', 'ok')")
        con.rollback()
    finally:
        con.close()


# ===================================================================== C2: campos obligatorios
def test_c2_cada_registro_trae_fecha_actor_ip_accion_y_resultado():
    async def esc(c):
        await _actividad(c)
        filas = await _filas()
        assert filas
        for f in filas:
            assert f.fecha and f.actor_rol and f.accion and f.resultado in ("ok", "rechazado", "error", "omitido")
            assert f.ip == "127.0.0.1"   # IP de la conexión del cliente de pruebas
            assert f.actor_id is not None or f.actor_rol in ("anonimo", "sistema")
        assert {f.resultado for f in filas} >= {"ok", "rechazado"}
    _correr(esc)


def test_c2_ip_del_bff_solo_con_su_secreto_y_siempre_normalizada(monkeypatch):
    async def esc(c):
        from _api_harness import ADMIN_EMAIL, ADMIN_PASSWORD
        cuerpo = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        monkeypatch.setattr(settings, "BFF_SHARED_SECRET", "b" * 32)
        await c.post("/api/auth/login", json=cuerpo, headers={"X-BFF-Secret": "b" * 32, "X-Cliente-IP": "200.27.10.5"})
        await c.post("/api/auth/login", json=cuerpo, headers={"X-BFF-Secret": "falso", "X-Cliente-IP": "8.8.8.8"})
        await c.post("/api/auth/login", json=cuerpo, headers={"X-BFF-Secret": "b" * 32, "X-Cliente-IP": "<script>x"})
        await c.post("/api/auth/login", json=cuerpo, headers={"X-BFF-Secret": "b" * 32, "X-Cliente-IP": "::ffff:10.1.2.3"})
        ips = [f.ip for f in await _filas("admin.inicio_sesion")]
        assert ips == ["200.27.10.5", "127.0.0.1", "desconocida", "10.1.2.3"]
    _correr(esc)


def test_c2_registrar_rechaza_campos_obligatorios_invalidos():
    from app.infrastructure.repositories.bitacora_repository import BitacoraRepository

    class _S:
        def add(self, _):
            pass
    repo = BitacoraRepository(_S())
    with pytest.raises(ValueError, match="resultado"):
        repo.registrar(accion="a", entidad="e", actor_rol="sistema", resultado="quizas")
    with pytest.raises(ValueError, match="debe llevar su id"):
        repo.registrar(accion="a", entidad="e", actor_rol="cliente")
    with pytest.raises(ValueError, match="obligatorias"):
        repo.registrar(accion="", entidad="e", actor_rol="sistema")


def test_c2_fuera_de_una_peticion_el_origen_es_el_proceso():
    from app.core import contexto_auditoria as ctx
    from app.infrastructure.repositories.bitacora_repository import BitacoraRepository

    class _S:
        def add(self, _):
            pass
    try:
        ctx.fijar_origen_por_defecto(ctx.ORIGEN_WORKER)
        assert BitacoraRepository(_S()).registrar(accion="a", entidad="e", actor_rol="sistema").ip == "sistema:worker"
    finally:
        ctx.fijar_origen_por_defecto(ctx.ORIGEN_INTERNO)
    assert ctx.normalizar_ip("2001:DB8::0001") == "2001:db8::1"
    assert ctx.normalizar_ip("") == ctx.normalizar_ip("no-es-ip") == "desconocida"


def test_c2_la_bd_rechaza_un_registro_sin_ip():
    async def esc(c):
        from sqlalchemy.exc import IntegrityError

        async def insertar(s):
            await s.execute(text("INSERT INTO audit_log (fecha, actor_rol, accion, entidad, resultado) "
                                 "VALUES ('2026-11-01 10:00:00', 'sistema', 'x', 'y', 'ok')"))
            await s.commit()
        with pytest.raises(IntegrityError):
            await _bd(insertar)
    _correr(esc)


# ===================================================================== C3: hash en lote
def _fila(i, ip="10.0.0.1", **extra):
    return {"id": i, "fecha": datetime(2026, 11, 1, 12, 0, 0) + timedelta(seconds=i), "actor_rol": "admin_therion",
            "actor_id": 1, "accion": "respuesta.modificada", "entidad": "respuestas", "entidad_id": i,
            "resultado": "ok", "detalle": {"n": i}, "ip": ip, **extra}


def _cadena(n=6, clave=b"k" * 32, ip="10.0.0.1"):
    filas, anterior = [], auditoria_hash.GENESIS
    for i in range(1, n + 1):
        f = _fila(i, ip=ip if i > 2 else None)   # las 2 primeras: filas previas a HU-09 (sin IP, v1)
        f["hash_anterior"] = anterior
        f["hash"] = auditoria_hash.calcular(clave, f, anterior)
        anterior = f["hash"]
        filas.append(f)
    return filas


def test_c3_la_ip_entra_al_hash_y_las_filas_previas_siguen_verificando():
    k = b"k" * 32
    filas = _cadena()
    assert auditoria_hash.verificar(filas, k)["integra"]
    sin_ip = [dict(f) for f in filas]
    sin_ip[4]["ip"] = None        # borrar la IP de una fila ya encadenada se detecta
    assert auditoria_hash.verificar(sin_ip, k)["primera_falla"] == {"id": 5, "motivo": "contenido_alterado"}
    otra_ip = [dict(f) for f in filas]
    otra_ip[3]["ip"] = "10.9.9.9"
    assert auditoria_hash.verificar(otra_ip, k)["primera_falla"] == {"id": 4, "motivo": "contenido_alterado"}


def test_c3_hash_de_lote_cambia_con_cualquier_alteracion():
    filas = _cadena()
    base = auditoria_hash.hash_lote(filas)
    alterada = [dict(f) for f in filas]
    alterada[2]["resultado"] = "rechazado"
    assert auditoria_hash.hash_lote(alterada) != base
    assert auditoria_hash.hash_lote(filas[:3] + filas[4:]) != base          # una fila menos
    assert auditoria_hash.hash_lote([filas[1], filas[0], *filas[2:]]) != base  # reordenadas
    renumerada = [dict(f) for f in filas]
    renumerada[5]["id"] = 60
    assert auditoria_hash.hash_lote(renumerada) != base                      # el id es parte de la huella


def test_c3_cadena_de_sellos_y_motivos_de_falla():
    k = b"k" * 32
    filas = _cadena()
    s1 = {"id": 1, "desde_id": 1, "hasta_id": 3, "cantidad": 3, "hash_lote": auditoria_hash.hash_lote(filas[:3]),
          "sello_anterior": auditoria_hash.GENESIS, "fecha": datetime(2026, 11, 1, 13, 0)}
    s1["sello"] = auditoria_hash.calcular_sello(s1)
    s1["firma"] = auditoria_hash.firmar_sello(k, s1["sello"])
    s2 = {"id": 2, "desde_id": 4, "hasta_id": 6, "cantidad": 3, "hash_lote": auditoria_hash.hash_lote(filas[3:]),
          "sello_anterior": s1["sello"], "fecha": datetime(2026, 11, 1, 13, 0)}
    s2["sello"] = auditoria_hash.calcular_sello(s2)
    s2["firma"] = auditoria_hash.firmar_sello(k, s2["sello"])
    assert auditoria_hash.verificar_sello(s1, filas[:3], None, k) is None
    assert auditoria_hash.verificar_sello(s2, filas[3:], s1["sello"], k) is None
    assert auditoria_hash.verificar_sello(s2, filas[3:], "f" * 64, k) == "cadena_de_sellos_rota"
    assert auditoria_hash.verificar_sello({**s2, "cantidad": 2}, filas[3:], s1["sello"], k) == "sello_alterado"
    assert auditoria_hash.verificar_sello(s2, filas[3:], s1["sello"], b"x" * 32) == "firma_invalida"
    assert auditoria_hash.verificar_sello(s2, filas[3:5], s1["sello"], k) == "cantidad_distinta"
    alterada = [dict(f) for f in filas[3:]]
    alterada[1]["detalle"] = {"n": 999}
    assert auditoria_hash.verificar_sello(s2, alterada, s1["sello"], k) == "hash_lote_distinto"


def test_c3_api_sella_por_lotes_verifica_y_detecta_alteracion_y_borrado():
    async def esc(c):
        from app.infrastructure.repositories.audit_log_lotes import sellar_pendientes

        await _actividad(c, n=12)  # 13 registros (12 logins + 1 fallido) -> lotes de 10
        _, ha = await _auditor(c)

        async def sellar(s):
            nuevos = await sellar_pendientes(s)
            await s.commit()
            return [(n.id, n.desde_id, n.hasta_id, n.cantidad) for n in nuevos]
        lotes = await _bd(sellar)
        assert len(lotes) == 2 and lotes[0][3] == 10 and lotes[0][1] == 1
        assert await _bd(sellar) == []   # nada pendiente: no duplica sellos

        r = (await c.get("/api/auditoria/verificacion", headers=ha)).json()
        assert r["integra"] is True and r["metodo"] == "hash_en_lote"
        assert r["lotes"]["total"] == 2 and r["lotes"]["con_falla"] == 0
        assert r["filas"]["fuera_de_lote"] == 0 and r["ancla"]["ultimo_lote"] == 2

        # Alguien con acceso directo a la BD (en PostgreSQL lo impiden permisos y triggers;
        # en el SQLite de la prueba no) altera una fila del lote 1 y borra otra del lote 2
        async def manipular(s):
            await s.execute(text("UPDATE audit_log SET resultado = 'ok' WHERE id = 3"))
            await s.execute(text("DELETE FROM audit_log WHERE id = 12"))
            await s.commit()
        await _bd(manipular)
        r = (await c.get("/api/auditoria/verificacion", headers=ha)).json()
        assert r["integra"] is False
        motivos = {(f["lote"], f["motivo"]) for f in r["lotes"]["fallas"]}
        assert (2, "cantidad_distinta") in motivos
        assert r["cadena"]["primera_falla"]["id"] in (3, 13)
        # la propia verificación con falla queda en el log como "rechazado"
        ver = await _filas("auditoria.verificacion")
        assert ver[-1].resultado == "rechazado" and ver[-1].actor_rol == "auditor_externo"
    _correr(esc)


def test_c3_admin_verificacion_conserva_las_claves_de_hu18_y_agrega_lotes():
    async def esc(c):
        await _actividad(c)
        r = (await c.get("/api/admin/bitacora/verificacion", headers=admin())).json()
        assert {"integra", "total", "verificadas", "primera_falla", "ancla", "lotes", "filas", "ancla_lote"} <= set(r)
        assert r["integra"] is True
    _correr(esc)


# ===================================================================== exportación
def _abrir_zip(contenido: bytes, destino: Path) -> dict:
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        z.extractall(destino)
        return {n: z.read(n) for n in z.namelist()}


def _verificar(destino: Path, *args) -> int:
    from app.domain import verificar_exportacion
    return verificar_exportacion.main([str(destino), *args])


def test_exportacion_zip_verificable_sin_el_sistema(tmp_path):
    async def esc(c):
        await _actividad(c, n=14)
        aid, ha = await _auditor(c)
        r = await c.get("/api/auditoria/exportacion", headers=ha)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        import hashlib
        assert r.headers["x-audit-export-sha256"] == hashlib.sha256(r.content).hexdigest()
        archivos = _abrir_zip(r.content, tmp_path / "exp1")
        assert set(archivos) == {"audit_log.jsonl", "audit_log.csv", "lotes.json", "verificacion.json",
                                 "manifiesto.json", "verificar_exportacion.py", "LEEME.txt"}
        manifiesto = json.loads(archivos["manifiesto.json"])
        for nombre, sha in manifiesto["archivos"].items():
            assert hashlib.sha256(archivos[nombre]).hexdigest() == sha
        registros = [json.loads(l) for l in archivos["audit_log.jsonl"].decode().splitlines()]
        assert manifiesto["registros"] == len(registros) >= 16
        for reg in registros:   # criterio 2 en lo exportado
            assert {"fecha", "actor_rol", "actor_id", "ip", "accion", "resultado", "categoria", "hash", "lote"} <= set(reg)
        assert manifiesto["log_integro_al_exportar"] is True
        # el script copiado en el ZIP es el mismo del sistema
        assert archivos["verificar_exportacion.py"] == (RAIZ / "app" / "domain" / "verificar_exportacion.py").read_bytes()
        assert _verificar(tmp_path / "exp1") == 0
        ancla = manifiesto["ultimo_sello"]

        # la exportación queda en el log, con el SHA-256 del ZIP y sin datos personales
        exp = (await _filas("auditoria.exportacion"))[-1]
        assert exp.actor_rol == "auditor_externo" and exp.actor_id == aid and exp.ip == "127.0.0.1"
        assert exp.detalle["sha256_zip"] == r.headers["x-audit-export-sha256"]

        # Exportación posterior: el ancla anterior sigue idéntica (el log no se reescribió)
        await _actividad(c, n=2)
        r2 = await c.get("/api/auditoria/exportacion", headers=ha)
        _abrir_zip(r2.content, tmp_path / "exp2")
        assert _verificar(tmp_path / "exp2", "--ancla", ancla) == 0
        assert _verificar(tmp_path / "exp2", "--ancla", "0" * 64) == 1
    _correr(esc)


def test_exportacion_adulterada_la_detecta_el_script(tmp_path):
    async def esc(c):
        await _actividad(c, n=5)
        _, ha = await _auditor(c)
        r = await c.get("/api/auditoria/exportacion", headers=ha)
        d = tmp_path / "exp"
        _abrir_zip(r.content, d)
        lineas = (d / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
        reg = json.loads(lineas[1])
        reg["resultado"] = "rechazado" if reg["resultado"] == "ok" else "ok"
        lineas[1] = json.dumps(reg, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        (d / "audit_log.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
        from app.domain import verificar_exportacion
        res = verificar_exportacion.verificar(d)
        assert res["ok"] is False
        assert any("SHA-256" in f for f in res["fallas"]) and any("hash recalculado" in f for f in res["fallas"])
        # aunque además se recalcule el manifiesto, el hash del lote sigue sin coincidir
        man = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
        import hashlib
        man["archivos"]["audit_log.jsonl"] = hashlib.sha256((d / "audit_log.jsonl").read_bytes()).hexdigest()
        (d / "manifiesto.json").write_text(json.dumps(man), encoding="utf-8")
        res = verificar_exportacion.verificar(d)
        assert res["ok"] is False and any("hash recalculado" in f for f in res["fallas"])
    _correr(esc)


def test_exportacion_por_rango_entrega_lotes_completos_y_valida_el_rango():
    async def esc(c):
        await _actividad(c, n=3)
        _, ha = await _auditor(c)
        manana = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        hoy = datetime.now(timezone.utc).date().isoformat()
        r = await c.get(f"/api/auditoria/exportacion?desde={hoy}&hasta={manana}", headers=ha)
        assert r.status_code == 200
        r = await c.get("/api/auditoria/exportacion?desde=2020-01-01&hasta=2020-01-02", headers=ha)
        assert r.status_code == 404 and r.json()["detail"]["codigo"] == "SIN_REGISTROS"
        r = await c.get(f"/api/auditoria/exportacion?desde={manana}&hasta={hoy}", headers=ha)
        assert r.status_code == 422
    _correr(esc)


def test_exportacion_con_tope_de_filas(monkeypatch):
    async def esc(c):
        await _actividad(c, n=5)
        monkeypatch.setattr(settings, "AUDIT_EXPORT_MAX_FILAS", 3)
        r = await c.get("/api/auditoria/exportacion", headers=admin())
        assert r.status_code == 413 and r.json()["detail"]["codigo"] == "EXPORTACION_DEMASIADO_GRANDE"
    _correr(esc)


# ===================================================================== rol auditor_externo
def test_auditor_solo_lee_el_log_y_cada_acceso_queda_registrado():
    async def esc(c):
        await _actividad(c)
        aid, ha = await _auditor(c)
        r = await c.get("/api/auditoria/registros?size=200", headers=ha)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all({"ip", "categoria", "hash"} <= set(i) for i in items)
        assert (await c.get("/api/auditoria/catalogo", headers=ha)).status_code == 200
        assert (await c.get("/api/auditoria/lotes", headers=ha)).status_code == 200
        # nada más del sistema
        assert (await c.get("/api/admin/bitacora", headers=ha)).status_code == 403
        assert (await c.get("/api/admin/auditores", headers=ha)).status_code == 403
        assert (await c.get("/api/admin/empresas", headers=ha)).status_code == 403
        assert (await c.get("/api/arcop/solicitudes", headers=ha)).status_code == 403
        assert (await c.get("/api/evaluaciones/1", headers=ha)).status_code == 404
        assert (await c.get("/api/evaluaciones", headers=ha)).json()["total"] == 0
        assert (await c.get("/api/respuestas/1", headers=ha)).status_code == 404
        consultas = await _filas("auditoria.consulta")
        assert consultas and consultas[-1].actor_id == aid and consultas[-1].detalle["filtros"] == {}
        login = (await _filas("auditor.inicio_sesion"))[-1]
        assert login.actor_rol == "auditor_externo" and login.ip == "127.0.0.1"
    _correr(esc)


def test_auditor_filtra_modificaciones_y_supresiones():
    async def esc(c):
        await _actividad(c)
        _, ha = await _auditor(c)
        r = await c.get("/api/auditoria/registros?categoria=seguridad", headers=ha)
        assert r.status_code == 200 and r.json()["total"] >= 1
        assert {i["categoria"] for i in r.json()["items"]} == {"seguridad"}
        assert (await c.get("/api/auditoria/registros?categoria=otra", headers=ha)).status_code == 422
        catalogo = (await c.get("/api/auditoria/catalogo", headers=ha)).json()
        por_accion = {a["accion"]: a["categoria"] for a in catalogo["acciones"]}
        assert por_accion["arcop.datos_suprimidos"] == "supresion"
        assert por_accion["respuesta.modificada"] == "modificacion"
        assert por_accion["retencion.titular_anonimizado"] == "supresion"
        assert "ip" in catalogo["campos_obligatorios"]
    _correr(esc)


def test_cuentas_de_auditor_validan_vencen_y_se_desactivan():
    async def esc(c):
        base = {"email": "a@firma.cl", "organizacion": "Firma", "password": PASSWORD_AUDITOR}
        assert (await c.post("/api/admin/auditores", headers=admin(), json={**base, "password": "corta"})).status_code == 422
        r = await c.post("/api/admin/auditores", headers=admin(), json={**base, "dias_vigencia": 400})
        assert r.status_code == 422
        aid, ha = await _auditor(c, email="a@firma.cl")
        assert (await c.post("/api/admin/auditores", headers=admin(), json=base)).status_code == 409
        assert (await c.post("/api/auth/auditor", json={"email": "a@firma.cl", "password": "mala-clave-123"})).status_code == 401

        # vence: el token deja de servir y no puede volver a entrar
        from app.domain.models import UsuarioAuditor

        async def vencer(s):
            a = await s.get(UsuarioAuditor, aid)
            a.fecha_expiracion = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
            await s.commit()
        await _bd(vencer)
        assert (await c.get("/api/auditoria/registros", headers=ha)).status_code == 401
        assert (await c.post("/api/auth/auditor", json={"email": "a@firma.cl", "password": PASSWORD_AUDITOR})).status_code == 401

        # el admin extiende la vigencia; luego lo desactiva y sus sesiones se cierran
        r = await c.patch(f"/api/admin/auditores/{aid}", headers=admin(), json={"dias_vigencia": 5})
        assert r.status_code == 200 and r.json()["vigente"] is True
        r = await c.post("/api/auth/auditor", json={"email": "a@firma.cl", "password": PASSWORD_AUDITOR})
        ha2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert (await c.get("/api/auditoria/lotes", headers=ha2)).status_code == 200
        r = await c.patch(f"/api/admin/auditores/{aid}", headers=admin(), json={"activo": False})
        assert r.status_code == 200 and r.json()["activo"] is False
        assert (await c.get("/api/auditoria/lotes", headers=ha2)).status_code == 401
        cambios = [f.detalle["cambios"] for f in await _filas("auditor.cuenta_actualizada")]
        assert cambios == [["vigencia"], ["desactivado"]]
        creada = (await _filas("auditor.cuenta_creada"))[-1]
        assert creada.actor_rol == "admin_therion" and "password" not in json.dumps(creada.detalle)
        listado = (await c.get("/api/admin/auditores", headers=admin())).json()["items"]
        assert listado[0]["id"] == aid and "password_hash" not in listado[0]
    _correr(esc)


@pytest.mark.parametrize("metodo,url,kwargs", [
    ("GET", "/api/auditoria/catalogo", {}),
    ("GET", "/api/auditoria/registros", {}),
    ("GET", "/api/auditoria/verificacion", {}),
    ("GET", "/api/auditoria/lotes", {}),
    ("GET", "/api/auditoria/exportacion", {}),
    ("GET", "/api/admin/auditores", {}),
    ("POST", "/api/admin/auditores", {"json": {"email": "x@y.cl", "organizacion": "Firma X", "password": PASSWORD_AUDITOR}}),
    ("PATCH", "/api/admin/auditores/1", {"json": {"activo": False}}),
])
def test_rutas_hu09_por_rol(metodo, url, kwargs):
    async def esc(c):
        await _actividad(c, n=1)
        assert (await c.request(metodo, url, **kwargs)).status_code == 401
        for cab in (_h(REFERENTE_ID, "referente"), _h(1, "encuestado")):
            r = await c.request(metodo, url, headers=cab, **kwargs)
            assert r.status_code in (401, 403), (url, r.status_code)
        solo_admin = url.startswith("/api/admin/")
        _, ha = await _auditor(c, email=f"aud{abs(hash(url)) % 10000}@firma.cl")
        r = await c.request(metodo, url, headers=ha, **kwargs)
        assert r.status_code == (403 if solo_admin else 200), (url, r.status_code, r.text)
        r = await c.request(metodo, url, headers=admin(), **kwargs)
        assert r.status_code in (200, 201), (url, r.status_code, r.text)
    _correr(esc)


# ===================================================================== modificaciones y supresiones
def test_modificacion_de_respuesta_y_revision_quedan_en_el_log_sin_texto():
    async def esc(c):
        from _api_harness import TODOS_LOS_CONTROLES
        from app.application.filters.control_tree import CONTROLES_BASE

        cuerpo = {"respuestas": [{"codigo": f"F{i}", "respuesta": i == 1} for i in range(1, 8)]}
        assert (await c.post("/api/evaluaciones/1/filtro", json=cuerpo, headers=admin())).status_code == 200
        control = TODOS_LOS_CONTROLES.index(CONTROLES_BASE[0]) + 1
        r = await c.post("/api/respuestas/", headers=admin(), json={
            "evaluacion_id": 1, "matriz_control_id": control, "estado_clasificacion": "cumplido",
            "justificacion": "Política aprobada por el directorio."})
        rid = r.json()["id_respuesta"]
        assert not await _filas("respuesta.modificada")  # crear no es modificar
        r = await c.put(f"/api/respuestas/{rid}", headers=admin(), json={
            "estado_clasificacion": "parcialmente_cumplido",
            "justificacion": "Existe la política, pero aún no se aplica en todas las áreas de la empresa."})
        assert r.status_code == 200, r.text
        # reenvío idéntico (guardado automático): no es una modificación
        await c.put(f"/api/respuestas/{rid}", headers=admin(), json={
            "estado_clasificacion": "parcialmente_cumplido",
            "justificacion": "Existe la política, pero aún no se aplica en todas las áreas de la empresa."})
        mods = await _filas("respuesta.modificada")
        assert len(mods) == 1
        d = mods[0].detalle
        assert (d["estado_anterior"], d["estado_nuevo"], d["justificacion_modificada"]) == \
            ("cumplido", "parcialmente_cumplido", True)
        assert "política" not in json.dumps(d, ensure_ascii=False).lower()   # nunca el texto
        assert mods[0].actor_rol == "admin_therion" and mods[0].ip == "127.0.0.1"

        r = await c.patch(f"/api/respuestas/{rid}/revision", headers=admin(), json={"clasificacion_revisada": "cumplido", "comentario": "Revisado por el Oficial de Cumplimiento."})
        assert r.status_code == 200
        rev = (await _filas("respuesta.revision_humana"))[-1]
        assert rev.detalle["estado_final_anterior"] == "parcialmente_cumplido" and rev.detalle["estado_final_nuevo"] == "cumplido"

        r = await c.patch("/api/evaluaciones/1/prueba", headers=admin(), json={"es_prueba": True})
        assert r.status_code == 200
        assert (await _filas("evaluacion.marcada_prueba"))[-1].detalle == {"es_prueba_anterior": False, "es_prueba": True}
    _correr(esc)


def test_supresion_arcop_queda_en_el_log_con_lo_suprimido():
    async def esc(c):
        titular = _h(REFERENTE_ID, "referente")
        r = await c.post("/api/arcop/solicitudes", headers=titular, json={
            "tipo": "supresion", "descripcion": "Solicito suprimir todos mis datos personales de la plataforma."})
        assert r.status_code == 201, r.text
        sid = r.json()["id_solicitud"]
        for estado in ("en_revision", "en_proceso"):
            assert (await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": estado},
                                  headers=admin())).status_code == 200
        r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion", headers=admin(),
                         json={"resultado": "resuelta", "respuesta": "Se anonimizaron sus datos personales."})
        assert r.status_code == 200, r.text
        filas = [f for f in await _filas() if f.entidad == "solicitudes_arcop" and f.entidad_id == sid]
        assert [f.accion for f in filas] == ["arcop.solicitud_creada", "arcop.estado_cambiado",
                                             "arcop.estado_cambiado", "arcop.solicitud_resuelta",
                                             "arcop.datos_suprimidos"]
        assert filas[0].actor_rol == "referente" and filas[0].actor_id == REFERENTE_ID
        supr = filas[-1]
        assert supr.actor_rol == "admin_therion" and isinstance(supr.detalle["suprimido"], dict)
        assert supr.detalle["tipo_solicitud"] == "supresion"
        assert "anonimizaron" not in json.dumps(supr.detalle)   # la respuesta (texto) no va
        _, ha = await _auditor(c)
        r = (await c.get("/api/auditoria/registros?categoria=supresion", headers=ha)).json()
        assert [i["accion"] for i in r["items"]] == ["arcop.datos_suprimidos"]
    _correr(esc)


def test_retencion_registra_cada_supresion_como_sistema():
    async def esc(c):
        from app.application.use_cases.aplicar_retencion import AplicarRetencionUseCase
        from app.domain.models import UsuarioTemporal

        async def correr(s):
            u = await s.get(UsuarioTemporal, REFERENTE_ID)
            u.fecha_expiracion = (datetime.now() - timedelta(days=400)).date()
            await s.commit()
            r = await AplicarRetencionUseCase(s, plazos={"titulares": 30, "arcop": None, "eventos": 10, "tutor": 30}).execute()
            return r
        r = await _bd(correr)
        assert r.titulares >= 1
        filas = await _filas("retencion.titular_anonimizado")
        assert filas and filas[0].actor_rol == "sistema" and filas[0].entidad_id == REFERENTE_ID
        assert filas[0].detalle["regla"] == "R1" and filas[0].detalle["plazo_dias"] == 30
        assert filas[0].ip.startswith("sistema:")
    _correr(esc)
