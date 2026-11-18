"""
T-17 — R7 de la retención: al terminar la gracia del contrato se borran los datos de la empresa.

Se borran documentos, evidencias (archivo y texto) y conversaciones del tutor; el contacto del usuario
definitivo se anonimiza; puntajes, resumen y benchmark quedan igual. Se omite a la empresa con una
solicitud ARCOP abierta y es idempotente (empresa.datos_eliminados_en).
"""
import asyncio
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

import app.domain.models  # noqa: F401
from app.application.retencion.casos_uso.aplicar_retencion import AplicarRetencionUseCase
from app.core.config import settings
from app.domain.models.base import Base
from app.domain.models.benchmark import Benchmark
from app.domain.models.bitacora_auditoria import BitacoraAuditoria
from app.domain.models.documento_empresa import TIPO_INFORME, DocumentoEmpresa
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.evidencia import EstadoValidacion, Evidencia
from app.domain.models.respuesta import Respuesta
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_arcop import SolicitudARCOP
from app.domain.models.tutor_conversaciones import ConversacionTutor, MensajeTutor
from app.domain.models.usuario_definitivo import UsuarioDefinitivo
from app.domain.models.usuario_temporal import UsuarioTemporal

HOY = date(2026, 10, 21)
VENCIDA, EN_GRACIA, VIGENTE, VENCIDA_CON_ARCOP = 1, 2, 3, 4
TERMINO = {VENCIDA: date(2026, 1, 31), VENCIDA_CON_ARCOP: date(2026, 1, 31),
           EN_GRACIA: date(2026, 10, 14), VIGENTE: date(2027, 12, 31)}


class StorageEspia:
    def __init__(self):
        self.borrados = []

    async def delete(self, ruta):
        self.borrados.append(ruta)


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
            for eid in (VENCIDA, EN_GRACIA, VIGENTE, VENCIDA_CON_ARCOP):
                await _empresa(s, eid)
        try:
            await escenario(Session)
        finally:
            await engine.dispose()
    asyncio.run(_f())


async def _empresa(s, eid):
    s.add(Empresa(id=eid, razon_social=f"Empresa {eid}", rut=f"7612345{eid}-0", rubro_id=1,
                  fecha_inicio_contrato=date(2025, 1, 1), fecha_termino_contrato=TERMINO[eid],
                  fecha_creacion=datetime(2025, 1, 1)))
    s.add(UsuarioDefinitivo(id=eid, empresa_id=eid, nombre="Ana Perez", email=f"ana{eid}@demo.cl",
                            password_hash="hash", estado="activo", fecha_creacion=datetime(2025, 1, 1)))
    s.add(UsuarioTemporal(id=eid, email=None, rubro_id=1, fecha_expiracion=date(2030, 1, 1)))
    s.add(Evaluacion(id=eid, usuario_temporal_id=eid, empresa_id=eid, fecha_inicio=date(2025, 2, 1),
                     estado_progreso="completada", filtro_completado=True, origen="invitacion", es_prueba=False))
    s.add(Respuesta(id=eid, evaluacion_id=eid, estado_clasificacion="cumplido",
                    estado_clasificacion_final="cumplido", justificacion_usuario="Texto"))
    s.add(Evidencia(id_evidencia=eid, respuesta_id=eid, nombre_archivo="acta.pdf", storage_path=f"/ev/{eid}.bin",
                    mime_type="application/pdf", hash_archivo="a" * 64, justificacion_llm="ok",
                    estado_validacion=EstadoValidacion.VALIDATED.value, clasificacion_llm="cumplido",
                    puntaje_resultante=80.0))
    s.add(Resumen(id_resumen=eid, evaluacion_id=eid, puntaje_obtenido=77.0, nivel_madurez="alto"))
    s.add(DocumentoEmpresa(id=eid, empresa_id=eid, evaluacion_id=eid, tipo=TIPO_INFORME, nombre="informe.pdf",
                           storage_path=f"/doc/{eid}.pdf", mime_type="application/pdf", tamano_bytes=10,
                           hash_contenido="b" * 64, fecha_creacion=datetime(2025, 3, 1), creado_por_usuario_id=eid))
    s.add(ConversacionTutor(id=eid, empresa_id=eid, usuario_definitivo_id=eid, evaluacion_id=eid, nivel="Inicial",
                            mensajes_total=1, fecha_creacion=datetime(2026, 10, 20),
                            fecha_ultimo_mensaje=datetime(2026, 10, 20)))
    s.add(MensajeTutor(id=eid, conversacion_id=eid, rol="usuario", tipo="pregunta", contenido="hola",
                       fecha=datetime(2026, 10, 20)))
    await s.commit()


def _uc(s, storage=None, empresa=True):
    p = {"titulares": None, "arcop": None, "eventos": None}
    if empresa is not None:
        p["empresa"] = empresa
    return AplicarRetencionUseCase(s, storage=storage, hoy=HOY, plazos=p)


async def _cuenta(s, modelo, **filtros):
    q = select(func.count()).select_from(modelo)
    for k, v in filtros.items():
        q = q.where(getattr(modelo, k) == v)
    return (await s.execute(q)).scalar_one()


async def _foto_benchmark(s):
    resumen = (await s.execute(select(Resumen.id_resumen, Resumen.puntaje_obtenido, Resumen.nivel_madurez)
                               .order_by(Resumen.id_resumen))).all()
    resp = (await s.execute(select(Respuesta.id, Respuesta.estado_clasificacion, Respuesta.estado_clasificacion_final)
                            .order_by(Respuesta.id))).all()
    bench = (await s.execute(select(Benchmark.id_benchmark, Benchmark.promedio_puntaje)
                             .order_by(Benchmark.id_benchmark))).all()
    return [tuple(x) for x in resumen], [tuple(x) for x in resp], [tuple(x) for x in bench]


async def _ejecuciones(s):
    return (await s.execute(select(BitacoraAuditoria).where(BitacoraAuditoria.accion == "retencion.ejecucion")
                            .order_by(BitacoraAuditoria.id))).scalars().all()


def test_empresa_con_gracia_vencida_pierde_sus_datos_y_queda_anonimizada():
    async def esc(Session):
        async with Session() as s:
            s.add(Benchmark(id_benchmark=1, promedio_puntaje=70.0, rubro_id=1))
            await s.commit()
            antes = await _foto_benchmark(s)
            espia = StorageEspia()
            # VENCIDA_CON_ARCOP no tiene solicitud aqui: tambien se procesa (2 empresas)
            r = await _uc(s, storage=espia).execute()
            assert r.empresas == 2 and r.empresas_fallidas == 0 and r.archivos_borrados == 4
            assert sorted(espia.borrados) == ["/doc/1.pdf", "/doc/4.pdf", "/ev/1.bin", "/ev/4.bin"]
        async with Session() as s:
            assert await _cuenta(s, DocumentoEmpresa, empresa_id=VENCIDA) == 0
            assert await _cuenta(s, ConversacionTutor, empresa_id=VENCIDA) == 0
            assert await _cuenta(s, MensajeTutor) == 2                       # las dos empresas no vencidas
            ev = await s.get(Evidencia, VENCIDA)
            assert ev.storage_path == "" and ev.nombre_archivo == "[anonimizado]" and ev.justificacion_llm is None
            assert ev.fecha_eliminacion is not None and ev.puntaje_resultante == 80.0
            u = await s.get(UsuarioDefinitivo, VENCIDA)
            assert u.nombre == "[anonimizado]" and u.email.endswith("@anonimizado.invalid")
            assert u.password_hash is None and u.estado == "bloqueado"
            assert (await s.get(Empresa, VENCIDA)).datos_eliminados_en is not None
            assert await _foto_benchmark(s) == antes                          # puntajes, resumen y benchmark intactos
            for eid in (EN_GRACIA, VIGENTE):                                  # el resto no se toca
                assert await _cuenta(s, DocumentoEmpresa, empresa_id=eid) == 1
                assert await _cuenta(s, ConversacionTutor, empresa_id=eid) == 1
                assert (await s.get(UsuarioDefinitivo, eid)).email == f"ana{eid}@demo.cl"
                assert (await s.get(Evidencia, eid)).storage_path == f"/ev/{eid}.bin"
                assert (await s.get(Empresa, eid)).datos_eliminados_en is None
            filas = (await s.execute(select(BitacoraAuditoria).where(
                BitacoraAuditoria.accion == "retencion.empresa_datos_eliminados")
                .order_by(BitacoraAuditoria.entidad_id))).scalars().all()
            assert [f.entidad_id for f in filas] == [VENCIDA, VENCIDA_CON_ARCOP]
            d = filas[0].detalle
            assert filas[0].actor_rol == "sistema"
            assert d["documentos"] == 1 and d["evidencias"] == 1
            assert d["conversaciones_tutor"] == 1 and d["usuarios_anonimizados"] == 1
            assert "ana1@demo" not in str(d) and "Perez" not in str(d)
    _con_bd(esc)


def test_empresa_vencida_con_arcop_abierta_se_omite():
    async def esc(Session):
        async with Session() as s:
            s.add(SolicitudARCOP(id=1, tipo="acceso", estado="en_revision", descripcion="x",
                                 codigo_seguimiento="ARC-T17-0001", usuario_definitivo_id=VENCIDA_CON_ARCOP,
                                 fecha_creacion=datetime(2026, 10, 1), fecha_actualizacion=datetime(2026, 10, 1)))
            await s.commit()
            r = await _uc(s).execute()
            assert r.empresas == 1 and r.empresas_omitidas_por_arcop_abierta == 1
            assert await _cuenta(s, DocumentoEmpresa, empresa_id=VENCIDA_CON_ARCOP) == 1
            assert (await s.get(Empresa, VENCIDA_CON_ARCOP)).datos_eliminados_en is None
            # Al cerrarse la solicitud, la siguiente corrida la procesa
            sol = await s.get(SolicitudARCOP, 1)
            sol.estado, sol.fecha_cierre = "resuelta", datetime(2026, 10, 20)
            await s.commit()
            assert (await _uc(s).execute()).empresas == 1
            assert await _cuenta(s, DocumentoEmpresa, empresa_id=VENCIDA_CON_ARCOP) == 0
    _con_bd(esc)


def test_es_idempotente():
    async def esc(Session):
        async with Session() as s:
            assert (await _uc(s).execute()).empresas == 2
            r2 = await _uc(s).execute()
            assert r2.empresas == 0 and r2.empresas_omitidas_por_arcop_abierta == 0
    _con_bd(esc)


def test_la_simulacion_cuenta_pero_no_borra():
    async def esc(Session):
        async with Session() as s:
            r = await _uc(s).execute(aplicar=False)
            assert r.simulacion and r.empresas == 2
            assert await _cuenta(s, DocumentoEmpresa) == 4 and await _cuenta(s, ConversacionTutor) == 4
            assert (await s.get(UsuarioDefinitivo, VENCIDA)).email == f"ana{VENCIDA}@demo.cl"
            assert (await s.get(Empresa, VENCIDA)).datos_eliminados_en is None
    _con_bd(esc)


def test_cada_corrida_registra_el_conteo_de_r7_tambien_cuando_es_cero():
    async def esc(Session):
        async with Session() as s:
            await _uc(s).execute()
            await _uc(s).execute()
            filas = await _ejecuciones(s)
            assert [f.detalle["conteos"]["empresas"] for f in filas] == [2, 0]
            assert filas[0].detalle["conteos"]["empresas_omitidas_por_arcop_abierta"] == 0
            assert "empresa" not in filas[0].detalle["plazos_dias"]
    _con_bd(esc)


def test_retencion_empresa_activa_false_desactiva_la_regla(monkeypatch):
    monkeypatch.setattr(settings, "RETENCION_EMPRESA_ACTIVA", False)

    async def esc(Session):
        async with Session() as s:
            # sin plazos propios: rige el ajuste
            r = await AplicarRetencionUseCase(s, hoy=HOY).execute()
            assert "empresa" in r.reglas_desactivadas and r.empresas == 0
            assert await _cuenta(s, DocumentoEmpresa) == 4
            assert (await _ejecuciones(s))[-1].detalle["conteos"]["empresas"] == 0
            # plazos propios con el interruptor apagado
            r = await _uc(s, empresa=False).execute()
            assert "empresa" in r.reglas_desactivadas and r.empresas == 0
    _con_bd(esc)


def test_con_ajuste_activo_y_sin_plazos_propios_corre(monkeypatch):
    monkeypatch.setattr(settings, "RETENCION_EMPRESA_ACTIVA", True)

    async def esc(Session):
        async with Session() as s:
            r = await AplicarRetencionUseCase(s, hoy=HOY).execute()
            assert r.empresas == 2 and "empresa" not in r.reglas_desactivadas
    _con_bd(esc)


def test_quien_pasa_sus_plazos_sin_empresa_no_usa_la_regla():
    async def esc(Session):
        async with Session() as s:
            r = await _uc(s, empresa=None).execute()
            assert r.empresas == 0 and "empresa" not in r.reglas_desactivadas
            assert await _cuenta(s, DocumentoEmpresa) == 4
    _con_bd(esc)
