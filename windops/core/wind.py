"""Synthetic wind resource and turbine power curve.

Design notes
------------
* Wind is simulated **hour by hour**, not as a monthly average. Because the
  power curve is non-linear (cubic), applying it to a monthly mean speed
  badly underestimates energy. Each hour draws a speed from a Weibull
  distribution (shape k = 2, the usual assumption for wind) whose mean
  follows a seasonal profile.
* The draw is deterministic: the same farm and hour always return the same
  speed, so results are reproducible without storing a wind time series.
* The seasonal profile is inspired by Brazil's Northeast, where the windy
  season peaks around August-October and the calmest months are around
  March-April.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from windops.core.entities import PowerCurve

WEIBULL_SHAPE = 2.0
# Mean of a Weibull(k=2) is scale * Gamma(1.5)
_WEIBULL_MEAN_FACTOR = math.gamma(1 + 1 / WEIBULL_SHAPE)

_EPOCH = datetime(2000, 1, 1)


@dataclass(frozen=True)
class WindProfile:
    """Seasonal wind characteristics of a farm."""

    annual_mean_ms: float = 8.0
    seasonal_amplitude_ms: float = 2.5
    peak_day_of_year: int = 245  # early September

    def seasonal_mean_ms(self, at: datetime) -> float:
        day = at.timetuple().tm_yday
        phase = 2 * math.pi * (day - self.peak_day_of_year) / 365.25
        return max(0.5, self.annual_mean_ms + self.seasonal_amplitude_ms * math.cos(phase))


def _hour_index(at: datetime) -> int:
    return int((at - _EPOCH).total_seconds() // 3600)


def wind_speed_at(farm_id: int, at: datetime, profile: WindProfile | None = None) -> float:
    """Hourly wind speed (m/s) at a farm. Constant within each clock hour."""
    profile = profile or WindProfile()
    mean = profile.seasonal_mean_ms(at)
    scale = mean / _WEIBULL_MEAN_FACTOR
    # Integer-only seed: Python hashes ints deterministically across runs.
    rng = random.Random(farm_id * 1_000_003 + _hour_index(at))
    return rng.weibullvariate(scale, WEIBULL_SHAPE)


def expected_power_mw(wind_speed_ms: float, rated_power_mw: float, curve: PowerCurve | None = None) -> float:
    """Expected electrical output (MW) for a given wind speed.

    * below cut-in or at/above cut-out: 0 (turbine idle or shut down for safety)
    * between cut-in and rated: grows with v^3
    * between rated and cut-out: rated power
    """
    curve = curve or PowerCurve()
    v = wind_speed_ms
    if v < curve.cut_in_ms or v >= curve.cut_out_ms:
        return 0.0
    if v >= curve.rated_ms:
        return rated_power_mw
    fraction = (v**3 - curve.cut_in_ms**3) / (curve.rated_ms**3 - curve.cut_in_ms**3)
    return rated_power_mw * fraction


@lru_cache(maxsize=1024)
def mean_wind_speed(farm_id: int, start: datetime, end: datetime, profile: WindProfile | None = None) -> float:
    """Average hourly wind speed (m/s) at a farm over [start, end).

    Cached: the synthetic wind is deterministic, so the same farm and window
    always give the same answer.
    """
    hour = start.replace(minute=0, second=0, microsecond=0)
    total, count = 0.0, 0
    while hour < end:
        total += wind_speed_at(farm_id, hour, profile)
        count += 1
        hour += timedelta(hours=1)
    return total / count if count else 0.0
