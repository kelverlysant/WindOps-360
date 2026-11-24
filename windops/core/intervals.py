"""Time-interval helpers.

Downtime must never be counted twice. If failure A runs 08h-16h and
failure B runs 12h-18h on the same turbine, the turbine was stopped for
10 hours, not 14. Every downtime-based metric (availability, lost energy)
goes through `merge_intervals` first.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

Interval = tuple[datetime, datetime]


def clip_interval(start: datetime, end: datetime, window_start: datetime, window_end: datetime) -> Interval | None:
    """Cut an interval to a window. Returns None when they do not overlap."""
    clipped_start = max(start, window_start)
    clipped_end = min(end, window_end)
    if clipped_end <= clipped_start:
        return None
    return clipped_start, clipped_end


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    """Merge overlapping or touching intervals into a sorted, disjoint list."""
    ordered = sorted(intervals, key=lambda item: item[0])
    merged: list[Interval] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            last_start, last_end = merged[-1]
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def total_hours(intervals: Iterable[Interval]) -> float:
    return sum((end - start).total_seconds() for start, end in intervals) / 3600
