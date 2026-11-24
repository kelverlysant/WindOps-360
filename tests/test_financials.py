from datetime import datetime, timedelta

import pytest

from windops.core.entities import Component, Failure, FailureCause, Turbine
from windops.core.financials import (
    energy_loss_by_month,
    energy_loss_cost_brl,
    turbine_energy_loss_mwh,
)
from windops.core.wind import expected_power_mw, wind_speed_at

TURBINE = Turbine(id=1, farm_id=1, code="WT-01", rated_power_mw=3.0, commissioned_at=datetime(2020, 1, 1))
FARM_ID = 1
WINDOW = (datetime(2025, 1, 1), datetime(2026, 1, 1))


def failure(fid, start, end):
    return Failure(id=fid, turbine_id=1, component=Component.GEARBOX, cause=FailureCause.WEAR, start=start, end=end)


def hour_power(at: datetime) -> float:
    return expected_power_mw(wind_speed_at(FARM_ID, at), TURBINE.rated_power_mw)


def test_full_hours_match_manual_sum():
    start = datetime(2025, 9, 1, 8)
    loss = turbine_energy_loss_mwh(TURBINE, FARM_ID, [failure(1, start, start + timedelta(hours=3))], *WINDOW)
    manual = sum(hour_power(start + timedelta(hours=h)) for h in range(3))
    assert loss == pytest.approx(manual)


def test_fractional_hour_is_weighted():
    start = datetime(2025, 9, 1, 10)
    half = turbine_energy_loss_mwh(TURBINE, FARM_ID, [failure(1, start, start + timedelta(minutes=30))], *WINDOW)
    assert half == pytest.approx(hour_power(start) * 0.5)


def test_failure_starting_mid_hour():
    start = datetime(2025, 9, 1, 10, 45)
    end = datetime(2025, 9, 1, 11, 15)
    loss = turbine_energy_loss_mwh(TURBINE, FARM_ID, [failure(1, start, end)], *WINDOW)
    expected = hour_power(datetime(2025, 9, 1, 10)) * 0.25 + hour_power(datetime(2025, 9, 1, 11)) * 0.25
    assert loss == pytest.approx(expected)


def test_overlapping_failures_do_not_double_count_energy():
    a = failure(1, datetime(2025, 9, 1, 8), datetime(2025, 9, 1, 16))
    b = failure(2, datetime(2025, 9, 1, 12), datetime(2025, 9, 1, 18))
    combined = turbine_energy_loss_mwh(TURBINE, FARM_ID, [a, b], *WINDOW)
    single = turbine_energy_loss_mwh(
        TURBINE, FARM_ID, [failure(3, datetime(2025, 9, 1, 8), datetime(2025, 9, 1, 18))], *WINDOW
    )
    assert combined == pytest.approx(single)


def test_open_failure_is_limited_by_window_end():
    f = failure(1, datetime(2025, 12, 31, 22), None)
    loss = turbine_energy_loss_mwh(TURBINE, FARM_ID, [f], *WINDOW)
    expected = hour_power(datetime(2025, 12, 31, 22)) + hour_power(datetime(2025, 12, 31, 23))
    assert loss == pytest.approx(expected)


def test_loss_is_split_by_month():
    start, end = datetime(2025, 1, 31, 22), datetime(2025, 2, 1, 2)
    by_month = energy_loss_by_month(TURBINE, FARM_ID, [(start, end)])
    assert set(by_month) == {"2025-01", "2025-02"}


def test_same_duration_costs_more_in_windy_season():
    def twelve_hours_on(month: int) -> float:
        total = 0.0
        for day in range(1, 29):  # average many days to avoid single-day noise
            start = datetime(2025, month, day, 6)
            total += turbine_energy_loss_mwh(
                TURBINE, FARM_ID, [failure(1, start, start + timedelta(hours=12))], *WINDOW
            )
        return total / 28

    assert twelve_hours_on(9) > 2 * twelve_hours_on(3)


def test_cost_conversion():
    assert energy_loss_cost_brl(10, 250) == 2500
    with pytest.raises(ValueError):
        energy_loss_cost_brl(10, -1)
