from datetime import datetime

from windops.core.intervals import clip_interval, merge_intervals, total_hours


def dt(hour: int, day: int = 1) -> datetime:
    return datetime(2025, 1, day, hour)


def test_overlapping_intervals_are_merged():
    # Failure A 08h-16h, failure B 12h-18h -> 10 hours, not 14
    merged = merge_intervals([(dt(8), dt(16)), (dt(12), dt(18))])
    assert merged == [(dt(8), dt(18))]
    assert total_hours(merged) == 10


def test_disjoint_intervals_stay_separate_and_sorted():
    merged = merge_intervals([(dt(14), dt(15)), (dt(8), dt(9))])
    assert merged == [(dt(8), dt(9)), (dt(14), dt(15))]


def test_touching_intervals_are_merged():
    assert merge_intervals([(dt(8), dt(10)), (dt(10), dt(12))]) == [(dt(8), dt(12))]


def test_contained_interval_does_not_extend():
    assert merge_intervals([(dt(8), dt(18)), (dt(10), dt(12))]) == [(dt(8), dt(18))]


def test_clip_interval_cuts_to_window():
    # Failure crossing the end of January
    start, end = datetime(2025, 1, 31, 20), datetime(2025, 2, 1, 4)
    clipped = clip_interval(start, end, datetime(2025, 1, 1), datetime(2025, 2, 1))
    assert clipped == (start, datetime(2025, 2, 1))


def test_clip_interval_outside_window_returns_none():
    assert clip_interval(dt(1), dt(2), dt(5), dt(6)) is None
