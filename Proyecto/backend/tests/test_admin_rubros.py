"""
Correcciones 05-11 · Rubros desde el panel interno (app/api/routes/admin_rubros.py).
Solo admin; cada cambio queda en el audit log; sin duplicados; el rubro nuevo aparece en
el catálogo público /api/rubros.
"""
import asyncio

import pytest

pytest.importorskip("httpx")

from _api_harness import EVAL_ID, MODO, cliente_api, encabezados_qa  # noqa: E402

api = pytest.mark.skipif(MODO == "live", reason="cambia el catálogo; solo en proceso")
if MODO == "en_proceso":
    pytest.importorskip("aiosqlite", reason="pip install aiosqlite")

B = "/api/admin/rubros"


def _correr(escenario):
    async def _main():
        async with cliente_api() as c:
            await escenario(c)
    asyncio.run(_main())


@api
def test_agregar_listar_renombrar_y_auditar():
    async def esc(c):
        antes = (await c.get(B)).json()["items"]
        assert antes and {"id", "nombre", "evaluaciones", "empresas"} <= set(antes[0])

        r = await c.post(B, json={"nombre": "  Minería   y energía "})
        assert r.status_code == 201, r.text
        nuevo = r.json()
        assert nuevo["nombre"] == "Minería y energía" and nuevo["id"] > max(x["id"] for x in antes)
        # visible para quien inicia el autodiagnóstico
        assert "Minería y energía" in {x["nombre_rubro"] for x in (await c.get("/api/rubros")).json()}

        r = await c.post(B, json={"nombre": "minería Y ENERGÍA"})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "RUBRO_DUPLICADO"
        r = await c.post(B, json={"nombre": "1"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "RUBRO_INVALIDO"

        r = await c.patch(f"{B}/{nuevo['id']}", json={"nombre": "Minería"})
        assert r.status_code == 200 and r.json()["nombre"] == "Minería"
        assert (await c.patch(f"{B}/99999", json={"nombre": "Otro"})).status_code == 404

        log = (await c.get("/api/admin/bitacora?entidad=rubro&size=50")).json()["items"]
        assert {f["accion"] for f in log} >= {"rubro.creado", "rubro.renombrado"}
    _correr(esc)


@api
def test_rutas_de_rubros_solo_admin():
    from app.core.autenticacion import Rol, emitir_token

    async def esc(c):
        rutas = [("GET", B, {}), ("POST", B, {"json": {"nombre": "Salud"}}),
                 ("PATCH", f"{B}/1", {"json": {"nombre": "Retail"}})]
        otros = [encabezados_qa("referente"),
                 {"Authorization": f"Bearer {emitir_token(EVAL_ID, Rol.ENCUESTADO.value)}"},
                 {"Authorization": f"Bearer {emitir_token(1, Rol.CLIENTE.value)}"}]
        for metodo, url, kw in rutas:
            assert (await c.request(metodo, url, headers={"Authorization": ""}, **kw)).status_code == 401
            for h in otros:
                assert (await c.request(metodo, url, headers=h, **kw)).status_code in (401, 403)
    _correr(esc)
