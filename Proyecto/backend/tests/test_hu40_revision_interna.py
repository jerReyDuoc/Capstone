"""
QA - HU-40: revisión interna del registro (modo de auditoría interna del usuario definitivo).

  C1  El mismo usuario entra al modo de revisión y recorre una lista de verificación por actividad y por elemento
      del mapa (campos completos, base de licitud, plazos, transferencias con garantía).
  C2  Observaciones por actividad o elemento; se cierran al corregir; con alguna abierta no se marca revisada.
  C3  Cada versión del RAT se marca revisada con fecha y nombre; la marca aparece en el informe y en el audit_log.
  C4  Diferencias entre versiones y paquete de evidencia (informe, historial, lista y observaciones) verificable
      con hash, como el ZIP del Auditor Externo.
  C5  Recordatorio de revisión periódica con plazo configurable (12 meses por defecto).

Parte 1: lógica pura (lista de verificación, reglas, periodicidad, diferencias, PDF, paquete y su script). Corre
sin BD (necesita reportlab). Parte 2: API en proceso (SQLite); necesita FastAPI, SQLAlchemy y aiosqlite (Docker).
"""
import asyncio
import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from app.application.rat import informe as I
from app.application.rat import paquete_revision as P
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import modelo as M
from app.domain.rat import revision as R
from test_hu36_informe_rat import AHORA, _informe, _mapa, _remuneraciones, _trabajo, _vigente

CODIGO_INTERNO = re.compile(r"\b(?:HU|T)-\d{2}\b|\bF[1-7]\b|\b(?:DAT|GOB|RIE|SEG)-\d{3}\b")


def _registro(con_trabajo=False):
    els, fls, ids = _mapa()
    fuentes = [_vigente(1, _remuneraciones(els, fls, ids), els, fls)]
    if con_trabajo:
        fuentes.append(_trabajo(2, M.normalizar({"nombre": "Selección de personal",
                                                 "finalidades": ["Evaluar postulantes"]}), els, fls))
    return _informe(fuentes), els, fls


def _por_clave(objs):
    return {o.clave: o for o in objs}


# ===================================================================== C1: lista de verificación
def test_lista_por_actividad_cubre_los_criterios_pedidos():
    inf, els, fls = _registro()
    o = R.objeto_actividad(inf.actividades[0])
    codigos = [i.codigo for i in o.items]
    assert codigos == ["vigencia", "campos", "base_licitud", "plazos", "transferencias", "terceros", "decisiones"]
    res = {i.codigo: i.resultado for i in o.items}
    assert res["vigencia"] == R.CUMPLE and res["campos"] == R.CUMPLE and res["base_licitud"] == R.CUMPLE
    # los plazos de la plantilla no traen fundamento: advertencia (se confirma o se acepta)
    assert res["plazos"] == R.ADVERTENCIA
    assert res["transferencias"] == R.NO_APLICA and res["decisiones"] == R.NO_APLICA
    assert all(i.pregunta and i.detalle for i in o.items)


def test_actividad_sin_version_vigente_es_un_bloqueo():
    inf, els, fls = _registro(con_trabajo=True)
    o = _por_clave(R.objetos(list(inf.actividades), els, fls))["actividad:2"]
    vig = next(i for i in o.items if i.codigo == "vigencia")
    campos = next(i for i in o.items if i.codigo == "campos")
    assert vig.resultado == R.FALLA and vig.bloqueante and campos.resultado == R.FALLA and campos.bloqueante
    with pytest.raises(R.ErrorRevision) as e:
        R.aplicar_verificacion({}, o, ["vigencia"], R.ACEPTADO, "Lo asumimos por ahora, se corrige luego", AHORA)
    assert e.value.codigo == "FALLA_BLOQUEANTE"


def test_elementos_y_flujos_del_mapa():
    inf, els, fls = _registro()
    objs = _por_clave(R.objetos(list(inf.actividades), els, fls))
    assert any(k.startswith("elemento:") for k in objs) and any(k.startswith("flujo:") for k in objs)
    # Las plantillas llegan como propuestas sin confirmar
    e = objs[f"elemento:{els[0].id}"]
    assert next(i for i in e.items if i.codigo == "confirmado").resultado == R.FALLA
    # Un elemento que ninguna actividad usa: advertencia de que podría faltar una actividad
    usados, _ = R.uso_en_registro(list(inf.actividades), fls)
    libre = next(x for x in els if x.id not in usados)
    assert next(i for i in objs[f"elemento:{libre.id}"].items if i.codigo == "en_registro").resultado == R.ADVERTENCIA


def test_transferencia_sin_garantia_y_tercero_sin_contrato():
    sis = Elemento(1, "sistema", "CRM", "saas", pais="US", responsable="Ventas", categorias_datos=["identificacion"],
                   categorias_titulares=["clientes"])
    local = Elemento(2, "sistema", "ERP", "erp", pais="CL", responsable="Finanzas", categorias_datos=["identificacion"],
                     categorias_titulares=["clientes"])
    ter = Elemento(3, "tercero", "Agencia", "marketing", pais="CL", rol_tercero="encargado", contrato_firmado=None,
                   categorias_datos=["identificacion"], categorias_titulares=["clientes"])
    f = Flujo(10, 2, 1, "Sincronizar clientes", ["identificacion"], ["clientes"], cifrado=True)
    objs = _por_clave(R.objetos_mapa([sis, local, ter], [f], {1, 2}, {10}))
    g = next(i for i in objs["flujo:10"].items if i.codigo == "garantia")
    assert g.resultado == R.FALLA and "Estados Unidos" in g.detalle or "US" in g.detalle
    c = next(i for i in objs["elemento:3"].items if i.codigo == "contrato")
    assert c.resultado == R.FALLA
    assert next(i for i in objs["elemento:1"].items if i.codigo == "contrato").resultado == R.NO_APLICA


# ===================================================================== C1/C2: reglas de la revisión
def test_verificar_aceptar_y_desactualizar():
    inf, els, fls = _registro()
    o = R.objeto_actividad(inf.actividades[0])
    with pytest.raises(R.ErrorRevision) as e:
        R.aplicar_verificacion({}, o, ["plazos"], R.ACEPTADO, "corto", AHORA)
    assert e.value.codigo == "JUSTIFICACION_REQUERIDA"
    with pytest.raises(R.ErrorRevision) as e:
        R.aplicar_verificacion({}, o, ["transferencias"], R.VERIFICADO, None, AHORA)
    assert e.value.codigo == "NO_APLICA"
    ver, cambiados = R.aplicar_verificacion({}, o, None, R.VERIFICADO, None, AHORA)
    fallas = [i.codigo for i in o.items if i.resultado == R.FALLA]
    assert fallas == ["terceros"]               # el banco de la plantilla no tiene el contrato confirmado
    assert set(cambiados) == {"vigencia", "campos", "base_licitud", "plazos"}
    assert not R.consolidar([o], ver)[0]["completo"]
    ver, _ = R.aplicar_verificacion(ver, o, fallas, R.ACEPTADO, "Contrato en revisión legal, se firma este mes", AHORA)
    c = R.consolidar([o], ver)[0]
    assert c["completo"] and c["revisados"] == c["por_revisar"] == 5
    # Si la actividad cambia (otra huella), lo revisado queda desactualizado
    otro = R.Objeto(o.clave, o.tipo, o.id, o.nombre, o.subtitulo, o.items, "x" * 64)
    c2 = R.consolidar([otro], ver)[0]
    assert not c2["completo"] and {i["revision"] for i in c2["items"]} >= {R.DESACTUALIZADO}


def test_falla_se_corrige_o_se_acepta_con_justificacion():
    sis = Elemento(1, "sistema", "CRM", "saas", pais="US", responsable="Ventas", categorias_datos=["identificacion"],
                   categorias_titulares=["clientes"])
    local = Elemento(2, "sistema", "ERP", "erp", pais="CL", responsable="Finanzas",
                     categorias_datos=["identificacion"], categorias_titulares=["clientes"])
    f = Flujo(10, 2, 1, "Sincronizar", ["identificacion"], ["clientes"], cifrado=True)
    o = _por_clave(R.objetos_mapa([sis, local], [f], {1, 2}, {10}))["flujo:10"]
    with pytest.raises(R.ErrorRevision) as e:
        R.aplicar_verificacion({}, o, ["garantia"], R.VERIFICADO, None, AHORA)
    assert e.value.codigo == "FALLA_SIN_JUSTIFICAR"
    ver, _ = R.aplicar_verificacion({}, o, ["garantia"], R.ACEPTADO,
                                    "Cláusulas tipo en firma, plazo comprometido para diciembre", AHORA)
    item = next(i for i in R.consolidar([o], ver)[0]["items"] if i["codigo"] == "garantia")
    assert item["revision"] == R.ACEPTADO and "Cláusulas" in item["nota"]
    # "verificar todo" deja fuera las fallas
    _, cambiados = R.aplicar_verificacion({}, o, None, R.VERIFICADO, None, AHORA)
    assert "garantia" not in cambiados


def test_requisitos_para_marcar():
    inf, els, fls = _registro()
    objs = [R.objeto_actividad(inf.actividades[0])]
    ver = {}
    for o in objs:
        ver, _ = R.aplicar_verificacion(ver, o, None, R.VERIFICADO, None, AHORA)
    pendiente = R.requisitos(R.consolidar(objs, ver), 0, 1)
    assert [f["codigo"] for f in pendiente["faltan"]] == ["PUNTOS_PENDIENTES"]     # la falla sin aceptar
    ver, _ = R.aplicar_verificacion(ver, objs[0], ["terceros"], R.ACEPTADO, "Contrato en firma con el banco", AHORA)
    c = R.consolidar(objs, ver)
    assert R.requisitos(c, 0, 1)["puede_marcar"]
    req = R.requisitos(c, 2, 1)
    assert not req["puede_marcar"] and req["faltan"][0]["codigo"] == "OBSERVACIONES_ABIERTAS"
    assert not R.requisitos(R.consolidar(objs, {}), 0, 1)["puede_marcar"]
    assert R.requisitos(c, 0, 1, "a" * 64, "b" * 64)["faltan"][0]["codigo"] == "REGISTRO_CAMBIO"
    assert R.requisitos([], 0, 0)["faltan"][0]["codigo"] == "SIN_ACTIVIDADES"


# ===================================================================== C5: revisión periódica
def test_sumar_meses_y_periodicidad():
    assert R.sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert R.sumar_meses(date(2026, 11, 13), 12) == date(2027, 11, 13)
    hoy = date(2027, 11, 1)
    assert R.periodicidad(hoy, date(2026, 11, 13), None, 12, 30)["estado"] == R.POR_VENCER
    assert R.periodicidad(hoy, date(2026, 6, 1), None, 12, 30)["estado"] == R.VENCIDA
    assert R.periodicidad(hoy, date(2027, 6, 1), None, 12, 30)["estado"] == R.AL_DIA
    assert R.periodicidad(hoy, None, date(2027, 6, 1), 12, 30)["estado"] == R.SIN_REVISION
    assert R.periodicidad(hoy, None, None, 12, 30)["estado"] == R.SIN_REGISTRO
    assert R.periodicidad(hoy, date(2027, 6, 1), None, 3, 30)["estado"] == R.VENCIDA      # plazo configurable


def test_recordatorio_una_vez_por_etapa_y_se_repite_si_sigue_vencida():
    hoy = date(2027, 12, 1)
    est = R.periodicidad(hoy, date(2026, 11, 13), None, 12, 30)
    etapa = R.toca_recordar(est, None, None, hoy, 30)
    assert etapa and etapa.startswith("vencida:")
    assert R.toca_recordar(est, hoy, etapa, hoy, 30) is None
    assert R.toca_recordar(est, hoy - timedelta(days=30), etapa, hoy, 30) == etapa
    assert R.toca_recordar(R.periodicidad(hoy, date(2027, 6, 1), None, 12, 30), None, None, hoy, 30) is None


# ===================================================================== C4: diferencias
def test_diferencias_entre_versiones():
    inf, els, fls = _registro()
    a = inf.actividades[0]
    campos = {c: (t, x) for c, t, x in I.campos_legibles(a)}
    antes = {1: R.EntradaComparacion(1, a.nombre, 1, "h1", campos),
             5: R.EntradaComparacion(5, "Ventas en línea", 2, "h5", {})}
    cambiado = dict(campos)
    cambiado["finalidades"] = (campos["finalidades"][0], "Pagar remuneraciones y bonos")
    despues = {1: R.EntradaComparacion(1, a.nombre, 2, "h2", cambiado),
               7: R.EntradaComparacion(7, "Videovigilancia", 1, "h7", {})}
    d = R.comparar(antes, despues)
    assert d["totales"] == {"agregadas": 1, "quitadas": 1, "cambiadas": 1, "iguales": 0} and not d["sin_cambios"]
    c = d["cambiadas"][0]
    assert c["version_antes"] == 1 and c["version_despues"] == 2
    assert [x["codigo"] for x in c["campos"]] == ["finalidades"] and c["campos"][0]["despues"].startswith("Pagar")
    assert R.comparar(antes, antes)["sin_cambios"]


# ===================================================================== C3: la marca en el informe del RAT
def test_la_marca_aparece_en_el_informe_pdf_y_excel():
    pytest.importorskip("reportlab")
    pytest.importorskip("openpyxl")
    from openpyxl import load_workbook

    from app.application.rat.pdf_rat import generar_pdf_rat
    from app.application.rat.xlsx_rat import generar_xlsx_rat

    inf, _, _ = _registro()
    marca = I.MarcaRevision(id=3, numero=2, fecha=datetime(2026, 11, 13, 15, 0), revisor="Jason Sánchez",
                            cargo="Encargado de prevención", version_rat=4, puntos=31, aceptados=1, observaciones=2)
    con = inf.con_emision("CIA-REG-2026-000010-8", 4).con_revision(marca)
    assert "Revisada el 13-11-2026 por Jason Sánchez, Encargado de prevención" == marca.texto
    pdf = generar_pdf_rat(con)
    assert pdf.startswith(b"%PDF")
    texto = _texto_pdf(pdf)
    assert "Revisada el 13-11-2026" in texto and "Jason S" in texto
    wb = load_workbook(io.BytesIO(generar_xlsx_rat(con)))
    celdas = [str(c.value) for f in wb["Portada"].iter_rows() for c in f if c.value]
    assert any("Revisada el 13-11-2026" in c for c in celdas)
    # Sin revisión: lo dice; el registro de la plataforma (sin revisión aplicable) no lo menciona
    assert "todavía no tiene una revisión interna" in _texto_pdf(generar_pdf_rat(inf.con_emision("X", 1).con_revision(None)))
    assert "revisión interna" not in _texto_pdf(generar_pdf_rat(inf.con_emision("X", 1))).lower()
    assert I.marca_dict(marca)["texto"] == marca.texto


def _texto_pdf(pdf: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        import zlib
        partes = []
        for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
            try:
                partes.append(zlib.decompress(m.group(1)).decode("latin-1"))
            except zlib.error:
                pass
        crudo = " ".join(partes)
        return " ".join(re.findall(r"\((.*?)(?<!\\)\)", crudo))
    return " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


# ===================================================================== constancia y paquete
def _datos_constancia(estado="revisada"):
    from app.application.rat.pdf_revision import DatosConstancia

    inf, els, fls = _registro()
    objs = R.objetos(list(inf.actividades), els, fls)
    ver = {}
    for o in objs:
        try:
            ver, _ = R.aplicar_verificacion(ver, o, None, R.VERIFICADO, None, AHORA)
        except R.ErrorRevision:
            pass
        fallas = [i.codigo for i in o.items if i.resultado == R.FALLA]
        if fallas:
            ver, _ = R.aplicar_verificacion(ver, o, fallas, R.ACEPTADO, "Propuesta confirmada en terreno por el área",
                                            AHORA)
    lista = R.consolidar(objs, ver)
    obs = [{"id": 1, "numero": 1, "revision_id": 1, "objeto_tipo": "actividad", "objeto_id": 1,
            "objeto_clave": "actividad:1", "objeto_nombre": "Pago de remuneraciones", "criterio": "plazos",
            "criterio_titulo": "Plazos de conservación", "prioridad": "alta",
            "texto": "Falta el fundamento del plazo de 6 años", "estado": "cerrada",
            "fecha_apertura": "2026-11-13T12:00:00", "fecha_cierre": "2026-11-13T14:00:00",
            "nota_cierre": "Se agregó el fundamento (Código del Trabajo)", "objeto_cambio": True}]
    resumen = R.resumen(lista, obs)
    return DatosConstancia(
        empresa="Comercial Andes SpA", rut="76123456-7", numero=2, estado=estado, fecha_inicio=AHORA,
        generado=AHORA, lista=lista, observaciones=obs, resumen=resumen,
        fecha_revision=AHORA if estado == "revisada" else None, revisor="Jason Sánchez" if estado == "revisada" else None,
        cargo="Encargado de prevención" if estado == "revisada" else None,
        conclusion="El registro refleja las actividades actuales." if estado == "revisada" else None,
        version_rat=4 if estado == "revisada" else None, huella=inf.huella, version_mapa=7,
        proxima_revision="13-11-2027" if estado == "revisada" else None,
        plazo_meses=12 if estado == "revisada" else None), inf


def test_constancia_pdf_revisada_y_en_curso():
    pytest.importorskip("reportlab")
    from app.application.rat.pdf_revision import generar_pdf_revision, nombre_archivo

    d, _ = _datos_constancia()
    pdf = generar_pdf_revision(d)
    assert pdf.startswith(b"%PDF") and len(pdf) > 4000
    t = _texto_pdf(pdf)
    assert "Informe de revisi" in t and "Declaraci" in t and "Jason S" in t and not CODIGO_INTERNO.search(t)
    assert nombre_archivo(d).startswith("revision_interna_2_v4_") and nombre_archivo(d).endswith(".pdf")
    d2, _ = _datos_constancia("en_curso")
    t2 = _texto_pdf(generar_pdf_revision(d2))
    assert "EN CURSO" in t2 and "Declaraci" not in t2


def _paquete():
    from app.application.rat.pdf_revision import generar_pdf_revision

    d, inf = _datos_constancia()
    a = inf.actividades[0]
    versiones = [{"actividad_id": a.id, "numero": a.version, "estado": a.estado, "huella": a.huella_version,
                  "fecha": "2026-11-12T10:00:00",
                  "contenido": {"actividad": a.contenido, "mapa": {k: v for k, v in a.mapa.items()
                                                                  if k in ("elementos", "flujos", "tipos_datos",
                                                                           "titulares", "bases_datos", "paises",
                                                                           "terceros", "transferencias")}}}]
    datos = P.DatosPaquete(
        codigo=P.codigo(12, 2026), empresa=d.empresa, generado="2026-11-13T18:00:00",
        revision={"numero": 2, "estado": "revisada", "version_rat": 4, "huella": inf.huella, "revisor": d.revisor},
        lista=d.lista, observaciones=d.observaciones, versiones=versiones,
        auditoria=[{"id": 7, "fecha": "2026-11-13T12:00:00", "actor_rol": "cliente", "accion": "rat.version_vigente",
                    "entidad": "rat_actividad", "entidad_id": 1, "resultado": "ok", "detalle": {"numero": 1},
                    "hash_anterior": "a" * 64, "hash": "b" * 64}],
        emisiones=[], diferencias=None, constancia_pdf=generar_pdf_revision(d),
        informe={"registro_actividades_v4.pdf": b"%PDF-1.4 informe"})
    return P.archivos(datos), inf


def test_paquete_determinista_y_verificable_con_hash(tmp_path):
    pytest.importorskip("reportlab")
    archivos, inf = _paquete()
    assert {"manifiesto.json", "verificar_paquete.py", "LEEME.txt", "revision/constancia_revision.pdf",
            "revision/lista_verificacion.csv", "revision/observaciones.json", "historial/registro_auditoria.jsonl",
            "historial/versiones_actividades.json", "informe/registro_actividades_v4.pdf"} <= set(archivos)
    z1, z2 = P.comprimir(archivos), P.comprimir(archivos)
    assert z1 == z2                                                    # determinista
    r = P.verificar_zip(z1)
    assert r.integro and r.manifiesto["codigo"] == P.codigo(12, 2026)
    assert r.manifiesto["huella_registro"] == inf.huella
    # alterar un archivo lo detecta
    alterado = dict(archivos)
    alterado["revision/observaciones.json"] = archivos["revision/observaciones.json"].replace(b"6 a", b"9 a")
    r2 = P.verificar_zip(P.comprimir(alterado))
    assert not r2.integro and r2.alterados == ["revision/observaciones.json"]
    assert not P.verificar_zip(b"no es un zip").integro
    # El script independiente (solo librería estándar) recalcula la huella del registro
    carpeta = tmp_path / "paquete"
    with zipfile.ZipFile(io.BytesIO(z1)) as z:
        z.extractall(carpeta)
    ok = subprocess.run([sys.executable, str(carpeta / "verificar_paquete.py"), str(carpeta)], capture_output=True,
                        text=True, encoding="utf-8")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "Huella del registro recalculada" in ok.stdout and "es íntegro" in ok.stdout
    (carpeta / "LEEME.txt").write_text("cambiado", encoding="utf-8")
    malo = subprocess.run([sys.executable, str(carpeta / "verificar_paquete.py"), str(carpeta)], capture_output=True,
                          text=True, encoding="utf-8")
    assert malo.returncode == 1 and "LEEME.txt fue modificado" in malo.stdout


def test_codigo_del_paquete_y_csv_sin_formulas():
    c = P.codigo(45, 2026)
    assert re.fullmatch(r"CIA-PAQ-2026-000045-[0-9K]", c) and P.leer_codigo(c) == (2026, 45)
    assert P.leer_codigo(c[:-1] + ("1" if c[-1] != "1" else "2")) is None
    csv_ = P._csv(["a"], [["=HYPERLINK(1)"], ["+1"], ["normal"]]).decode("utf-8")
    assert "'=HYPERLINK" in csv_ and "'+1" in csv_


def test_textos_amigables_sin_codigos_internos():
    from app.application.rat import correo_revision as CR

    for lista in (R.CRITERIOS_ACTIVIDAD, R.CRITERIOS_ELEMENTO, R.CRITERIOS_FLUJO):
        for c in lista:
            assert not CODIGO_INTERNO.search(c.titulo + c.pregunta) and "RAT" not in c.pregunta
    d, _ = _datos_constancia()
    for texto in (*CR.cuerpo_constancia(d, True, "CIA-PAQ-2026-000001-9"),
                  *CR.cuerpo_recordatorio("Comercial Andes SpA", {"estado": "vencida", "vence": "2027-11-13", "dias": -3},
                                          12, "13-11-2026", "http://localhost:3000/x")):
        assert not CODIGO_INTERNO.search(texto)
    assert "vence" in CR.asunto_recordatorio("por_vencer", "Acme")


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
def hu35(monkeypatch, tmp_path):
    """El mismo entorno de las pruebas de API del registro (test_hu35_rat.py: fixture hu27)."""
    if not _hay_api():
        pytest.skip("sin FastAPI/SQLAlchemy")
    import test_hu27_empresa_cliente as m
    import test_hu35_rat as m35
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("HU-40: solo en proceso")
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
    yield m35, m
    app.dependency_overrides.pop(obtener_limitador, None)


async def _registro_vigente(m35, hu27, c):
    x = await m35._cliente(hu27, c)
    h = x["hc"]
    m = await m35._mapa_api(c, h)
    r = await c.post("/api/registro-actividades/actividades", headers=h, json={"nombre": "Pago de remuneraciones"})
    a = r.json()["actividad"]
    r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                      json={"revision": a["revision"], **m35._completa(m)})
    a = r.json()["actividad"]
    for accion in ("enviar_revision", "aprobar"):
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": accion})
        assert r.status_code == 200, r.text
        a = r.json()["actividad"]
    return x, h, m, a


async def _verificar_todo(c, h, estado):
    for o in estado["objetos"]:
        fallas = [i["codigo"] for i in o["items"] if i["resultado"] == "falla"]
        if any(i["resultado"] not in ("falla", "no_aplica") for i in o["items"]):
            r = await c.post("/api/registro-actividades/revision/verificaciones", headers=h,
                             json={"clave": o["clave"], "decision": "verificado"})
            assert r.status_code == 200, r.text
        if fallas:
            r = await c.post("/api/registro-actividades/revision/verificaciones", headers=h,
                             json={"clave": o["clave"], "criterios": fallas, "decision": "aceptado",
                                   "nota": "Revisado con el área responsable, se mantiene"})
            assert r.status_code == 200, r.text


@api
def test_api_ciclo_completo_de_la_revision_interna(hu35):
    m35, hu27 = hu35

    async def esc(c):
        from app.domain.models import BitacoraAuditoria, RatInforme, RatRevision

        x, h, m, a = await _registro_vigente(m35, hu27, c)
        # C1: el mismo usuario, sin cuentas nuevas; otros roles no
        assert (await c.get("/api/registro-actividades/revision")).status_code == 401
        assert (await c.get("/api/registro-actividades/revision", headers=hu27.admin())).status_code == 403
        r = await c.post("/api/registro-actividades/revision", headers=h)
        assert r.status_code == 201, r.text
        e = r.json()
        assert e["revision"]["estado"] == "en_curso" and e["objetos"] and not e["requisitos"]["puede_marcar"]
        assert {o["tipo"] for o in e["objetos"]} == {"actividad", "elemento", "flujo"}

        # C2: observación abierta bloquea la marca
        r = await c.post("/api/registro-actividades/revision/observaciones", headers=h, json={
            "clave": f"actividad:{a['id']}", "criterio": "plazos", "prioridad": "alta",
            "texto": "Confirmar el fundamento del plazo de conservación"})
        assert r.status_code == 201, r.text
        obs = r.json()["observacion"]
        r = await c.post("/api/registro-actividades/revision/observaciones", headers=h, json={
            "clave": f"actividad:{a['id']}", "prioridad": "media", "texto": "Escribir a ana@acme.cl"})
        assert r.status_code == 422 and hu27._codigo(r) == "DATOS_DE_CONTACTO"
        e = (await c.get("/api/registro-actividades/revision", headers=h)).json()
        await _verificar_todo(c, h, e)
        e = (await c.get("/api/registro-actividades/revision", headers=h)).json()
        assert [f["codigo"] for f in e["requisitos"]["faltan"]] == ["OBSERVACIONES_ABIERTAS"]
        r = await c.post("/api/registro-actividades/revision/marcar", headers=h, json={
            "revisor_nombre": "Jason Sánchez", "huella": e["registro"]["huella"], "confirmo": True})
        assert r.status_code == 409 and hu27._codigo(r) == "REVISION_INCOMPLETA"
        r = await c.post(f"/api/registro-actividades/revision/observaciones/{obs['id']}/cerrar", headers=h,
                         json={"nota": "Se confirmó el plazo con el área de personas"})
        assert r.status_code == 200 and r.json()["observacion"]["estado"] == "cerrada"

        # C3: marcar con fecha y nombre; queda en el informe y en el audit_log
        r = await c.post("/api/registro-actividades/revision/marcar", headers=h, json={
            "revisor_nombre": "Jason Sánchez", "revisor_cargo": "Encargado de prevención",
            "huella": e["registro"]["huella"], "confirmo": True})
        assert r.status_code == 200, r.text
        rev = r.json()["revision"]
        assert rev["estado"] == "revisada" and rev["version_rat"] >= 1 and rev["revisor"] == "Jason Sánchez"
        assert r.json()["informe"]["revision"]["texto"].startswith("Revisada el")
        lista = (await c.get("/api/registro-actividades/informes", headers=h)).json()
        assert lista["previa"]["revision"]["id"] == rev["id"] and lista["al_dia"]
        acciones = [f.accion for f in await m35._filas(hu27, BitacoraAuditoria)]
        assert "revision_rat.version_revisada" in acciones and "revision_rat.observacion_cerrada" in acciones
        filas = await m35._filas(hu27, RatInforme)
        assert filas[-1].revision_id == rev["id"]
        assert (await m35._filas(hu27, RatRevision))[0].informe_id == filas[-1].id

        # C4: constancia, paquete verificable y diferencias
        r = await c.get(f"/api/registro-actividades/revision/revisiones/{rev['id']}/constancia", headers=h)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        r = await c.get(f"/api/registro-actividades/revision/revisiones/{rev['id']}/paquete", headers=h)
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/zip")
        zip_ = r.content
        assert P.verificar_zip(zip_).integro
        r = await c.post("/api/registro-actividades/revision/paquetes/verificacion", headers=h,
                         files={"file": ("p.zip", zip_, "application/zip")})
        assert r.status_code == 200 and r.json()["valido"], r.text
        r = await c.get("/api/registro-actividades/revision/diferencias", headers=h)
        assert r.status_code == 200 and r.json()["sin_cambios"]

        # C5: plazo configurable
        r = await c.patch("/api/registro-actividades/revision/configuracion", headers=h,
                          json={"plazo_meses": 6, "aviso_dias": 15, "recordatorio_correo": True})
        assert r.status_code == 200 and r.json()["periodicidad"]["plazo_meses"] == 6
        assert r.json()["periodicidad"]["estado"] == "al_dia"
        # sin textos libres en el audit_log
        for f in await m35._filas(hu27, BitacoraAuditoria):
            if f.accion.startswith("revision_rat."):
                assert "Jason" not in json.dumps(f.detalle or {}) and "fundamento" not in json.dumps(f.detalle or {})

    m35._correr(esc)


@api
def test_api_recordatorio_periodico(hu35, monkeypatch):
    m35, hu27 = hu35

    async def esc(c):
        from app.application.use_cases.revision_interna import enviar_recordatorios

        await _registro_vigente(m35, hu27, c)
        futuro = datetime.now(timezone.utc) + timedelta(days=400)
        monkeypatch.setattr("app.domain.models.empresa.Empresa.contrato_vigente", lambda self, hoy=None: True)
        r1 = await hu27._bd(lambda s: enviar_recordatorios(s, futuro))
        r2 = await hu27._bd(lambda s: enviar_recordatorios(s, futuro))
        assert r1["enviados"] == 1 and r2["enviados"] == 0          # una vez por etapa

    m35._correr(esc)
