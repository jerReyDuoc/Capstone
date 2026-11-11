"""
QA - HU-34: mapa de datos personales del cliente (base del RAT y del RoPA).

  C1  Sistemas y bases de datos (nombre, tipo, proveedor, país, responsable) y flujos entre
      ellos, hacia terceros y transferencias internacionales.
  C2  Categorías de datos (sensibles) y de titulares (NNA) de un catálogo común con el RAT.
  C3  Mapa navegable con filtros (sensible, tercero, país) exportable a PDF (y PNG en el panel).
  C4  Inicio desde una plantilla por rubro y desde las respuestas de la evaluación.
  C5  Cada cambio versionado y en el audit_log; solo con contrato vigente.

Parte 1: lógica pura (catálogo, validación, transferencias, hallazgos, filtros, versiones,
disposición, plantillas, sugerencias y PDF). Corre sin BD.
Parte 2: API en proceso (SQLite), reutiliza la preparación de test_hu27_empresa_cliente.py;
necesita FastAPI, SQLAlchemy y aiosqlite (Docker).
"""
import asyncio
import re

import pytest

from app.application.mapa_datos import plantillas as P
from app.application.mapa_datos import sugerencias as S
from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos import analisis as A
from app.domain.mapa_datos import disposicion as D
from app.domain.mapa_datos import versiones as V
from app.domain.mapa_datos.modelo import (
    Elemento, ErrorValidacion, Flujo, contiene_contacto, normalizar_elemento, normalizar_flujo,
)

CODIGO_INTERNO = re.compile(r"\b(?:HU|T)-\d{2}\b|\bF[1-7]\b|\b(?:DAT|GOB|RIE|SEG)-\d{3}\b")


def _mapa(codigo: str = "retail"):
    """Mapa de dominio armado con una plantilla (ids correlativos)."""
    p = P.PLANTILLAS[codigo]
    ids, els = {}, []
    for i, e in enumerate(p.elementos, 1):
        ids[e.clave] = i
        els.append(Elemento(i, e.tipo, e.nombre, e.subtipo, e.descripcion, None, e.pais, e.responsable, list(e.datos),
                            list(e.titulares), e.nna, e.rol, None, "plantilla", e.clave, True))
    fls = [Flujo(j, ids[f.origen], ids[f.destino], f.finalidad, list(f.datos), list(f.titulares), f.nna, f.frecuencia,
                 f.medio) for j, f in enumerate(p.flujos, 1)]
    return els, fls, ids


# ===================================================================== C2: catálogo común
def test_catalogo_comun_codigos_unicos_sensibles_de_la_ley_y_titulares_nna():
    codigos = [c.codigo for c in cat.CATEGORIAS_DATOS]
    assert len(codigos) == len(set(codigos))
    assert len({c.codigo for c in cat.CATEGORIAS_TITULARES}) == len(cat.CATEGORIAS_TITULARES)
    # Datos sensibles de la Ley 21.719 presentes y marcados
    for sensible in ("salud", "biometricos", "perfil_biologico", "origen_etnico", "socioeconomicos", "afiliacion",
                     "creencias", "vida_sexual"):
        assert cat.DATOS_POR_CODIGO[sensible].sensible, sensible
    assert not cat.DATOS_POR_CODIGO["contacto"].sensible
    assert cat.CODIGOS_TITULARES_NNA == {"nna"}
    assert cat.TITULARES_POR_CODIGO["estudiantes"].posible_nna
    d = cat.catalogo_dict()
    assert d["version"] == cat.VERSION_CATALOGO and d["pais_local"] == "CL"
    assert {c["codigo"] for c in d["categorias_datos"] if c["sensible"]} == set(cat.CODIGOS_SENSIBLES)
    assert set(d["subtipos"]) == set(cat.TIPOS)
    assert not CODIGO_INTERNO.search(str(d))


def test_catalogo_estable_para_el_rat():
    """Los códigos son la llave con el RAT: no se renombran (si cambian, esta prueba avisa)."""
    assert {"identificacion", "contacto", "financieros", "salud", "biometricos", "comunicaciones",
            "perfilamiento"} <= set(cat.DATOS_POR_CODIGO)
    assert {"clientes", "trabajadores", "pacientes", "estudiantes", "nna"} <= set(cat.TITULARES_POR_CODIGO)
    assert cat.GARANTIAS_VALIDAS == cat.GARANTIAS - {"ninguna"}


# ===================================================================== C1: validación
def test_elemento_valido_se_normaliza():
    datos = normalizar_elemento({"tipo": "tercero", "nombre": "  Proveedor   de nube ", "pais": "us",
                                 "rol_tercero": "encargado", "categorias_datos": ["contacto", "contacto", "salud"],
                                 "subtipo": "proveedor_nube", "contrato_firmado": True})
    assert datos["nombre"] == "Proveedor de nube" and datos["pais"] == "US"
    assert datos["categorias_datos"] == ["contacto", "salud"] and datos["contrato_firmado"] is True


@pytest.mark.parametrize("datos, campo", [
    ({"tipo": "nube", "nombre": "X1"}, "tipo"),
    ({"tipo": "sistema", "nombre": " "}, "nombre"),
    ({"tipo": "sistema", "nombre": "CRM", "subtipo": "proveedor_ia"}, "subtipo"),
    ({"tipo": "sistema", "nombre": "CRM", "pais": "XX"}, "pais"),
    ({"tipo": "sistema", "nombre": "CRM", "categorias_datos": ["inventada"]}, "categorias_datos"),
    ({"tipo": "sistema", "nombre": "CRM", "categorias_titulares": "clientes"}, "categorias_titulares"),
    ({"tipo": "sistema", "nombre": "CRM", "rol_tercero": "encargado"}, "rol_tercero"),
    ({"tipo": "sistema", "nombre": "CRM", "responsable": "Ana Pérez ana.perez@acme.cl"}, "responsable"),
    ({"tipo": "sistema", "nombre": "CRM", "responsable": "Jefe TI +56 9 8765 4321"}, "responsable"),
    ({"tipo": "sistema", "nombre": "CRM de 12.345.678-5"}, "nombre"),
    ({"tipo": "sistema", "nombre": "x" * 121}, "nombre"),
])
def test_elemento_invalido_responde_el_campo(datos, campo):
    with pytest.raises(ErrorValidacion) as e:
        normalizar_elemento(datos)
    assert e.value.campo == campo and e.value.mensaje


def test_minimizacion_detecta_contactos_pero_no_nombres_de_sistemas():
    assert contiene_contacto("escribir a dpo@empresa.cl")
    assert contiene_contacto("RUT 12.345.678-5") and contiene_contacto("+56 9 1234 5678")
    for limpio in ("SAP S/4HANA 2023", "Jefatura de TI", "Servidor 10.0.0.12", "Plan 2026 v3", None):
        assert not contiene_contacto(limpio), limpio


def test_edicion_parcial_solo_devuelve_lo_que_cambia_y_limpia_lo_de_tercero():
    tercero = Elemento(1, "tercero", "Courier", "logistica", rol_tercero="encargado", contrato_firmado=True)
    assert normalizar_elemento({"nombre": "Courier", "pais": None}, tercero) == {}
    cambio = normalizar_elemento({"tipo": "sistema"}, tercero)
    assert cambio["tipo"] == "sistema" and cambio["subtipo"] is None
    assert cambio["rol_tercero"] is None and cambio["contrato_firmado"] is None


def test_flujo_valida_extremos_y_codigos():
    assert normalizar_flujo({"origen_id": 1, "destino_id": 2, "garantia": "clausulas_contractuales",
                             "cifrado": True})["garantia"] == "clausulas_contractuales"
    for datos, campo in (({"origen_id": 1, "destino_id": 1}, "destino_id"), ({"origen_id": 0, "destino_id": 2}, "origen_id"),
                         ({"origen_id": 1, "destino_id": 2, "frecuencia": "anual"}, "frecuencia"),
                         ({"origen_id": 1, "destino_id": 2, "cifrado": "si"}, "cifrado")):
        with pytest.raises(ErrorValidacion) as e:
            normalizar_flujo(datos)
        assert e.value.campo == campo


# ===================================================================== C1: transferencias internacionales
def test_transferencia_internacional_se_calcula_con_el_pais_de_cada_extremo():
    assert A.es_internacional("CL", "US") and A.es_internacional(None, "US") and A.es_internacional("US", "DE")
    assert not A.es_internacional("US", "US") and not A.es_internacional("US", "CL") and not A.es_internacional("CL", None)
    interno = Elemento(1, "sistema", "ERP", "erp")                     # sin país: se asume Chile
    saas = Elemento(2, "sistema", "CRM", "saas")                       # SaaS sin país: desconocido
    llm = Elemento(3, "tercero", "LLM", "proveedor_ia", pais="US")
    assert A.pais_efectivo(interno) == "CL" and A.pais_efectivo(saas) is None
    d = A.derivados_flujo(Flujo(1, 1, 3, garantia="ninguna"), {1: interno, 3: llm})
    assert d.internacional and d.hacia_tercero and not d.garantia_valida and d.pais_destino == "US"


# ===================================================================== hallazgos, resumen, completitud
def test_hallazgos_priorizados_con_referencia_y_sin_codigos_internos():
    els = [Elemento(1, "sistema", "Asistente", "sistema_ia", pais="CL", categorias_datos=["comunicaciones"]),
           Elemento(2, "tercero", "LLM externo", "proveedor_ia", pais="US", rol_tercero="encargado"),
           Elemento(3, "base_datos", "Fichas", "relacional", categorias_datos=["salud"],
                    categorias_titulares=["pacientes", "nna"]),
           Elemento(4, "sistema", "Huérfano", "otro")]
    fls = [Flujo(1, 1, 2, "Prompts", ["comunicaciones", "salud"], ["pacientes"], cifrado=False),
           Flujo(2, 3, 1, "Contexto", ["salud"], ["nna"])]
    h = A.hallazgos(els, fls)
    codigos = [x.codigo for x in h]
    assert codigos[0] in ("transferencia_sensible_sin_garantia", "ia_externa_con_sensibles", "tercero_sin_contrato")
    assert {"transferencia_sensible_sin_garantia", "ia_externa_con_sensibles", "tercero_sin_contrato",
            "sensibles_sin_cifrar", "tratamiento_nna", "sensibles_sin_responsable", "elemento_aislado"} <= set(codigos)
    orden = [A.SEVERIDADES.index(x.severidad) for x in h]
    assert orden == sorted(orden)
    for x in h:
        assert x.recomendacion and x.referencia and (x.elementos or x.flujos)
        assert not CODIGO_INTERNO.search(x.titulo + x.detalle + x.recomendacion)
    assert A.contar_hallazgos(h)["Crítica"] >= 2


def test_con_garantia_y_contrato_desaparecen_los_hallazgos_graves():
    els = [Elemento(1, "sistema", "App", "aplicacion_propia", responsable="TI", categorias_datos=["contacto"],
                    categorias_titulares=["clientes"]),
           Elemento(2, "tercero", "Nube", "proveedor_nube", pais="US", rol_tercero="encargado", contrato_firmado=True)]
    fls = [Flujo(1, 1, 2, "Alojar", ["contacto"], ["clientes"], cifrado=True, garantia="clausulas_contractuales")]
    assert [x.severidad for x in A.hallazgos(els, fls)] == []
    r = A.resumen(els, fls)
    assert r["transferencias_internacionales"] == 1 and r["transferencias_sin_garantia"] == 0
    assert r["paises"][0]["codigo"] == "CL"
    assert A.completitud(els, fls)["porcentaje"] > 80


def test_completitud_indica_lo_que_falta():
    c = A.completitud([Elemento(1, "sistema", "ERP")], [])
    assert c["porcentaje"] < 50
    assert {"responsable interno", "categorías de datos", "categorías de titulares"} <= set(c["pendientes"][0]["faltan"])


# ===================================================================== C3: filtros
def test_filtros_por_sensible_tercero_y_pais_no_dejan_flechas_sueltas():
    els, fls, ids = _mapa("salud")
    sens_e, sens_f = A.aplicar_filtros(els, fls, A.FiltrosMapa(sensibles=True))
    assert sens_f and all(next(f for f in fls if f.id == i).sensibles for i in sens_f)
    for i in sens_f:
        f = next(x for x in fls if x.id == i)
        assert {f.origen_id, f.destino_id} <= sens_e
    lab = ids["salud_laboratorio"]
    e_t, f_t = A.aplicar_filtros(els, fls, A.parsear_filtros(tercero=str(lab)))
    assert lab in e_t and all(lab in (f.origen_id, f.destino_id) for f in fls if f.id in f_t)
    e_p, f_p = A.aplicar_filtros(els, fls, A.parsear_filtros(pais="us"))
    por_id = {e.id: e for e in els}
    extremos = {x for f in fls if f.id in f_p for x in (f.origen_id, f.destino_id)}
    assert e_p and all(A.pais_efectivo(por_id[i]) == "US" or i in extremos for i in e_p)
    assert any(A.pais_efectivo(por_id[i]) == "US" for i in e_p)
    todo = A.aplicar_filtros(els, fls, A.FiltrosMapa())
    assert todo == ({e.id for e in els}, {f.id for f in fls})
    f = A.parsear_filtros("1", "no", "true", "abc", "zz", "otro")
    assert f.sensibles and not f.nna and f.internacional and f.tercero is None and f.pais is None and f.tipo is None
    assert "solo datos sensibles" in A.parsear_filtros(sensibles="1").describir()


# ===================================================================== C5: versiones
def test_versiones_huella_diferencias_y_resumen_legible():
    els, fls, _ = _mapa()
    v1 = V.instantanea(els, fls)
    assert V.huella(v1) == V.huella(V.instantanea(list(reversed(els)), fls))      # no depende del orden
    els2 = [Elemento(**{**e.como_dict(), "pais": "AR"}) if e.id == 1 else e for e in els[:-1]]
    v2 = V.instantanea(els2, [f for f in fls if f.destino_id != els[-1].id])
    assert V.huella(v1) != V.huella(v2)
    cambios = V.diferencias(v1, v2)
    ops = {(c["entidad"], c["operacion"]) for c in cambios}
    assert ("elemento", "editado") in ops and ("elemento", "eliminado") in ops
    assert next(c for c in cambios if c["operacion"] == "editado")["campos"] == ["pais"]
    assert V.describir(cambios).startswith("Cambios en el mapa:")
    assert V.describir(V.diferencias(None, V.instantanea(els[:1], []))).startswith("Se agregó el sistema")
    e2, f2 = V.desde_instantanea(v2)
    assert [x.como_dict() for x in e2] == v2["elementos"] and len(f2) == len(v2["flujos"])


# ===================================================================== C3: disposición del diagrama
def test_disposicion_por_capas_en_el_sentido_de_los_datos():
    els, fls, ids = _mapa("retail")
    lay = D.calcular([(e.id, e.tipo, e.nombre) for e in els], [(f.id, f.origen_id, f.destino_id) for f in fls])
    col = {i: n.columna for i, n in lay.nodos.items()}
    assert set(lay.nodos) == {e.id for e in els}
    for f in fls:                                     # sin ciclos en la plantilla: todo fluye a la derecha
        assert col[f.destino_id] > col[f.origen_id]
    assert col[ids["retail_pagos"]] == lay.columnas - 1     # los terceros que solo reciben, al final
    posiciones = {(n.x, n.y) for n in lay.nodos.values()}
    assert len(posiciones) == len(els)                      # nadie encima de nadie
    # Un ciclo no rompe el cálculo
    ciclo = D.calcular([(1, "sistema", "A"), (2, "sistema", "B")], [(1, 1, 2), (2, 2, 1)])
    assert {n.columna for n in ciclo.nodos.values()} == {0, 1}
    assert D.calcular([], []).columnas == 0


# ===================================================================== C4: plantillas por rubro
def test_plantillas_coherentes_con_el_catalogo():
    assert len(P.PLANTILLAS) == 8
    for p in P.PLANTILLAS.values():
        claves = [e.clave for e in p.elementos]
        assert len(claves) == len(set(claves)), p.codigo
        for e in p.elementos:
            normalizar_elemento({"tipo": e.tipo, "subtipo": e.subtipo, "nombre": e.nombre, "pais": e.pais,
                                 "descripcion": e.descripcion, "responsable": e.responsable,
                                 "categorias_datos": list(e.datos), "categorias_titulares": list(e.titulares),
                                 "rol_tercero": e.rol})
            assert (e.rol is None) == (e.tipo != "tercero"), e.clave
        for f in p.flujos:
            assert f.origen in claves and f.destino in claves and f.origen != f.destino, (p.codigo, f)
            normalizar_flujo({"origen_id": 1, "destino_id": 2, "finalidad": f.finalidad, "frecuencia": f.frecuencia,
                              "medio": f.medio, "categorias_datos": list(f.datos),
                              "categorias_titulares": list(f.titulares)})
        assert not CODIGO_INTERNO.search(str(P.catalogo_plantillas(None)))


@pytest.mark.parametrize("rubro, codigo", [
    ("Banca y Finanzas", "banca"), ("Salud", "salud"), ("Retail y E-commerce", "retail"),
    ("Telecomunicaciones", "telecomunicaciones"), ("Educación", "educacion"), ("Tecnología/SaaS", "tecnologia"),
    ("Manufactura", "manufactura"), ("Servicios/Otros", "general"), (None, "general"), ("Clínica dental", "salud"),
])
def test_plantilla_recomendada_por_rubro(rubro, codigo):
    assert P.plantilla_para_rubro(rubro).codigo == codigo
    cat_p = P.catalogo_plantillas(rubro)
    assert cat_p[0]["codigo"] == codigo and cat_p[0]["recomendada"]


def test_plantilla_educacion_marca_nna():
    els, _, _ = _mapa("educacion")
    assert any(e.incluye_nna for e in els)


# ===================================================================== C4: sugerencias desde la evaluación
def test_llm_externo_sugiere_el_flujo_hacia_el_proveedor():
    sug = S.calcular({"F1": True, "F4": True}, [])
    llm = next(s for s in sug if s.clave == "llm_externo")
    assert any(e.subtipo == "proveedor_ia" and e.pais == "US" for e in llm.elementos)
    assert llm.flujos and llm.flujos[0].destino == "nuevo:sug_llm_proveedor"
    assert "modelos de lenguaje" in llm.motivo and not CODIGO_INTERNO.search(llm.motivo + llm.descripcion)


def test_sugerencia_usa_el_sistema_existente_y_desaparece_al_aplicarse_o_descartarse():
    ia = Elemento(7, "sistema", "Chatbot de ventas", "sistema_ia")
    llm = S.sugerencia({"F4": True}, [ia], "llm_externo")
    assert llm.usa_existente == 7 and llm.flujos[0].origen == "id:7"
    d = llm.como_dict({7: "Chatbot de ventas"})
    assert [e["clave"] for e in d["elementos"]] == ["sug_llm_proveedor"]
    assert d["flujos"][0]["origen"] == {"existente": True, "id": 7, "nombre": "Chatbot de ventas"}
    aplicado = Elemento(8, "tercero", "LLM", "proveedor_ia", clave="sug_llm_proveedor")
    assert S.sugerencia({"F4": True}, [ia, aplicado], "llm_externo") is None
    assert S.sugerencia({"F4": True}, [ia], "llm_externo", {"llm_externo"}) is None


def test_sin_ia_no_hay_sugerencias_y_cada_respuesta_trae_la_suya():
    assert S.calcular({"F1": False, "F4": True}, []) == []
    todas = {s.clave for s in S.calcular({f"F{i}": True for i in range(1, 8)}, [])}
    assert todas == {"llm_externo", "base_vectorial", "datos_sensibles", "agente_ia", "decisiones_automatizadas",
                     "entrenamiento"}
    assert {s.clave for s in S.calcular({"F3": True}, [])} == {"ia_nube"}


# ===================================================================== C3: informe PDF
def test_informe_pdf_completo_y_filtrado():
    pytest.importorskip("reportlab")
    from datetime import datetime, timezone

    from app.application.mapa_datos.pdf_mapa import (
        DatosInformeMapa, VersionResumen, cuerpo_correo, generar_pdf_mapa, nombre_archivo,
    )

    els, fls, _ = _mapa("salud")
    ahora = datetime.now(timezone.utc)
    huella = V.huella(V.instantanea(els, fls))
    for filtros in (A.FiltrosMapa(), A.FiltrosMapa(sensibles=True), A.FiltrosMapa(pais="AR")):
        pdf = generar_pdf_mapa(DatosInformeMapa("Clínica Austral SpA", "Salud", 3, ahora, huella, els, fls, filtros,
                                                ahora, [VersionResumen(3, ahora, "Se agregó el tercero «Lab».")]))
        assert pdf.startswith(b"%PDF") and len(pdf) > 5000
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    import io
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    for frase in ("Mapa de datos personales", "Hallazgos de riesgo", "Transferencias internacionales",
                  "registro de actividades de tratamiento", "Clínica Austral SpA"):
        assert frase in texto, frase
    assert not CODIGO_INTERNO.search(texto)
    assert nombre_archivo(3, ahora).startswith("mapa_datos_personales_v3_")
    t, h = cuerpo_correo("Clínica <Austral>", 3, A.resumen(els, fls), {"Crítica": 1, "Alta": 2}, 70)
    assert "versión 3" in t and "&lt;Austral&gt;" in h and "<Austral>" not in h


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
    if not _hay_api():
        pytest.skip("sin FastAPI/SQLAlchemy")
    import test_hu27_empresa_cliente as m
    from _api_harness import MODO
    if MODO == "live":
        pytest.skip("HU-34: solo en proceso")
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


def _correr(escenario):
    from _api_harness import cliente_api

    async def _main():
        async with cliente_api(rol=None) as c:
            await escenario(c)
    asyncio.run(_main())


async def _cliente(hu27, c) -> dict:
    x = await hu27._empresa_creada(c)
    return {**x, "hc": await hu27._activar_y_entrar(c)}


async def _filas(hu27, modelo, *where):
    from sqlalchemy import select

    async def f(s):
        return list((await s.execute(select(modelo).where(*where))).scalars().all())
    return await hu27._bd(f)


@api
def test_api_solo_usuario_definitivo_con_contrato_vigente(hu27, monkeypatch):
    async def esc(c):
        x = await _cliente(hu27, c)
        assert (await c.get("/api/mapa-datos")).status_code == 401
        r = await c.get("/api/mapa-datos", headers=hu27.admin())
        assert r.status_code == 403 and hu27._codigo(r) == "NO_AUTORIZADO"
        assert (await c.get("/api/mapa-datos", headers=x["h"])).status_code in (401, 403)   # usuario temporal

        import app.core.servicio_pagado as sp
        monkeypatch.setattr(sp, "servicio_habilitado", lambda empresa, hoy=None: False)
        for metodo, ruta, kw in (("get", "/api/mapa-datos", {}), ("get", "/api/mapa-datos/catalogo", {}),
                                 ("post", "/api/mapa-datos/elementos", {"json": {"version": 0, "tipo": "sistema",
                                                                                 "nombre": "ERP"}}),
                                 ("get", "/api/mapa-datos/informe/pdf", {})):
            r = await getattr(c, metodo)(ruta, headers=x["hc"], **kw)
            assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE", ruta
    _correr(esc)


@api
def test_api_crear_editar_eliminar_con_versiones_y_audit_log(hu27):
    async def esc(c):
        from app.domain.models import BitacoraAuditoria, MapaDatosVersion

        x = await _cliente(hu27, c)
        h = x["hc"]
        vacio = (await c.get("/api/mapa-datos", headers=h)).json()
        assert vacio["mapa"]["version"] == 0 and vacio["elementos"] == [] and not vacio["mapa"]["iniciado"]
        cat_api = (await c.get("/api/mapa-datos/catalogo", headers=h)).json()
        assert any(x["sensible"] for x in cat_api["categorias_datos"])

        # C1/C2: sistema, base y tercero con categorías
        r = await c.post("/api/mapa-datos/elementos", headers=h, json={
            "version": 0, "tipo": "sistema", "subtipo": "sistema_ia", "nombre": "Asistente de ventas", "pais": "CL",
            "responsable": "Gerencia Comercial", "categorias_datos": ["comunicaciones", "salud"],
            "categorias_titulares": ["clientes"]})
        assert r.status_code == 201, r.text
        m = r.json()
        assert m["mapa"]["version"] == 1 and m["cambio"]["resumen"].startswith("Se agregó el sistema")
        asistente = m["elementos"][0]
        assert asistente["derivados"]["sensibles"] == ["salud"]
        r = await c.post("/api/mapa-datos/elementos", headers=h, json={
            "version": 1, "tipo": "tercero", "subtipo": "proveedor_ia", "nombre": "Proveedor LLM", "pais": "US",
            "rol_tercero": "encargado"})
        llm = next(e for e in r.json()["elementos"] if e["tipo"] == "tercero")
        # versión desactualizada: 409 y queda el intento rechazado
        r = await c.post("/api/mapa-datos/elementos", headers=h, json={"version": 1, "tipo": "sistema", "nombre": "X1"})
        assert r.status_code == 409 and hu27._codigo(r) == "MAPA_DESACTUALIZADO"
        assert r.json()["detail"]["version_actual"] == 2
        # minimización: el responsable es un cargo, no una persona
        r = await c.post("/api/mapa-datos/elementos", headers=h, json={
            "version": 2, "tipo": "base_datos", "nombre": "BD", "responsable": "ana@acme.cl"})
        assert r.status_code == 422 and r.json()["detail"]["campo"] == "responsable"
        # flujo internacional con datos sensibles y sin garantía → hallazgo crítico
        r = await c.post("/api/mapa-datos/flujos", headers=h, json={
            "version": 2, "origen_id": asistente["id"], "destino_id": llm["id"], "finalidad": "Enviar prompts",
            "categorias_datos": ["comunicaciones", "salud"], "categorias_titulares": ["clientes"]})
        assert r.status_code == 201, r.text
        m = r.json()
        assert m["flujos"][0]["derivados"]["internacional"] and m["resumen"]["transferencias_internacionales"] == 1
        assert m["conteo_hallazgos"]["Crítica"] >= 1
        flujo = m["flujos"][0]
        r = await c.patch(f"/api/mapa-datos/flujos/{flujo['id']}", headers=h, json={
            "version": 3, "garantia": "clausulas_contractuales", "cifrado": True})
        assert r.status_code == 200 and r.json()["flujos"][0]["derivados"]["garantia_valida"]
        r = await c.patch(f"/api/mapa-datos/elementos/{llm['id']}", headers=h, json={"version": 4, "campo_raro": 1})
        assert r.status_code == 422
        # sin cambios: no crea versión
        r = await c.patch(f"/api/mapa-datos/elementos/{llm['id']}", headers=h, json={"version": 4, "pais": "US"})
        assert r.status_code == 200 and r.json()["cambio"] is None and r.json()["mapa"]["version"] == 4
        # eliminar el tercero se lleva su flujo
        r = await c.delete(f"/api/mapa-datos/elementos/{llm['id']}?version=4", headers=h)
        assert r.status_code == 200 and r.json()["flujos"] == [] and r.json()["mapa"]["version"] == 5

        versiones = await _filas(hu27, MapaDatosVersion)
        assert [v.numero for v in sorted(versiones, key=lambda v: v.numero)] == [1, 2, 3, 4, 5]
        from app.domain.mapa_datos.versiones import huella
        assert all(huella(v.contenido) == v.huella for v in versiones)
        acciones = [b.accion for b in await _filas(hu27, BitacoraAuditoria)
                    if b.accion.startswith("mapa_datos.")]
        for a in ("mapa_datos.elemento_creado", "mapa_datos.flujo_creado", "mapa_datos.flujo_editado",
                  "mapa_datos.elemento_eliminado", "mapa_datos.cambio_rechazado"):
            assert a in acciones, a
        for b in await _filas(hu27, BitacoraAuditoria):
            if b.accion.startswith("mapa_datos."):
                assert "Asistente" not in str(b.detalle) and b.ip     # el log no lleva los textos del mapa

        # historial y restauración (crea una versión nueva)
        hist = (await c.get("/api/mapa-datos/versiones", headers=h)).json()
        assert hist["version_actual"] == 5 and hist["items"][0]["numero"] == 5
        v3 = (await c.get("/api/mapa-datos/versiones/3", headers=h)).json()
        assert v3["verificada"] and len(v3["version"]["contenido"]["flujos"]) == 1
        r = await c.post("/api/mapa-datos/versiones/3/restaurar", headers=h, json={"version": 5})
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["mapa"]["version"] == 6 and len(m["elementos"]) == 2 and len(m["flujos"]) == 1
        assert {e["id"] for e in m["elementos"]} == {asistente["id"], llm["id"]}      # mismos ids
    _correr(esc)


@api
def test_api_plantilla_sugerencias_e_informe(hu27):
    async def esc(c):
        from sqlalchemy import select

        from app.domain.models import PreguntaFiltro, RespuestaFiltro

        x = await _cliente(hu27, c)
        h = x["hc"]
        pl = (await c.get("/api/mapa-datos/plantillas", headers=h)).json()["plantillas"]
        assert pl[0]["recomendada"]
        r = await c.post("/api/mapa-datos/plantillas/aplicar", headers=h, json={"version": 0, "codigo": "retail"})
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["mapa"]["version"] == 1 and len(m["elementos"]) == len(P.PLANTILLAS["retail"].elementos)
        assert all(e["pendiente_revision"] and e["origen"] == "plantilla" for e in m["elementos"])
        r = await c.post("/api/mapa-datos/plantillas/aplicar", headers=h, json={"version": 1, "codigo": "retail"})
        assert r.status_code == 409 and hu27._codigo(r) == "PLANTILLA_SIN_CAMBIOS"
        r = await c.post("/api/mapa-datos/revision", headers=h, json={"version": 1, "todo": True})
        assert r.status_code == 200 and r.json()["resumen"]["pendientes_revision"] == 0

        # C4: la evaluación declaró usar un LLM (F4) → se sugiere el flujo hacia el proveedor
        async def declarar_llm(s):
            f4 = (await s.execute(select(PreguntaFiltro).where(PreguntaFiltro.codigo == "F4"))).scalar_one()
            fila = (await s.execute(select(RespuestaFiltro).where(
                RespuestaFiltro.evaluacion_id == x["ev"], RespuestaFiltro.pregunta_id == f4.id_pregunta))).scalar_one()
            fila.respuesta = True
            await s.commit()
        await hu27._bd(declarar_llm)
        sug = (await c.get("/api/mapa-datos/sugerencias", headers=h)).json()
        assert sug["evaluacion_id"] == x["ev"]
        llm = next(s for s in sug["sugerencias"] if s["clave"] == "llm_externo")
        crm = next(e for e in m["elementos"] if e["clave"] == "retail_crm")
        r = await c.post("/api/mapa-datos/sugerencias/llm_externo/aceptar", headers=h,
                         json={"version": 2, "origen_id": crm["id"]})
        assert r.status_code == 200, r.text
        m = r.json()
        prov = next(e for e in m["elementos"] if e["clave"] == "sug_llm_proveedor")
        assert prov["origen"] == "evaluacion" and any(
            f["origen_id"] == crm["id"] and f["destino_id"] == prov["id"] for f in m["flujos"])
        assert not any(e["clave"] == "sug_asistente_ia" for e in m["elementos"])      # usó el CRM elegido
        sug = (await c.get("/api/mapa-datos/sugerencias", headers=h)).json()
        assert "llm_externo" not in {s["clave"] for s in sug["sugerencias"]}
        r = await c.post("/api/mapa-datos/sugerencias/base_vectorial/descartar", headers=h)
        assert r.status_code == 200 and "base_vectorial" not in {s["clave"] for s in r.json()["sugerencias"]}
        assert llm["motivo"]

        # C3: informe PDF (con filtros) y envío por correo
        r = await c.get("/api/mapa-datos/informe/pdf?sensibles=1&pais=US", headers=h)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        assert r.headers["content-disposition"].startswith('attachment; filename="mapa_datos_personales_v3_')
        r = await c.post("/api/mapa-datos/informe/enviar", headers=h, json={})
        assert r.status_code == 200 and r.json()["enviado"] and "***" in r.json()["destino"]
        r = await c.post("/api/mapa-datos/informe/enviar", headers=h, json={"email": "no-es-correo"})
        assert r.status_code == 422
    _correr(esc)


@api
def test_api_aislamiento_entre_empresas(hu27):
    async def esc(c):
        x = await _cliente(hu27, c)
        r = await c.post("/api/mapa-datos/elementos", headers=x["hc"], json={"version": 0, "tipo": "sistema",
                                                                              "nombre": "ERP"})
        eid = r.json()["elementos"][0]["id"]
        # Un elemento que no es de la empresa responde 404 (aquí: un id inexistente en su mapa)
        r = await c.patch(f"/api/mapa-datos/elementos/{eid + 999}", headers=x["hc"], json={"version": 1, "nombre": "Y"})
        assert r.status_code == 404 and hu27._codigo(r) == "ELEMENTO_NO_ENCONTRADO"
        r = await c.get("/api/mapa-datos/versiones/99", headers=x["hc"])
        assert r.status_code == 404
    _correr(esc)
