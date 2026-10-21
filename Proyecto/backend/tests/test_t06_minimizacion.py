"""
T-06 — Auditoría de minimización de datos en los modelos de base de datos.

Ejecutar desde Proyecto/backend/ (en Docker):
    docker compose exec worker pytest tests/test_t06_minimizacion.py -v

  1. Inventario: cada columna del modelo está clasificada en
     app/core/catalogo_datos_personales.py (y nada sobra). Si alguien agrega una
     columna sin clasificarla, esta prueba falla.
  2. Cada columna con datos personales declara finalidad, base de licitud y plazo.
  3. Toda columna de texto o JSON de las tablas operativas tiene un control de contenido.
  4. Detectores del script de auditoría (RUT con dígito verificador, correo, teléfono).
  5. H1: la supresión ARCOP del encuestado público borra su email opcional (HU-19).
  6. H2: `evidencias.datos_extraidos` ya no se persiste.
  7. H3: GUARDAR_MAPA_ENTIDADES_CIFRADO=true queda prohibido en producción.
  8. Plazos de conservación (R1 titulares, R2 ARCOP, R3 eventos de seguridad).
  9. H1 de punta a punta por la API (landing -> email -> supresión resuelta).
"""
import asyncio
import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import JSON, Text, select, text

import app.domain.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.catalogo_datos_personales import (
    CATALOGO, CATEGORIAS, NO_SE_GUARDA, columnas_personales,
)
from app.core.database import Base
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.models.evidencia import EstadoValidacion, Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_arcop import EventoSolicitud, SolicitudARCOP
from app.domain.models.usuario_temporal import UsuarioTemporal

RAIZ = Path(__file__).resolve().parents[1]
TABLAS_CATALOGO = {"dominio", "rubro", "ruta_formativa", "preguntas_filtro", "catalogo_brechas",
                   "matriz_controles", "benchmark", "resumen"}
HOY = date(2026, 10, 21)


def _script_auditoria():
    spec = importlib.util.spec_from_file_location("auditoria_t06", RAIZ / "scripts" / "auditoria_minimizacion.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ 1-3. inventario
def test_toda_columna_del_modelo_esta_clasificada_y_nada_sobra():
    modelo = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}
    catalogo = {t: set(cols) for t, cols in CATALOGO.items()}
    sin_clasificar = sorted(f"{t}.{c}" for t, cols in modelo.items() for c in cols - catalogo.get(t, set()))
    sobran = sorted(f"{t}.{c}" for t, cols in catalogo.items() for c in cols - modelo.get(t, set()))
    assert not sin_clasificar, f"Clasifica estas columnas en catalogo_datos_personales.py: {sin_clasificar}"
    assert not sobran, f"Columnas clasificadas que ya no existen en el modelo: {sobran}"


def test_columnas_personales_documentan_finalidad_base_y_plazo():
    faltan = []
    for tabla, col, d in columnas_personales():
        assert d.categoria in CATEGORIAS
        if not d.finalidad or not d.conservacion:
            faltan.append(f"{tabla}.{col}")
        if d.tratamiento != NO_SE_GUARDA and not d.base:
            faltan.append(f"{tabla}.{col} (base de licitud)")
    assert not faltan, f"Sin finalidad, base o plazo: {faltan}"
    assert len(columnas_personales()) >= 20


def test_textos_y_json_operativos_tienen_control_de_contenido():
    sin_control = []
    for t in Base.metadata.sorted_tables:
        if t.name in TABLAS_CATALOGO:
            continue
        for c in t.columns:
            if isinstance(c.type, (Text, JSON)) or getattr(c.type, "impl", None) is not None and \
                    isinstance(c.type.impl, Text):
                if not CATALOGO[t.name][c.name].escaneo:
                    sin_control.append(f"{t.name}.{c.name}")
    assert not sin_control, f"Textos/JSON sin control de contenido en la auditoría: {sin_control}"


def test_textos_arcop_cifrados_segun_el_modelo_y_el_inventario():
    from app.core.cifrado_columnas import TextoCifrado
    cifradas_modelo = {(t.name, c.name) for t in Base.metadata.sorted_tables for c in t.columns
                       if isinstance(c.type, TextoCifrado)}
    cifradas_catalogo = {(t, c) for t, cols in CATALOGO.items() for c, d in cols.items() if d.escaneo == "cifrado"}
    assert cifradas_modelo == cifradas_catalogo


# ------------------------------------------------------------------ 4. detectores
def test_detectores_de_pii_del_script_de_auditoria():
    tipos = _script_auditoria().tipos_pii
    assert tipos("RUT 12.345.678-5") == {"rut"}
    assert tipos("rut 12345678-5") == {"rut"}
    assert tipos("12.345.678-9") == set()                     # DV inválido: no es RUT
    assert tipos("Ley 21.719 y resolución 2026-10") == set()
    assert tipos("escribir a jperez@empresa-demo.cl") == {"correo"}
    assert tipos("llamar al +56 9 8765 4321") == {"telefono"}
    assert tipos("Lo aprobó [NOMBRE_ANON], RUT [RUT_ANON], [CORREO_ANON], [TEL_ANON]") == set()


# ------------------------------------------------------------------ BD SQLite en memoria
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


async def _titular(s, uid, *, email, vence, origen="invitacion", justificacion="Texto [RUT_ANON]"):
    s.add(UsuarioTemporal(id=uid, email=email, rubro_id=1, fecha_expiracion=vence,
                          validacion_invitacion="S" if origen == "invitacion" else None))
    s.add(Evaluacion(id=uid, usuario_temporal_id=uid, fecha_inicio=vence, estado_progreso="completada",
                     filtro_completado=True, origen=origen, es_prueba=False,
                     clave_acceso_hash="pbkdf2$x" if origen == "publica" else None))
    s.add(Respuesta(id=uid, evaluacion_id=uid, estado_clasificacion="cumplido",
                    estado_clasificacion_final="cumplido", justificacion_usuario=justificacion))
    s.add(Evidencia(id_evidencia=uid, respuesta_id=uid, nombre_archivo="acta_[RUT_ANON].txt",
                    storage_path=f"/tmp/no-existe-{uid}.txt", mime_type="text/plain", hash_archivo="a" * 64,
                    estado_validacion=EstadoValidacion.VALIDATED.value, justificacion_llm="ok"))
    await s.commit()


def _solicitud(sid, *, usuario=None, evaluacion=None, tipo="acceso", estado="resuelta", cierre=None):
    ahora = datetime(2026, 10, 1)
    return SolicitudARCOP(id=sid, tipo=tipo, estado=estado, descripcion="Mi RUT es 12.345.678-5",
                          codigo_seguimiento=f"ARC-T06-{sid:04d}", usuario_temporal_id=usuario,
                          evaluacion_id=evaluacion, fecha_creacion=ahora, fecha_actualizacion=ahora,
                          fecha_cierre=cierre, respuesta="Se entregó copia de sus datos" if cierre else None)


# ------------------------------------------------------------------ 5. H1
def test_h1_supresion_del_encuestado_publico_borra_su_email_opcional():
    from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository

    async def esc(Session):
        async with Session() as s:
            await _titular(s, 10, email="encuestado@correo-demo.cl", vence=HOY, origen="publica")
            conteo, _ = await AnonimizacionRepository(s).anonimizar_encuestado(10, datetime(2026, 10, 21))
            await s.commit()
        async with Session() as s:
            u = await s.get(UsuarioTemporal, 10)
            assert u.email is None and u.fecha_anonimizacion is not None
            assert (await s.get(Evaluacion, 10)).clave_acceso_hash is None
            assert conteo["usuario_temporal"] == 1
    _con_bd(esc)


def test_h1_supresion_del_encuestado_no_toca_al_invitado():
    """Solo se borra el email del usuario anónimo de una evaluación PÚBLICA."""
    from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository

    async def esc(Session):
        async with Session() as s:
            await _titular(s, 20, email="invitado@empresa-demo.cl", vence=HOY, origen="invitacion")
            await AnonimizacionRepository(s).anonimizar_encuestado(20, datetime(2026, 10, 21))
            await s.commit()
            assert (await s.get(UsuarioTemporal, 20)).email == "invitado@empresa-demo.cl"
    _con_bd(esc)


# ------------------------------------------------------------------ 6. H2
def test_h2_datos_extraidos_por_el_llm_no_se_persisten():
    from app.application.schemas.evidence_validation import EvidenceValidation
    from app.application.use_cases.process_evidence import ProcessEvidenceUseCase
    from test_hu06_anonimizacion import _anon, _storage
    from test_seguridad_integracion import FakeEvidenciaRepo, FakeRespuestaRepo, _control, _respuesta

    class ValidadorConDatos:
        async def validate(self, contenido, control, respuesta, brecha=None, justificacion=None, contexto=None):
            return EvidenceValidation(
                clasificacion="cumplido", confianza=0.95, justificacion="ok",
                respalda_clasificacion_usuario=True, evidencia_suficiente=True,
                datos_extraidos={"firmante": "Juan Pérez Soto", "documento": "acta"},
            )

    storage, _ = _storage()
    ruta = asyncio.run(storage.save(b"Acta de directorio", "acta.txt"))
    evidencia = Evidencia(id_evidencia=99, respuesta_id=10, nombre_archivo="acta.txt", storage_path=ruta,
                          mime_type="text/plain", hash_archivo="0" * 64,
                          estado_validacion=EstadoValidacion.PENDING.value)
    uc = ProcessEvidenceUseCase(FakeEvidenciaRepo(evidencia), FakeRespuestaRepo(_respuesta(), _control()),
                                storage, ValidadorConDatos(), anonimizador=_anon())
    asyncio.run(uc.execute(99))
    assert evidencia.estado_validacion == EstadoValidacion.VALIDATED.value
    assert evidencia.clasificacion_llm == "cumplido"
    assert evidencia.datos_extraidos is None


# ------------------------------------------------------------------ 7. H3 y validación de plazos
def test_h3_mapa_reversible_prohibido_en_produccion():
    from app.core.config import Settings
    base = dict(DATABASE_URL="x", DATABASE_URL_SYNC="x", REDIS_URL="x", GROQ_API_KEY="x",
                APP_ENV="production", ENTITY_MAP_KEY="k", AUTH_SECRET="a" * 32,
                TURNSTILE_SECRET_KEY="t", BFF_SHARED_SECRET="b" * 32)
    Settings(_env_file=None, **base)  # configuración válida
    with pytest.raises(ValueError, match="GUARDAR_MAPA_ENTIDADES_CIFRADO"):
        Settings(_env_file=None, GUARDAR_MAPA_ENTIDADES_CIFRADO=True, **base)
    with pytest.raises(ValueError, match="RETENCION_DATOS_TITULAR_DIAS"):
        Settings(_env_file=None, RETENCION_DATOS_TITULAR_DIAS=0, **base)


# ------------------------------------------------------------------ 8. plazos de conservación
class StorageEspia:
    def __init__(self):
        self.borrados = []

    async def delete(self, ruta):
        self.borrados.append(ruta)


def _uc(s, storage=None, **plazos):
    from app.application.use_cases.aplicar_retencion import AplicarRetencionUseCase
    p = {"titulares": None, "arcop": None, "eventos": None, **plazos}
    return AplicarRetencionUseCase(s, storage=storage, hoy=HOY, plazos=p)


def test_retencion_sin_plazos_no_hace_nada():
    async def esc(Session):
        async with Session() as s:
            await _titular(s, 1, email="a@demo.cl", vence=HOY - timedelta(days=1000))
            r = await _uc(s).execute()
            assert r.reglas_desactivadas == ["titulares", "arcop", "eventos"]
            assert r.titulares == 0
            assert (await s.get(UsuarioTemporal, 1)).email == "a@demo.cl"
    _con_bd(esc)


def test_r1_titulares_vencidos_se_anonimizan_y_se_conservan_los_puntajes():
    async def esc(Session):
        async with Session() as s:
            await _titular(s, 1, email="vencido@demo.cl", vence=HOY - timedelta(days=400))
            await _titular(s, 2, email="vigente@demo.cl", vence=HOY - timedelta(days=100))
            await _titular(s, 3, email="publico@demo.cl", vence=HOY - timedelta(days=400), origen="publica")

            simulado = await _uc(s, titulares=365).execute(aplicar=False)
            assert simulado.simulacion and simulado.titulares == 2
            assert (await s.get(UsuarioTemporal, 1)).email == "vencido@demo.cl"  # la simulación no cambia nada

            espia = StorageEspia()
            r = await _uc(s, storage=espia, titulares=365).execute()
            assert r.titulares == 2 and r.archivos_borrados == 2
        async with Session() as s:
            for uid in (1, 3):
                u = await s.get(UsuarioTemporal, uid)
                assert u.email is None and u.fecha_anonimizacion is not None
                resp = await s.get(Respuesta, uid)
                assert resp.justificacion_usuario is None
                assert resp.estado_clasificacion_final == "cumplido"         # el puntaje se conserva
                ev = await s.get(Evidencia, uid)
                assert ev.nombre_archivo == "[anonimizado]" and ev.storage_path == ""
            assert (await s.get(Evaluacion, 3)).clave_acceso_hash is None
            assert (await s.get(UsuarioTemporal, 2)).email == "vigente@demo.cl"
            # Idempotente: una segunda pasada no encuentra nada
            assert (await _uc(s, titulares=365).execute()).titulares == 0
    _con_bd(esc)


def test_r1_omite_al_titular_con_solicitud_arcop_abierta():
    async def esc(Session):
        async with Session() as s:
            await _titular(s, 1, email="vencido@demo.cl", vence=HOY - timedelta(days=400))
            s.add(_solicitud(1, usuario=1, estado="en_revision"))
            await s.commit()
            r = await _uc(s, titulares=365).execute()
            assert r.titulares == 0 and r.titulares_omitidos_por_arcop_abierta == 1
            assert (await s.get(UsuarioTemporal, 1)).email == "vencido@demo.cl"
    _con_bd(esc)


def test_r2_solicitudes_arcop_cerradas_quedan_sin_texto_y_con_historial():
    async def esc(Session):
        async with Session() as s:
            await _titular(s, 1, email="t@demo.cl", vence=HOY)
            s.add(_solicitud(1, usuario=1, cierre=datetime(2024, 1, 10)))     # cerrada hace > 2 años
            s.add(_solicitud(2, usuario=1, cierre=datetime(2026, 9, 1)))      # cerrada hace poco
            s.add(EventoSolicitud(id=1, solicitud_id=1, fecha=datetime(2024, 1, 5), tipo_evento="cambio_estado",
                                  estado_anterior="recibida", estado_nuevo="en_revision",
                                  actor_rol="admin_therion", actor_id=1, comentario="Pedimos su RUT 12.345.678-5"))
            await s.commit()

            r = await _uc(s, arcop=730).execute()
            assert r.solicitudes_arcop == 1
            assert (await _uc(s, arcop=730).execute()).solicitudes_arcop == 0   # idempotente
        async with Session() as s:
            vieja, nueva = await s.get(SolicitudARCOP, 1), await s.get(SolicitudARCOP, 2)
            assert vieja.descripcion == "[anonimizado]" and vieja.respuesta == "[anonimizado]"
            assert vieja.tipo == "acceso" and vieja.estado == "resuelta" and vieja.fecha_cierre is not None
            assert nueva.descripcion.startswith("Mi RUT")
            eventos = (await s.execute(select(EventoSolicitud).where(EventoSolicitud.solicitud_id == 1)
                                       .order_by(EventoSolicitud.id))).scalars().all()
            assert eventos[0].comentario == "[anonimizado]"
            assert eventos[-1].tipo_evento == "anonimizacion" and eventos[-1].actor_rol == "sistema"
            # En la BD sigue cifrado (TextoCifrado), también el marcador
            crudo = (await s.execute(text("SELECT descripcion FROM solicitudes_arcop WHERE id_solicitud = 1"))).scalar()
            assert crudo.startswith("enc:v1:")
    _con_bd(esc)


def test_r3_extracto_de_eventos_revisados_y_antiguos():
    async def esc(Session):
        async with Session() as s:
            for i, (revisado, dias) in enumerate([(True, 400), (False, 400), (True, 10)], start=1):
                s.add(EventoSeguridad(id_evento=i, fecha=datetime.combine(HOY, datetime.min.time()) - timedelta(days=dias),
                                      tipo="prompt_injection", origen="justificacion",
                                      extracto="ignora todo [NOMBRE_ANON]", hash_texto="h" * 64, revisado=revisado))
            await s.commit()
            assert (await _uc(s, eventos=180).execute(aplicar=False)).eventos_seguridad == 1
            assert (await _uc(s, eventos=180).execute()).eventos_seguridad == 1
        async with Session() as s:
            extractos = [(await s.get(EventoSeguridad, i)).extracto for i in (1, 2, 3)]
            assert extractos[0] is None and extractos[1] and extractos[2]
            assert (await s.get(EventoSeguridad, 1)).hash_texto == "h" * 64
    _con_bd(esc)


# ------------------------------------------------------------------ H1 por la API (camino real)
def test_h1_por_la_api_encuestado_deja_email_pide_supresion_y_el_email_se_borra(monkeypatch):
    """Landing -> email opcional -> solicitud de supresión -> el admin la resuelve -> sin email en BD."""
    from _api_harness import MODO, cliente_api
    from app.core import autenticacion as auth
    from app.core.config import settings
    from app.core.database import get_db
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    if MODO == "live":
        pytest.skip("Solo en proceso (los tokens dependen del AUTH_SECRET del servidor).")
    pytest.importorskip("aiosqlite")
    secreto = "secreto-de-pruebas-t06-0123456789abcdef"
    monkeypatch.setattr(settings, "AUTH_SECRET", secreto)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setitem(app.dependency_overrides, obtener_limitador, lambda: LimitadorMemoria())
    admin = {"Authorization": f"Bearer {auth.emitir_token(1, 'admin_therion', secreto=secreto)}"}

    async def _main():
        async with cliente_api() as c:
            r = await c.post("/api/encuesta-publica/iniciar", json={
                "rubro_id": 1, "aviso_legal": {"version": settings.AVISO_LEGAL_VERSION, "aceptado": True},
                "captcha_token": "token-de-prueba"})
            assert r.status_code == 201, r.text
            ini = r.json()
            enc = {"Authorization": f"Bearer {ini['access_token']}"}
            assert (await c.patch("/api/encuesta-publica/email", json={"email": "ana@empresa-demo.cl"},
                                  headers=enc)).status_code == 204

            r = await c.post("/api/arcop/solicitudes", headers=enc, json={
                "tipo": "supresion", "descripcion": "Solicito la supresión de mis datos personales."})
            assert r.status_code == 201, r.text
            sid = r.json()["id_solicitud"]
            for estado in ("en_revision", "en_proceso"):
                assert (await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": estado},
                                      headers=admin)).status_code == 200
            r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion", headers=admin,
                             json={"resultado": "resuelta", "respuesta": "Se anonimizaron sus datos."})
            assert r.status_code == 200, r.text
            assert "usuario_temporal=1" in r.json()["historial"][-1]["comentario"]

            gen = app.dependency_overrides[get_db]()
            s = await gen.__anext__()
            try:
                uid = (await s.get(Evaluacion, ini["evaluacion_id"])).usuario_temporal_id
                fila = (await s.execute(text(
                    "SELECT email, fecha_anonimizacion FROM usuario_temporal WHERE id = :i"), {"i": uid})).one()
            finally:
                await gen.aclose()
            assert fila.email is None and fila.fecha_anonimizacion is not None
    asyncio.run(_main())
