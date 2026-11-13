"""
QA - HU-38: el registro de actividades conectado con la evaluación, las brechas y los borradores.

  C1  Cada actividad recibe un nivel de riesgo con reglas explicables (datos sensibles, de NNA,
      transferencias sin garantía, decisiones automatizadas, uso de IA, volumen). Las de mayor riesgo
      forman la matriz de riesgos (Decreto 662, art. 3 letra e) y se recomienda una evaluación de impacto.
  C2  La PIA de los borradores se pre-llena con las actividades de alto riesgo y el aviso de privacidad
      toma las finalidades y bases de licitud del registro.
  C3  Un registro vigente y completo cuenta como evidencia de los controles de protección de datos y
      actualiza puntaje y brechas igual que una evidencia de remediación, sin bajar nunca un control.
  C4  El espacio de la empresa muestra el estado del mapeo y del registro y las brechas que generan (sin
      base de licitud, sin plazo, transferencia sin garantía) con su ruta de remediación.

Parte 1: lógica pura (sin BD). Parte 2: API en proceso (SQLite), con la preparación de test_hu35_rat.py.
"""
import asyncio
import re
from datetime import datetime, timedelta

import pytest

from app.application.borradores import generador as G
from app.application.borradores import registro as BR
from app.application.borradores.plantillas import TipoPlantilla, plantilla
from app.application.rat import informe as I
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.rat import analisis as A
from app.domain.rat import cumplimiento as CU
from app.domain.rat import modelo as M
from app.domain.rat import riesgos as RG
from app.domain.rat import versiones as V

CODIGO_INTERNO = re.compile(r"\b(?:HU|T)-\d{2}\b|\bF[1-7]\b|\b(?:ERR-)?(?:DAT|GOB|RIE|SEG)-\d{3}\b")
AHORA = datetime(2026, 11, 13, 10, 0)


# ===================================================================== mapa de prueba
def _mapa():
    """CRM (CL) con clientes, asistente con IA (CL), proveedor de IA en EE. UU. y banco encargado."""
    els = [
        Elemento(1, "sistema", "CRM de clientes", "crm", pais="CL", categorias_datos=["identificacion", "contacto", "salud"],
                 categorias_titulares=["clientes", "nna"]),
        Elemento(2, "sistema", "Asistente virtual", "sistema_ia", pais="CL",
                 categorias_datos=["identificacion", "contacto"], categorias_titulares=["clientes"]),
        Elemento(3, "tercero", "Proveedor de modelos", "proveedor_ia", pais="US", rol_tercero="encargado",
                 contrato_firmado=True, categorias_datos=["identificacion", "contacto"], categorias_titulares=["clientes"]),
        Elemento(4, "tercero", "Banco pagador", "pagos", pais="CL", rol_tercero="encargado", contrato_firmado=False,
                 categorias_datos=["identificacion"], categorias_titulares=["clientes"]),
    ]
    fls = [
        Flujo(1, 1, 2, "Atención", ["identificacion", "contacto"], ["clientes"]),
        Flujo(2, 2, 3, "Respuestas del asistente", ["identificacion", "contacto"], ["clientes"], garantia="clausulas_contractuales"),
        Flujo(3, 1, 4, "Pagos", ["identificacion"], ["clientes"]),
    ]
    return els, fls


def _sel(x, datos=None, titulares=None):
    return {"id": x.id, "categorias_datos": list(datos or x.categorias_datos),
            "categorias_titulares": list(titulares or x.categorias_titulares)}


def _atencion(els, fls, **cambios) -> dict:
    base = {
        "nombre": "Atención de clientes con asistente", "finalidades": ["Responder consultas de los clientes"],
        "rol": "responsable", "elementos": [_sel(els[0], ["identificacion", "contacto"], ["clientes"]), _sel(els[1])],
        "flujos": [_sel(fls[0]), _sel(fls[1])], "fuentes": [{"tipo": "titular"}], "base_licitud": "contrato",
        "plazos": [{"categoria": c, "plazo": 2, "unidad": "anios", "desde": "termino_relacion"}
                   for c in ("identificacion", "contacto")],
        "decisiones": {"existe": False},
        "medidas": {"codigos": ["control_acceso", "cifrado_transito", "cifrado_reposo"]},
    }
    base.update(cambios)
    return M.normalizar(base)


def _riesgo(contenido, els, fls, faltantes=0):
    return RG.evaluar(1, contenido["nombre"], contenido, A.derivados(contenido, els, fls), faltantes)


# ===================================================================== C1 · riesgo explicable
def test_uso_de_ia_y_volumen_son_factores_explicables_del_riesgo():
    els, fls = _mapa()
    sin_volumen = _atencion(els, fls)
    deriv = A.derivados(sin_volumen, els, fls)
    assert [x["nombre"] for x in deriv["sistemas_ia"]] == ["Asistente virtual", "Proveedor de modelos"]
    r = _riesgo(sin_volumen, els, fls)
    ia = next(f for f in r.factores if f.titulo == "Uso de inteligencia artificial")
    assert ia.eje == "probabilidad" and "Asistente virtual" in ia.detalle and ia.tratamiento
    assert not any(f.titulo == "Gran volumen de personas" for f in r.factores)

    masivo = M.normalizar({"volumen": "mas_100_mil"}, sin_volumen)
    r2 = _riesgo(masivo, els, fls)
    vol = next(f for f in r2.factores if f.titulo == "Gran volumen de personas")
    assert vol.eje == "impacto" and vol.puntos == 2 and "100.000" in vol.detalle
    assert r2.impacto == r.impacto + 2
    medio = M.normalizar({"volumen": "hasta_100_mil"}, sin_volumen)
    assert next(f for f in _riesgo(medio, els, fls).factores if f.titulo == "Gran volumen de personas").puntos == 1
    assert not any(f.titulo == "Gran volumen de personas"
                   for f in _riesgo(M.normalizar({"volumen": "hasta_mil"}, sin_volumen), els, fls).factores)


def test_reglas_de_la_evaluacion_de_impacto_y_matriz_de_mayor_riesgo():
    els, fls = _mapa()
    simple = _atencion(els, fls, elementos=[_sel(els[0], ["identificacion"], ["clientes"])], flujos=[],
                       plazos=[{"categoria": "identificacion", "plazo": 2, "unidad": "anios"}], sin_destinatarios=True)
    r = _riesgo(simple, els, fls)
    assert r.nivel in ("Bajo", "Medio") and not r.requiere_pia and not r.mayor_riesgo

    # decisiones automatizadas → evaluación de impacto
    decide = M.normalizar({"decisiones": {"existe": True, "logica": "Prioriza solicitudes por puntaje",
                                          "intervencion_humana": True}}, simple)
    rd = _riesgo(decide, els, fls)
    assert rd.requiere_pia and any("decisiones automatizadas" in m for m in rd.motivos_pia)
    # datos sensibles y de NNA a gran escala → evaluación de impacto
    sensibles = M.normalizar({"elementos": [_sel(els[0])], "base_sensibles": "consentimiento_expreso",
                              "volumen": "hasta_100_mil",
                              "plazos": [{"categoria": c, "plazo": 2, "unidad": "anios"}
                                         for c in ("identificacion", "contacto", "salud")]}, simple)
    rs = _riesgo(sensibles, els, fls)
    assert any("gran escala" in m for m in rs.motivos_pia)
    assert any("sensibles y de niños" in m for m in rs.motivos_pia)
    # IA con datos sensibles → evaluación de impacto
    ia = M.normalizar({"elementos": [_sel(els[0]), _sel(els[1])], "base_sensibles": "consentimiento_expreso",
                       "plazos": [{"categoria": c, "plazo": 2, "unidad": "anios"}
                                  for c in ("identificacion", "contacto", "salud")]}, simple)
    ri = _riesgo(ia, els, fls)
    assert any("inteligencia artificial" in m for m in ri.motivos_pia)

    matriz = RG.matriz_mayor_riesgo([r, rd, rs, ri])
    assert r not in matriz and {x.puntaje for x in matriz} and all(x.mayor_riesgo for x in matriz)
    assert [x.puntaje for x in matriz] == sorted((x.puntaje for x in matriz), reverse=True)
    d = rd.como_dict()
    assert d["requiere_pia"] and d["motivos_pia"] and d["mayor_riesgo"]
    assert "Decreto 662" in RG.REFERENCIA_MATRIZ and "evaluación de impacto" in RG.METODOLOGIA_PIA
    for texto in [RG.METODOLOGIA, RG.METODOLOGIA_PIA] + [m for x in (rd, rs, ri) for m in x.motivos_pia]:
        assert not CODIGO_INTERNO.search(texto)


def test_volumen_opcional_no_cambia_las_versiones_ni_la_completitud():
    els, fls = _mapa()
    c = _atencion(els, fls)
    assert "volumen" not in c and "volumen" not in M.completar(c)
    with pytest.raises(Exception):
        M.normalizar({"volumen": "muchisimas"}, c)
    con = M.normalizar({"volumen": "hasta_10_mil"}, c)
    assert con["volumen"] == "hasta_10_mil" and M.campos_cambiados(c, con) == ["volumen"]
    assert "volumen" not in M.normalizar({"volumen": None}, con)
    d = A.derivados(c, els, fls)
    # la huella de una actividad sin volumen es la misma que antes de que existiera el dato
    inst = V.instantanea(c, d)
    assert "volumen" not in inst["actividad"] and "sistemas_ia" not in inst["mapa"]
    assert A.completitud(con, A.derivados(con, els, fls))["total"] == 13
    assert V.diferencias(inst, V.instantanea(con, A.derivados(con, els, fls))) == ["volumen"]
    assert V.describir(["volumen"]) == "Cambió: Cantidad de personas."


def test_el_informe_marca_la_matriz_de_mayor_riesgo_y_la_pia_recomendada():
    els, fls = _mapa()
    c = _atencion(els, fls, decisiones={"existe": True, "perfilamiento": True, "logica": "Segmenta clientes",
                                        "intervencion_humana": False})
    d = A.derivados(c, els, fls)
    inst = V.instantanea(c, d)
    vig = I.FuenteActividad(1, c["nombre"], "vigente", 1, AHORA, AHORA, (), inst, V.huella(inst),
                            AHORA - timedelta(days=1), sistemas_ia=tuple(A.sistemas_ia_en(inst["mapa"], els)))
    inf = I.armar([vig], AHORA, "Clínica Demo SpA")
    a = inf.actividades[0]
    assert a.riesgo.requiere_pia and any(f.titulo == "Uso de inteligencia artificial" for f in a.riesgo.factores)
    assert inf.resumen["pia_recomendadas"] == 1 and inf.resumen["mayor_riesgo"] == 1
    prev = I.resumen_publico(inf)
    assert prev["actividades"][0]["riesgo"]["requiere_pia"] and prev["actividades"][0]["riesgo"]["motivos_pia"]
    # la instantánea sola (sin el mapa actual) no sabe del uso de IA
    sin_ia = I.armar([I.FuenteActividad(1, c["nombre"], "vigente", 1, AHORA, AHORA, (), inst, V.huella(inst), AHORA)],
                     AHORA, "Clínica Demo SpA")
    assert not any(f.titulo == "Uso de inteligencia artificial" for f in sin_ia.actividades[0].riesgo.factores)


def test_pdf_y_xlsx_incluyen_la_matriz_de_mayor_riesgo():
    pytest.importorskip("reportlab")
    pytest.importorskip("openpyxl")
    pypdf = pytest.importorskip("pypdf")
    import io

    from openpyxl import load_workbook

    from app.application.rat.pdf_rat import generar_pdf_rat
    from app.application.rat.xlsx_rat import generar_xlsx_rat

    els, fls = _mapa()
    c = _atencion(els, fls, decisiones={"existe": True, "logica": "Prioriza consultas", "intervencion_humana": True})
    d = A.derivados(c, els, fls)
    inst = V.instantanea(c, d)
    inf = I.armar([I.FuenteActividad(1, c["nombre"], "vigente", 1, AHORA, AHORA, (), inst, V.huella(inst), AHORA)],
                  AHORA, "Clínica Demo SpA").con_emision(I.codigo(7, 2026), 1)
    texto = " ".join(pg.extract_text() for pg in pypdf.PdfReader(io.BytesIO(generar_pdf_rat(inf))).pages)
    texto = " ".join(texto.split())
    assert "Actividades de mayor riesgo" in texto and "Decreto 662" in texto and "Recomendada" in texto
    ws = load_workbook(io.BytesIO(generar_xlsx_rat(inf)))["Matriz de riesgos"]
    valores = [str(v) for fila in ws.iter_rows(values_only=True) for v in fila if v is not None]
    assert "Evaluación de impacto" in valores and any(v.startswith("Recomendada: ") for v in valores)


# ===================================================================== C3 · el registro como evidencia
def _actividad_registro(id_, contenido, els, fls, estado="vigente", motivos=()):
    d = A.derivados(contenido, els, fls)
    return CU.ActividadRegistro(id_, contenido["nombre"], estado, M.completar(contenido), d,
                                A.completitud(contenido, d), tuple(motivos))


def test_solo_un_registro_vigente_y_completo_aporta_y_nunca_baja_un_control():
    els, fls = _mapa()
    c = _atencion(els, fls)
    pagos = _atencion(els, fls, nombre="Pago a proveedores", elementos=[_sel(els[0], ["identificacion"], ["clientes"])],
                      flujos=[_sel(fls[2])], plazos=[{"categoria": "identificacion", "plazo": 5, "unidad": "anios"}])
    vig = [_actividad_registro(1, c, els, fls), _actividad_registro(2, pagos, els, fls)]
    est = CU.estado_registro(vig, 0, True)
    assert est.vigente_completo and est.faltantes() == []
    ap = {a.control: a for a in CU.aportes(est, vig)}
    assert ap["DAT-005"].estado == "cumplido" and ap["DAT-001"].estado == "cumplido"
    assert ap["DAT-003"].estado == "parcialmente_cumplido"
    assert ap["DAT-008"].estado == "cumplido"                        # la transferencia tiene garantía
    assert ap["DAT-007"].estado == "parcialmente_cumplido"            # el banco no tiene contrato confirmado
    for a in ap.values():
        assert not CODIGO_INTERNO.search(a.motivo)

    # sin vigencia, con un envío sin actividad o con cambios del mapa por revisar: no aporta nada
    for estado in (CU.estado_registro([_actividad_registro(1, c, els, fls, "borrador")], 0, True),
                   CU.estado_registro(vig, 1, True),
                   CU.estado_registro([_actividad_registro(1, c, els, fls, "en_revision", ({"texto": "x"},))], 0, True),
                   CU.estado_registro([], 0, False)):
        assert not estado.vigente_completo and CU.aportes(estado, vig) == [] and estado.faltantes()

    # solo mejora: nunca baja, no toca un "no aplica" ni un estado desconocido
    assert CU.mejora("no_cumplido", "parcialmente_cumplido") and CU.mejora("requiere_revision", "cumplido")
    assert not CU.mejora("cumplido", "parcialmente_cumplido") and not CU.mejora("cumplido", "cumplido")
    assert not CU.mejora("no_aplica", "cumplido") and not CU.mejora(None, "cumplido")


def test_brechas_del_registro_con_su_paso_y_sin_codigos_internos():
    els, fls = _mapa()
    sin_base = _atencion(els, fls, base_licitud=None)
    sin_plazo = _atencion(els, fls, nombre="Marketing", plazos=[])
    sin_garantia_fls = [fls[0], Flujo(2, 2, 3, "Respuestas", ["identificacion", "contacto"], ["clientes"])]
    transf = _atencion(els, sin_garantia_fls, nombre="Envío al proveedor")
    acts = [_actividad_registro(1, sin_base, els, fls, "borrador"),
            _actividad_registro(2, sin_plazo, els, fls, "borrador"),
            _actividad_registro(3, transf, els, sin_garantia_fls, "borrador")]
    b = CU.brechas(acts, [{"id": 3, "nombre": "CRM de clientes → Banco pagador"}])
    codigos = [x["codigo"] for x in b]
    assert set(codigos) == {"sin_base_licitud", "sin_plazo", "transferencia_sin_garantia", "flujo_sin_actividad"}
    por = {x["codigo"]: x for x in b}
    assert por["sin_base_licitud"]["paso"] == 3 and por["sin_base_licitud"]["actividad"]["id"] == 1
    assert por["sin_plazo"]["paso"] == 5 and por["transferencia_sin_garantia"]["paso"] == 4
    assert por["transferencia_sin_garantia"]["flujo_id"] == 2 and "Estados Unidos" in por["transferencia_sin_garantia"]["texto"]
    assert por["flujo_sin_actividad"]["actividad"] is None and por["flujo_sin_actividad"]["flujo_id"] == 3
    assert codigos.index("sin_base_licitud") < codigos.index("sin_plazo")     # de la más grave a la más leve
    for x in b:
        assert not CODIGO_INTERNO.search(x["texto"] + x["titulo"])


# ===================================================================== C2 · borradores desde el registro
def _ctx():
    return G.ContextoBorrador(evaluacion_id=9, fecha_evaluacion=None, rubro="Salud", puntaje_general=40.0,
                              nivel_general="en_desarrollo")


def _identidad():
    return G.IdentidadEmpresa("Clínica Demo SpA", "76.086.428-5", "Salud")


def _registro_borradores():
    els, fls = _mapa()
    alto = _atencion(els, fls, elementos=[_sel(els[0]), _sel(els[1])], base_sensibles="consentimiento_expreso",
                     volumen="mas_100_mil", decisiones={"existe": True, "perfilamiento": True,
                                                         "logica": "Segmenta clientes", "intervencion_humana": True},
                     plazos=[{"categoria": c, "plazo": 2, "unidad": "anios", "desde": "termino_relacion"}
                             for c in ("identificacion", "contacto", "salud")])
    bajo = _atencion(els, fls, nombre="Pago a proveedores", finalidades=["Pagar a los proveedores"],
                     base_licitud="obligacion_legal", elementos=[_sel(els[0], ["identificacion"], ["clientes"])],
                     flujos=[_sel(fls[2])], plazos=[{"categoria": "identificacion", "plazo": 5, "unidad": "anios"}])
    fuentes = []
    for i, c in ((1, alto), (2, bajo)):
        d = A.derivados(c, els, fls)
        inst = V.instantanea(c, d)
        fuentes.append(I.FuenteActividad(i, c["nombre"], "vigente", 1, AHORA, AHORA, (), inst, V.huella(inst), AHORA,
                                         sistemas_ia=tuple(A.sistemas_ia_en(inst["mapa"], els))))
    return I.armar(fuentes, AHORA, "Clínica Demo SpA")


def test_pia_pre_llenada_con_las_actividades_de_alto_riesgo():
    inf = _registro_borradores()
    reg = BR.desde_informe(inf)
    assert [a.nombre for a in reg.para_pia()] == ["Atención de clientes con asistente"]
    md = G.generar_markdown(plantilla(TipoPlantilla.PIA), _ctx(), _identidad(), registro=reg,
                            ahora=datetime(2026, 11, 13, 9, 0))
    assert "Atención de clientes con asistente" in md and "Pago a proveedores" not in md
    assert "Responder consultas de los clientes" in md                   # finalidad del registro
    assert "Salud (sensible)" in md and "Ejecución de un contrato" in md       # datos y base de licitud
    assert "Estados Unidos" in md and "Proveedor de modelos" in md            # proveedor y ubicación
    assert "versión vigente 1" in md                                          # referencia al registro
    assert "Uso de inteligencia artificial" in md and "Gran volumen de personas" in md   # riesgos del registro
    assert "Por qué se recomienda" in md
    assert "[COMPLETAR: nombre del sistema o proyecto]" not in md
    assert G.sin_codigos_internos(md) and not re.search(r"\b(?:HU|T)-\d{2}\b", md)
    # elegir otras actividades
    md2 = G.generar_markdown(plantilla(TipoPlantilla.PIA), _ctx(), _identidad(), registro=reg.con_seleccion([2]))
    assert "Pago a proveedores" in md2 and "Atención de clientes con asistente" not in md2
    # sin registro la plantilla queda igual que antes
    base = G.generar_markdown(plantilla(TipoPlantilla.PIA), _ctx(), _identidad(), ahora=datetime(2026, 11, 13, 9, 0))
    assert "[COMPLETAR: nombre del sistema o proyecto]" in base


def test_aviso_de_privacidad_toma_finalidades_y_bases_del_registro():
    reg = BR.desde_informe(_registro_borradores())
    md = G.generar_markdown(plantilla(TipoPlantilla.AVISO_PRIVACIDAD), _ctx(), _identidad(), registro=reg)
    assert "Responder consultas de los clientes" in md and "Pagar a los proveedores" in md
    assert "Ejecución de un contrato" in md and "Cumplimiento de una obligación legal" in md
    assert "[COMPLETAR: finalidades concretas]" not in md
    assert "Estados Unidos" in md                                             # transferencias del registro
    assert "2 años" in md and "5 años" in md                                  # plazos de conservación
    # el aviso es para las personas: no muestra nombres internos de sistemas
    assert "CRM de clientes" not in md and "Asistente virtual" not in md
    assert G.sin_codigos_internos(md)
    # la política de uso de LLM no cambia con el registro
    pol = plantilla(TipoPlantilla.POLITICA_LLM)
    assert G.generar_markdown(pol, _ctx(), _identidad(), registro=reg, ahora=AHORA) == \
        G.generar_markdown(pol, _ctx(), _identidad(), ahora=AHORA)


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
        pytest.skip("HU-38: solo en proceso")
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
    monkeypatch.setattr(settings, "BORRADORES_IA_HABILITADA", False)     # los borradores se arman sin el LLM
    limitador = LimitadorMemoria()
    app.dependency_overrides[obtener_limitador] = lambda: limitador
    yield m
    app.dependency_overrides.pop(obtener_limitador, None)


async def _aprobar(c, h, a) -> dict:
    a = (await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                      json={"revision": a["revision"], "accion": "enviar_revision"})).json()["actividad"]
    r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                     json={"revision": a["revision"], "accion": "aprobar"})
    assert r.status_code == 200, r.text
    return r.json()


async def _estados(hu27, ev_id) -> dict:
    from sqlalchemy import select

    from app.domain.models.matriz_control import MatrizControl
    from app.domain.models.respuesta import Respuesta

    async def f(s):
        filas = (await s.execute(select(Respuesta, MatrizControl.codigo_control)
                                 .join(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
                                 .where(Respuesta.evaluacion_id == ev_id))).all()
        return {cod: (r.estado_clasificacion_final or r.estado_clasificacion, r.fuente_clasificacion,
                      r.catalogo_brechas_id_brecha) for r, cod in filas}
    return await hu27._bd(f)


@api
def test_api_registro_vigente_y_completo_mejora_la_evaluacion_sin_bajar_controles(hu27):
    import test_hu35_rat as hu35

    async def esc(c):
        from app.domain.models import BitacoraAuditoria, Evidencia

        x = await hu35._cliente(hu27, c)
        h, ev = x["hc"], x["ev"]
        base = "/api/registro-actividades/cumplimiento"
        r = await c.get(base, headers=h)
        assert r.status_code == 200, r.text
        vacio = r.json()
        assert vacio["mapa"]["iniciado"] is False and vacio["registro"]["activas"] == 0
        assert vacio["evidencia"]["evaluacion_id"] == ev and not vacio["evidencia"]["aplicable"]
        assert vacio["evidencia"]["faltantes"] and vacio["brechas"] == []
        r = await c.post(f"{base}/evidencia", headers=h)
        assert r.status_code == 200 and r.json()["aplicado"] is False and r.json()["motivo"] == "registro_incompleto"

        antes = await _estados(hu27, ev)
        assert antes["DAT-001"][0] == "cumplido" and antes["DAT-005"][0] == "no_cumplido"
        assert antes["DAT-003"][0] == "no_cumplido" and antes["DAT-005"][2] is not None
        puntaje_antes = (await c.get(f"/api/remediacion/evaluaciones/{ev}", headers=h)).json()["puntaje_general"]

        # registro: una actividad completa que cubre el único envío del mapa
        m = await hu35._mapa_api(c, h)
        a = (await c.post("/api/registro-actividades/actividades", headers=h,
                          json={"nombre": "Pago de remuneraciones"})).json()["actividad"]
        a = (await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                           json={"revision": a["revision"], **hu35._completa(m), "volumen": "hasta_mil"})).json()["actividad"]
        assert a["contenido"]["volumen"] == "hasta_mil" and a["riesgo"]["nivel"]
        lista = (await c.get("/api/registro-actividades", headers=h)).json()
        assert lista["actividades"][0]["riesgo"]["nivel"] and lista["riesgos"]["mayor_riesgo"] >= 0
        assert lista["riesgos"]["referencia"].startswith("Decreto 662")

        # C3: al dejarla vigente el registro cuenta como evidencia (automático)
        res = await _aprobar(c, h, a)
        evid = res["evidencia"]
        assert evid and evid["aplicado"] is True, res
        assert evid["puntaje_resultante"] > evid["puntaje_previo"]
        despues = await _estados(hu27, ev)
        assert despues["DAT-005"][:2] == ("cumplido", "rat") and despues["DAT-005"][2] is None   # brecha cerrada
        assert despues["DAT-003"][:2] == ("parcialmente_cumplido", "rat")
        assert despues["DAT-001"] == antes["DAT-001"]          # ya estaba cumplido: no se toca
        for cod in ("DAT-004", "DAT-006", "DAT-010"):
            assert despues[cod] == antes[cod]                  # el registro no los respalda

        # igual que una remediación: evidencia (sin archivo), evolución del puntaje y bitácora
        filas = await hu35._filas(hu27, Evidencia, Evidencia.origen == "rat")
        assert len(filas) == 2 and all(e.storage_path == "" and e.estado_validacion == "validated" for e in filas)
        assert all(e.puntaje_resultante is not None and e.puntaje_previo is not None for e in filas)
        rem = (await c.get(f"/api/remediacion/evaluaciones/{ev}", headers=h)).json()
        assert rem["puntaje_general"] > puntaje_antes and rem["controles_mejorados"] >= 2
        assert any(x["estado_resultante"] == "cumplido" for x in rem["evolucion"])
        parcial = next(x for x in rem["controles"] if x["ultima_evidencia"] and x["ultima_evidencia"]["origen"] == "rat")
        assert parcial["estado"] == "parcialmente_cumplido"
        bit = [b for b in await hu35._filas(hu27, BitacoraAuditoria) if b.accion == "rat.evidencia_aplicada"]
        assert len(bit) == 1 and bit[0].detalle["origen"] == "aprobacion"
        assert "remuneraciones" not in str(bit[0].detalle).lower()
        # Mis documentos no la lista como un archivo
        docs = (await c.get("/api/cliente/documentos", headers=h)).json()
        assert not any("Registro de actividades" in (e.get("nombre_archivo") or e.get("nombre") or "")
                       for e in docs.get("evidencias", []))

        # aplicar de nuevo no repite ni baja nada
        r = await c.post(f"{base}/evidencia", headers=h)
        assert r.status_code == 200 and r.json()["aplicado"] is False and r.json()["motivo"] == "sin_mejoras"
        assert await _estados(hu27, ev) == despues
        assert len(await hu35._filas(hu27, Evidencia, Evidencia.origen == "rat")) == 2

        # C4: el espacio de la empresa ve el registro vigente y completo y lo que aporta
        est = (await c.get(base, headers=h)).json()
        assert est["mapa"]["iniciado"] and est["mapa"]["flujos_sin_actividad"] == 0
        assert est["registro"]["vigente_completo"] and est["registro"]["completitud"] == 100
        assert est["evidencia"]["aplicable"] and est["evidencia"]["por_mejorar"] == 0
        assert any(x["respaldado_por_registro"] for x in est["evidencia"]["controles"])
        assert est["brechas"] == []
        assert not CODIGO_INTERNO.search(str(est))
    hu35._correr(esc)


@api
def test_api_brechas_del_registro_con_su_ruta_de_remediacion(hu27):
    import test_hu35_rat as hu35

    async def esc(c):
        x = await hu35._cliente(hu27, c)
        h, ev = x["hc"], x["ev"]
        m = await hu35._mapa_api(c, h)
        completa = hu35._completa(m)
        a = (await c.post("/api/registro-actividades/actividades", headers=h,
                          json={"nombre": "Pago de remuneraciones"})).json()["actividad"]
        sin = {k: v for k, v in completa.items() if k not in ("base_licitud", "base_sensibles", "plazos", "flujos")}
        r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                          json={"revision": a["revision"], **sin})
        assert r.status_code == 200, r.text
        est = (await c.get("/api/registro-actividades/cumplimiento", headers=h)).json()
        por = {b["codigo"]: b for b in est["brechas"]}
        assert {"sin_base_licitud", "sin_plazo", "flujo_sin_actividad"} <= set(por)
        assert por["sin_base_licitud"]["severidad"] == "Crítica"          # usa datos de salud (sensibles)
        assert por["sin_base_licitud"]["actividad"]["id"] == a["id"] and por["sin_base_licitud"]["paso"] == 3
        # ruta de remediación: el control de la evaluación y, si el catálogo lo tiene, su módulo formativo
        rem = por["sin_plazo"]["remediacion"]
        assert rem["evaluacion_id"] == ev and rem["respuesta_id"] and rem["abierta"] is True
        assert "obligacion" in por["sin_plazo"]
        for b in est["brechas"]:
            assert "control" not in b
            if b["ruta"]:
                assert b["ruta"]["id"] and b["ruta"]["nombre"] and b["ruta"]["estado"] in (
                    "no_iniciado", "en_curso", "completado")
        assert not est["registro"]["vigente_completo"] and est["registro"]["faltantes"]
        assert not CODIGO_INTERNO.search(str(est))
    hu35._correr(esc)


@api
def test_api_borradores_pia_y_aviso_desde_el_registro(hu27):
    import test_hu35_rat as hu35

    async def esc(c):
        x = await hu35._cliente(hu27, c)
        h = x["hc"]
        m = await hu35._mapa_api(c, h)
        a = (await c.post("/api/registro-actividades/actividades", headers=h,
                          json={"nombre": "Pago de remuneraciones"})).json()["actividad"]
        a = (await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                           json={"revision": a["revision"], **hu35._completa(m), "volumen": "mas_100_mil"})).json()["actividad"]
        assert a["riesgo"]["requiere_pia"]                                      # salud a gran escala
        await _aprobar(c, h, a)

        cat_b = (await c.get("/api/borradores/plantillas", headers=h)).json()
        assert cat_b["registro"]["pia"][0]["actividad_id"] == a["id"]
        r = await c.post("/api/borradores", headers=h, json={"tipo": "pia", "usar_ia": False})
        assert r.status_code == 201, r.text
        md = r.json()["borrador"]["contenido"]
        assert "Pago de remuneraciones" in md and "Pagar las remuneraciones del personal" in md
        assert r.json()["registro"]["actividades"] == 1 and "registro_aplicado" in r.json()["borrador"]["advertencias"]
        r = await c.post("/api/borradores", headers=h, json={"tipo": "aviso_privacidad", "usar_ia": False})
        md = r.json()["borrador"]["contenido"]
        assert "Pagar las remuneraciones del personal" in md and "Ejecución de un contrato" in md
        # actividades elegidas: solo las de la empresa
        r = await c.post("/api/borradores", headers=h, json={"tipo": "pia", "usar_ia": False, "actividades": [99999]})
        assert r.status_code == 422 and hu27._codigo(r) == "ACTIVIDADES_INVALIDAS"
    hu35._correr(esc)


@api
def test_api_cumplimiento_solo_con_contrato_y_aislado_por_empresa(hu27, monkeypatch):
    import test_hu35_rat as hu35

    async def esc(c):
        x = await hu35._cliente(hu27, c)
        h = x["hc"]
        assert (await c.get("/api/registro-actividades/cumplimiento")).status_code == 401
        r = await c.get("/api/registro-actividades/cumplimiento", headers=hu27.admin())
        assert r.status_code == 403 and hu27._codigo(r) == "NO_AUTORIZADO"
        r = await c.post("/api/registro-actividades/cumplimiento/evidencia", headers=x["h"])   # usuario temporal
        assert r.status_code in (401, 403)

        import app.core.servicio_pagado as sp
        monkeypatch.setattr(sp, "servicio_habilitado", lambda empresa, hoy=None: False)
        for metodo, ruta in (("get", "/api/registro-actividades/cumplimiento"),
                             ("post", "/api/registro-actividades/cumplimiento/evidencia")):
            r = await getattr(c, metodo)(ruta, headers=h)
            assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE", ruta
    hu35._correr(esc)


@api
def test_api_el_registro_nunca_baja_un_control_ya_mejor(hu27):
    import test_hu35_rat as hu35

    async def esc(c):
        from sqlalchemy import select

        from app.domain.models import Evidencia
        from app.domain.models.matriz_control import MatrizControl
        from app.domain.models.respuesta import Respuesta

        x = await hu35._cliente(hu27, c)
        h, ev = x["hc"], x["ev"]

        async def subir(s):
            fila = (await s.execute(select(Respuesta).join(
                MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control).where(
                Respuesta.evaluacion_id == ev, MatrizControl.codigo_control == "DAT-003"))).scalar_one()
            fila.estado_clasificacion_final = "cumplido"
            fila.fuente_clasificacion = "revision"
            fila.catalogo_brechas_id_brecha = None
            await s.commit()
        await hu27._bd(subir)

        m = await hu35._mapa_api(c, h)
        a = (await c.post("/api/registro-actividades/actividades", headers=h,
                          json={"nombre": "Pago de remuneraciones"})).json()["actividad"]
        a = (await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                           json={"revision": a["revision"], **hu35._completa(m)})).json()["actividad"]
        res = await _aprobar(c, h, a)
        assert res["evidencia"]["aplicado"] is True
        despues = await _estados(hu27, ev)
        assert despues["DAT-003"][:2] == ("cumplido", "revision")       # el registro aporta "parcial": no lo baja
        assert despues["DAT-005"][:2] == ("cumplido", "rat")
        filas = await hu35._filas(hu27, Evidencia, Evidencia.origen == "rat")
        assert len(filas) == 1
    hu35._correr(esc)
