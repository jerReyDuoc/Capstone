"""
QA - HU-36: informe del Registro de Actividades de Tratamiento (RAT) del cliente.

  C1  PDF armado en el servidor desde la versión vigente del RAT (motor de informes de HU-21): portada,
      resumen (actividades, datos sensibles, transferencias, decisiones automatizadas), detalle por
      actividad y matriz de riesgos.
  C2  Fecha, versión del RAT, código verificable y aviso legal (la plataforma apoya, no reemplaza la
      asesoría legal).
  C3  También en XLSX; ambos quedan en "Mis documentos" y cada descarga en el audit_log.
  C4  Con actividades incompletas o en revisión, sale como borrador con marca de agua y lo dice la portada.

Parte 1: lógica pura (armado, riesgos, código, PDF y XLSX). Corre sin BD (necesita reportlab y openpyxl).
Parte 2: API en proceso (SQLite), reutiliza la preparación de test_hu35_rat.py; necesita FastAPI,
SQLAlchemy y aiosqlite (Docker).
"""
import asyncio
import io
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.application.mapa_datos import plantillas as P
from app.application.rat import informe as I
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import analisis as A
from app.domain.rat import modelo as M
from app.domain.rat import riesgos as RG
from app.domain.rat import versiones as V

CODIGO_INTERNO = re.compile(r"\b(?:HU|T)-\d{2}\b|\bF[1-7]\b|\b(?:DAT|GOB|RIE|SEG)-\d{3}\b")
AHORA = datetime(2026, 11, 12, 17, 0)


def _mapa(codigo: str = "retail"):
    p = P.PLANTILLAS[codigo]
    ids, els = {}, []
    for i, e in enumerate(p.elementos, 1):
        ids[e.clave] = i
        els.append(Elemento(i, e.tipo, e.nombre, e.subtipo, e.descripcion, None, e.pais, e.responsable, list(e.datos),
                            list(e.titulares), e.nna, e.rol, None, "plantilla", e.clave, True))
    fls = [Flujo(j, ids[f.origen], ids[f.destino], f.finalidad, list(f.datos), list(f.titulares), f.nna, f.frecuencia,
                 f.medio) for j, f in enumerate(p.flujos, 1)]
    return els, fls, ids


def _sel(x):
    return {"id": x.id, "categorias_datos": list(x.categorias_datos), "categorias_titulares": list(x.categorias_titulares)}


def _remuneraciones(els, fls, ids) -> dict:
    rrhh = next(e for e in els if e.id == ids["comun_rrhh"])
    banco = next(f for f in fls if f.origen_id == rrhh.id and f.destino_id == ids["comun_banco"])
    return M.normalizar({
        "nombre": "Pago de remuneraciones", "area": "Gerencia de Personas",
        "finalidades": ["Calcular y pagar las remuneraciones del personal"], "rol": "responsable",
        "elementos": [_sel(rrhh)], "flujos": [_sel(banco)],
        "fuentes": [{"tipo": "titular", "detalle": "Formulario de ingreso"}, {"tipo": "generados"}],
        "base_licitud": "contrato", "base_sensibles": "obligacion_laboral",
        "plazos": [{"categoria": c, "plazo": 6, "unidad": "anios", "desde": "termino_relacion"}
                   for c in rrhh.categorias_datos],
        "decisiones": {"existe": False},
        "medidas": {"codigos": ["control_acceso", "cifrado_transito", "cifrado_reposo", "respaldos"]},
    })


def _vigente(id_, contenido, els, fls, estado="vigente", version=1, motivos=()):
    d = A.derivados(contenido, els, fls)
    inst = V.instantanea(contenido, d)
    return I.FuenteActividad(id_, contenido["nombre"], estado, version, AHORA, AHORA, tuple(motivos), inst,
                             V.huella(inst), AHORA - timedelta(days=1))


def _trabajo(id_, contenido, els, fls, estado="borrador"):
    d = A.derivados(contenido, els, fls)
    return I.FuenteActividad(id_, contenido["nombre"], estado, None, None, AHORA, (), None, None, None, contenido, d,
                             A.completitud(contenido, d))


def _informe(fuentes, **kw):
    return I.armar(fuentes, datetime(2026, 11, 12, 17, 4, tzinfo=timezone.utc), "Comercial Andes SpA",
                   "76123456-7", "Comercio minorista", **kw)


# ===================================================================== C2: código verificable
def test_codigo_verificable_con_digito_modulo_11():
    c = I.codigo(45, 2026)
    assert re.fullmatch(r"CIA-REG-2026-000045-[0-9K]", c)
    assert I.leer_codigo(c) == (2026, 45)
    assert I.leer_codigo(c.lower().replace("-", " - ").replace(" ", "")) == (2026, 45)
    dv = c[-1]
    otro = "1" if dv != "1" else "2"
    assert I.leer_codigo(c[:-1] + otro) is None                # dígito mal transcrito
    for malo in ("", "CIA-2026-000045-0", "CIA-REG-26-000045-0", "CIA-REG-2026-45-0", "XYZ-REG-2026-000045-0"):
        assert I.leer_codigo(malo) is None, malo


def test_aviso_legal_dice_que_apoya_y_no_reemplaza_la_asesoria():
    texto = " ".join(I.AVISO_RAT.texto).lower()
    assert "no constituye asesoría legal" in texto and "apoyo" in texto
    assert "no reemplaza la asesoría legal" in I.AVISO_RAT.pie.lower()
    assert I.AVISO_RAT.version and not CODIGO_INTERNO.search(" ".join(I.AVISO_RAT.texto) + I.AVISO_RAT.pie)


# ===================================================================== C1 y C4: armado
def test_oficial_solo_con_todas_las_actividades_vigentes():
    els, fls, ids = _mapa()
    inf = _informe([_vigente(1, _remuneraciones(els, fls, ids), els, fls)])
    assert not inf.borrador and inf.motivos_borrador == () and inf.estado_texto == "Oficial"
    a = inf.actividades[0]
    assert a.origen == "vigente" and a.version == 1 and a.huella_version and a.pendiente is None
    r = inf.resumen
    assert r["actividades"] == 1 and r["con_sensibles"] == 1 and "Salud" in r["categorias_sensibles"]
    assert r["con_decisiones"] == 0 and r["transferencias"] == 0 and r["terceros"] == 1


def test_en_revision_o_sin_version_vigente_sale_como_borrador():
    els, fls, ids = _mapa()
    rem = _remuneraciones(els, fls, ids)
    nueva = M.normalizar({"nombre": "Selección de personal", "finalidades": ["Evaluar postulantes"]})
    inf = _informe([_vigente(1, rem, els, fls, estado="en_revision", motivos=[{"texto": "cambió"}]),
                    _trabajo(2, nueva, els, fls)], archivadas=2)
    assert inf.borrador and len(inf.motivos_borrador) == 2
    assert "sin versión vigente" in inf.motivos_borrador[0] and "en revisión" in inf.motivos_borrador[1]
    revisada = next(a for a in inf.actividades if a.id == 1)
    # Criterio 1: la que está en revisión se informa con su versión VIGENTE (la instantánea)
    assert revisada.origen == "vigente" and revisada.version == 1 and "mapa de datos" in revisada.pendiente
    sin = next(a for a in inf.actividades if a.id == 2)
    assert sin.origen == "trabajo" and sin.version is None and sin.faltantes
    assert inf.resumen["archivadas_excluidas"] == 2 and inf.resumen["sin_version_vigente"] == 1


def test_la_version_vigente_manda_aunque_haya_una_nueva_en_preparacion():
    els, fls, ids = _mapa()
    rem = _remuneraciones(els, fls, ids)
    f = _vigente(1, rem, els, fls, estado="borrador", version=3)
    cambiada = M.normalizar({"finalidades": ["Otra finalidad completamente distinta"]}, rem)
    f = I.FuenteActividad(**{**f.__dict__, "contenido": cambiada})
    inf = _informe([f])
    a = inf.actividades[0]
    assert a.contenido["finalidades"] == rem["finalidades"] and a.version == 3
    assert inf.borrador and "nueva versión en preparación" in inf.motivos_borrador[0]


def test_huella_no_depende_de_la_fecha_y_cambia_con_el_contenido():
    els, fls, ids = _mapa()
    rem = _remuneraciones(els, fls, ids)
    f = [_vigente(1, rem, els, fls)]
    a = I.armar(f, datetime(2026, 1, 1, tzinfo=timezone.utc), "X")
    b = I.armar(f, datetime(2026, 6, 1, tzinfo=timezone.utc), "X")
    assert a.huella == b.huella
    otro = [_vigente(1, M.normalizar({"area": "Otra área"}, rem), els, fls)]
    assert I.armar(otro, AHORA, "X").huella != a.huella


def test_campos_legibles_cubren_los_13_campos_sin_codigos_internos():
    els, fls, ids = _mapa()
    a = _informe([_vigente(1, _remuneraciones(els, fls, ids), els, fls)]).actividades[0]
    campos = I.campos_legibles(a)
    assert len(campos) == 13 and len({c for c, _, _ in campos}) == 13
    textos = dict((c, t) for c, _, t in campos)
    assert "(sensible)" in textos["tipos_datos"] and "6 años desde que termina" in textos["conservacion"]
    assert "Ejecución de un contrato" in textos["base_licitud"]
    resumido = dict((c, t) for c, _, t in I.campos_legibles(a, plazos_aparte=True))
    assert "ver la tabla" in resumido["conservacion"]
    for _, titulo, texto in campos:
        assert not CODIGO_INTERNO.search(titulo + texto)
        assert "_" not in texto, texto      # sin códigos del catálogo


# ===================================================================== matriz de riesgos (base HU-38)
def test_matriz_de_riesgos_probabilidad_por_impacto():
    els, fls, ids = _mapa()
    rem = _remuneraciones(els, fls, ids)
    r = RG.evaluar(1, "x", rem, A.derivados(rem, els, fls))
    assert 1 <= r.probabilidad <= 5 and 1 <= r.impacto <= 5 and r.puntaje == r.probabilidad * r.impacto
    assert any(f.titulo == "Datos sensibles" for f in r.factores) and r.impacto >= 3
    # Decisiones con perfilamiento y sin revisión humana, pocas medidas y datos incompletos: sube
    peor = M.normalizar({"decisiones": {"existe": True, "perfilamiento": True, "logica": "Modelo que puntúa clientes",
                                        "intervencion_humana": False}, "medidas": {"codigos": []}}, rem)
    r2 = RG.evaluar(1, "x", peor, A.derivados(peor, els, fls), faltantes=2)
    assert r2.puntaje > r.puntaje and r2.nivel in ("Alto", "Crítico") and r2.tratamientos
    assert [RG.nivel_de(n) for n in (1, 4, 5, 9, 10, 14, 15, 25)] == ["Bajo", "Bajo", "Medio", "Medio", "Alto", "Alto",
                                                                       "Crítico", "Crítico"]
    calor = RG.mapa_calor([r, r2])
    assert sum(map(sum, calor)) == 2 and calor[5 - r2.probabilidad][r2.impacto - 1] >= 1
    assert RG.ordenar([r, r2])[0] is r2


# ===================================================================== PDF y XLSX
def _pdf_texto(datos: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(datos)).pages)


def test_pdf_oficial_con_portada_resumen_detalle_matriz_y_aviso():
    pytest.importorskip("reportlab")
    from app.application.rat.pdf_rat import generar_pdf_rat, nombre_archivo

    els, fls, ids = _mapa()
    inf = _informe([_vigente(1, _remuneraciones(els, fls, ids), els, fls)]).con_emision(I.codigo(7, 2026), 2)
    datos = generar_pdf_rat(inf)
    assert datos[:5] == b"%PDF-"
    texto = _pdf_texto(datos)
    for esperado in ("Registro de Actividades de Tratamiento", "Resumen ejecutivo", "Detalle por actividad",
                     "Matriz de riesgos", "Verificación del informe", inf.codigo, "Versión del RAT", "Emitido el",
                     "Aviso legal", "no reemplaza la asesoría legal", "Pago de remuneraciones", "Oficial"):
        assert esperado in texto, esperado
    assert "BORRADOR" not in texto
    assert nombre_archivo(inf, "pdf") == "registro_actividades_v2_2026-11-12.pdf"
    assert not CODIGO_INTERNO.search(texto)


def test_pdf_borrador_con_marca_de_agua_y_aviso_en_la_portada():
    pytest.importorskip("reportlab")
    from app.application.rat.pdf_rat import generar_pdf_rat, nombre_archivo

    els, fls, ids = _mapa()
    nueva = M.normalizar({"nombre": "Selección de personal"})
    inf = _informe([_vigente(1, _remuneraciones(els, fls, ids), els, fls), _trabajo(2, nueva, els, fls)])
    inf = inf.con_emision(I.codigo(8, 2026), 3)
    texto = _pdf_texto(generar_pdf_rat(inf))
    assert "BORRADOR: este informe no corresponde a una versión oficial" in texto
    assert texto.count("no apto para presentación oficial") >= 2        # encabezado de cada página
    assert nombre_archivo(inf, "pdf").endswith("_borrador.pdf")


def test_xlsx_con_las_mismas_hojas_y_sin_formulas():
    openpyxl = pytest.importorskip("openpyxl")
    from app.application.rat.xlsx_rat import generar_xlsx_rat

    els, fls, ids = _mapa()
    rem = M.normalizar({"descripcion": "=HYPERLINK(\"http://x\")"}, _remuneraciones(els, fls, ids))
    inf = _informe([_vigente(1, rem, els, fls), _trabajo(2, M.normalizar({"nombre": "Ventas"}), els, fls)])
    inf = inf.con_emision(I.codigo(9, 2026), 1)
    wb = openpyxl.load_workbook(io.BytesIO(generar_xlsx_rat(inf)))
    assert wb.sheetnames == ["Portada", "Resumen", "Actividades", "Datos y plazos", "Destinatarios", "Transferencias",
                             "Decisiones", "Matriz de riesgos", "Verificación"]
    portada = [c for fila in wb["Portada"].iter_rows(values_only=True) for c in fila if c]
    assert inf.codigo in portada and "Borrador" in portada and any("BORRADOR" in str(c) for c in portada)
    assert wb["Actividades"].oddHeader.center.text.startswith("BORRADOR")
    for ws in wb:
        for fila in ws.iter_rows():
            for c in fila:
                assert c.data_type != "f", f"{ws.title}!{c.coordinate} quedó como fórmula"
    filas = list(wb["Actividades"].iter_rows(values_only=True))
    cab = next(f for f in filas if f and f[0] == "N.º")
    assert "Finalidades" in cab and "Medidas de seguridad" in cab and "Riesgo" in cab


# ===================================================================== Parte 2: API en proceso
def _hay_api() -> bool:
    try:
        import aiosqlite  # noqa: F401
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ImportError:
        return False
    return True


api = pytest.mark.skipif(not _hay_api(), reason="Pruebas de API: requieren FastAPI, SQLAlchemy y aiosqlite (Docker)")


@pytest.fixture
def hu27(monkeypatch, tmp_path):
    """Misma preparación que test_hu35_rat.py (empresa con contrato, correo a archivo, limitador en memoria)."""
    if not _hay_api():
        pytest.skip("sin FastAPI/SQLAlchemy")
    import test_hu27_empresa_cliente as m
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("HU-36: solo en proceso")
    from app.core.config import settings
    from app.infrastructure.cache.limitador import LimitadorMemoria, obtener_limitador
    from app.main import app

    monkeypatch.setattr(settings, "AUTH_SECRET", m.SECRETO)
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ACTIVACION_URL_BASE", "http://localhost:3000/activar")
    limitador = LimitadorMemoria()
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield m
    app.dependency_overrides.pop(obtener_limitador, None)


@api
def test_api_informe_borrador_oficial_documentos_correo_y_audit_log(hu27):
    import test_hu35_rat as hu35

    async def esc(c):
        from app.domain.models import BitacoraAuditoria, DocumentoEmpresa, RatInforme

        x = await hu35._cliente(hu27, c)
        h = x["hc"]
        base = "/api/registro-actividades/informes"
        r = await c.get(base, headers=h)
        assert r.status_code == 200 and r.json()["previa"]["puede_emitir"] is False
        r = await c.post(base, headers=h, json={})
        assert r.status_code == 409 and hu27._codigo(r) == "RAT_VACIO"

        m = await hu35._mapa_api(c, h)
        a = (await c.post("/api/registro-actividades/actividades", headers=h,
                          json={"nombre": "Pago de remuneraciones"})).json()["actividad"]
        # Borrador: la actividad no está vigente (C4)
        r = await c.post(base, headers=h, json={})
        assert r.status_code == 201, r.text
        inf = r.json()["informe"]
        assert inf["borrador"] and inf["version_rat"] == 1 and inf["motivos_borrador"]
        assert re.fullmatch(r"CIA-REG-\d{4}-\d{6}-[0-9K]", inf["codigo"])
        assert inf["documentos"]["pdf"] and inf["documentos"]["xlsx"]
        assert inf["documentos"]["pdf"]["nombre"].endswith("_borrador.pdf")

        # Sin cambios: reutiliza la emisión (no llena Mis documentos de copias)
        r = await c.post(base, headers=h, json={})
        assert r.status_code == 200 and r.json()["reutilizado"] and r.json()["informe"]["id"] == inf["id"]

        # Oficial: completar y dejar vigente (sube la versión del RAT)
        r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                          json={"revision": a["revision"], **hu35._completa(m)})
        a = r.json()["actividad"]
        a = (await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                          json={"revision": a["revision"], "accion": "enviar_revision"})).json()["actividad"]
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": "aprobar"})
        assert r.status_code == 200, r.text
        lista = (await c.get(base, headers=h)).json()
        assert lista["previa"]["borrador"] is False and lista["al_dia"] is False
        r = await c.post(base, headers=h, json={})
        oficial = r.json()["informe"]
        assert r.status_code == 201 and not oficial["borrador"] and oficial["version_rat"] == 2

        # Descargas (C3) con su tipo y en el audit_log
        r = await c.get(f"{base}/{oficial['id']}/descarga?formato=pdf", headers=h)
        assert r.status_code == 200 and r.content[:5] == b"%PDF-"
        r = await c.get(f"{base}/{oficial['id']}/descarga?formato=xlsx", headers=h)
        assert r.status_code == 200 and r.content[:2] == b"PK"
        assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml")

        # Mis documentos (HU-29) los lista con su código
        docs = (await c.get("/api/cliente/documentos", headers=h)).json()
        rat = docs["registro_actividades"]
        assert len(rat) == 4 and {d["tipo"] for d in rat} == {"rat_pdf", "rat_xlsx"}
        assert any(d["rat"]["codigo"] == oficial["codigo"] for d in rat)

        # Verificación del código
        r = await c.get(f"{base}/verificacion", headers=h, params={"codigo": oficial["codigo"]})
        assert r.status_code == 200 and r.json()["sigue_al_dia"]
        r = await c.get(f"{base}/verificacion", headers=h, params={"codigo": oficial["codigo"][:-1] + "X"})
        assert r.status_code == 422 and hu27._codigo(r) == "CODIGO_INVALIDO"

        # Correo con los dos adjuntos
        r = await c.post(f"{base}/{oficial['id']}/enviar", headers=h, json={"formatos": ["pdf", "xlsx"]})
        assert r.status_code == 200 and r.json()["enviado"], r.text

        # Si se elimina el archivo de Mis documentos, la descarga lo explica
        pdf_id = oficial["documentos"]["pdf"]["id"]
        assert (await c.delete(f"/api/cliente/documentos/{pdf_id}", headers=h)).status_code in (200, 204)
        r = await c.get(f"{base}/{oficial['id']}/descarga?formato=pdf", headers=h)
        assert r.status_code == 410 and hu27._codigo(r) == "ARCHIVO_ELIMINADO"

        assert len(await hu35._filas(hu27, RatInforme)) == 2
        assert len(await hu35._filas(hu27, DocumentoEmpresa)) == 3
        acciones = [b.accion for b in await hu35._filas(hu27, BitacoraAuditoria)]
        for accion in ("rat.informe_generado", "rat.informe_descargado", "rat.informe_enviado",
                       "rat.informe_verificado", "documento.generado"):
            assert accion in acciones, accion
        for b in await hu35._filas(hu27, BitacoraAuditoria):
            if b.accion.startswith("rat.informe"):
                assert "remuneraciones" not in str(b.detalle).lower() and "@" not in str(b.detalle)
    hu35._correr(esc)


@api
def test_api_informe_aislado_por_empresa_y_solo_con_contrato(hu27, monkeypatch):
    import test_hu35_rat as hu35

    async def esc(c):
        x = await hu35._cliente(hu27, c)
        r = await c.get("/api/registro-actividades/informes", headers=hu27.admin())
        assert r.status_code == 403
        r = await c.get("/api/registro-actividades/informes/999/descarga", headers=x["hc"])
        assert r.status_code == 404 and hu27._codigo(r) == "INFORME_NO_ENCONTRADO"
        import app.core.servicio_pagado as sp
        monkeypatch.setattr(sp, "servicio_habilitado", lambda empresa, hoy=None: False)
        r = await c.post("/api/registro-actividades/informes", headers=x["hc"], json={})
        assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE"
    hu35._correr(esc)
