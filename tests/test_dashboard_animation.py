"""Rules that turn data into rotor speed in the dashboard's animated turbines."""

import base64

from windops.dashboard.components import (
    MAX_PERIOD_S,
    MIN_PERIOD_S,
    availability_factor,
    rotor_period_from_wind,
    turbine_status,
    turbine_svg,
)


def test_rotor_stops_below_cut_in():
    assert rotor_period_from_wind(2.5, cut_in_ms=3.0) is None


def test_more_wind_spins_faster():
    assert rotor_period_from_wind(10) < rotor_period_from_wind(6)


def test_rotor_period_is_clamped():
    assert rotor_period_from_wind(100) == MIN_PERIOD_S
    assert rotor_period_from_wind(3.0) <= MAX_PERIOD_S


def test_availability_factor_range():
    assert availability_factor(1.0, 0.97) == 1.0
    assert availability_factor(0.80, 0.97) == 0.15
    assert availability_factor(0.99, 0.97) > availability_factor(0.95, 0.97)


def test_status_priority():
    assert turbine_status(True, 0.99, 0.97)[1] == "parada"
    assert turbine_status(False, 0.90, 0.97)[1] == "abaixo da meta"
    assert turbine_status(False, 0.99, 0.97)[1] == "operando"


def _svg_inside(img_tag: str) -> str:
    return base64.b64decode(img_tag.split("base64,")[1].split('"')[0]).decode()


def test_svg_animates_only_when_running():
    running = _svg_inside(turbine_svg(2.0, "#2F8F5B", 100))
    still = _svg_inside(turbine_svg(None, "#C8362B", 100))
    assert "animation:spin 2.00s" in running and "prefers-reduced-motion" in running
    assert "animation" not in still and "#C8362B" in still
