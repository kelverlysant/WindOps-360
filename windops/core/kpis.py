"""Operational KPIs: availability, MTTR, MTBF, downtime and failure counts.

Conventions (documented so results can be checked by hand)
-----------------------------------------------------------
* Every KPI is computed over a half-open window [window_start, window_end).
* Downtime comes from failures only. Preventive maintenance is treated as
  planned downtime and excluded, as in most contractual availability rules.
* An open failure (end = None) is considered still running at window_end.
* Overlapping failures on the same turbine are merged before summing.
* MTTR uses failures that started in the window and are already closed.
* MTBF = operating hours in the window / number of failures that started in it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from windops.core.entities import Component, Failure
from windops.core.intervals import Interval, clip_interval, merge_intervals, total_hours


@dataclass
class TurbineKPIs:
    turbine_id: int
    period_hours: float
    downtime_hours: float
    availability: float  # 0..1
    failure_count: int
    open_failures: int
    mttr_hours: float | None
    mtbf_hours: float | None
    failures_by_component: dict[str, int] = field(default_factory=dict)


def downtime_intervals(failures: list[Failure], window_start: datetime, window_end: datetime) -> list[Interval]:
    """Merged, window-clipped downtime intervals for one turbine's failures."""
    raw: list[Interval] = []
    for failure in failures:
        end = failure.end if failure.end is not None else window_end
        clipped = clip_interval(failure.start, end, window_start, window_end)
        if clipped:
            raw.append(clipped)
    return merge_intervals(raw)


def failures_started_in(failures: list[Failure], window_start: datetime, window_end: datetime) -> list[Failure]:
    return [f for f in failures if window_start <= f.start < window_end]


def mttr_hours(failures: list[Failure]) -> float | None:
    closed = [f for f in failures if f.end is not None]
    if not closed:
        return None
    return sum((f.end - f.start).total_seconds() for f in closed) / 3600 / len(closed)  # type: ignore[operator]


def turbine_kpis(turbine_id: int, failures: list[Failure], window_start: datetime, window_end: datetime) -> TurbineKPIs:
    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")

    period = (window_end - window_start).total_seconds() / 3600
    downtime = total_hours(downtime_intervals(failures, window_start, window_end))
    started = failures_started_in(failures, window_start, window_end)
    operating = period - downtime

    by_component = Counter(f.component.value for f in started)
    return TurbineKPIs(
        turbine_id=turbine_id,
        period_hours=round(period, 2),
        downtime_hours=round(downtime, 2),
        availability=round(operating / period, 4),
        failure_count=len(started),
        open_failures=sum(1 for f in started if f.is_open),
        mttr_hours=None if (m := mttr_hours(started)) is None else round(m, 2),
        mtbf_hours=round(operating / len(started), 2) if started else None,
        failures_by_component={c.value: by_component.get(c.value, 0) for c in Component},
    )
