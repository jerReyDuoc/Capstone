"""
QA - HU-24: el Administrador de Therion Labs edita controles, brechas, rutas y reglas de
aplicabilidad con versionado, sin modificar código.

  C1  CRUD de matriz, brechas, rutas y árbol de aplicabilidad (solo admin).
  C2  Las evaluaciones cerradas conservan la versión de la matriz con que se respondieron.
  C3  Cada cambio queda en el audit log.

Parte 1: lógica pura (app/domain/matriz); corre en cualquier entorno, sin BD.
Parte 2: API en proceso (SQLite, _api_harness.py).
"""
import asyncio
import itertools

import pytest

from app.application.filters.control_tree import ARBOL_POR_DEFECTO, CONTROLES_BASE, CONTROLES_POR_FILTRO
from app.domain.matriz import contenido as C
from app.domain.matriz import edicion as E
from app.domain.matriz.diferencias import conteo, diferencias, estado_de
from app.domain.matriz.validacion import ADVERTENCIA, ERROR, validar


# ===================================================================== parte 1: lógica pura
TODOS = sorted(set(CONTROLES_BASE).union(*CONTROLES_POR_FILTRO.values()))
DOM = {"DAT": 1, "GOB": 2, "RIE": 3, "SEG": 4}


def _semilla() -> dict:
    """Contenido como el de la migración: 40 controles, 7 filtros, F1 compuerta, el árbol de control_tree.py."""
    ids_c = {codigo: i + 1 for i, codigo in enumerate(TODOS)}
    ids_p = {f"F{i}": i for i in range(1, 8)}
    reglas = [(ids_c[c], None) for c in CONTROLES_BASE]
    reglas += [(ids_c[c], ids_p[f]) for f, cs in CONTROLES_POR_FILTRO.items() for c in cs]
    return C.construir(
        dominios=[{"id": i, "nombre_dominio": n} for n, i in DOM.items()],
        rutas=[{"id": 1, "nombre": "Gobernanza de IA - Inicial", "dominio_id": 2, "nivel": "Inicial"},
               {"id": 2, "nombre": "Protección de Datos - Inicial", "dominio_id": 1, "nivel": "Inicial"}],
        brechas=[{"id_brecha": 1, "codigo_brecha": "ERR-GOB-001", "comportamiento_detectado": "Sin política de IA",
                  "criticidad": "Alta", "ruta_formativa_id": 1},
                 {"id_brecha": 2, "codigo_brecha": "ERR-DAT-001", "comportamiento_detectado": "Sin base de licitud",
                  "criticidad": "Alta", "ruta_formativa_id": 2}],
        controles=[{"id_control": ids_c[c], "codigo_control": c, "dominio_id": DOM[c[:3]], "criticidad": "Alta",
                    "pregunta_evaluacion": f"¿Cumple {c}?", "catalogo_brechas_id_brecha": 1 if c[:3] != "DAT" else 2}
                   for c in TODOS],
        preguntas=[{"id_pregunta": i, "codigo": f"F{i}", "orden": i, "pregunta": f"Filtro {i}", "activa": True,
                    "es_compuerta": i == 1} for i in range(1, 8)],
        reglas=reglas,
    )


def test_c1_el_arbol_como_dato_es_igual_al_que_estaba_en_el_codigo():
    """La migración copia el árbol: para las 128 combinaciones del filtro da lo mismo."""
    arbol = C.arbol(_semilla())
    for valores in itertools.product([True, False], repeat=7):
        respuestas = {f"F{i + 1}": v for i, v in enumerate(valores)}
        assert arbol.aplicables(respuestas) == ARBOL_POR_DEFECTO.aplicables(respuestas), respuestas
    assert arbol.compuertas == {"F1"} and len(arbol.base) == 22


def test_huella_no_depende_del_orden_y_cambia_con_el_contenido():
    a = _semilla()
    b = C.copiar(a)
    b["controles"].reverse()
    assert C.huella(a) == C.huella(b)
    E.actualizar(b, "controles", 1, {"pregunta_evaluacion": "Texto nuevo"})
    assert C.huella(a) != C.huella(b)
    assert C.version_texto("2026.2", C.huella(b)).startswith("2026.2+") and len(C.version_texto("x", "f" * 64)) == 10


def test_c1_crud_del_borrador_con_ids_temporales_y_retiro_sin_borrar():
    c = _semilla()
    nuevo = E.crear(c, "controles", {"codigo_control": "dat-099", "pregunta_evaluacion": "¿Nuevo?",
                                     "criticidad": "media", "dominio_id": 1, "brecha_id": 2, "aplica_siempre": True})
    assert nuevo.id < 0 and nuevo.operacion == "creado"
    item = C.por_id(c, "controles")[nuevo.id]
    assert item["codigo_control"] == "DAT-099" and item["criticidad"] == "Media" and item["activo"] is True
    assert "DAT-099" in C.arbol(c).base
    # retirar uno publicado: queda con activo=false (no se borra)
    r = E.retirar(c, "controles", 1)
    assert r.operacion == "retirado" and C.por_id(c, "controles")[1]["activo"] is False
    assert TODOS[0] not in C.arbol(c).aplicables({f"F{i}": True for i in range(1, 8)})
    E.restaurar(c, "controles", 1)
    assert C.por_id(c, "controles")[1]["activo"] is True
    # retirar uno nuevo: se quita del borrador
    assert E.retirar(c, "controles", nuevo.id).operacion == "quitado"
    assert nuevo.id not in C.por_id(c, "controles")


@pytest.mark.parametrize("accion,codigo", [
    (lambda c: E.crear(c, "controles", {"codigo_control": "GOB-001", "pregunta_evaluacion": "x"}), "CODIGO_DUPLICADO"),
    (lambda c: E.crear(c, "controles", {"codigo_control": "mal codigo"}), "CODIGO_INVALIDO"),
    (lambda c: E.actualizar(c, "controles", 1, {"codigo_control": "DAT-777"}), "CODIGO_INMUTABLE"),
    (lambda c: E.actualizar(c, "controles", 1, {"dominio_id": 99}), "REFERENCIA_INVALIDA"),
    (lambda c: E.actualizar(c, "controles", 1, {"filtros": [42]}), "REFERENCIA_INVALIDA"),
    (lambda c: E.actualizar(c, "controles", 1, {"criticidad": "urgentísima"}), "VALOR_INVALIDO"),
    (lambda c: E.actualizar(c, "controles", 1, {"inventado": 1}), "CAMPO_DESCONOCIDO"),
    (lambda c: E.actualizar(c, "controles", 1, {"pregunta_evaluacion": "x" * 501}), "VALOR_DEMASIADO_LARGO"),
    (lambda c: E.actualizar(c, "controles", 1, {"criticidad": "Alta"}), "SIN_CAMBIOS"),
    (lambda c: E.retirar(c, "brechas", 1), "EN_USO"),            # la usan controles activos
    (lambda c: E.retirar(c, "rutas", 1), "EN_USO"),              # la usa una brecha activa
    (lambda c: E.retirar(c, "preguntas_filtro", 2), "EN_USO"),   # F2 la usan reglas
    (lambda c: E.retirar(c, "controles", 999), "NO_ENCONTRADO"),
    (lambda c: E.restaurar(c, "controles", 1), "YA_ACTIVO"),
])
def test_c1_la_edicion_protege_a_las_evaluaciones_anteriores(accion, codigo):
    with pytest.raises(E.EdicionError) as e:
        accion(_semilla())
    assert e.value.codigo == codigo


def test_c1_arbol_editable_por_control():
    c = _semilla()
    gob1 = next(x for x in c["controles"] if x["codigo_control"] == "GOB-001")
    cambio = E.fijar_aplicabilidad(c, gob1["id"], False, [3])      # deja de ser base; se suma con F3
    assert [x["campo"] for x in cambio.campos] == ["aplica_siempre", "filtros"]
    arbol = C.arbol(c)
    assert "GOB-001" not in arbol.base and "GOB-001" in arbol.por_filtro["F3"]
    assert "GOB-001" not in arbol.aplicables({"F1": True})
    assert "GOB-001" in arbol.aplicables({"F1": True, "F3": True})
    # una compuerta nueva corta todo si se responde NO
    E.actualizar(c, "preguntas_filtro", 7, {"es_compuerta": True})
    assert C.arbol(c).aplicables({"F1": True, "F7": False}) == []


def test_validacion_errores_bloquean_y_advertencias_no():
    c = _semilla()
    assert not [p for p in validar(c) if p.nivel == ERROR]
    E.crear(c, "controles", {"codigo_control": "GOB-050", "pregunta_evaluacion": "¿Sin reglas?", "criticidad": "Baja",
                             "dominio_id": 2})
    c["brechas"][0]["activo"] = False      # a mano: controles activos apuntan a una brecha retirada
    problemas = validar(c)
    codigos = {(p.nivel, p.codigo) for p in problemas}
    assert (ERROR, "BRECHA_INACTIVA") in codigos
    assert (ADVERTENCIA, "CONTROL_NUNCA_APLICA") in codigos
    assert (ADVERTENCIA, "CONTROL_SIN_BRECHA") in codigos


def test_diferencias_entre_versiones():
    a = _semilla()
    b = C.copiar(a)
    E.actualizar(b, "rutas", 1, {"nombre": "Gobernanza de IA - Inicial (2026)"})
    E.crear(b, "brechas", {"codigo_brecha": "ERR-GOB-050", "comportamiento_detectado": "x", "criticidad": "Media"})
    E.retirar(b, "controles", 40)
    d = diferencias(a, b)
    assert d["total"] == 3
    assert d["rutas"]["modificados"][0]["campos"] == ["nombre"]
    assert conteo(d) == {"rutas": {"modificados": 1}, "brechas": {"nuevos": 1}, "controles": {"retirados": 1}}
    assert estado_de(d, "controles") == {40: "retirado"}


def test_el_detalle_del_cambio_es_apto_para_el_audit_log():
    """La bitácora no admite correos ni la clave 'nombre': el detalle usa {campo, antes, despues}."""
    from app.infrastructure.repositories.bitacora_repository import _validar_detalle

    c = _semilla()
    cambio = E.actualizar(c, "rutas", 1, {"nombre": "Ruta con contacto ana@acme.cl", "objetivo": "y" * 400})
    detalle = cambio.como_detalle()
    _validar_detalle(detalle)  # no lanza
    assert {x["campo"] for x in detalle["campos"]} == {"nombre", "objetivo"}
    assert all(len(str(x["despues"])) <= 120 for x in detalle["campos"])


# ===================================================================== parte 2: API en proceso
from _api_harness import (  # noqa: E402
    EVAL_ID, EVAL_NA_ID, MODO, TODOS_LOS_CONTROLES, cliente_api, encabezados_qa,
)

api = pytest.mark.skipif(MODO == "live", reason="HU-24: cambian el catálogo; solo en proceso")
if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

ID = {codigo: i + 1 for i, codigo in enumerate(TODOS_LOS_CONTROLES)}
SOLO_BASE = {"respuestas": [{"codigo": f"F{i}", "respuesta": i == 1} for i in range(1, 8)]}
B = "/api/admin/matriz"


def _correr(escenario):
    async def _main():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_main())


def _cod(r):
    return r.json()["detail"]["codigo"]


async def _sesion():
    from app.core.database import get_db
    from app.main import app
    gen = app.dependency_overrides[get_db]()
    return gen, await gen.__anext__()


async def _completar(c, evaluacion=EVAL_ID, no_cumple=("GOB-001",)):
    assert (await c.post(f"/api/evaluaciones/{evaluacion}/filtro", json=SOLO_BASE)).status_code == 200
    for codigo in CONTROLES_BASE:
        r = await c.post("/api/respuestas/", json={
            "evaluacion_id": evaluacion, "matriz_control_id": ID[codigo],
            "estado_clasificacion": "no_cumplido" if codigo in no_cumple else "cumplido",
            "justificacion": "Tenemos una política aprobada por el directorio."})
        assert r.status_code in (200, 201), r.text
    r = await c.post(f"/api/evaluaciones/{evaluacion}/completar")
    assert r.status_code == 200, r.text


async def _borrador(c):
    r = await c.post(f"{B}/borrador", json={})
    assert r.status_code == 201, r.text
    return r.json()


async def _editar(c, metodo, ruta, revision, **cuerpo):
    r = await c.request(metodo, f"{B}/borrador/{ruta}", json={"revision": revision, **cuerpo})
    assert r.status_code in (200, 201), (ruta, r.text)
    return r.json()


async def _bitacora(c, accion=None):
    q = f"&accion={accion}" if accion else ""
    return (await c.get(f"/api/admin/bitacora?entidad=matriz_version&size=200{q}")).json()["items"]


@api
def test_rutas_hu24_solo_admin():
    from app.core.autenticacion import Rol, emitir_token

    async def esc(c):
        await _borrador(c)
        otros = {
            "referente": encabezados_qa("referente"),
            "encuestado": {"Authorization": f"Bearer {emitir_token(EVAL_ID, Rol.ENCUESTADO.value)}"},
            "cliente": {"Authorization": f"Bearer {emitir_token(1, Rol.CLIENTE.value)}"},
            "auditor": {"Authorization": f"Bearer {emitir_token(1, Rol.AUDITOR_EXTERNO.value)}"},
        }
        rutas = [
            ("GET", B, {}), ("GET", f"{B}/versiones", {}), ("GET", f"{B}/versiones/1", {}),
            ("POST", f"{B}/borrador", {"json": {}}), ("GET", f"{B}/borrador", {}),
            ("GET", f"{B}/borrador/validacion", {}), ("POST", f"{B}/borrador/descartar", {"json": {}}),
            ("POST", f"{B}/borrador/publicar", {"json": {"etiqueta": "2026.9", "nota_cambio": "x" * 20}}),
            ("PATCH", f"{B}/borrador/controles/1/aplicabilidad", {"json": {"aplica_siempre": True}}),
            ("POST", f"{B}/borrador/brechas", {"json": {"datos": {}}}),
            ("PATCH", f"{B}/borrador/rutas/1", {"json": {"datos": {"horas": 3}}}),
            ("POST", f"{B}/borrador/controles/1/retirar", {"json": {}}),
            ("POST", f"{B}/borrador/controles/1/restaurar", {"json": {}}),
        ]
        for metodo, url, kw in rutas:
            r = await c.request(metodo, url, headers={"Authorization": ""}, **kw)
            assert r.status_code == 401, (url, r.status_code)
            r = await c.request(metodo, url, headers=otros.pop("referente", None) or encabezados_qa("referente"), **kw)
            assert r.status_code == 403 and _cod(r) == "NO_AUTORIZADO", (url, r.text)
            # Encuestado, cliente y auditor de prueba no existen en la BD sembrada: 401 o 403, nunca 2xx
            for nombre, h in otros.items():
                r = await c.request(metodo, url, headers=h, **kw)
                assert r.status_code in (401, 403), (nombre, url, r.text)
        # admin: las de lectura responden 2xx
        for metodo, url, kw in rutas[:3] + rutas[4:6]:
            r = await c.request(metodo, url, **kw)
            assert 200 <= r.status_code < 300, (url, r.text)
    _correr(esc)


@api
def test_c1_c3_flujo_completo_editar_validar_publicar_y_auditar():
    async def esc(c):
        estado = (await c.get(B)).json()
        v1 = estado["vigente"]
        assert estado["borrador"] is None and v1["estado"] == "publicada"
        assert v1["resumen"]["controles"]["activos"] == 40 and estado["etiqueta_sugerida"].endswith(".2")

        b = await _borrador(c)
        rev = b["revision"]
        assert b["cambios"] == 0 and b["arbol"]["compuertas"] == ["F1"]
        assert (await c.post(f"{B}/borrador", json={})).status_code == 409   # uno a la vez

        # controles: modificar, crear con regla, retirar
        r = await _editar(c, "PATCH", f"controles/{ID['GOB-001']}", rev, datos={"criticidad": "Media"})
        rev = r["revision"]
        r = await _editar(c, "POST", "controles", rev, datos={
            "codigo_control": "GOB-011", "pregunta_evaluacion": "¿Revisan los sesgos de los modelos?",
            "criticidad": "Alta", "dominio_id": 2, "brecha_id": 1, "filtros": [2]})
        nuevo_id, rev = r["elemento"]["id"], r["revision"]
        assert nuevo_id < 0
        rev = (await _editar(c, "POST", f"controles/{ID['SEG-009']}/retirar", rev))["revision"]
        # árbol: GOB-002 deja de ser base y se suma con F3
        rev = (await _editar(c, "PATCH", f"controles/{ID['GOB-002']}/aplicabilidad", rev,
                             aplica_siempre=False, filtros=[3]))["revision"]
        # rutas y preguntas de filtro
        rev = (await _editar(c, "PATCH", "rutas/1", rev, datos={"nivel": "intermedio", "horas": 8}))["revision"]
        rev = (await _editar(c, "PATCH", "preguntas-filtro/2", rev,
                             datos={"pregunta": "¿Procesan datos sensibles con IA?"}))["revision"]

        # revisión vieja → 409 (otro admin cambió el borrador)
        r = await c.patch(f"{B}/borrador/rutas/1", json={"revision": 1, "datos": {"horas": 9}})
        assert r.status_code == 409 and _cod(r) == "BORRADOR_CAMBIADO"

        # la brecha sembrada no tiene comportamiento: publicar se rechaza y queda en el log
        val = (await c.get(f"{B}/borrador/validacion")).json()
        assert not val["puede_publicar"] and any(p["codigo"] == "CAMPO_REQUERIDO" for p in val["problemas"])
        r = await c.post(f"{B}/borrador/publicar", json={"etiqueta": "2026.2", "nota_cambio": "Circular 2026",
                                                          "revision": rev})
        assert r.status_code == 422 and _cod(r) == "BORRADOR_CON_ERRORES" and r.json()["detail"]["problemas"]
        rev = (await _editar(c, "PATCH", "brechas/1", rev,
                             datos={"comportamiento_detectado": "Usar IA sin política aprobada"}))["revision"]

        # mientras no se publica, el cuestionario sigue con la versión vigente
        assert (await c.post(f"/api/evaluaciones/{EVAL_NA_ID}/filtro", json=SOLO_BASE)).status_code == 200
        aplicables = {x["codigo_control"] for x in
                      (await c.get(f"/api/evaluaciones/{EVAL_NA_ID}/controles-aplicables")).json()}
        assert "SEG-009" in aplicables and "GOB-002" in aplicables

        for cuerpo, codigo in [({"etiqueta": "mal etiqueta", "nota_cambio": "Circular 2026"}, "ETIQUETA_INVALIDA"),
                               ({"etiqueta": v1["etiqueta"], "nota_cambio": "Circular 2026"}, "ETIQUETA_DUPLICADA"),
                               ({"etiqueta": "2026.2", "nota_cambio": "corta"}, "NOTA_INVALIDA")]:
            r = await c.post(f"{B}/borrador/publicar", json={**cuerpo, "revision": rev})
            assert _cod(r) == codigo, r.text
        r = await c.post(f"{B}/borrador/publicar", json={
            "etiqueta": "2026.2", "nota_cambio": "Ajuste por la circular de la Agencia (nov 2026)", "revision": rev})
        assert r.status_code == 200, r.text
        v2 = r.json()
        assert v2["estado"] == "publicada" and v2["version_texto"].startswith("2026.2+")
        assert v2["diferencias"]["controles"]["nuevos"][0]["etiqueta"] == "GOB-011"
        assert (await c.get(f"{B}/borrador")).status_code == 404

        # el cuestionario ya usa la versión nueva (sin modificar código)
        aplicables = {x["codigo_control"]: x for x in
                      (await c.get(f"/api/evaluaciones/{EVAL_NA_ID}/controles-aplicables")).json()}
        assert "SEG-009" not in aplicables and "GOB-002" not in aplicables
        assert aplicables["GOB-001"]["criticidad"] == "Media"
        con_f3 = {"respuestas": [{"codigo": f"F{i}", "respuesta": i in (1, 2, 3)} for i in range(1, 8)]}
        assert (await c.post(f"/api/evaluaciones/{EVAL_NA_ID}/filtro", json=con_f3)).status_code == 200
        aplicables = {x["codigo_control"] for x in
                      (await c.get(f"/api/evaluaciones/{EVAL_NA_ID}/controles-aplicables")).json()}
        assert {"GOB-011", "GOB-002"} <= aplicables
        # el catálogo público ya no lista lo retirado y el historial tiene ambas versiones
        assert "SEG-009" not in {x["codigo_control"] for x in (await c.get("/api/controles")).json()}
        versiones = (await c.get(f"{B}/versiones")).json()["items"]
        assert [v["estado"] for v in versiones] == ["publicada", "reemplazada"]
        detalle = (await c.get(f"{B}/versiones/{v2['id']}")).json()
        assert detalle["anterior"]["id"] == v1["id"] and detalle["diferencias"]["total"] >= 6

        # C3: cada cambio en el audit log (creación, 7 ediciones, rechazos y publicación)
        filas = await _bitacora(c)
        acciones = [f["accion"] for f in filas]
        assert acciones.count("matriz.borrador_creado") == 1
        assert acciones.count("matriz.borrador_editado") == 7
        assert acciones.count("matriz.publicacion_rechazada") == 4
        assert acciones.count("matriz.version_publicada") == 1
        pub = next(f for f in filas if f["accion"] == "matriz.version_publicada")
        assert pub["actor_rol"] == "admin_therion" and pub["detalle"]["etiqueta"] == "2026.2"
        assert pub["detalle"]["cambios"]["controles"] == {"nuevos": 1, "modificados": 2, "retirados": 1}
        edicion = next(f for f in filas if f["accion"] == "matriz.borrador_editado"
                       and f["detalle"]["tipo"] == "controles" and f["detalle"]["operacion"] == "modificado")
        assert edicion["detalle"]["campos"] == [{"campo": "criticidad", "antes": "alta", "despues": "Media"}]
    _correr(esc)


@api
def test_c2_la_evaluacion_cerrada_conserva_su_version():
    async def esc(c):
        v1 = (await c.get(B)).json()["vigente"]          # en producción la siembra la migración
        await _completar(c)                              # GOB-001 no cumplido → brecha 1 → ruta 1

        b = await _borrador(c)
        rev = b["revision"]
        rev = (await _editar(c, "PATCH", f"controles/{ID['GOB-001']}", rev, datos={"criticidad": "Baja"}))["revision"]
        rev = (await _editar(c, "PATCH", "brechas/1", rev,
                             datos={"comportamiento_detectado": "Texto de la versión nueva"}))["revision"]
        rev = (await _editar(c, "PATCH", "rutas/1", rev, datos={"nombre": "Ruta renombrada en 2026.2"}))["revision"]
        r = await c.post(f"{B}/borrador/publicar", json={"etiqueta": "2026.2", "revision": rev,
                                                          "nota_cambio": "Cambio de criticidad por la circular"})
        assert r.status_code == 200, r.text

        from app.application.informes.carga import cargar_evaluacion
        from app.domain.models.evaluacion import Evaluacion
        gen, s = await _sesion()
        try:
            ev = await s.get(Evaluacion, EVAL_ID)
            assert ev.matriz_version_id == v1["id"] and ev.version_matriz == v1["version_texto"]
            datos = await cargar_evaluacion(s, EVAL_ID)
        finally:
            await gen.aclose()
        fila = next(x for x in datos.respuestas if x.control_codigo == "GOB-001")
        assert fila.control_criticidad == "alta"                       # la de v1, no "Baja"
        assert fila.brecha_control.comportamiento is None              # v1 no tenía texto
        assert fila.brecha_control.ruta.nombre == "Ruta base de gobernanza IA"
        assert [r.nombre for r in datos.rutas] == ["Ruta base de gobernanza IA"]

        # la ficha del informe sigue diciendo con qué versión se respondió
        ficha = (await c.get(f"/api/evaluaciones/{EVAL_ID}/informe/ficha")).json()
        assert ficha["version_matriz"] == v1["version_texto"] and ficha["version_matriz_registrada"] is True
        # y el historial cuenta la evaluación en v1
        versiones = {v["id"]: v for v in (await c.get(f"{B}/versiones")).json()["items"]}
        assert versiones[v1["id"]]["evaluaciones"] == 1

        # el contenido de una versión publicada no cambia con borradores posteriores
        antes = (await c.get(f"{B}/versiones/{v1['id']}")).json()["huella"]
        b = await _borrador(c)
        await _editar(c, "PATCH", "rutas/1", b["revision"], datos={"horas": 40})
        assert (await c.get(f"{B}/versiones/{v1['id']}")).json()["huella"] == antes
        r = await c.post(f"{B}/borrador/descartar", json={})
        assert r.status_code == 200
        assert (await _bitacora(c, "matriz.borrador_descartado"))[0]["detalle"]["cambios_descartados"] == {
            "rutas": {"modificados": 1}}
    _correr(esc)


@api
def test_borrador_desde_una_version_anterior_permite_volver_atras():
    async def esc(c):
        v1 = (await c.get(B)).json()["vigente"]
        b = await _borrador(c)
        rev = (await _editar(c, "PATCH", "brechas/1", b["revision"],
                             datos={"comportamiento_detectado": "Usar IA sin política"}))["revision"]
        rev = (await _editar(c, "POST", f"controles/{ID['SEG-009']}/retirar", rev))["revision"]
        r = await c.post(f"{B}/borrador/publicar", json={"etiqueta": "2026.2", "revision": rev,
                                                          "nota_cambio": "Se retira SEG-009 por la circular"})
        assert r.status_code == 200, r.text

        # volver: borrador desde v1 (SEG-009 activo otra vez)
        r = await c.post(f"{B}/borrador", json={"desde_version_id": v1["id"]})
        assert r.status_code == 201
        seg9 = next(x for x in r.json()["contenido"]["controles"] if x["codigo_control"] == "SEG-009")
        assert seg9["activo"] is True and r.json()["conteo_cambios"]["controles"] == {"restaurados": 1}
        # (v1 tenía la brecha sin comportamiento: se completa para poder publicar)
        rev = (await _editar(c, "PATCH", "brechas/1", r.json()["revision"],
                             datos={"comportamiento_detectado": "Usar IA sin política aprobada"}))["revision"]
        r = await c.post(f"{B}/borrador/publicar", json={"etiqueta": "2026.3", "revision": rev,
                                                          "nota_cambio": "Se revierte el retiro de SEG-009"})
        assert r.status_code == 200, r.text
        assert (await c.post(f"/api/evaluaciones/{EVAL_ID}/filtro", json=SOLO_BASE)).status_code == 200
        aplicables = {x["codigo_control"] for x in
                      (await c.get(f"/api/evaluaciones/{EVAL_ID}/controles-aplicables")).json()}
        assert "SEG-009" in aplicables
    _correr(esc)


@api
def test_publicar_sin_cambios_se_rechaza():
    async def esc(c):
        await _borrador(c)
        r = await c.post(f"{B}/borrador/publicar", json={"etiqueta": "2026.2", "nota_cambio": "Sin cambios reales"})
        assert r.status_code == 409 and _cod(r) == "SIN_CAMBIOS"
    _correr(esc)
