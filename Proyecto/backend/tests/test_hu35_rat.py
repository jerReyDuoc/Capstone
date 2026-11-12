"""
QA - HU-35: registro de actividades de tratamiento (RAT) del cliente.

  C1  Cada actividad registra los 11 campos mínimos del reglamento, las medidas de seguridad y el
      rol de la empresa (responsable o encargado).
  C2  Sistemas, bases y flujos se eligen del mapa (HU-34) y no se ingresan dos veces; un cambio en el
      mapa devuelve a revisión las actividades afectadas.
  C3  Completitud por actividad y global; no queda vigente con campos obligatorios vacíos.
  C4  Estados borrador → en revisión → vigente → archivada; la versión vigente es inmutable y cada
      cambio queda en el audit_log.

Parte 1: lógica pura (catálogo, validación, lo que se toma del mapa, completitud, estados, versiones y
vínculo con el mapa). Corre sin BD.
Parte 2: API en proceso (SQLite), reutiliza la preparación de test_hu27_empresa_cliente.py; necesita
FastAPI, SQLAlchemy y aiosqlite (Docker).
"""
import asyncio
import copy
import re

import pytest

from app.application.mapa_datos import plantillas as P
from app.domain.mapa_datos.modelo import ErrorValidacion, Elemento, Flujo
from app.domain.mapa_datos import versiones as VM
from app.domain.rat import analisis as A
from app.domain.rat import catalogo as cat
from app.domain.rat import estados as E
from app.domain.rat import modelo as M
from app.domain.rat import versiones as V
from app.domain.rat import vinculo_mapa as VIN

CODIGO_INTERNO = re.compile(r"\b(?:HU|T)-\d{2}\b|\bF[1-7]\b|\b(?:DAT|GOB|RIE|SEG)-\d{3}\b|\bRAT-\d")


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


def _flujo_id(fls, ids, origen, destino):
    return next(f.id for f in fls if f.origen_id == ids[origen] and f.destino_id == ids[destino])


def _remuneraciones(els, fls, ids, sin_salud=False) -> dict:
    """Actividad completa: pago de remuneraciones (RR.HH. → banco)."""
    rrhh = next(e for e in els if e.id == ids["comun_rrhh"])
    datos = [c for c in rrhh.categorias_datos if not (sin_salud and c == "salud")]
    return M.normalizar({
        "nombre": "Pago de remuneraciones",
        "area": "Gerencia de Personas",
        "finalidades": ["Calcular y pagar las remuneraciones del personal"],
        "rol": "responsable",
        "elementos": [{"id": rrhh.id, "categorias_datos": datos, "categorias_titulares": ["trabajadores"]}],
        "flujos": [{"id": _flujo_id(fls, ids, "comun_rrhh", "comun_banco"), "categorias_datos": ["identificacion",
                    "financieros"], "categorias_titulares": ["trabajadores"]}],
        "fuentes": [{"tipo": "titular", "detalle": "Formulario de ingreso"}, {"tipo": "generados"}],
        "base_licitud": "contrato",
        "base_sensibles": None if sin_salud else "obligacion_laboral",
        "plazos": [{"categoria": c, "plazo": 6, "unidad": "anios", "desde": "termino_relacion"}
                   for c in datos],
        "decisiones": {"existe": False},
        "medidas": {"codigos": ["control_acceso", "cifrado_transito"]},
    })


# ===================================================================== C1: catálogo y campos
def test_campos_minimos_del_reglamento_mas_medidas_y_rol():
    codigos = [c.codigo for c in cat.CAMPOS]
    assert len(codigos) == len(set(codigos)) == 13
    reglamento = {"tipos_datos", "ambito", "bases_datos", "titulares", "finalidades", "fuentes", "base_licitud",
                  "destinatarios", "transferencias", "conservacion", "decisiones"}
    assert reglamento | {"medidas", "rol"} == set(codigos)
    # Lo que viene del mapa no se ingresa en el formulario
    assert {c.codigo for c in cat.CAMPOS if c.desde_mapa} == {"tipos_datos", "ambito", "bases_datos", "titulares",
                                                             "destinatarios", "transferencias"}
    assert {c.paso for c in cat.CAMPOS} == {n for n, _, _ in cat.PASOS} == set(range(1, 7))


def test_catalogo_es_propuesta_legal_y_sin_codigos_internos():
    d = cat.catalogo_dict()
    assert d["revision_legal"]["estado"] == "pendiente_validacion_legal" and d["aviso"]
    assert {"consentimiento", "contrato", "obligacion_legal", "interes_legitimo"} <= {b["codigo"] for b in d["bases_licitud"]}
    assert all(b.get("descripcion") and b.get("referencia") for b in d["bases_licitud"] + d["bases_sensibles"])
    assert {r["codigo"] for r in d["roles_empresa"]} == {"responsable", "encargado"}
    assert any(f.get("acceso_publico") for f in d["fuentes"])
    assert {e["codigo"] for e in d["estados"]} == {"borrador", "en_revision", "vigente", "archivada"}
    for grupo in ("bases_licitud", "bases_sensibles", "fuentes", "medidas_seguridad", "unidades_plazo", "inicios_plazo",
                  "estados", "roles_empresa"):
        codigos = [x["codigo"] for x in d[grupo]]
        assert len(codigos) == len(set(codigos)), grupo
    assert not CODIGO_INTERNO.search(str(d))
    assert "RAT" not in str({k: v for k, v in d.items() if k != "version_textos"})


# ===================================================================== validación
def test_crear_exige_nombre_y_normaliza():
    with pytest.raises(ErrorValidacion) as e:
        M.normalizar({"finalidades": ["Atender reclamos de clientes"]})
    assert e.value.campo == "nombre"
    c = M.normalizar({"nombre": "  Atención   de reclamos ", "finalidades": ["Responder reclamos", "responder RECLAMOS"]})
    assert c["nombre"] == "Atención de reclamos" and c["finalidades"] == ["Responder reclamos"]
    assert set(M.contenido_vacio()) == set(c)


@pytest.mark.parametrize("datos, campo", [
    ({"nombre": "Ventas", "campo_raro": 1}, "campo_raro"),
    ({"nombre": "Ventas", "area": "Ana Pérez ana@acme.cl"}, "area"),
    ({"nombre": "Ventas", "finalidades": ["Llamar al +56 9 8765 4321"]}, "finalidades"),
    ({"nombre": "Ventas", "base_licitud": "porque_si"}, "base_licitud"),
    ({"nombre": "Ventas", "rol": "dueno"}, "rol"),
    ({"nombre": "Ventas", "fuentes": [{"tipo": "otro"}]}, "fuentes"),
    ({"nombre": "Ventas", "plazos": [{"categoria": "contacto", "plazo": 0, "unidad": "anios"}]}, "plazos"),
    ({"nombre": "Ventas", "plazos": [{"categoria": "contacto", "plazo": 500, "unidad": "anios"}]}, "plazos"),
    ({"nombre": "Ventas", "plazos": [{"categoria": "inventada", "plazo": 1, "unidad": "anios"}]}, "plazos"),
    ({"nombre": "Ventas", "elementos": [{"id": 0}]}, "elementos"),
    ({"nombre": "Ventas", "elementos": [{"id": 1, "categorias_datos": ["inventada"]}]}, "elementos"),
    ({"nombre": "Ventas", "medidas": {"codigos": ["magia"]}}, "medidas"),
    ({"nombre": "Ventas", "decisiones": {"existe": "quizas"}}, "decisiones"),
    ({"nombre": "x" * 151}, "nombre"),
])
def test_validacion_responde_el_campo(datos, campo):
    with pytest.raises(ErrorValidacion) as e:
        M.normalizar(datos)
    assert e.value.campo == campo and e.value.mensaje and not CODIGO_INTERNO.search(e.value.mensaje)


def test_edicion_parcial_y_coherencia_de_condicionales():
    base = M.normalizar({"nombre": "Marketing", "base_licitud": "interes_legitimo",
                         "interes_legitimo": "Enviar ofertas a clientes actuales con productos similares.",
                         "rol": "encargado", "responsable_mandante": "Empresa matriz",
                         "decisiones": {"existe": True, "logica": "Segmentación por historial de compras",
                                        "perfilamiento": True}})
    c = M.normalizar({"base_licitud": "consentimiento", "rol": "responsable", "decisiones": {"existe": False}}, base)
    assert c["interes_legitimo"] is None and c["responsable_mandante"] is None
    assert c["decisiones"] == {"existe": False, "perfilamiento": False, "logica": None, "consecuencias": None,
                               "intervencion_humana": None}
    assert c["nombre"] == "Marketing"
    assert set(M.campos_cambiados(base, c)) == {"base_licitud", "interes_legitimo", "decisiones", "rol",
                                                "responsable_mandante"}
    # El texto multilínea conserva los saltos de párrafo
    d = M.normalizar({"descripcion": "Primera línea\n\n\n\nSegunda   línea"}, base)
    assert d["descripcion"] == "Primera línea\n\nSegunda línea"


# ===================================================================== C2: lo que viene del mapa
def test_derivados_desde_el_mapa_con_el_subconjunto_elegido():
    els, fls, ids = _mapa()
    c = _remuneraciones(els, fls, ids)
    d = A.derivados(c, els, fls)
    assert [x["nombre"] for x in d["bases_datos"]] == ["Sistema de remuneraciones y RR.HH."]
    assert d["tipos_datos"][0]["codigo"] == "salud" and d["tipos_datos"][0]["sensible"] and d["hay_sensibles"]
    assert [t["nombre"] for t in d["terceros"]] == ["Banco para el pago de remuneraciones"]
    assert [p["codigo"] for p in d["paises"]] == ["CL"] and d["transferencias"] == []
    assert [t["codigo"] for t in d["titulares"]] == ["trabajadores"]
    # Elegir un subconjunto: sin salud no hay sensibles
    d2 = A.derivados(_remuneraciones(els, fls, ids, sin_salud=True), els, fls)
    assert not d2["hay_sensibles"] and "salud" not in {t["codigo"] for t in d2["tipos_datos"]}
    # Si el mapa quita una categoría al elemento, deja de contarse
    els2 = copy.deepcopy(els)
    next(e for e in els2 if e.id == ids["comun_rrhh"]).categorias_datos.remove("salud")
    assert not A.derivados(c, els2, fls)["hay_sensibles"]


def test_transferencia_internacional_requiere_garantia_registrada_en_el_mapa():
    els, fls, ids = _mapa()
    f = _flujo_id(fls, ids, "retail_bd_clientes", "retail_crm")      # CL → US
    c = M.normalizar({"nombre": "Fidelización", "elementos": [{"id": ids["retail_crm"],
                                                              "categorias_datos": ["contacto", "perfilamiento"],
                                                              "categorias_titulares": ["clientes"]}],
                      "flujos": [{"id": f, "categorias_datos": ["contacto"], "categorias_titulares": ["clientes"]}]})
    d = A.derivados(c, els, fls)
    assert len(d["transferencias"]) == 1 and d["transferencias"][0]["pais_destino"] == "US"
    assert not A.completitud(c, d)["campos"]["transferencias"]["completo"]
    fls2 = copy.deepcopy(fls)
    next(x for x in fls2 if x.id == f).garantia = "clausulas_contractuales"
    d2 = A.derivados(c, els, fls2)
    assert A.completitud(c, d2)["campos"]["transferencias"]["completo"]


# ===================================================================== C3: completitud
def test_actividad_vacia_y_completa():
    els, fls, ids = _mapa()
    vacia = M.normalizar({"nombre": "Nueva actividad"})
    r = A.completitud(vacia, A.derivados(vacia, els, fls))
    assert r["porcentaje"] == 0 and r["total"] == 13 and not r["puede_quedar_vigente"]
    assert len(r["faltantes"]) == 13 and all(f["mensaje"] for f in r["faltantes"])
    c = _remuneraciones(els, fls, ids)
    r = A.completitud(c, A.derivados(c, els, fls))
    assert r["porcentaje"] == 100 and r["puede_quedar_vigente"], r["faltantes"]
    assert not r["campos"]["transferencias"]["aplica"] and not r["campos"]["decisiones"]["aplica"]
    assert any("contrato" in a for a in r["advertencias"])          # el banco es encargado sin contrato marcado


@pytest.mark.parametrize("cambio, campo", [
    ({"base_licitud": "interes_legitimo"}, "base_licitud"),           # falta describir el interés legítimo
    ({"base_sensibles": None}, "base_licitud"),                       # hay datos sensibles
    ({"rol": "encargado"}, "rol"),                                    # falta por cuenta de quién
    ({"decisiones": {"existe": True}}, "decisiones"),                 # falta la lógica
    ({"decisiones": {"existe": None}}, "decisiones"),
    ({"medidas": {"codigos": []}}, "medidas"),
    ({"fuentes": []}, "fuentes"),
    ({"finalidades": []}, "finalidades"),
    ({"plazos": []}, "conservacion"),
    ({"flujos": [], "sin_destinatarios": False}, "destinatarios"),
])
def test_campos_condicionales_y_obligatorios(cambio, campo):
    els, fls, ids = _mapa()
    c = M.normalizar(cambio, _remuneraciones(els, fls, ids))
    r = A.completitud(c, A.derivados(c, els, fls))
    assert not r["campos"][campo]["completo"] and not r["puede_quedar_vigente"]
    assert not CODIGO_INTERNO.search(r["campos"][campo]["faltante"])


def test_no_aplica_se_responde_de_forma_explicita():
    els, fls, ids = _mapa()
    c = M.normalizar({"flujos": [], "sin_destinatarios": True}, _remuneraciones(els, fls, ids))
    r = A.completitud(c, A.derivados(c, els, fls))
    assert r["campos"]["destinatarios"]["completo"]


def test_lo_elegido_que_el_mapa_elimino_bloquea_la_vigencia():
    els, fls, ids = _mapa()
    c = _remuneraciones(els, fls, ids)
    sin_rrhh = [e for e in els if e.id != ids["comun_rrhh"]]
    d = A.derivados(c, sin_rrhh, fls)
    assert {"tipo": "elemento", "id": ids["comun_rrhh"]} in d["no_encontrados"]
    assert not A.completitud(c, d)["puede_quedar_vigente"]


def test_completitud_global():
    assert A.completitud_global([]) == {"porcentaje": 0, "actividades": 0, "completas": 0}
    assert A.completitud_global([100, 50, 0]) == {"porcentaje": 50, "actividades": 3, "completas": 1}


# ===================================================================== C4: estados
def test_ciclo_de_estados_y_decisiones_del_po():
    assert E.destino("enviar_revision", "borrador") == "en_revision"
    assert E.destino("aprobar", "en_revision") == "vigente"
    assert E.destino("volver_borrador", "en_revision") == "borrador"
    assert E.destino("nueva_version", "vigente") == "borrador"
    for estado in ("borrador", "en_revision", "vigente"):
        assert E.destino("archivar", estado) == "archivada"
    # Reactivar sin duplicar: a borrador si nunca estuvo vigente, si no a revisión
    assert E.destino("reactivar", "archivada", "borrador") == "borrador"
    assert E.destino("reactivar", "archivada", "vigente", tuvo_vigente=True) == "en_revision"
    assert E.destino("reactivar", "archivada", "borrador", tuvo_vigente=True) == "en_revision"
    # Un cambio en el mapa devuelve la vigente a revisión
    assert E.tras_cambio_en_mapa("vigente") == "en_revision"
    assert E.tras_cambio_en_mapa("borrador") == "borrador"
    for accion, estado in (("aprobar", "borrador"), ("nueva_version", "en_revision"), ("archivar", "archivada"),
                           ("reactivar", "vigente"), ("inventada", "borrador")):
        with pytest.raises(E.TransicionInvalida) as e:
            E.destino(accion, estado)
        assert e.value.mensaje and not CODIGO_INTERNO.search(e.value.mensaje)
    assert E.acciones_disponibles("vigente") == ["nueva_version", "archivar"]
    assert "vigente" not in E.EDITABLES and "archivada" not in E.EDITABLES


def test_versiones_huella_y_diferencias():
    els, fls, ids = _mapa()
    c = _remuneraciones(els, fls, ids)
    i1 = V.instantanea(c, A.derivados(c, els, fls))
    assert V.huella(i1) == V.huella(copy.deepcopy(i1)) and len(V.huella(i1)) == 64
    assert V.diferencias(None, i1) == []
    # Cambia el nombre de un sistema en el mapa: cambia la huella y se ve qué campo cambió
    els2 = copy.deepcopy(els)
    next(e for e in els2 if e.id == ids["comun_rrhh"]).nombre = "Buk RR.HH."
    i2 = V.instantanea(c, A.derivados(c, els2, fls))
    assert V.huella(i2) != V.huella(i1) and "bases_datos" in V.diferencias(i1, i2)
    c3 = M.normalizar({"finalidades": ["Pagar remuneraciones", "Emitir certificados laborales"]}, c)
    i3 = V.instantanea(c3, A.derivados(c3, els, fls))
    assert V.diferencias(i1, i3) == ["finalidades"]
    assert V.describir(["finalidades"]) == "Cambió: Finalidades."
    assert V.describir(["finalidades", "medidas"]).startswith("Cambiaron: Finalidades y medidas")
    # La instantánea no guarda las listas de "disponibles" del mapa (no son parte del registro)
    assert "disponibles_datos" not in str(i1["mapa"])


# ===================================================================== C2: vínculo con el mapa
def test_cambios_del_mapa_que_afectan_a_una_actividad():
    els, fls, ids = _mapa()
    c = _remuneraciones(els, fls, ids)
    acts = [{"id": 1, "contenido": c}, {"id": 2, "contenido": M.normalizar({"nombre": "Otra"})}]
    inst = VM.instantanea(els, fls)

    def cambio(entidad, op, id_, campos=(), nombre="X", tipo="sistema"):
        return {"entidad": entidad, "operacion": op, "id": id_, "nombre": nombre, "tipo": tipo, "campos": list(campos)}

    rrhh = ids["comun_rrhh"]
    r = VIN.afectadas(acts, [cambio("elemento", "editado", rrhh, ["pais"], "RR.HH.")], inst, inst)
    assert list(r) == [1] and "país" in r[1][0] and "«RR.HH.»" in r[1][0]
    # Solo la marca "por confirmar" no afecta; lo nuevo tampoco
    assert VIN.afectadas(acts, [cambio("elemento", "editado", rrhh, ["pendiente_revision"])], inst, inst) == {}
    assert VIN.afectadas(acts, [cambio("elemento", "creado", 999)], inst, inst) == {}
    # Cambia el banco (extremo del flujo elegido, aunque no se eligió directamente)
    banco = ids["comun_banco"]
    r = VIN.afectadas(acts, [cambio("elemento", "eliminado", banco, nombre="Banco", tipo="tercero")], inst, inst)
    assert list(r) == [1] and r[1][0].startswith("Se eliminó del mapa el tercero")
    # Un flujo que no eligió no la afecta
    otro = _flujo_id(fls, ids, "retail_erp", "retail_courier")
    assert VIN.afectadas(acts, [cambio("flujo", "editado", otro, ["finalidad"])], inst, inst) == {}


def test_textos_de_ayuda_amigables():
    for c in cat.CAMPOS:
        assert c.ayuda and not CODIGO_INTERNO.search(c.ayuda) and "RAT" not in c.ayuda, c.codigo
    for e in cat.ESTADOS:
        assert e.descripcion and not CODIGO_INTERNO.search(e.descripcion)


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
        pytest.skip("HU-35: solo en proceso")
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


async def _mapa_api(c, h) -> dict:
    """Mapa mínimo: sistema de RR.HH. (CL), banco (encargado) y el flujo entre ambos."""
    r = await c.post("/api/mapa-datos/elementos", headers=h, json={
        "version": 0, "tipo": "sistema", "subtipo": "rrhh", "nombre": "Sistema de remuneraciones", "pais": "CL",
        "categorias_datos": ["identificacion", "financieros", "salud"], "categorias_titulares": ["trabajadores"]})
    assert r.status_code == 201, r.text
    rrhh = r.json()["elementos"][0]
    r = await c.post("/api/mapa-datos/elementos", headers=h, json={
        "version": 1, "tipo": "tercero", "subtipo": "pagos", "nombre": "Banco pagador", "pais": "CL",
        "rol_tercero": "encargado", "contrato_firmado": True, "categorias_datos": ["identificacion", "financieros"],
        "categorias_titulares": ["trabajadores"]})
    banco = next(e for e in r.json()["elementos"] if e["tipo"] == "tercero")
    r = await c.post("/api/mapa-datos/flujos", headers=h, json={
        "version": 2, "origen_id": rrhh["id"], "destino_id": banco["id"], "finalidad": "Pago de sueldos",
        "categorias_datos": ["identificacion", "financieros"], "categorias_titulares": ["trabajadores"]})
    assert r.status_code == 201, r.text
    return {"rrhh": rrhh, "banco": banco, "flujo": r.json()["flujos"][0], "version": 3}


def _completa(m: dict) -> dict:
    return {
        "finalidades": ["Pagar las remuneraciones del personal"], "rol": "responsable",
        "elementos": [{"id": m["rrhh"]["id"], "categorias_datos": ["identificacion", "financieros", "salud"],
                       "categorias_titulares": ["trabajadores"]}],
        "flujos": [{"id": m["flujo"]["id"], "categorias_datos": ["identificacion", "financieros"],
                    "categorias_titulares": ["trabajadores"]}],
        "fuentes": [{"tipo": "titular"}], "base_licitud": "contrato", "base_sensibles": "obligacion_laboral",
        "plazos": [{"categoria": x, "plazo": 6, "unidad": "anios", "desde": "termino_relacion"}
                   for x in ("identificacion", "financieros", "salud")],
        "decisiones": {"existe": False}, "medidas": {"codigos": ["control_acceso"]},
    }


@api
def test_api_solo_usuario_definitivo_con_contrato_vigente(hu27, monkeypatch):
    async def esc(c):
        x = await _cliente(hu27, c)
        assert (await c.get("/api/registro-actividades")).status_code == 401
        r = await c.get("/api/registro-actividades", headers=hu27.admin())
        assert r.status_code == 403 and hu27._codigo(r) == "NO_AUTORIZADO"
        import app.core.servicio_pagado as sp
        monkeypatch.setattr(sp, "servicio_habilitado", lambda empresa, hoy=None: False)
        for metodo, ruta, kw in (("get", "/api/registro-actividades", {}),
                                 ("get", "/api/registro-actividades/catalogo", {}),
                                 ("post", "/api/registro-actividades/actividades", {"json": {"nombre": "Ventas"}})):
            r = await getattr(c, metodo)(ruta, headers=x["hc"], **kw)
            assert r.status_code == 403 and hu27._codigo(r) == "CONTRATO_NO_VIGENTE", ruta
    _correr(esc)


@api
def test_api_ciclo_completo_versiones_inmutables_y_audit_log(hu27):
    async def esc(c):
        from app.domain.models import BitacoraAuditoria, RatActividad, RatActividadVersion

        x = await _cliente(hu27, c)
        h = x["hc"]
        cat_api = (await c.get("/api/registro-actividades/catalogo", headers=h)).json()
        assert len(cat_api["campos"]) == 13 and cat_api["revision_legal"]["estado"]
        vacio = (await c.get("/api/registro-actividades", headers=h)).json()
        assert vacio["actividades"] == [] and vacio["global"]["porcentaje"] == 0
        m = await _mapa_api(c, h)

        # crear (borrador) y completitud parcial
        r = await c.post("/api/registro-actividades/actividades", headers=h, json={"nombre": "Pago de remuneraciones"})
        assert r.status_code == 201, r.text
        a = r.json()["actividad"]
        assert a["estado"] == "borrador" and a["revision"] == 1 and a["completitud"]["porcentaje"] == 0
        r = await c.post("/api/registro-actividades/actividades", headers=h, json={"nombre": "pago de REMUNERACIONES"})
        assert r.status_code == 409 and hu27._codigo(r) == "NOMBRE_DUPLICADO"
        # un elemento que no existe en el mapa no se puede elegir
        r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                          json={"revision": 1, "elementos": [{"id": 9999}]})
        assert r.status_code == 422 and r.json()["detail"]["campo"] == "elementos"
        # minimización
        r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                          json={"revision": 1, "area": "ana@acme.cl"})
        assert r.status_code == 422 and r.json()["detail"]["campo"] == "area"

        # no pasa a vigente incompleta (C3)
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": 1, "accion": "enviar_revision"})
        assert r.status_code == 200 and r.json()["actividad"]["estado"] == "en_revision"
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": 2, "accion": "aprobar"})
        assert r.status_code == 422 and hu27._codigo(r) == "ACTIVIDAD_INCOMPLETA"
        # versión desactualizada
        r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                          json={"revision": 1, "finalidades": ["Pagar sueldos"]})
        assert r.status_code == 409 and hu27._codigo(r) == "ACTIVIDAD_DESACTUALIZADA"

        # completar (los datos del mapa se toman del mapa) y aprobar
        r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                          json={"revision": 2, **_completa(m)})
        assert r.status_code == 200, r.text
        a = r.json()["actividad"]
        assert a["completitud"]["porcentaje"] == 100 and a["derivados"]["hay_sensibles"]
        assert [t["nombre"] for t in a["derivados"]["terceros"]] == ["Banco pagador"]
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": "aprobar"})
        assert r.status_code == 200, r.text
        a = r.json()["actividad"]
        assert a["estado"] == "vigente" and a["version_vigente"] == 1 and r.json()["version_creada"] == 1

        # vigente: no se edita (hay que abrir una nueva versión)
        r = await c.patch(f"/api/registro-actividades/actividades/{a['id']}", headers=h,
                          json={"revision": a["revision"], "finalidades": ["Otra finalidad distinta"]})
        assert r.status_code == 409 and hu27._codigo(r) == "ACTIVIDAD_NO_EDITABLE"

        # C2: un cambio en el mapa la devuelve a revisión, en la misma transacción
        r = await c.patch(f"/api/mapa-datos/elementos/{m['banco']['id']}", headers=h,
                          json={"version": m["version"], "pais": "US"})
        assert r.status_code == 200 and r.json()["cambio"]["actividades_afectadas"] == 1
        a = (await c.get(f"/api/registro-actividades/actividades/{a['id']}", headers=h)).json()["actividad"]
        assert a["estado"] == "en_revision" and a["motivos_revision"] and a["version_vigente"] == 1
        assert "Banco pagador" in a["motivos_revision"][0]["texto"]
        # ahora hay una transferencia internacional sin garantía: no puede quedar vigente
        assert not a["completitud"]["campos"]["transferencias"]["completo"]
        r = await c.patch(f"/api/mapa-datos/flujos/{m['flujo']['id']}", headers=h,
                          json={"version": m["version"] + 1, "garantia": "clausulas_contractuales"})
        assert r.status_code == 200
        a = (await c.get(f"/api/registro-actividades/actividades/{a['id']}", headers=h)).json()["actividad"]
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": "aprobar"})
        assert r.status_code == 200, r.text
        assert r.json()["actividad"]["version_vigente"] == 2 and r.json()["actividad"]["motivos_revision"] == []
        a = r.json()["actividad"]

        # nueva versión: vuelve a borrador y la vigente sigue valiendo
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": "nueva_version"})
        a = r.json()["actividad"]
        assert a["estado"] == "borrador" and a["version_vigente"] == 2 and a["editable"]

        # archivar y reactivar sin duplicar
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": "archivar"})
        a = r.json()["actividad"]
        assert a["estado"] == "archivada"
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": "reactivar"})
        a = r.json()["actividad"]
        assert a["estado"] == "en_revision"
        # aprobar sin cambios no crea otra versión
        r = await c.post(f"/api/registro-actividades/actividades/{a['id']}/estado", headers=h,
                         json={"revision": a["revision"], "accion": "aprobar"})
        assert r.status_code == 200 and r.json()["version_creada"] is None
        assert r.json()["actividad"]["version_vigente"] == 2
        assert len(await _filas(hu27, RatActividad)) == 1

        # versiones e historial
        hist = (await c.get(f"/api/registro-actividades/actividades/{a['id']}/versiones", headers=h)).json()
        assert [v["numero"] for v in hist["versiones"]] == [2, 1]
        assert "transferencias" in {x["codigo"] for x in hist["versiones"][0]["cambios"]}
        v1 = (await c.get(f"/api/registro-actividades/actividades/{a['id']}/versiones/1", headers=h)).json()
        assert v1["verificada"] and not v1["es_la_vigente"]
        assert v1["contenido"]["mapa"]["transferencias"] == []        # lo que decía entonces
        from app.domain.rat.versiones import huella
        assert all(huella(v.contenido) == v.huella for v in await _filas(hu27, RatActividadVersion))

        # global
        lista = (await c.get("/api/registro-actividades", headers=h)).json()
        assert lista["global"]["porcentaje"] == 100 and lista["global"]["por_estado"]["vigente"] == 1

        # audit_log sin los textos de la empresa
        acciones = [b.accion for b in await _filas(hu27, BitacoraAuditoria)]
        for accion in ("rat.actividad_creada", "rat.actividad_editada", "rat.estado_cambiado", "rat.version_vigente",
                       "rat.marcada_revision", "rat.cambio_rechazado"):
            assert accion in acciones, accion
        for b in await _filas(hu27, BitacoraAuditoria):
            if b.accion.startswith("rat."):
                assert "remuneraciones" not in str(b.detalle).lower() and b.ip
    _correr(esc)


@api
def test_api_aislamiento_entre_empresas(hu27):
    async def esc(c):
        x = await _cliente(hu27, c)
        h = x["hc"]
        r = await c.post("/api/registro-actividades/actividades", headers=h, json={"nombre": "Ventas en línea"})
        a = r.json()["actividad"]
        # Otra sesión (un admin) no la ve; un id inexistente responde 404 sin revelar nada
        r = await c.get(f"/api/registro-actividades/actividades/{a['id'] + 1000}", headers=h)
        assert r.status_code == 404 and hu27._codigo(r) == "ACTIVIDAD_NO_ENCONTRADA"
        r = await c.get(f"/api/registro-actividades/actividades/{a['id']}", headers=hu27.admin())
        assert r.status_code == 403
    _correr(esc)
