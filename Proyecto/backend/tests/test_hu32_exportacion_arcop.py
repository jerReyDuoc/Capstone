"""
QA · HU-32 — Exportación de datos del titular (derechos de Acceso y Portabilidad).

Ejecutar desde Proyecto/backend/:
  pytest tests/test_hu32_exportacion_arcop.py -v

GET /api/arcop/solicitudes/{id}/exportacion?formato=json|csv
  - Solo el titular dueño (invitado, encuestado o usuario definitivo); ajena -> 404.
  - Solo acceso/portabilidad RESUELTA; si no -> 409 EXPORTACION_NO_DISPONIBLE.
  - JSON estructurado y CSV largo (seccion, referencia, campo, valor) con BOM.
  - Sin secretos (hashes, rutas en disco, tokens) y con registro en el audit_log.
"""
import csv
import io
import json

import pytest

pytest.importorskip("httpx")

from test_solicitudes_arcop import (  # noqa: E402
    ADMIN, DESCRIPCION, OTRO, TITULAR, _clave_de, _correr, _llevar_a_en_proceso, _token_encuestado,
    _auth_secret,  # noqa: F401  (fixture autouse: AUTH_SECRET y plazos de prueba)
)
from _api_harness import EVAL_NA_ID, body_filtro  # noqa: E402
from test_hu30_contrato import _cliente, api, hu27  # noqa: E402,F401  (fixture del usuario definitivo)
from test_hu30_contrato import _correr as _correr_hu30  # noqa: E402

from app.application.use_cases.exportar_datos_arcop import (  # noqa: E402
    a_csv, a_json, conteos, nombre_archivo,
)

RESPUESTA = "Adjuntamos la exportación de sus datos personales."


async def _crear(c, headers, tipo="acceso"):
    r = await c.post("/api/arcop/solicitudes", json={"tipo": tipo, "descripcion": DESCRIPCION}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id_solicitud"]


async def _resolver(c, sid, resultado="resuelta"):
    await _llevar_a_en_proceso(c, sid)
    r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion",
                     json={"resultado": resultado, "respuesta": RESPUESTA}, headers=ADMIN())
    assert r.status_code == 200, r.text


def _url(sid, formato="json"):
    return f"/api/arcop/solicitudes/{sid}/exportacion?formato={formato}"


# ---------------------------------------------------------------- formatos (puros)
DATOS = {
    "formato": "x", "version_formato": 1, "generado_en": "2026-11-10T12:00:00",
    "solicitud": {"codigo_seguimiento": "ARC-AAAA-BBBB", "tipo": "portabilidad", "fecha_resolucion": None},
    "titular": {"tipo": "encuestado", "correo": None, "rubro": "Retail"},
    "evaluaciones": [{
        "numero_evaluacion": 7, "origen": "publica", "estado": "completada", "fecha_inicio": "2026-11-01",
        "fecha_completado": None, "filtro_aplicabilidad": [],
        "respuestas": [{"control": "C-01", "pregunta": "¿Tiene política?", "estado_declarado": "cumplido",
                        "justificacion": "=HYPERLINK(\"x\")", "estado_final": "cumplido",
                        "evidencias": [{"nombre_archivo": "politica.pdf", "tipo_archivo": "application/pdf",
                                        "fecha_subida": "2026-11-01", "estado_validacion": "procesada"}]}],
        "resultados": [],
    }],
    "solicitudes_arcop": [{"codigo_seguimiento": "ARC-AAAA-BBBB", "tipo": "portabilidad"}],
    "notas": ["nota"],
}


def test_conteos_y_nombre_de_archivo():
    assert conteos(DATOS) == {"evaluaciones": 1, "respuestas": 1, "evidencias": 1, "solicitudes_arcop": 1}
    assert nombre_archivo("ARC-AAAA-BBBB", "csv") == "mis-datos-ARC-AAAA-BBBB.csv"
    assert nombre_archivo('ARC"; rm', "json") == "mis-datos-ARCrm.json"


def test_json_es_utf8_legible():
    texto = a_json(DATOS).decode("utf-8")
    assert "¿Tiene política?" in texto and json.loads(texto)["evaluaciones"][0]["numero_evaluacion"] == 7


def test_csv_largo_con_bom_y_sin_formulas():
    crudo = a_csv(DATOS)
    assert crudo.startswith("﻿".encode("utf-8"))
    filas = list(csv.reader(io.StringIO(crudo.decode("utf-8-sig"))))
    assert filas[0] == ["seccion", "referencia", "campo", "valor"]
    secciones = {f[0] for f in filas[1:]}
    assert {"solicitud", "titular", "evaluacion", "respuesta", "evidencia", "solicitud_arcop", "nota"} <= secciones
    just = next(f for f in filas if f[0] == "respuesta" and f[2] == "justificacion")
    assert just[3].startswith("'=")  # CSV injection neutralizada
    assert ["evidencia", "evaluacion 7 · C-01 · archivo 1", "nombre_archivo", "politica.pdf"] in filas


# ---------------------------------------------------------------- API: invitado
def test_no_disponible_hasta_que_se_resuelve():
    async def esc(c):
        sid = await _crear(c, TITULAR())
        r = await c.get(_url(sid), headers=TITULAR())
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "EXPORTACION_NO_DISPONIBLE"
        await _resolver(c, sid, "rechazada")
        assert (await c.get(_url(sid), headers=TITULAR())).status_code == 409
    _correr(esc)


@pytest.mark.parametrize("tipo", ["rectificacion", "supresion", "oposicion", "bloqueo"])
def test_otros_derechos_no_exportan(tipo):
    async def esc(c):
        sid = await _crear(c, TITULAR(), tipo)
        if tipo != "supresion":  # una supresión resuelta anonimiza y corta el acceso
            await _resolver(c, sid)
        r = await c.get(_url(sid), headers=TITULAR())
        assert r.status_code == 409, r.text
    _correr(esc)


def test_invitado_descarga_sus_datos_en_json_y_csv():
    async def esc(c):
        assert (await c.post("/api/evaluaciones/1/filtro", json=body_filtro(True), headers=ADMIN())).status_code == 200
        r = await c.post("/api/respuestas/", headers=ADMIN(), json={
            "evaluacion_id": 1, "matriz_control_id": 1, "estado_clasificacion": "cumplido",
            "justificacion": "Contamos con una política de uso de IA aprobada por el directorio.",
        })
        assert r.status_code == 201, r.text
        sid = await _crear(c, TITULAR(), "portabilidad")
        await _resolver(c, sid)

        r = await c.get(_url(sid), headers=TITULAR())
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/json")
        assert "attachment" in r.headers["content-disposition"] and ".json" in r.headers["content-disposition"]
        assert r.headers["cache-control"] == "no-store"
        d = r.json()
        assert d["titular"]["tipo"] == "invitado" and d["titular"]["correo"] == "qa@example.com"
        assert d["solicitud"]["tipo"] == "portabilidad"
        numeros = [e["numero_evaluacion"] for e in d["evaluaciones"]]
        assert 1 in numeros
        ev1 = next(e for e in d["evaluaciones"] if e["numero_evaluacion"] == 1)
        assert ev1["respuestas"] and ev1["respuestas"][0]["estado_declarado"] == "cumplido"
        assert len(ev1["filtro_aplicabilidad"]) > 0
        assert any(s["respuesta"] == RESPUESTA for s in d["solicitudes_arcop"])
        # nada de secretos ni datos internos
        texto = r.text
        for prohibido in ("password", "clave_acceso", "storage_path", "hash_archivo", "token", "validacion_invitacion"):
            assert prohibido not in texto

        r = await c.get(_url(sid, "csv"), headers=TITULAR())
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        filas = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        assert ["titular", "", "correo", "qa@example.com"] in filas

        # formato inválido -> 400; otro titular -> 404; el admin no descarga por el titular -> 403
        assert (await c.get(_url(sid, "xml"), headers=TITULAR())).status_code == 400
        assert (await c.get(_url(sid), headers=OTRO())).status_code == 404
        assert (await c.get(_url(sid), headers=ADMIN())).status_code == 403
        assert (await c.get(_url(sid))).status_code == 401

        # HU-09: cada descarga queda en el audit_log, sin datos personales
        r = await c.get("/api/admin/bitacora?entidad=solicitudes_arcop&size=200", headers=ADMIN())
        assert r.status_code == 200, r.text
        exportes = [i for i in r.json()["items"] if i["accion"] == "arcop.datos_exportados"]
        assert {i["detalle"]["formato"] for i in exportes} == {"json", "csv"}
        assert "@" not in str([i["detalle"] for i in exportes])
    _correr(esc)


# ---------------------------------------------------------------- API: encuestado
def test_encuestado_exporta_solo_su_evaluacion():
    async def esc(c):
        ENC = await _token_encuestado(c, EVAL_NA_ID, await _clave_de(c, EVAL_NA_ID))
        sid = await _crear(c, ENC, "acceso")
        await _resolver(c, sid)
        r = await c.get(_url(sid), headers=ENC)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["titular"]["tipo"] == "encuestado"
        assert [e["numero_evaluacion"] for e in d["evaluaciones"]] == [EVAL_NA_ID]
        assert [s["tipo"] for s in d["solicitudes_arcop"]] == ["acceso"]
        # el invitado no descarga la del encuestado
        assert (await c.get(_url(sid), headers=TITULAR())).status_code == 404
    _correr(esc)


# ---------------------------------------------------------------- API: usuario definitivo
@api
def test_usuario_definitivo_exporta_su_cuenta_sin_la_empresa(hu27):  # noqa: F811
    async def esc(c):
        x = await _cliente(hu27, c)
        h, adm = x["hc"], hu27.admin()
        r = await c.post("/api/arcop/solicitudes", headers=h, json={"tipo": "acceso", "descripcion": DESCRIPCION})
        assert r.status_code == 201, r.text
        sid = r.json()["id_solicitud"]
        for estado in ("en_revision", "en_proceso"):
            assert (await c.patch(f"/api/arcop/solicitudes/{sid}/estado", json={"estado": estado},
                                  headers=adm)).status_code == 200
        r = await c.post(f"/api/arcop/solicitudes/{sid}/resolucion", headers=adm,
                         json={"resultado": "resuelta", "respuesta": RESPUESTA})
        assert r.status_code == 200, r.text

        r = await c.get(_url(sid), headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["titular"]["tipo"] == "usuario_definitivo"
        assert d["titular"]["correo"] == "gerencia@acme.cl" and d["titular"]["empresa"] == "ACME Servicios SpA"
        assert d["evaluaciones"] == []  # las evaluaciones son de la persona jurídica
        assert any("Mis documentos" in n for n in d["notas"])
        assert "password" not in r.text
    _correr_hu30(esc)
