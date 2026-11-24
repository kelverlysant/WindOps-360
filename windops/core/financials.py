"""Lost energy and its financial impact.

For each hour a turbine was down, we look up the farm's wind speed, convert
it to expected power with the power curve, and multiply by the fraction of
that hour the turbine was actually stopped. Downtime intervals are merged
first, so overlapping failures never double-count energy.

    Impact (R$) = Lost energy (MWh) x Price (R$/MWh)

The default price (R$ 250/MWh) is a didactic assumption, not a market quote.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from windops.core.entities import Failure, Turbine
from windops.core.intervals import Interval
from windops.core.kpis import downtime_intervals
from windops.core.wind import WindProfile, expected_power_mw, wind_speed_at

DEFAULT_PRICE_BRL_PER_MWH = 250.0
_ONE_HOUR = timedelta(hours=1)

MonthKey = str  # "YYYY-MM"


def _floor_hour(at: datetime) -> datetime:
    return at.replace(minute=0, second=0, microsecond=0)


def energy_loss_by_month(
    turbine: Turbine,
    farm_id: int,
    intervals: list[Interval],
    profile: WindProfile | None = None,
) -> dict[MonthKey, float]:
    """Lost energy (MWh) per calendar month for already-merged intervals.

    Partial hours are weighted by the fraction actually stopped, so a failure
    from 10:00 to 10:30 counts half an hour, not a full one.
    """
    by_month: dict[MonthKey, float] = defaultdict(float)
    for start, end in intervals:
        cursor = start
        while cursor < end:
            hour_start = _floor_hour(cursor)
            segment_end = min(end, hour_start + _ONE_HOUR)
            fraction = (segment_end - cursor).total_seconds() / 3600
            speed = wind_speed_at(farm_id, hour_start, profile)
            power = expected_power_mw(speed, turbine.rated_power_mw, turbine.power_curve)
            by_month[hour_start.strftime("%Y-%m")] += power * fraction
            cursor = segment_end
    return dict(by_month)


def turbine_energy_loss_mwh(
    turbine: Turbine,
    farm_id: int,
    failures: list[Failure],
    window_start: datetime,
    window_end: datetime,
    profile: WindProfile | None = None,
) -> float:
    intervals = downtime_intervals(failures, window_start, window_end)
    return sum(energy_loss_by_month(turbine, farm_id, intervals, profile).values())


def energy_loss_cost_brl(energy_mwh: float, price_brl_per_mwh: float = DEFAULT_PRICE_BRL_PER_MWH) -> float:
    if price_brl_per_mwh < 0:
        raise ValueError("Price cannot be negative")
    return energy_mwh * price_brl_per_mwh
