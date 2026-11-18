"""
T-11 · Completar los plazos del registro de la propia plataforma.

  - RETENCION_SOLICITUDES_DESCARTADAS_DIAS (180): regla R5 que borra las solicitudes de contratación
    descartadas y deja un registro por solicitud en el audit log.
  - RETENCION_ARCOP_SEGUIMIENTO_DIAS (730): plazo del código de seguimiento y del historial ARCOP (R6).
  - El contacto del RoPA de la plataforma tiene un plazo POR CONDICIÓN ("mientras ejerza el cargo").
  - Los tres quedan enlazados al registro: con la configuración por defecto, sale OFICIAL.

Ejecutar desde Proyecto/backend/:
    pytest tests/integracion/test_t11_plazos_registro.py -v
"""
import asyncio
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

import app.domain.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.application.plataforma import registro_plataforma as R
from app.application.plataforma import revision_plataforma as REV
from app.application.rat import armado_informe_rat as I
from app.core.config import Settings, settings
from app.domain.models import AuditLog
from app.domain.models.base import Base
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_arcop import EventoSolicitud, SolicitudARCOP
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.domain.privacidad import catalogo_datos_personales as inv
from app.domain.rat import catalogo as cat

from integracion.test_hu41_registro_plataforma import _conf

HOY = date.today()


# ===================================================================== configuración y registro
def test_los_plazos_nuevos_tienen_su_valor_por_defecto():
    campos = Settings.model_fields
    assert campos["RETENCION_SOLICITUDES_DESCARTADAS_DIAS"].default == 180
    assert campos["RETENCION_ARCOP_SEGUIMIENTO_DIAS"].default == 730


def test_los_tres_plazos_estan_enlazados():
    ajustes = set(inv.AJUSTE_POR_CONSERVACION.values())
    assert {"RETENCION_SOLICITUDES_DESCARTADAS_DIAS", "RETENCION_ARCOP_SEGUIMIENTO_DIAS"} <= ajustes
    assert inv.AJUSTE_POR_CONSERVACION[inv.C_CONTRATACION] == "RETENCION_SOLICITUDES_DESCARTADAS_DIAS"
    assert inv.AJUSTE_POR_CONSERVACION[inv.C_ARCOP_SEGUIMIENTO] == "RETENCION_ARCOP_SEGUIMIENTO_DIAS"
    # el contacto del RoPA: plazo por condición, sin número
    assert inv.CONDICION_POR_CONSERVACION[inv.C_REGISTRO_PLATAFORMA] == "mientras ejerza el cargo"
    assert inv.C_REGISTRO_PLATAFORMA not in inv.AJUSTE_POR_CONSERVACION
    # el código de seguimiento y el actor del historial ARCOP usan el plazo nuevo
    assert inv.CATALOGO["solicitudes_arcop"]["codigo_seguimiento"].conservacion == inv.C_ARCOP_SEGUIMIENTO
    assert inv.CATALOGO["eventos_solicitud_arcop"]["actor_id"].conservacion == inv.C_ARCOP_SEGUIMIENTO


def test_con_la_configuracion_por_defecto_el_registro_sale_oficial():
    reg = R.generar(_conf())
    assert reg.oficial, R.motivos_borrador(reg)
    assert not R.informe_rat(reg, 1, datetime(2026, 11, 17, 12, 0)).borrador


def test_contratacion_y_seguimiento_toman_el_valor_vigente():
    reg = R.generar(_conf(RETENCION_SOLICITUDES_DESCARTADAS_DIAS=90, RETENCION_ARCOP_SEGUIMIENTO_DIAS=1000))
    contratacion = next(a for a in reg.actividades if a.clave == "contratacion")
    assert {p.categoria: p.dias for p in contratacion.plazos}["contacto"] == 90
    arcop = next(a for a in reg.actividades if a.clave == "arcop")
    assert {p.categoria: p.dias for p in arcop.plazos}["navegacion"] == 1000


def test_el_contacto_del_ropa_tiene_plazo_por_condicion():
    reg = R.generar(_conf())
    auditoria = next(a for a in reg.actividades if a.clave == "auditoria")
    contacto = next(p for p in auditoria.contenido["plazos"] if p["categoria"] == "contacto")
    assert contacto["plazo"] is None and contacto["condicion"] == "mientras ejerza el cargo"
    assert cat.plazo_definido(contacto)
    assert I.texto_plazo(contacto) == "Mientras ejerza el cargo"
    # sin número ni condición, sigue faltando el plazo
    assert not cat.plazo_definido({"categoria": "contacto", "plazo": None, "unidad": None})


def test_sin_el_ajuste_la_contratacion_vuelve_a_quedar_sin_plazo():
    reg = R.generar(_conf(RETENCION_SOLICITUDES_DESCARTADAS_DIAS=None))
    assert "contratacion" in reg.incompletas
    r = REV.revisar(reg, _conf(RETENCION_SOLICITUDES_DESCARTADAS_DIAS=None), None, datetime(2026, 11, 17))
    assert any(h["codigo"] == "regla_desactivada:RETENCION_SOLICITUDES_DESCARTADAS_DIAS" for h in r["hallazgos"])


# ===================================================================== retención (corrida diaria)
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


async def _solicitud(s, sid: int, estado: str, dias_desde_cambio: int):
    s.add(Evaluacion(id=sid, fecha_inicio=HOY, estado_progreso="completada", filtro_completado=True,
                     origen="publica", es_prueba=False))
    cambio = datetime.combine(HOY - timedelta(days=dias_desde_cambio), datetime.min.time())
    s.add(SolicitudContratacion(id=sid, evaluacion_id=sid, estado=estado, nombre_contacto="Contacto",
                                email_contacto=f"c{sid}@ejemplo.cl", autoriza_migracion=False,
                                fecha_creacion=cambio - timedelta(days=5), fecha_actualizacion=cambio))
    await s.commit()


def _uc(s, **plazos):
    from app.application.retencion.casos_uso.aplicar_retencion import AplicarRetencionUseCase
    base = {"titulares": None, "arcop": None, "eventos": None, "tutor": None,
            "contratacion": 180, "arcop_seguimiento": None}
    return AplicarRetencionUseCase(s, plazos={**base, **plazos}, hoy=HOY)


def test_una_solicitud_descartada_hace_mas_de_180_dias_se_borra_y_queda_en_el_audit_log():
    async def esc(Session):
        async with Session() as s:
            await _solicitud(s, 1, "descartada", 181)    # vencida: se borra
            await _solicitud(s, 2, "descartada", 30)     # descartada hace poco: se queda
            await _solicitud(s, 3, "contactada", 400)    # no descartada: se queda
            simulada = await _uc(s).execute(aplicar=False)
            assert simulada.solicitudes_contratacion == 1
            assert {x for x in (await s.execute(select(SolicitudContratacion.id))).scalars()} == {1, 2, 3}

            r = await _uc(s).execute()
            assert r.solicitudes_contratacion == 1 and r.error is None
            quedan = {x for x in (await s.execute(select(SolicitudContratacion.id))).scalars()}
            assert quedan == {2, 3}
            filas = list((await s.execute(select(AuditLog).where(
                AuditLog.accion == "retencion.contratacion_descartada_eliminada"))).scalars())
            assert len(filas) == 1 and filas[0].entidad_id == 1 and filas[0].actor_rol == "sistema"
            assert filas[0].detalle["regla"] == "R5" and filas[0].detalle["plazo_dias"] == 180
            # el registro de la ejecución cuenta lo borrado
            ejecucion = (await s.execute(select(AuditLog).where(AuditLog.accion == "retencion.ejecucion")
                                         .order_by(AuditLog.id.desc()))).scalars().first()
            assert ejecucion.detalle["conteos"]["solicitudes_contratacion"] == 1
            # la siguiente corrida no encuentra nada más
            assert (await _uc(s).execute()).solicitudes_contratacion == 0
    _con_bd(esc)


def test_el_codigo_de_seguimiento_arcop_vence_y_el_historial_pierde_al_actor():
    async def esc(Session):
        async with Session() as s:
            cierre = datetime.combine(HOY - timedelta(days=800), datetime.min.time())
            for sid, cerrada in ((1, cierre), (2, datetime.combine(HOY - timedelta(days=10), datetime.min.time()))):
                s.add(Evaluacion(id=10 + sid, fecha_inicio=HOY, estado_progreso="completada", filtro_completado=True,
                                 origen="publica", es_prueba=False))
                s.add(SolicitudARCOP(id=sid, tipo="acceso", estado="resuelta", descripcion="Quiero mis datos",
                                     evaluacion_id=10 + sid,
                                     codigo_seguimiento=f"ARC-0000-000{sid}", fecha_creacion=cerrada - timedelta(days=20),
                                     fecha_actualizacion=cerrada, fecha_cierre=cerrada))
                s.add(EventoSolicitud(solicitud_id=sid, fecha=cerrada, tipo_evento="cambio_estado",
                                      estado_anterior="recibida", estado_nuevo="resuelta", actor_rol="admin_therion",
                                      actor_id=7))
            await s.commit()
            r = await _uc(s, contratacion=None, arcop_seguimiento=730).execute()
            assert r.seguimientos_arcop == 1
            vieja, nueva = (await s.execute(select(SolicitudARCOP).order_by(SolicitudARCOP.id))).scalars().all()
            assert vieja.codigo_seguimiento.startswith("RET-") and len(vieja.codigo_seguimiento) == 20
            assert nueva.codigo_seguimiento == "ARC-0000-0002"
            actores = dict((await s.execute(select(EventoSolicitud.solicitud_id, EventoSolicitud.actor_id))).all())
            assert actores == {1: None, 2: 7}
            assert (await _uc(s, contratacion=None, arcop_seguimiento=730).execute()).seguimientos_arcop == 0
    _con_bd(esc)


def test_quien_pasa_plazos_propios_sin_las_reglas_nuevas_no_las_ejecuta():
    from app.application.retencion.casos_uso.aplicar_retencion import AplicarRetencionUseCase

    async def esc(Session):
        async with Session() as s:
            await _solicitud(s, 1, "descartada", 999)
            uc = AplicarRetencionUseCase(s, plazos={"titulares": None, "arcop": None, "eventos": None}, hoy=HOY)
            r = await uc.execute()
            assert r.solicitudes_contratacion == 0
            assert (await s.execute(select(SolicitudContratacion.id))).scalars().all() == [1]
    _con_bd(esc)

