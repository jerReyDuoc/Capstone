"""A-20: la caché del catálogo ya no usa ControlResponse; su serialización debe ser idéntica."""
from types import SimpleNamespace

from app.application.schemas.api_schemas import ControlResponse
from app.infrastructure.cache.catalogo_controles import _serializar


def _control(con_brecha=True, con_ruta=True, con_dominio=True):
    ruta = SimpleNamespace(id=3, nombre="Ruta", dominio_id=2, nivel="basico", objetivo="obj",
                           horas=8, modalidad="online", publico_objetivo="todos") if con_ruta else None
    brecha = SimpleNamespace(id_brecha=7, codigo_brecha="B-07", categoria="x", comportamiento_detectado="comp",
                             criticidad="alta", accion_sistema="acc", ruta_formativa=ruta) if con_brecha else None
    dominio = SimpleNamespace(id=2, nombre_dominio="Dominio ñ") if con_dominio else None
    return SimpleNamespace(
        id_control=1, codigo_control="C-01", framework_fuente="Ley 21.719", articulo_referencia="art. 4",
        tipo_fuente="ley", obligacion="obl", pregunta_evaluacion="¿pregunta?", aplicabilidad="todas",
        evidencia_esperada="evid", criticidad="alta", recomendacion="rec", test_asociado="t1",
        dominio=dominio, brecha=brecha,
    )


def test_serializar_igual_a_control_response():
    for kw in ({}, {"con_ruta": False}, {"con_brecha": False}, {"con_dominio": False}):
        c = _control(**kw)
        esperado = ControlResponse.model_validate(c).model_dump(mode="json")
        obtenido = _serializar(c)
        assert obtenido == esperado
        assert list(obtenido) == list(esperado)
        assert (list(obtenido["brecha"]) == list(esperado["brecha"])) if obtenido["brecha"] else True


def test_serializar_con_campos_nulos():
    c = _control()
    for campo in ("codigo_control", "framework_fuente", "recomendacion", "test_asociado"):
        setattr(c, campo, None)
    assert _serializar(c) == ControlResponse.model_validate(c).model_dump(mode="json")
