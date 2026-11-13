"""
QA - HU-41: registro de tratamiento de la propia plataforma (mapa, RAT y RoPA de ComplianceAI).

  C1  Las actividades (encuesta pública, contratación, cuentas, tutor, evidencias, borradores, ARCOP y auditoría)
      se generan desde catalogo_datos_personales.py con finalidad, base de licitud y plazo.
  C2  Los plazos del RAT coinciden con los ajustes de retención configurados; esta prueba falla si difieren o si
      aparece una tabla nueva sin actividad (como test_t06_minimizacion.py).
  C3  Los proveedores (LLM, Azure, correo) figuran como encargados con su país y la garantía de la transferencia.
  C4  El admin descarga el RAT y el RoPA de la plataforma con el mismo formato que los clientes.

Parte 1: lógica pura (inventario, generador, revisión, PDF y XLSX). Corre sin BD (necesita reportlab y openpyxl).
Parte 2: API en proceso (SQLite); necesita FastAPI, SQLAlchemy, httpx y aiosqlite (Docker).
"""
import asyncio
import io
import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.plataforma import registro as R
from app.application.plataforma import revision as REV
from app.core import catalogo_datos_personales as inv
from app.domain import catalogo_tratamiento as cat_mapa
from app.domain.rat import catalogo as cat_rat

RAIZ = Path(__file__).resolve().parents[1]
CODIGO_INTERNO = re.compile(r"\b(?:HU|T)-\d{2}\b")
GENERADO = datetime(2026, 11, 13, 4, 0, tzinfo=timezone.utc)
NOMBRES_AJUSTE = re.compile(r"\b(RETENCION_[A-Z_]+|TUTOR_RETENCION_DIAS|CONTRATO_GRACIA_DIAS)\b")


def _conf(**kw):
    base = dict(
        RETENCION_DATOS_TITULAR_DIAS=365, RETENCION_ARCOP_CERRADAS_DIAS=730, RETENCION_EVENTOS_SEGURIDAD_DIAS=180,
        TUTOR_RETENCION_DIAS=30, CONTRATO_GRACIA_DIAS=30, LLM_PROVIDER="groq", CORREO_MODO="smtp",
        TURNSTILE_SECRET_KEY="clave-turnstile", PLATAFORMA_PAIS_ALOJAMIENTO="US", CORREO_PROVEEDOR_NOMBRE="Correo SA",
        CORREO_PROVEEDOR_PAIS="US", CORREO_PROVEEDOR_GARANTIA="clausulas_contractuales",
        PROVEEDORES_CONTRATO_CONFIRMADO="", THERION_RAZON_SOCIAL="Therion Labs SpA", THERION_RUT=None,
        GUARDAR_MAPA_ENTIDADES_CIFRADO=False, SANITIZER_ENABLED=True, PLATAFORMA_INFORMES_DIA=20)
    base.update(kw)
    return SimpleNamespace(**base)


def _campos_settings() -> set[str]:
    """Los ajustes declarados en Settings (se lee el archivo: no necesita pydantic-settings)."""
    texto = (RAIZ / "app" / "core" / "config.py").read_text(encoding="utf-8")
    return set(re.findall(r"^    ([A-Z][A-Z0-9_]+): ", texto, re.MULTILINE))


DATOS_ROPA = {"direccion": "Av. Providencia 1234, Santiago", "correo": "privacidad@therionlabs.cl",
              "telefono": "+56 2 2345 6789", "tiene_dpo": True, "dpo_cargo": "Oficial de Protección de Datos",
              "dpo_correo": "dpo@therionlabs.cl"}


# ===================================================================== C1: actividades desde el inventario
def test_las_actividades_exigidas_existen_con_finalidad_base_y_plazo():
    claves = {a.clave for a in inv.ACTIVIDADES_PLATAFORMA}
    assert set(inv.ACTIVIDADES_OBLIGATORIAS) <= claves
    reg = R.generar(_conf())
    for a in reg.actividades:
        d = a.definicion
        assert d.finalidades and all(len(f) >= 5 for f in d.finalidades), d.clave
        assert d.base_licitud in cat_rat.BASES_POR_CODIGO, d.clave
        assert d.fuentes and all(t in cat_rat.FUENTES_POR_CODIGO for t, _ in d.fuentes)
        assert d.titulares and all(t in cat_mapa.TITULARES_POR_CODIGO for t in d.titulares)
        assert d.medidas and all(m in cat_rat.MEDIDAS_POR_CODIGO for m in d.medidas)
        assert a.contenido["plazos"], f"{d.clave} sin plazos"
        # una actividad trae plazo para cada categoría de datos que guarda
        assert {p["categoria"] for p in a.contenido["plazos"]} == {t["codigo"] for t in a.derivados["tipos_datos"]}


def test_la_base_de_cada_actividad_es_una_de_las_bases_de_sus_columnas():
    for a in inv.ACTIVIDADES_PLATAFORMA:
        bases = {inv.BASE_RAT[d.base] for _, _, d in inv.columnas_de_actividad(a)}
        assert a.base_licitud in bases, f"{a.clave}: {a.base_licitud} no está en {bases}"


def test_toda_base_y_categoria_del_inventario_tiene_su_equivalente_en_el_rat():
    for tabla, columna, d in inv.columnas_personales():
        if d.tratamiento == inv.NO_SE_GUARDA:
            continue
        assert inv.BASE_RAT.get(d.base) in cat_rat.BASES_POR_CODIGO, f"{tabla}.{columna}: base sin equivalente"
        assert inv.categoria_rat(tabla, columna, d) in cat_mapa.DATOS_POR_CODIGO


# ===================================================================== C2: cobertura (tabla nueva = falla)
def test_cada_tabla_del_inventario_esta_en_una_actividad_o_declarada_sin_tratamiento():
    p = inv.problemas_de_cobertura()
    assert not p["sin_actividad"], f"Asigna estas tablas a una actividad (o a TABLAS_SIN_TRATAMIENTO): {p['sin_actividad']}"
    assert not p["personales_sin_tratamiento"], f"Tablas con datos personales sin tratamiento: {p['personales_sin_tratamiento']}"
    assert not p["en_varias"], f"Tablas en más de una actividad: {p['en_varias']}"
    assert not p["inexistentes"], f"Tablas que ya no existen: {p['inexistentes']}"


def test_cada_tabla_del_modelo_esta_en_el_registro():
    pytest.importorskip("sqlalchemy")
    import app.domain.models  # noqa: F401
    from app.core.database import Base
    p = inv.problemas_de_cobertura({t.name for t in Base.metadata.sorted_tables})
    assert not any(p.values()), p


def test_una_tabla_nueva_sin_actividad_hace_fallar_la_cobertura(monkeypatch):
    monkeypatch.setitem(inv.CATALOGO, "tabla_nueva", {"id": inv._N, "email": inv.Dato(
        inv.CONTACTO, finalidad="x", base=inv.B_CONTRATO, conservacion=inv.C_ADMIN)})
    p = inv.problemas_de_cobertura()
    assert p["sin_actividad"] == ["tabla_nueva"]
    assert "tabla_nueva" in REV.tablas_sin_actividad()
    monkeypatch.setattr(inv, "TABLAS_SIN_TRATAMIENTO", inv.TABLAS_SIN_TRATAMIENTO | {"tabla_nueva"})
    assert inv.problemas_de_cobertura()["personales_sin_tratamiento"] == ["tabla_nueva"]


# ===================================================================== C2: plazos = ajustes configurados
def test_toda_conservacion_que_nombra_un_ajuste_esta_enlazada_y_el_ajuste_existe():
    campos = _campos_settings()
    for tabla, cols in inv.CATALOGO.items():
        for columna, d in cols.items():
            nombrados = set(NOMBRES_AJUSTE.findall(d.conservacion or ""))
            if not nombrados:
                continue
            assert d.conservacion in inv.AJUSTE_POR_CONSERVACION, f"{tabla}.{columna}: enlaza su conservación a un ajuste"
            assert inv.AJUSTE_POR_CONSERVACION[d.conservacion] in nombrados
    for clave in inv.AJUSTE_POR_CONSERVACION.values():
        assert clave in campos, f"{clave} no existe en Settings"
        assert clave in inv.INICIO_POR_AJUSTE and clave in inv.NOMBRE_AJUSTE
        assert inv.INICIO_POR_AJUSTE[clave] in cat_rat.INICIOS_POR_CODIGO


@pytest.mark.parametrize("valores", [
    dict(RETENCION_DATOS_TITULAR_DIAS=365, RETENCION_ARCOP_CERRADAS_DIAS=730, RETENCION_EVENTOS_SEGURIDAD_DIAS=180,
         TUTOR_RETENCION_DIAS=30, CONTRATO_GRACIA_DIAS=30),
    dict(RETENCION_DATOS_TITULAR_DIAS=45, RETENCION_ARCOP_CERRADAS_DIAS=400, RETENCION_EVENTOS_SEGURIDAD_DIAS=90,
         TUTOR_RETENCION_DIAS=12, CONTRATO_GRACIA_DIAS=60),
])
def test_los_plazos_del_rat_son_los_ajustes_configurados(valores):
    reg = R.generar(_conf(**valores))
    revisadas = 0
    for a in reg.actividades:
        plazos = {p["categoria"]: p for p in a.contenido["plazos"]}
        for tabla, columna, d in inv.columnas_de_actividad(a.definicion):
            clave = inv.AJUSTE_POR_CONSERVACION.get(d.conservacion)
            if clave is None:
                continue
            categoria = inv.categoria_rat(tabla, columna, d)
            p = plazos[categoria]
            # el plazo de la categoría nombra el ajuste y es el mayor de los que rigen en ella
            rige = max(valores[k] for k in next(x for x in a.plazos if x.categoria == categoria).ajustes)
            assert p["plazo"] == rige and p["unidad"] == "dias", f"{a.clave}/{categoria}"
            assert p["plazo"] >= valores[clave]
            assert inv.NOMBRE_AJUSTE[clave] in p["fundamento"]
            revisadas += 1
    assert revisadas > 20


def test_el_plazo_de_titulares_fijado_en_el_panel_manda_sobre_el_entorno():
    reg = R.generar(_conf(RETENCION_DATOS_TITULAR_DIAS=365), (120, R.FUENTE_PANEL))
    enc = next(a for a in reg.actividades if a.clave == "encuesta_publica")
    assert {p["plazo"] for p in enc.contenido["plazos"]} == {120}
    assert "fijado en Retención de datos" in enc.contenido["plazos"][0]["fundamento"]
    assert reg.ajustes["RETENCION_DATOS_TITULAR_DIAS"].fuente == R.FUENTE_PANEL


def test_un_cambio_de_plazo_cambia_la_huella_del_registro():
    a, b = R.generar(_conf()), R.generar(_conf(RETENCION_ARCOP_CERRADAS_DIAS=731))
    assert a.huella != b.huella and R.generar(_conf()).huella == a.huella


def test_un_ajuste_vacio_deja_el_plazo_sin_numero_y_genera_un_hallazgo():
    reg = R.generar(_conf(RETENCION_ARCOP_CERRADAS_DIAS=None))
    arcop = next(a for a in reg.actividades if a.clave == "arcop")
    com = next(p for p in arcop.contenido["plazos"] if p["categoria"] == "comunicaciones")
    assert com["plazo"] is None and "regla desactivada" in com["fundamento"]
    assert not arcop.completa and "arcop" in reg.incompletas
    r = REV.revisar(reg, _conf(), None, GENERADO.replace(tzinfo=None))
    h = next(x for x in r["hallazgos"] if x["codigo"] == "regla_desactivada:RETENCION_ARCOP_CERRADAS_DIAS")
    assert h["nivel"] == "alto" and "Derechos ARCOP" in h["actividades"]


# ===================================================================== C3: proveedores como encargados
def test_los_proveedores_son_encargados_con_pais_y_garantia_de_la_transferencia():
    reg = R.generar(_conf())
    terceros = [e for e in reg.elementos if e.es_tercero]
    assert {e.clave for e in terceros} == {"azure", "llm", "correo", "verificacion"}
    for e in terceros:
        assert e.rol_tercero == "encargado" and e.pais == "US"
    transfer = {t["nombre"].split(" → ")[1]: t for a in reg.actividades for t in a.derivados["transferencias"]}
    for nombre in ("Microsoft Azure", "Groq", "Correo SA", "Cloudflare Turnstile", "Base de datos de la plataforma"):
        assert transfer[nombre]["garantia_valida"], nombre
        assert transfer[nombre]["garantia_nombre"] == "Cláusulas contractuales tipo"


def test_solo_figuran_los_proveedores_que_usa_la_configuracion():
    reg = R.generar(_conf(LLM_PROVIDER="ollama", CORREO_MODO="archivo", TURNSTILE_SECRET_KEY=None))
    assert {p.clave for p in reg.proveedores} == {"azure"}
    assert all("Groq" not in t["nombre"] for a in reg.actividades for t in a.derivados["transferencias"])


def test_los_valores_posibles_de_la_configuracion_tienen_su_proveedor():
    texto = (RAIZ / "app" / "core" / "config.py").read_text(encoding="utf-8")
    llm = set(re.findall(r'"(\w+)"', re.search(r"LLM_PROVIDER: Literal\[([^\]]+)\]", texto).group(1)))
    correo = set(re.findall(r'"(\w+)"', re.search(r"CORREO_MODO: Literal\[([^\]]+)\]", texto).group(1)))
    assert llm == {"groq", "ollama"}, "Proveedor de IA nuevo: agrégalo a PROVEEDORES_PLATAFORMA y a proveedores_activos"
    assert correo == {"smtp", "archivo", "desactivado"}


def test_proveedor_de_correo_sin_pais_ni_garantia_es_un_hallazgo_alto():
    conf = _conf(CORREO_PROVEEDOR_PAIS=None, CORREO_PROVEEDOR_GARANTIA=None)
    r = REV.revisar(R.generar(conf), conf, None, GENERADO.replace(tzinfo=None))
    h = next(x for x in r["hallazgos"] if x["codigo"] == "proveedor:correo")
    assert h["nivel"] == "alto" and "país" in h["titulo"] and "garantía" in h["titulo"]
    assert next(x for x in r["revisiones"] if x["codigo"] == "proveedores")["estado"] == "error"


def test_contratos_por_confirmar_salvo_los_confirmados():
    conf = _conf(PROVEEDORES_CONTRATO_CONFIRMADO="azure, llm,correo,verificacion")
    reg = R.generar(conf)
    assert all(e.contrato_firmado is True for e in reg.elementos if e.es_tercero)
    r = REV.revisar(reg, conf, None, GENERADO.replace(tzinfo=None))
    assert not any(h["codigo"] == "contratos" for h in r["hallazgos"])


# ===================================================================== revisión interna
def test_revision_interna_retencion_atrasada_y_capa_de_ia():
    conf = _conf(GUARDAR_MAPA_ENTIDADES_CIFRADO=True, SANITIZER_ENABLED=False)
    reg = R.generar(conf)
    ahora = GENERADO.replace(tzinfo=None)
    vieja = {"fecha": ahora - timedelta(hours=72), "resultado": "ok", "detalle": {}}
    r = REV.revisar(reg, conf, vieja, ahora)
    codigos = {h["codigo"]: h["nivel"] for h in r["hallazgos"]}
    assert codigos["retencion_atrasada"] == "alto"
    assert codigos["mapa_reversible"] == "critico" and codigos["sanitizador"] == "critico"
    assert r["hallazgos"][0]["nivel"] == "critico"          # ordenados por nivel
    ok = REV.revisar(reg, _conf(), {"fecha": ahora - timedelta(hours=2), "resultado": "ok", "detalle": {}}, ahora)
    assert next(x for x in ok["revisiones"] if x["codigo"] == "ultima_retencion")["estado"] == "ok"
    assert next(x for x in ok["revisiones"] if x["codigo"] == "cobertura")["estado"] == "ok"


def test_los_plazos_pendientes_del_po_quedan_a_la_vista():
    r = REV.revisar(R.generar(_conf()), _conf(), None, GENERADO.replace(tzinfo=None))
    titulos = " ".join(h["titulo"] for h in r["hallazgos"])
    assert "registro de auditoría" in titulos and "Sesiones" in titulos and "contratación" in titulos


# ===================================================================== C4: informes con el formato del cliente
def test_informe_oficial_solo_si_todas_las_actividades_estan_completas():
    reg = R.generar(_conf())
    inf = R.informe_rat(reg, 1, GENERADO)
    assert inf.borrador == (not reg.oficial)
    assert len(inf.motivos_borrador) == len(reg.incompletas)
    assert inf.nota_borrador == R.NOTA_BORRADOR and inf.huella == reg.huella
    completo = replace(reg, incompletas=())
    for a in reg.actividades:      # sin motivos (todo completo) el informe es oficial
        object.__setattr__(a, "completitud", {**a.completitud, "faltantes": []})
    assert not R.informe_rat(completo, 1, GENERADO).borrador


def test_rat_y_ropa_con_los_mismos_generadores_del_cliente():
    pytest.importorskip("reportlab")
    openpyxl = pytest.importorskip("openpyxl")
    from app.application.rat.pdf_rat import generar_pdf_rat
    from app.application.rat.xlsx_rat import generar_xlsx_rat
    from app.application.ropa.pdf_ropa import generar_pdf_ropa
    from app.application.ropa.xlsx_ropa import generar_xlsx_ropa
    from test_hu36_informe_rat import _informe, _mapa, _remuneraciones, _vigente

    reg = R.generar(_conf())
    inf = R.informe_rat(reg, 2, GENERADO).con_emision(R.codigo(R.PREFIJO_RAT, 7, 2026), 2)
    pdf, xlsx = generar_pdf_rat(inf), generar_xlsx_rat(inf)
    assert pdf.startswith(b"%PDF") and xlsx.startswith(b"PK")
    els, fls, ids = _mapa()
    cliente = _informe([_vigente(1, _remuneraciones(els, fls, ids), els, fls)]).con_emision("CIA-REG-2026-000001-1", 1)
    hojas = openpyxl.load_workbook(io.BytesIO(xlsx)).sheetnames
    assert hojas == openpyxl.load_workbook(io.BytesIO(generar_xlsx_rat(cliente))).sheetnames

    ropa = R.informe_ropa(reg, DATOS_ROPA, 2, GENERADO).con_emision(R.codigo(R.PREFIJO_ROPA, 8, 2026), 1)
    assert len(ropa.responsable) == len(inv.ACTIVIDADES_PLATAFORMA) and ropa.partes == ("responsable",)
    assert generar_pdf_ropa(ropa).startswith(b"%PDF") and generar_xlsx_ropa(ropa).startswith(b"PK")
    texto = "\n".join(p.extract_text() for p in __import__("pypdf").PdfReader(io.BytesIO(pdf)).pages) \
        if __import__("importlib").util.find_spec("pypdf") else ""
    if texto:
        assert "Therion Labs SpA" in texto and "Groq" in texto and "Cláusulas contractuales tipo" in texto


def test_codigo_verificable_propio_de_la_plataforma():
    c = R.codigo(R.PREFIJO_RAT, 45, 2026)
    assert c.startswith("CIA-PLAT-REG-2026-000045-") and R.leer_codigo(c.lower()) == ("rat", 2026, 45)
    assert R.leer_codigo(R.codigo(R.PREFIJO_ROPA, 3, 2026)) == ("ropa", 2026, 3)
    assert R.leer_codigo(c[:-1] + ("0" if c[-1] != "0" else "1")) is None
    assert R.leer_codigo("CIA-REG-2026-000045-K") is None           # el del cliente no es de la plataforma


def test_la_huella_del_ropa_cambia_con_los_datos_de_contacto():
    reg = R.generar(_conf())
    assert R.huella_ropa(reg, DATOS_ROPA) != R.huella_ropa(reg, {**DATOS_ROPA, "telefono": "+56 2 1111 2222"})
    assert R.huella_ropa(reg, DATOS_ROPA) == R.huella_ropa(reg, dict(DATOS_ROPA))


def test_vistas_para_el_panel_en_lenguaje_simple():
    reg = R.generar(_conf())
    provs = {p.clave: p for p in reg.proveedores}
    datos = {"actividades": [R.vista_actividad(a, provs) for a in reg.actividades], "mapa": R.vista_mapa(reg),
             "revision": REV.revisar(reg, _conf(), None, GENERADO.replace(tzinfo=None))}
    texto = json.dumps(datos, ensure_ascii=False, default=str)
    for v in datos["actividades"]:
        for t in (v["nombre"], v["descripcion"], *v["finalidades"], *v["faltantes"], *(p["fundamento"] for p in v["plazos"])):
            assert not CODIGO_INTERNO.search(t), t
    for h in datos["revision"]["hallazgos"]:
        assert not CODIGO_INTERNO.search(h["titulo"] + h["detalle"] + h["recomendacion"])
    assert "@" not in texto


# ===================================================================== Parte 2: API
def _api():
    pytest.importorskip("httpx")
    pytest.importorskip("aiosqlite")
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("emite informes y cambia los datos de la plataforma; solo en proceso")


def _correr(escenario):
    from _api_harness import cliente_api

    async def _main():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_main())


B = "/api/admin/privacidad-plataforma"


def test_api_solo_admin():
    _api()
    from _api_harness import EVAL_ID, encabezados_qa
    from app.core.autenticacion import Rol, emitir_token

    async def esc(c):
        rutas = [("GET", B, {}), ("GET", f"{B}/actividades/arcop", {}),
                 ("PATCH", f"{B}/ropa-datos", {"json": {"direccion": "Av. Siempre Viva 123"}}),
                 ("POST", f"{B}/informes", {"json": {"tipo": "rat"}}),
                 ("GET", f"{B}/informes/verificacion?codigo=CIA-PLAT-REG-2026-000001-1", {}),
                 ("GET", f"{B}/informes/1/descarga?formato=pdf", {}), ("GET", f"{B}/mapa/descarga", {})]
        otros = [encabezados_qa("referente"),
                 {"Authorization": f"Bearer {emitir_token(EVAL_ID, Rol.ENCUESTADO.value)}"},
                 {"Authorization": f"Bearer {emitir_token(1, Rol.CLIENTE.value)}"}]
        for metodo, url, kw in rutas:
            assert (await c.request(metodo, url, headers={"Authorization": ""}, **kw)).status_code == 401
            for h in otros:
                assert (await c.request(metodo, url, headers=h, **kw)).status_code in (401, 403)
    _correr(esc)


def test_api_registro_emision_descarga_y_verificacion():
    _api()

    async def esc(c):
        r = await c.get(B)
        assert r.status_code == 200, r.text
        e = r.json()
        assert len(e["actividades"]) == len(inv.ACTIVIDADES_PLATAFORMA)
        assert {a["clave"] for a in e["actividades"]} >= set(inv.ACTIVIDADES_OBLIGATORIAS)
        assert e["revision"]["revisiones"] and e["mapa"]["elementos"] and e["proveedores"]
        assert all(p["rol"] == "encargado" for p in e["proveedores"])
        assert e["registro"]["version_siguiente"] == 1 and e["ultimas"]["rat"] is None
        assert (await c.get(f"{B}/actividades/arcop")).json()["nombre"] == "Derechos ARCOP"
        assert (await c.get(f"{B}/actividades/no_existe")).status_code == 404

        # RAT: emitir, reutilizar, forzar
        r = await c.post(f"{B}/informes", json={"tipo": "rat"})
        assert r.status_code == 201, r.text
        rat = r.json()["informe"]
        assert rat["codigo"].startswith("CIA-PLAT-REG-") and rat["version"] == 1
        r = await c.post(f"{B}/informes", json={"tipo": "rat"})
        assert r.status_code == 200 and r.json()["reutilizado"] is True
        r = await c.post(f"{B}/informes", json={"tipo": "rat", "forzar": True})
        assert r.status_code == 201 and r.json()["informe"]["version"] == 1      # mismo contenido, misma versión
        d = await c.get(f"{B}/informes/{rat['id']}/descarga?formato=pdf")
        assert d.status_code == 200 and d.content.startswith(b"%PDF")
        assert "registro_plataforma_v1_" in d.headers["content-disposition"]
        x = await c.get(f"{B}/informes/{rat['id']}/descarga?formato=xlsx")
        assert x.status_code == 200 and x.content.startswith(b"PK")
        v = (await c.get(f"{B}/informes/verificacion", params={"codigo": rat["codigo"]})).json()
        assert v["valido"] is True and v["sigue_al_dia"] is True
        assert (await c.get(f"{B}/informes/verificacion", params={"codigo": "CIA-PLAT-REG-2026-000099-X"})).status_code == 422

        # RoPA: pide los datos de contacto antes de generar
        r = await c.post(f"{B}/informes", json={"tipo": "ropa"})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "ROPA_DATOS_INCOMPLETOS"
        r = await c.patch(f"{B}/ropa-datos", json={"correo": "no-es-correo"})
        assert r.status_code == 422 and r.json()["detail"]["campo"] == "correo"
        r = await c.patch(f"{B}/ropa-datos", json=DATOS_ROPA)
        assert r.status_code == 200 and r.json()["puede_emitir"] is True
        r = await c.post(f"{B}/informes", json={"tipo": "ropa"})
        assert r.status_code == 201, r.text
        ropa = r.json()["informe"]
        assert ropa["codigo"].startswith("CIA-PLAT-ROPA-")
        assert (await c.get(f"{B}/informes/{ropa['id']}/descarga?formato=pdf")).content.startswith(b"%PDF")
        m = await c.get(f"{B}/mapa/descarga")
        assert m.status_code == 200 and m.content.startswith(b"%PDF")

        e = (await c.get(B)).json()
        assert e["ultimas"]["rat"]["id"] != rat["id"] and e["registro"]["al_dia"] is True
        assert e["ropa"]["datos"]["correo"] == "privacidad@therionlabs.cl" and len(e["emisiones"]) == 3
    _correr(esc)


def test_api_bitacora_sin_datos_de_contacto():
    _api()
    from app.infrastructure.repositories.bitacora_repository import Accion

    async def esc(c):
        await c.patch(f"{B}/ropa-datos", json=DATOS_ROPA)
        await c.post(f"{B}/informes", json={"tipo": "rat"})
        r = await c.get("/api/admin/bitacora", params={"accion": Accion.PLATAFORMA_ROPA_DATOS_ACTUALIZADOS})
        assert r.status_code == 200, r.text
        cuerpo = r.text
        assert "privacidad@therionlabs.cl" not in cuerpo and "2345 6789" not in cuerpo
        items = r.json()["items"]
        assert items and "correo" in items[0]["detalle"]["campos"]
        g = (await c.get("/api/admin/bitacora", params={"accion": Accion.PLATAFORMA_INFORME_GENERADO})).json()["items"]
        assert g and g[0]["detalle"]["tipo"] == "rat"
    _correr(esc)


def test_catalogo_de_datos_personales_incluye_las_tablas_nuevas():
    pytest.importorskip("sqlalchemy")
    from app.domain.models.plataforma import PlataformaInforme, PlataformaRegistro
    assert set(inv.CATALOGO["plataforma_informe"]) == {c.name for c in PlataformaInforme.__table__.columns}
    assert set(inv.CATALOGO["plataforma_registro"]) == {c.name for c in PlataformaRegistro.__table__.columns}
    assert inv.actividad_de_tabla("plataforma_informe").clave == "auditoria"
