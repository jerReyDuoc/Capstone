"""
T-12 · Aceptar una propuesta del asistente sin dejarla colgada.

En rat/casos_uso/asistente_rat/decisiones.py::aceptar, crear el elemento, el flujo o la actividad y cerrar
la propuesta van en UN solo commit:
  - si falla el segundo paso (cerrar la propuesta), no se crea nada y la propuesta sigue "por revisar";
  - aceptar dos veces no duplica ni responde NOMBRE_DUPLICADO;
  - si en un reintento ya existe lo que creó la propuesta (propuesta_ia_id), la propuesta se marca aceptada;
  - la versión del mapa y el audit log se escriben una sola vez.

Mismo arnés que HU-39 (FastAPI + SQLite en memoria, proveedor LLM falso).
"""
from __future__ import annotations

from test_hu34_mapa_datos import _cliente, _correr, _filas, api, hu27  # noqa: F401
from test_hu39_asistente_rat import ia  # noqa: F401


async def _aceptar_con_falla(c, h, pid: int) -> None:
    """El arnés puede propagar la excepción o devolver 500: en ambos casos la petición falló."""
    try:
        r = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
    except RuntimeError:
        return
    assert r.status_code == 500, r.text


async def _propuestas(c, h) -> dict:
    r = await c.post("/api/asistente/sesiones", headers=h, json={})
    assert r.status_code == 201, r.text
    s = r.json()["sesion"]
    r = await c.post(f"/api/asistente/sesiones/{s['id']}/respuestas", headers=h, json={
        "texto": "Llevamos los sueldos en un sistema de remuneraciones en la nube"})
    assert r.status_code == 200, r.text
    return {p["clave"]: p for p in r.json()["propuestas"] if p["estado"] == "sugerida"}


@api
def test_aceptar_dos_veces_no_duplica_ni_responde_nombre_duplicado(hu27, ia):
    async def esc(c):
        from app.domain.models import BitacoraAuditoria, MapaDatosVersion, MapaElemento

        h = (await _cliente(hu27, c))["hc"]
        por = await _propuestas(c, h)
        pid = por["sistema_remu"]["id"]
        r1 = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
        assert r1.status_code == 200, r1.text
        r2 = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
        assert r2.status_code == 200, r2.text          # ni 409 PROPUESTA_DECIDIDA ni NOMBRE_DUPLICADO
        assert r2.json()["aceptada"] == r1.json()["aceptada"]

        elementos = await _filas(hu27, MapaElemento)
        assert len(elementos) == 1 and elementos[0].propuesta_ia_id == pid
        assert len(await _filas(hu27, MapaDatosVersion)) == 1          # una sola versión del mapa
        acciones = [b.accion for b in await _filas(hu27, BitacoraAuditoria)]
        assert acciones.count("mapa_datos.elemento_creado") == 1
        assert acciones.count("asistente.propuesta_aceptada") == 1
    _correr(esc)


@api
def test_si_falla_cerrar_la_propuesta_no_se_crea_nada(hu27, ia, monkeypatch):
    async def esc(c):
        from app.application.rat.casos_uso.asistente_rat import decisiones
        from app.domain.models import AsistentePropuesta, BitacoraAuditoria, MapaDatosVersion, MapaElemento

        h = (await _cliente(hu27, c))["hc"]
        por = await _propuestas(c, h)
        pid = por["sistema_remu"]["id"]

        # El segundo paso (cerrar la propuesta) falla después de crear el elemento
        def falla():
            raise RuntimeError("falla simulada al cerrar la propuesta")
        original = decisiones._ahora
        monkeypatch.setattr(decisiones, "_ahora", falla)
        await _aceptar_con_falla(c, h, pid)
        monkeypatch.setattr(decisiones, "_ahora", original)

        assert await _filas(hu27, MapaElemento) == []
        assert await _filas(hu27, MapaDatosVersion) == []
        propuesta = (await _filas(hu27, AsistentePropuesta, AsistentePropuesta.id == pid))[0]
        assert propuesta.estado == "sugerida" and propuesta.entidad_destino_id is None
        acciones = [b.accion for b in await _filas(hu27, BitacoraAuditoria)]
        assert "mapa_datos.elemento_creado" not in acciones and "asistente.propuesta_aceptada" not in acciones

        # Y se puede volver a aceptar normalmente
        r = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
        assert r.status_code == 200, r.text
        assert len(await _filas(hu27, MapaElemento)) == 1
    _correr(esc)


@api
def test_reintento_con_el_objeto_ya_creado_marca_la_propuesta_como_aceptada(hu27, ia):
    async def esc(c):
        from sqlalchemy import select

        from app.domain.models import AsistentePropuesta, BitacoraAuditoria, MapaDatosVersion, MapaElemento

        h = (await _cliente(hu27, c))["hc"]
        por = await _propuestas(c, h)
        pid = por["sistema_remu"]["id"]
        r = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
        assert r.status_code == 200, r.text
        destino = r.json()["aceptada"]["destino_id"]

        # Simula un intento anterior que guardó el elemento pero no alcanzó a cerrar la propuesta
        async def reabrir(s):
            p = (await s.execute(select(AsistentePropuesta).where(AsistentePropuesta.id == pid))).scalar_one()
            p.estado, p.entidad_destino, p.entidad_destino_id = "sugerida", None, None
            p.decidido_por = p.fecha_decision = None
            await s.commit()
        await hu27._bd(reabrir)

        r = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
        assert r.status_code == 200, r.text
        assert r.json()["aceptada"]["destino_id"] == destino
        assert len(await _filas(hu27, MapaElemento)) == 1               # no se creó otro
        assert len(await _filas(hu27, MapaDatosVersion)) == 1           # ni otra versión del mapa
        propuesta = (await _filas(hu27, AsistentePropuesta, AsistentePropuesta.id == pid))[0]
        assert propuesta.estado == "aceptada" and propuesta.entidad_destino_id == destino
        acciones = [b.accion for b in await _filas(hu27, BitacoraAuditoria)]
        assert acciones.count("mapa_datos.elemento_creado") == 1
        reintentos = [b for b in await _filas(hu27, BitacoraAuditoria)
                      if b.accion == "asistente.propuesta_aceptada" and (b.detalle or {}).get("reintento")]
        assert len(reintentos) == 1
    _correr(esc)


@api
def test_la_actividad_tambien_se_crea_y_cierra_en_un_solo_commit(hu27, ia, monkeypatch):
    async def esc(c):
        from app.application.rat.casos_uso.asistente_rat import decisiones
        from app.domain.models import AsistentePropuesta, RatActividad

        h = (await _cliente(hu27, c))["hc"]
        por = await _propuestas(c, h)
        for clave in ("sistema_remu", "mutual", "remu_mutual"):
            r = await c.post(f"/api/asistente/propuestas/{por[clave]['id']}/aceptar", headers=h, json={})
            assert r.status_code == 200, r.text
        pid = por["pago_remu"]["id"]

        def falla():
            raise RuntimeError("falla simulada")
        original = decisiones._ahora
        monkeypatch.setattr(decisiones, "_ahora", falla)
        await _aceptar_con_falla(c, h, pid)
        monkeypatch.setattr(decisiones, "_ahora", original)
        assert await _filas(hu27, RatActividad) == []
        assert (await _filas(hu27, AsistentePropuesta, AsistentePropuesta.id == pid))[0].estado == "sugerida"

        r = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
        assert r.status_code == 200, r.text
        r = await c.post(f"/api/asistente/propuestas/{pid}/aceptar", headers=h, json={})
        assert r.status_code == 200, r.text
        assert len(await _filas(hu27, RatActividad)) == 1
    _correr(esc)
