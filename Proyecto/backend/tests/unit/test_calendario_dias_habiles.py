"""T-18: la gracia del contrato y el bloqueo ARCOP cuentan días hábiles (lunes a viernes sin feriados de Chile)."""
import logging
from datetime import date, datetime

import pytest

from app.application.arcop.casos_uso.gestionar_solicitud_arcop import _sumar_dias, _sumar_dias_habiles
from app.core.config import settings
from app.core.feriados import FERIADOS_CHILE
from app.domain import calendario
from app.domain.calendario import sumar_dias_habiles
from app.domain.contrato.vigencia import fin_de_gracia


@pytest.fixture(autouse=True)
def _sin_avisos_previos():
    calendario._AVISADOS.clear()
    yield
    calendario._AVISADOS.clear()


def test_calendario_cargado_para_2026_y_2027():
    assert set(settings.FERIADOS_CL) >= {2026, 2027}
    assert date(2026, 9, 18) in settings.FERIADOS_CL[2026] and date(2027, 12, 25) in settings.FERIADOS_CL[2027]


def test_gracia_desde_un_viernes_son_30_dias_habiles_sin_fines_de_semana_ni_feriados():
    # Viernes 04-sep-2026. El día de partida no cuenta. A mano:
    #   7-11 sep = 5 | 14-18 sep = 4 (vie 18 feriado) = 9 | 21-25 sep = 14 | 28 sep-2 oct = 19
    #   5-9 oct = 24 | lun 12 oct feriado; 13-16 oct = 28 | lun 19 oct = 29 | mar 20 oct = 30
    inicio = date(2026, 9, 4)
    assert inicio.weekday() == 4
    assert fin_de_gracia(inicio, None, 30, FERIADOS_CHILE) == date(2026, 10, 20)
    # Sin feriados serían 6 semanas exactas: viernes 16-oct (los dos feriados empujan 2 días hábiles).
    assert fin_de_gracia(inicio, None, 30, {2026: ()}) == date(2026, 10, 16)


def test_bloqueo_arcop_que_cruza_un_feriado_vence_un_dia_habil_despues(monkeypatch):
    jueves = datetime(2026, 9, 17, 10, 0)
    monkeypatch.setattr(settings, "FERIADOS_CL", {2026: ()})
    sin_feriado = _sumar_dias_habiles(jueves, 2)          # vie 18 + lun 21
    monkeypatch.setattr(settings, "FERIADOS_CL", FERIADOS_CHILE)
    con_feriado = _sumar_dias_habiles(jueves, 2)          # 18 y 19 feriados: lun 21 + mar 22
    assert sin_feriado == datetime(2026, 9, 21, 10, 0)
    assert con_feriado == datetime(2026, 9, 22, 10, 0)


def test_anio_sin_feriados_cargados_advierte_una_vez_y_no_falla(caplog):
    assert 2028 not in FERIADOS_CHILE
    with caplog.at_level(logging.WARNING, logger="app.domain.calendario"):
        with pytest.warns(RuntimeWarning, match="2028"):
            fin = sumar_dias_habiles(date(2028, 3, 3), 2, FERIADOS_CHILE)   # viernes: lun 6 + mar 7
        sumar_dias_habiles(date(2028, 3, 3), 2, FERIADOS_CHILE)
    assert fin == date(2028, 3, 7)
    assert len([r for r in caplog.records if "2028" in r.getMessage()]) == 1


def test_plazo_de_30_dias_corridos_para_responder_arcop_no_cambia():
    assert _sumar_dias(datetime(2026, 9, 1, 9, 0), 30) == datetime(2026, 10, 1, 9, 0)
    assert _sumar_dias(datetime(2026, 9, 17, 9, 0), 30) == datetime(2026, 10, 17, 9, 0)   # cruza feriados y sábados
    assert _sumar_dias(datetime(2026, 9, 1), None) is None
