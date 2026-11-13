"""
QA - HU-37: informe RoPA desde el registro de actividades de tratamiento.

  C1  Se genera desde el RAT vigente sin ingresar los datos de nuevo; cada campo se traduce a los del RoPA
      (responsable y delegado, finalidades, categorías, destinatarios, transferencias, plazos y medidas).
  C2  Dos vistas según el rol marcado en cada actividad: como responsable y como encargado.
  C3  En español; los datos que el RoPA pide y el registro no tiene se solicitan antes de generar.
  C4  PDF y XLSX con fecha, versión y aviso legal; quedan en Mis documentos y en el audit log.

Además (decisiones del PO): los documentos no mencionan RGPD, Unión Europea ni representante en la UE.

Parte 1: lógica pura (datos, armado, PDF y XLSX). Corre sin BD (necesita reportlab y openpyxl).
Parte 2: API en proceso (SQLite), reutiliza la preparación de test_hu35_rat.py; necesita FastAPI,
SQLAlchemy y aiosqlite (Docker).
"""
import io
import re
from datetime import datetime, timezone

import pytest

from app.application.ropa import informe as R
from app.domain.mapa_datos.modelo import ErrorValidacion
from app.domain.rat import modelo as M
from app.domain.ropa import datos as D
from test_hu36_informe_rat import CODIGO_INTERNO, _informe, _mapa, _remuneraciones, _trabajo, _vigente

# Lo que el PO pidió no mencionar en ninguna parte del informe
PROHIBIDO = re.compile(r"RGPD|GDPR|Uni[oó]n Europea|\bUE\b|representante en la", re.IGNORECASE)
GENERADO = datetime(2026, 11, 13, 3, 20, tzinfo=timezone.utc)

DATOS = {
    "direccion": "Av. Apoquindo 4500, Las Condes, Santiago", "correo": "privacidad@andes.cl", "telefono": "+56 2 2345 6789",
    "tiene_dpo": True, "dpo_cargo": "Oficial de Protección de Datos", "dpo_correo": "dpo@andes.cl",
    "mandantes": {"grupo sur s.a.": {"nombre": "Grupo Sur S.A.", "direccion": "Av. Libertador 1000, Santiago",
                                     "correo": "contacto@gruposur.cl", "dpo": None}},
}


def _registro(con_encargado=True, con_borrador=True):
    els, fls, ids = _mapa()
    rem = _remuneraciones(els, fls, ids)
    fuentes = [_vigente(1, rem, els, fls)]
    if con_encargado:
        enc = M.normalizar({"nombre": "Cálculo de nómina", "rol": "encargado", "responsable_mandante": "Grupo Sur S.A.",
                            "descripcion": "Cálculo mensual de liquidaciones"}, rem)
        fuentes.append(_vigente(2, enc, els, fls))
    if con_borrador:
        fuentes.append(_trabajo(3, M.normalizar({"nombre": "Videovigilancia de bodegas"}), els, fls))
    return _informe(fuentes)


# ===================================================================== C3: datos que faltan
def test_normalizar_valida_formatos_y_borra_lo_del_delegado_sin_delegado():
    d = D.normalizar({"direccion": "  Av.  Apoquindo   4500 ", "correo": "Privacidad@Andes.CL", "tiene_dpo": True,
                      "dpo_cargo": "Oficial de datos", "dpo_correo": "dpo@andes.cl"})
    assert d["direccion"] == "Av. Apoquindo 4500" and d["correo"] == "privacidad@andes.cl"
    assert D.normalizar({"tiene_dpo": False}, d)["dpo_correo"] is None          # sin delegado no se guarda
    for malo, campo in (({"correo": "no-es-correo"}, "correo"), ({"telefono": "llamar"}, "telefono"),
                        ({"dpo_cargo": "juan@andes.cl"}, "dpo_cargo"), ({"direccion": "x"}, "direccion"),
                        ({"representante": "algo"}, "representante")):
        with pytest.raises(ErrorValidacion) as e:
            D.normalizar(malo)
        assert e.value.campo.startswith(campo)


def test_mandantes_se_actualizan_por_clave_con_el_nombre_del_registro():
    nombres = {"grupo sur s.a.": "Grupo Sur S.A."}
    d = D.normalizar({"mandantes": [{"clave": "Grupo Súr S.A.", "direccion": "Av. Libertador 1000"}]}, None, nombres)
    assert d["mandantes"]["grupo sur s.a."]["nombre"] == "Grupo Sur S.A."
    d = D.normalizar({"mandantes": [{"clave": "grupo sur s.a.", "correo": "Contacto@GrupoSur.cl"}]}, d, nombres)
    m = d["mandantes"]["grupo sur s.a."]
    assert m["direccion"] == "Av. Libertador 1000" and m["correo"] == "contacto@gruposur.cl"   # se conserva lo previo
    assert D.campos_cambiados(None, d) == ["mandantes"]


def test_faltantes_segun_las_partes_elegidas():
    mand = {"grupo sur s.a.": "Grupo Sur S.A."}
    vacio = D.faltantes(None, ("responsable", "encargado"), mand)
    assert {f["campo"] for f in vacio if f["grupo"] == "empresa"} == {"direccion", "correo", "tiene_dpo"}
    assert {f["grupo"] for f in vacio} == {"empresa", "grupo sur s.a."}
    assert D.texto_faltantes(vacio, mand) == "Completa los datos de la empresa y Grupo Sur S.A."
    sin_mand = {**DATOS, "mandantes": {}}
    assert D.faltantes(sin_mand, ("responsable",), mand) == []                   # solo responsable: no se piden
    assert [f["grupo"] for f in D.faltantes(sin_mand, ("encargado",), mand)] == ["grupo sur s.a."] * 2
    assert D.faltantes({**DATOS, "dpo_correo": None}, ("responsable",), mand)[0]["campo"] == "dpo_correo"
    assert D.faltantes(DATOS, ("responsable", "encargado"), mand) == []


# ===================================================================== C1 y C2: traducción
def test_solo_entran_las_vigentes_y_se_separan_por_rol():
    inf = R.armar(_registro(), DATOS, None, GENERADO)
    assert inf.partes == ("responsable", "encargado") and inf.excluidas == 1
    assert [a.nombre for a in inf.responsable] == ["Pago de remuneraciones"]
    (g,) = inf.encargado
    assert g.nombre == "Grupo Sur S.A." and [a.nombre for a in g.actividades] == ["Cálculo de nómina"]
    assert g.contacto["correo"] == "contacto@gruposur.cl"
    assert [a.numero for a in inf.actividades] == [1, 2]
    assert all("Videovigilancia" not in a.nombre for a in inf.actividades)


def test_cada_campo_del_registro_se_traduce_al_ropa():
    inf = R.armar(_registro(), DATOS, None, GENERADO)
    a = inf.responsable[0]
    campos = {k: lineas for k, _, lineas in R.campos_responsable(inf, a)}
    assert set(campos) == {"responsable", "finalidades", "titulares", "datos", "destinatarios", "transferencias",
                           "plazos", "medidas"}
    assert "Comercial Andes SpA (RUT 76123456-7)" in campos["responsable"][0]
    assert any("Oficial de Protección de Datos" in x for x in campos["responsable"])
    assert campos["finalidades"] == ["Calcular y pagar las remuneraciones del personal"]
    assert "Salud (sensible)" in campos["datos"] and a.sensibles
    assert any("Trabajadores" in x for x in campos["titulares"])
    assert any("Banco" in x and "Encargado del tratamiento" in x for x in campos["destinatarios"])
    assert campos["transferencias"] == ["No hay transferencias internacionales."]
    assert any("6 años" in x for x in campos["plazos"])
    assert any(x.startswith("Técnicas:") for x in campos["medidas"])
    enc = {k: lineas for k, _, lineas in R.campos_encargado(inf, inf.encargado[0], inf.encargado[0].actividades[0])}
    assert enc["mandante"][:3] == ["Grupo Sur S.A.", "Av. Libertador 1000, Santiago", "contacto@gruposur.cl"]
    assert enc["tratamientos"][0] == "Cálculo mensual de liquidaciones"
    for _, titulo in R.CAMPOS_RESPONSABLE + R.CAMPOS_ENCARGADO:
        assert not PROHIBIDO.search(titulo) and not CODIGO_INTERNO.search(titulo)


def test_se_puede_generar_solo_una_parte():
    reg = _registro()
    solo = R.armar(reg, DATOS, ["encargado"], GENERADO)
    assert solo.partes == ("encargado",) and solo.responsable == () and solo.encargado
    assert R.armar(reg, DATOS, ["responsable"], GENERADO).encargado == ()
    # Pedir una parte sin actividades no la inventa
    sin_enc = R.armar(_registro(con_encargado=False), DATOS, ["encargado"], GENERADO)
    assert sin_enc.partes == () and R.partes_disponibles(_registro(con_encargado=False)) == ("responsable",)


def test_huella_no_depende_de_la_fecha_y_cambia_con_los_datos_o_las_partes():
    reg = _registro()
    a = R.armar(reg, DATOS, None, datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = R.armar(reg, DATOS, None, datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert a.huella == b.huella
    assert R.armar(reg, {**DATOS, "correo": "otro@andes.cl"}, None, GENERADO).huella != a.huella
    assert R.armar(reg, DATOS, ["responsable"], GENERADO).huella != a.huella
    # Un mandante que no está en el informe no cambia la huella
    otro = {**DATOS, "mandantes": {**DATOS["mandantes"], "x": {"nombre": "X", "correo": "x@x.cl"}}}
    assert R.armar(reg, otro, None, GENERADO).huella == a.huella


def test_codigo_y_nombre_de_archivo():
    assert re.fullmatch(r"CIA-ROPA-2026-000031-[0-9K]", R.codigo(31, 2026))
    inf = R.armar(_registro(), DATOS, None, GENERADO).con_emision(R.codigo(31, 2026), 3)
    assert R.nombre_archivo(inf, "pdf") == "ropa_v3_2026-11-13.pdf"
    assert re.fullmatch(r"[A-Za-z0-9_.-]+", R.nombre_archivo(inf, "xlsx"))


def test_previa_publica_para_el_panel():
    p = R.previa_publica(R.armar(_registro(), DATOS, None, GENERADO))
    assert p["partes"] == ["responsable", "encargado"] and p["disponibles"] == ["responsable", "encargado"]
    assert p["responsable"][0]["finalidades"] and p["encargado"][0]["clave"] == "grupo sur s.a."
    assert p["resumen"] == {"responsable": 1, "encargado": 1, "organizaciones": 1, "transferencias": 0,
                            "transferencias_sin_garantia": 0, "excluidas": 1}


def test_aviso_legal_sin_rgpd_y_dice_que_no_reemplaza_la_asesoria():
    texto = " ".join(R.AVISO_ROPA.texto) + " " + R.AVISO_ROPA.pie
    assert "no constituye asesoría legal" in texto and "no reemplaza la asesoría legal" in R.AVISO_ROPA.pie
    assert not PROHIBIDO.search(texto) and not CODIGO_INTERNO.search(texto)


# ===================================================================== C4: PDF y XLSX
def _pdf_texto(datos: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(datos)).pages)


def test_pdf_con_fecha_version_aviso_y_las_dos_partes():
    pytest.importorskip("reportlab")
    from app.application.ropa.pdf_ropa import generar_pdf_ropa

    inf = R.armar(_registro(), DATOS, None, GENERADO).con_emision(R.codigo(31, 2026), 3)
    datos = generar_pdf_ropa(inf)
    assert datos[:5] == b"%PDF-"
    texto = _pdf_texto(datos)
    for esperado in ("Registro de actividades de tratamiento (RoPA)", inf.codigo, "Versión del informe", "N.º 3",
                     "Emitido el", "13-11-2026", "Aviso legal", "no reemplaza la asesoría legal",
                     "Como responsable del tratamiento", "Como encargado del tratamiento", "Por cuenta de Grupo Sur S.A.",
                     "Pago de remuneraciones", "Cálculo de nómina", "Plazos previstos de supresión",
                     "Transferencias internacionales", "privacidad@andes.cl", "Oficial de Protección de Datos"):
        assert esperado in texto, esperado
    assert "Videovigilancia" not in texto                 # sin versión vigente: no entra
    assert not PROHIBIDO.search(texto), PROHIBIDO.search(texto)
    assert not CODIGO_INTERNO.search(texto)


def test_pdf_de_una_sola_parte():
    pytest.importorskip("reportlab")
    from app.application.ropa.pdf_ropa import generar_pdf_ropa

    inf = R.armar(_registro(), DATOS, ["responsable"], GENERADO).con_emision(R.codigo(32, 2026), 1)
    texto = _pdf_texto(generar_pdf_ropa(inf))
    assert "Como responsable del tratamiento" in texto and "Como encargado del tratamiento" not in texto


def test_xlsx_con_las_hojas_de_cada_parte_y_sin_formulas():
    openpyxl = pytest.importorskip("openpyxl")
    from app.application.ropa.xlsx_ropa import generar_xlsx_ropa

    datos = {**DATOS, "direccion": "=HYPERLINK(\"http://x\")"}
    inf = R.armar(_registro(), datos, None, GENERADO).con_emision(R.codigo(33, 2026), 2)
    wb = openpyxl.load_workbook(io.BytesIO(generar_xlsx_ropa(inf)))
    assert wb.sheetnames == ["Portada", "Organización", "Como responsable", "Como encargado", "Transferencias",
                             "Aviso legal"]
    portada = [c for fila in wb["Portada"].iter_rows(values_only=True) for c in fila if c]
    assert inf.codigo in portada and "N.º 2" in portada and "Español" in portada
    for ws in wb:
        for fila in ws.iter_rows():
            for c in fila:
                assert c.data_type != "f", f"{ws.title}!{c.coordinate} quedó como fórmula"
                assert not (isinstance(c.value, str) and PROHIBIDO.search(c.value)), c.value
    filas = list(wb["Como responsable"].iter_rows(values_only=True))
    cab = next(f for f in filas if f and f[0] == "N.º")
    assert "Finalidades del tratamiento" in cab and "Plazos previstos de supresión" in cab
    filas = list(wb["Como encargado"].iter_rows(values_only=True))
    assert any(f and "Grupo Sur S.A." in f for f in filas)
    aviso = " ".join(str(c) for fila in wb["Aviso legal"].iter_rows(values_only=True) for c in fila if c)
    assert "no constituye asesoría legal" in aviso and R.AVISO_ROPA.version in aviso


def test_xlsx_de_una_sola_parte_no_trae_la_otra_hoja():
    openpyxl = pytest.importorskip("openpyxl")
    from app.application.ropa.xlsx_ropa import generar_xlsx_ropa

    inf = R.armar(_registro(), DATOS, ["encargado"], GENERADO).con_emision(R.codigo(34, 2026), 1)
    wb = openpyxl.load_workbook(io.BytesIO(generar_xlsx_ropa(inf)))
    assert "Como responsable" not in wb.sheetnames and "Como encargado" in wb.sheetnames


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
    """Misma preparación que test_hu36_informe_rat.py."""
    if not _hay_api():
        pytest.skip("sin FastAPI/SQLAlchemy")
    import test_hu27_empresa_cliente as m
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("HU-37: solo en proceso")
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_SECRET", m.SECRETO)
    monkeypatch.setattr(settings, "EXIGIR_TOKEN_EVALUACIONES", True)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "BFF_SHARED_SECRET", None)
    monkeypatch.setattr(settings, "CORREO_MODO", "archivo")
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ACTIVACION_URL_BASE", "http://localhost:3000/activar")
    yield m


async def _vigente_api(c, h, m, nombre, extra):
    import test_hu35_rat as hu35

    a = (await c.post("/api/registro-actividades/actividades", headers=h, json={"nombre": nombre})).json()["actividad"]
    r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                      json={"revision": a["revision"], **hu35._completa(m), **extra})
    assert r.status_code == 200, r.text
    a = r.json()["actividad"]
    a = (await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                      json={"revision": a["revision"], "accion": "enviar_revision"})).json()["actividad"]
    r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                     json={"revision": a["revision"], "accion": "aprobar"})
    assert r.status_code == 200, r.text
    return r.json()["actividad"]


@api
def test_api_datos_emision_documentos_y_audit_log(hu27):
    import test_hu35_rat as hu35

    async def esc(c):
        from app.domain.models import BitacoraAuditoria, DocumentoEmpresa, RopaDatos, RopaInforme

        x = await hu35._cliente(hu27, c)
        h = x["hc"]
        base = "/api/registro-actividades/ropa"
        r = await c.get(base, headers=h)
        assert r.status_code == 200 and r.json()["puede_emitir"] is False and r.json()["previa"]["partes"] == []
        r = await c.post(base, headers=h, json={})
        assert r.status_code == 409 and hu27._codigo(r) == "ROPA_SIN_ACTIVIDADES"

        m = await hu35._mapa_api(c, h)
        await _vigente_api(c, h, m, "Pago de remuneraciones", {})
        await _vigente_api(c, h, m, "Cálculo de nómina", {"rol": "encargado", "responsable_mandante": "Grupo Sur S.A."})
        await c.post("/api/registro-actividades/actividades", headers=h, json={"nombre": "Videovigilancia"})

        # C3: faltan los datos que el registro no tiene: no se emite
        lista = (await c.get(base, headers=h)).json()
        assert lista["previa"]["partes"] == ["responsable", "encargado"] and lista["previa"]["resumen"]["excluidas"] == 1
        assert lista["datos"]["mandantes"][0]["nombre"] == "Grupo Sur S.A." and lista["faltantes"]
        r = await c.post(base, headers=h, json={})
        assert r.status_code == 422 and hu27._codigo(r) == "ROPA_DATOS_INCOMPLETOS"

        r = await c.patch(f"{base}/datos", headers=h, json={"correo": "no-es-correo"})
        assert r.status_code == 422 and hu27._codigo(r) == "DATOS_INVALIDOS"
        r = await c.patch(f"{base}/datos", headers=h, json={"representante": "x"})
        assert r.status_code == 422
        clave = lista["datos"]["mandantes"][0]["clave"]
        r = await c.patch(f"{base}/datos", headers=h, json={
            "direccion": "Av. Apoquindo 4500, Las Condes", "correo": "privacidad@andes.cl", "tiene_dpo": True,
            "dpo_cargo": "Oficial de Protección de Datos", "dpo_correo": "dpo@andes.cl",
            "mandantes": [{"clave": clave, "direccion": "Av. Libertador 1000", "correo": "contacto@gruposur.cl"}]})
        assert r.status_code == 200 and r.json()["guardado"] and r.json()["faltantes"] == [], r.text
        # Quedan guardados (cifrados en reposo) y vuelven prellenados
        lista = (await c.get(base, headers=h)).json()
        assert lista["datos"]["correo"] == "privacidad@andes.cl" and lista["puede_emitir"]
        (fila,) = await hu35._filas(hu27, RopaDatos)
        assert "privacidad@andes.cl" in fila.contenido                      # el ORM lo descifra

        async def crudo(s):
            from sqlalchemy import text
            return (await s.execute(text("SELECT contenido FROM ropa_datos"))).scalar_one()
        assert (await hu27._bd(crudo)).startswith("enc:v1:")

        # C4: emisión con los dos formatos en Mis documentos
        r = await c.post(base, headers=h, json={})
        assert r.status_code == 201, r.text
        inf = r.json()["informe"]
        assert inf["version"] == 1 and inf["partes"] == ["responsable", "encargado"] and inf["actividades"] == 2
        assert re.fullmatch(r"CIA-ROPA-\d{4}-\d{6}-[0-9K]", inf["codigo"])
        assert inf["documentos"]["pdf"]["nombre"].startswith("ropa_v1_")
        # Sin cambios: reutiliza
        r = await c.post(base, headers=h, json={})
        assert r.status_code == 200 and r.json()["reutilizado"] and r.json()["informe"]["id"] == inf["id"]
        # Solo una parte: otra emisión con otra versión
        r = await c.post(base, headers=h, json={"partes": ["responsable"]})
        assert r.status_code == 201 and r.json()["informe"]["partes"] == ["responsable"]
        assert r.json()["informe"]["version"] == 2
        r = await c.post(base, headers=h, json={"partes": ["otra"]})
        assert r.status_code == 422

        r = await c.get(f"{base}/{inf['id']}/descarga?formato=pdf", headers=h)
        assert r.status_code == 200 and r.content[:5] == b"%PDF-"
        r = await c.get(f"{base}/{inf['id']}/descarga?formato=xlsx", headers=h)
        assert r.status_code == 200 and r.content[:2] == b"PK"

        docs = (await c.get("/api/cliente/documentos", headers=h)).json()["registro_actividades"]
        ropa = [d for d in docs if d["tipo"] in ("ropa_pdf", "ropa_xlsx")]
        assert len(ropa) == 4 and any(d["ropa"]["codigo"] == inf["codigo"] for d in ropa)

        pdf_id = inf["documentos"]["pdf"]["id"]
        assert (await c.delete(f"/api/cliente/documentos/{pdf_id}", headers=h)).status_code in (200, 204)
        r = await c.get(f"{base}/{inf['id']}/descarga?formato=pdf", headers=h)
        assert r.status_code == 410 and hu27._codigo(r) == "ARCHIVO_ELIMINADO"

        assert len(await hu35._filas(hu27, RopaInforme)) == 2
        assert len([d for d in await hu35._filas(hu27, DocumentoEmpresa) if d.tipo.startswith("ropa")]) == 3
        bitacora = await hu35._filas(hu27, BitacoraAuditoria)
        acciones = [b.accion for b in bitacora]
        for accion in ("ropa.datos_actualizados", "ropa.informe_generado", "ropa.informe_descargado"):
            assert accion in acciones, accion
        for b in bitacora:
            if b.accion.startswith("ropa."):
                assert "@" not in str(b.detalle) and "apoquindo" not in str(b.detalle).lower()
    hu35._correr(esc)


@api
def test_api_ropa_aislado_por_empresa_y_solo_con_contrato(hu27, monkeypatch):
    import test_hu35_rat as hu35

    async def esc(c):
        x = await hu35._cliente(hu27, c)
        assert (await c.get("/api/registro-actividades/ropa")).status_code == 401
        r = await c.get("/api/registro-actividades/ropa", headers=hu27.admin())
        assert r.status_code == 403
        r = await c.get("/api/registro-actividades/ropa/999/descarga", headers=x["hc"])
        assert r.status_code == 404 and hu27._codigo(r) == "INFORME_NO_ENCONTRADO"
        import app.core.servicio_pagado as sp
        monkeypatch.setattr(sp, "servicio_habilitado", lambda empresa, hoy=None: False)
        r = await c.post("/api/registro-actividades/ropa", headers=x["hc"], json={})
        assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE"
        r = await c.patch("/api/registro-actividades/ropa/datos", headers=x["hc"], json={"correo": "a@b.cl"})
        assert r.status_code == 403
    hu35._correr(esc)
