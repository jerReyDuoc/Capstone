"""
HU-10 · Comparativa de madurez contra el sector con k-anonimato (k < 5 => se oculta).

Criterios de aceptación:
  C1  Cálculo de promedios de madurez agregados por sector (por dimensión y general).
  C2  Supresión automática de las métricas si la cohorte tiene menos de 5 empresas.
  C3  Advertencia (código + mensaje) para la interfaz cuando k < 5.

Además se prueban las defensas que hacen que la supresión sea real y no decorativa:
  - k cuenta ORGANIZACIONES distintas, no evaluaciones (repetir la encuesta no infla k);
  - no se revela el valor de k cuando es < 5;
  - máximo y mínimo nunca se publican; mediana y percentiles solo con cohortes >= 10;
  - el promedio publicado va en enteros (mitiga el ataque de diferenciación).
"""
import asyncio

import pytest

from app.application.benchmark.k_anonimato import (
    SUPRIMIDA,
    FilaCandidata,
    calcular,
    clave_organizacion,
    cohorte_suficiente,
    diferencia,
    evaluaciones_por_organizacion,
    percentil,
    posicion,
    publicar,
)


# ===================================================================== reglas puras
def test_k_cuenta_organizaciones_y_no_evaluaciones():
    filas = [
        FilaCandidata(1, empresa_id=7, usuario_temporal_id=None),
        FilaCandidata(5, empresa_id=7, usuario_temporal_id=None),   # reevaluación: cuenta la 5
        FilaCandidata(2, empresa_id=None, usuario_temporal_id=40),
        FilaCandidata(3, empresa_id=None, usuario_temporal_id=40),  # repitió la encuesta: cuenta la 3
        FilaCandidata(4, empresa_id=None, usuario_temporal_id=None),
        # evaluación migrada a la empresa 9 que conserva su usuario temporal: manda la empresa
        FilaCandidata(6, empresa_id=9, usuario_temporal_id=41),
        FilaCandidata(8, empresa_id=None, usuario_temporal_id=41),
    ]
    assert evaluaciones_por_organizacion(filas) == {5, 3, 4, 6, 8}
    assert clave_organizacion(filas[5]) == "empresa:9"
    assert evaluaciones_por_organizacion([]) == set()


def test_calculo_de_estadisticas():
    e = calcular([10, 20, 30, 40, None, 50])
    assert e.empresas == 5 and e.promedio == 30 and e.mediana == 30
    assert e.p25 == 20 and e.p75 == 40 and e.maximo == 50 and e.minimo == 10
    assert calcular([None, None]).empresas == 0
    assert percentil([1, 2, 3, 4], 0.5) == 2.5 and percentil([], 0.5) is None


@pytest.mark.parametrize("k,suficiente", [(0, False), (1, False), (4, False), (5, True), (12, True)])
def test_umbral_k_5(k, suficiente):
    assert cohorte_suficiente(k) is suficiente
    pub = publicar(k, 61.4, 60.0, 50.0, 70.0)
    assert pub.suficiente is suficiente
    if not suficiente:
        # C2: todo suprimido, incluido el tamaño de la cohorte
        assert pub == SUPRIMIDA and all(v in (None, False) for v in pub.como_dict().values())


def test_distribucion_solo_con_cohortes_grandes_y_promedio_entero():
    chica = publicar(5, 62.5, 61.0, 50.0, 72.0)
    assert chica.promedio == 63  # redondeo a entero (62.5 -> 63, no al par)
    assert chica.mediana is None and chica.p25 is None and chica.p75 is None
    grande = publicar(10, 62.49, 61.0, 50.2, 72.6)
    assert (grande.promedio, grande.mediana, grande.p25, grande.p75) == (62, 61, 50, 73)
    assert "maximo" not in grande.como_dict() and "minimo" not in grande.como_dict()


def test_posicion_y_diferencia_sin_revelar_puntajes_ajenos():
    con_cuartiles = publicar(10, 60, 60, 50, 70)
    assert posicion(45, con_cuartiles) == "bajo_cuartil_inferior"
    assert posicion(60, con_cuartiles) == "franja_central"
    assert posicion(71, con_cuartiles) == "sobre_cuartil_superior"
    solo_promedio = publicar(6, 60.4, 60, 50, 70)
    assert posicion(61, solo_promedio) == "en_promedio"
    assert posicion(70, solo_promedio) == "sobre_promedio"
    assert posicion(40, solo_promedio) == "bajo_promedio"
    assert diferencia(70, solo_promedio) == 10.0  # frente al promedio PUBLICADO (60)
    assert posicion(70, SUPRIMIDA) is None and diferencia(70, SUPRIMIDA) is None


def test_configuracion_del_umbral():
    from app.core.config import Settings, settings

    assert settings.K_ANONIMATO_MINIMO == 5  # criterio de aceptación
    with pytest.raises(ValueError):
        Settings(K_ANONIMATO_MINIMO=0)
    with pytest.raises(ValueError):
        Settings(K_ANONIMATO_MINIMO=5, K_ANONIMATO_DISTRIBUCION=4)


# ===================================================================== API (en proceso)
try:
    import aiosqlite  # noqa: F401
    import httpx  # noqa: F401

    _HAY_API = True
except ImportError:  # pragma: no cover
    _HAY_API = False

api = pytest.mark.skipif(not _HAY_API, reason="requiere httpx y aiosqlite (pip install -r requirements.txt)")

# Puntajes de las organizaciones del rubro 1 (Retail) en la dimensión "Datos" y "Gobernanza"
PUNTAJES = [40.0, 55.0, 60.0, 70.0, 82.0, 90.0]


async def _sembrar_cohorte(c, n: int, *, repetidas_de_una: int = 0):
    """
    n organizaciones (usuarios temporales 300..) con una evaluación completada cada una en
    Datos y Gobernanza; si `repetidas_de_una`, además esa cantidad de evaluaciones extra del
    MISMO usuario temporal (no deben aumentar k). Devuelve el id de la primera evaluación.
    """
    from _api_harness import DOMINIOS

    from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase
    from app.core.database import get_db
    from app.domain.models import Evaluacion, UsuarioTemporal
    from app.domain.models.resumen import Resumen
    from app.main import app

    datos, gob = DOMINIOS["DAT"][0], DOMINIOS["GOB"][0]
    gen = app.dependency_overrides[get_db]()
    s = await gen.__anext__()
    try:
        ev_id = 3000
        for i in range(n):
            s.add(UsuarioTemporal(id=300 + i, rubro_id=1))
        await s.flush()
        filas = [(300 + i, PUNTAJES[i % len(PUNTAJES)]) for i in range(n)]
        filas += [(300, 10.0)] * repetidas_de_una
        primera = None
        for temporal, puntaje in filas:
            ev_id += 1
            primera = primera or ev_id
            s.add(Evaluacion(id=ev_id, estado_progreso="completada", usuario_temporal_id=temporal, origen="publica"))
            await s.flush()
            s.add_all([
                Resumen(evaluacion_id=ev_id, dominio_id=datos, puntaje_obtenido=puntaje, total_controles_evaluados=4),
                Resumen(evaluacion_id=ev_id, dominio_id=gob, puntaje_obtenido=puntaje, total_controles_evaluados=4),
            ])
        await s.commit()
        await UpdateBenchmarkUseCase(s).execute()
        return primera
    finally:
        await gen.aclose()


def _correr(escenario):
    from _api_harness import cliente_api

    async def _main():
        async with cliente_api() as c:  # admin: puede ver cualquier evaluación
            await escenario(c)
    asyncio.run(_main())


@api
def test_api_cohorte_de_4_empresas_suprime_todo_y_advierte():
    async def esc(c):
        ev = await _sembrar_cohorte(c, 4)
        j = (await c.get(f"/api/evaluaciones/{ev}/comparativa")).json()
        sector = j["sector"]
        assert j["k_minimo"] == 5 and sector["cohorte_suficiente"] is False
        # C2: nada del sector, ni siquiera cuántas empresas hay
        for campo in ("empresas", "promedio", "mediana", "percentil_25", "percentil_75", "diferencia", "posicion"):
            assert sector[campo] is None, campo
        # C3: advertencia para la interfaz, sin revelar k
        assert sector["advertencia"]["codigo"] == "COHORTE_INSUFICIENTE"
        assert "menos de 5" in sector["advertencia"]["mensaje"] and "4" not in sector["advertencia"]["mensaje"]
        for fila in j["comparativas"]:
            assert fila["cohorte_suficiente"] is False and fila["promedio_industria"] is None
            assert fila["muestras"] is None and fila["diferencia_vs_promedio"] is None
            assert "maximo_industria" not in fila and "minimo_industria" not in fila
        # Tu propio puntaje y la meta siguen disponibles
        assert sector["tu_puntaje"] == 40.0 and j["comparativas"][0]["meta"] == j["meta_puntaje"]
    _correr(esc)


@api
def test_api_cohorte_de_5_empresas_publica_promedio_general_y_por_dimension():
    async def esc(c):
        ev = await _sembrar_cohorte(c, 5)
        j = (await c.get(f"/api/evaluaciones/{ev}/comparativa")).json()
        sector = j["sector"]
        # C1: promedio general del rubro (40, 55, 60, 70, 82 -> 61,4 -> 61)
        assert sector["cohorte_suficiente"] is True and sector["empresas"] == 5
        assert sector["promedio"] == 61 and sector["rubro"] == "Retail"
        assert sector["diferencia"] == -21.0 and sector["posicion"] == "bajo_promedio"
        assert sector["advertencia"] is None
        # Con 5 (< 10) no se publican mediana ni percentiles
        assert sector["mediana"] is None and sector["percentil_25"] is None
        filas = {f["dominio"]: f for f in j["comparativas"]}
        assert filas["Datos"]["promedio_industria"] == 61 and filas["Datos"]["empresas"] == 5
    _correr(esc)


@api
def test_api_repetir_la_encuesta_no_infla_la_cohorte():
    async def esc(c):
        # 4 organizaciones + 6 evaluaciones extra de una de ellas = 10 evaluaciones, k = 4
        ev = await _sembrar_cohorte(c, 4, repetidas_de_una=6)
        j = (await c.get(f"/api/evaluaciones/{ev}/comparativa")).json()
        assert j["sector"]["cohorte_suficiente"] is False
    _correr(esc)


@api
def test_api_benchmark_por_sector_suprime_y_no_publica_extremos():
    async def esc(c):
        await _sembrar_cohorte(c, 4)
        filas = (await c.get("/api/evaluaciones/benchmark", params={"rubro_id": 1})).json()
        assert filas and any(f["dominio_id"] is None for f in filas)  # fila del puntaje general
        for f in filas:
            assert f["cohorte_suficiente"] is False and f["promedio"] is None and f["empresas"] is None
            assert "maximo" not in f and "minimo" not in f and "total_evaluaciones" not in f
    _correr(esc)


@api
def test_api_benchmark_con_cohorte_grande_publica_distribucion():
    async def esc(c):
        await _sembrar_cohorte(c, 10)
        general = next(f for f in (await c.get("/api/evaluaciones/benchmark", params={"rubro_id": 1})).json()
                       if f["dominio_id"] is None)
        assert general["cohorte_suficiente"] and general["empresas"] == 10
        assert None not in (general["mediana"], general["percentil_25"], general["percentil_75"])
    _correr(esc)
