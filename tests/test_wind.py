from datetime import datetime

import pytest

from windops.core.entities import PowerCurve
from windops.core.wind import WindProfile, expected_power_mw, wind_speed_at

CURVE = PowerCurve(cut_in_ms=3.0, rated_ms=12.0, cut_out_ms=25.0)


@pytest.mark.parametrize("speed", [0.0, 1.5, 2.99])
def test_no_power_below_cut_in(speed):
    assert expected_power_mw(speed, 3.0, CURVE) == 0.0


@pytest.mark.parametrize("speed", [12.0, 15.0, 24.9])
def test_rated_power_between_rated_and_cut_out(speed):
    assert expected_power_mw(speed, 3.0, CURVE) == 3.0


@pytest.mark.parametrize("speed", [25.0, 30.0])
def test_no_power_at_or_above_cut_out(speed):
    assert expected_power_mw(speed, 3.0, CURVE) == 0.0


def test_power_grows_with_cube_of_speed():
    p6 = expected_power_mw(6.0, 3.0, CURVE)
    p9 = expected_power_mw(9.0, 3.0, CURVE)
    expected_ratio = (9**3 - 3**3) / (6**3 - 3**3)
    assert p9 / p6 == pytest.approx(expected_ratio)
    assert 0 < p6 < p9 < 3.0


def test_wind_is_reproducible_for_same_farm_and_hour():
    at = datetime(2025, 9, 1, 14)
    assert wind_speed_at(1, at) == wind_speed_at(1, at)


def test_wind_is_constant_within_an_hour():
    assert wind_speed_at(1, datetime(2025, 9, 1, 14, 0)) == wind_speed_at(1, datetime(2025, 9, 1, 14, 59))


def test_different_farms_have_different_wind():
    at = datetime(2025, 9, 1, 14)
    assert wind_speed_at(1, at) != wind_speed_at(2, at)


def test_windy_season_is_stronger_than_calm_season():
    def monthly_mean(month: int) -> float:
        speeds = [wind_speed_at(1, datetime(2025, month, day, hour)) for day in range(1, 29) for hour in range(24)]
        return sum(speeds) / len(speeds)

    assert monthly_mean(9) > monthly_mean(3) + 2


def test_seasonal_mean_peaks_near_september():
    profile = WindProfile()
    assert profile.seasonal_mean_ms(datetime(2025, 9, 2)) > profile.seasonal_mean_ms(datetime(2025, 3, 2))


def test_mean_wind_follows_season():
    from windops.core.wind import mean_wind_speed

    september = mean_wind_speed(1, datetime(2025, 9, 1), datetime(2025, 10, 1))
    march = mean_wind_speed(1, datetime(2025, 3, 1), datetime(2025, 4, 1))
    assert september > march
    assert 3 < march < september < 15


def test_mean_wind_empty_window_is_zero():
    from windops.core.wind import mean_wind_speed

    assert mean_wind_speed(1, datetime(2025, 1, 1), datetime(2025, 1, 1)) == 0.0
