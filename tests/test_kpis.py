from datetime import datetime

import pytest

from windops.core.entities import Component, Failure, FailureCause
from windops.core.kpis import turbine_kpis

JAN_START = datetime(2025, 1, 1)
FEB_START = datetime(2025, 2, 1)
JAN_HOURS = 31 * 24


def failure(fid, start, end, component=Component.SENSOR):
    return Failure(id=fid, turbine_id=1, component=component, cause=FailureCause.WEAR, start=start, end=end)


def test_no_failures_means_full_availability():
    k = turbine_kpis(1, [], JAN_START, FEB_START)
    assert k.availability == 1.0
    assert k.downtime_hours == 0
    assert k.mttr_hours is None and k.mtbf_hours is None


def test_overlapping_failures_count_downtime_once():
    failures = [
        failure(1, datetime(2025, 1, 10, 8), datetime(2025, 1, 10, 16)),
        failure(2, datetime(2025, 1, 10, 12), datetime(2025, 1, 10, 18), Component.ELECTRICAL),
    ]
    k = turbine_kpis(1, failures, JAN_START, FEB_START)
    assert k.downtime_hours == 10
    assert k.availability == pytest.approx((JAN_HOURS - 10) / JAN_HOURS, abs=1e-4)
    assert k.failure_count == 2
    assert k.mttr_hours == 7  # (8 + 6) / 2
    assert k.failures_by_component["Sensor"] == 1
    assert k.failures_by_component["Electrical"] == 1


def test_failure_crossing_month_end_is_split():
    f = failure(1, datetime(2025, 1, 31, 20), datetime(2025, 2, 1, 6))
    january = turbine_kpis(1, [f], JAN_START, FEB_START)
    february = turbine_kpis(1, [f], FEB_START, datetime(2025, 3, 1))
    assert january.downtime_hours == 4
    assert february.downtime_hours == 6
    # The failure is counted in the month it started
    assert january.failure_count == 1
    assert february.failure_count == 0


def test_open_failure_runs_until_window_end():
    f = failure(1, datetime(2025, 1, 31, 12), None)
    k = turbine_kpis(1, [f], JAN_START, FEB_START)
    assert k.downtime_hours == 12
    assert k.open_failures == 1
    assert k.mttr_hours is None  # open failures do not enter MTTR


def test_mtbf_uses_operating_hours():
    failures = [
        failure(1, datetime(2025, 1, 5), datetime(2025, 1, 5, 10)),
        failure(2, datetime(2025, 1, 20), datetime(2025, 1, 20, 10)),
    ]
    k = turbine_kpis(1, failures, JAN_START, FEB_START)
    assert k.mtbf_hours == (JAN_HOURS - 20) / 2


def test_invalid_window_raises():
    with pytest.raises(ValueError):
        turbine_kpis(1, [], FEB_START, JAN_START)


def test_failure_cannot_end_before_start():
    with pytest.raises(ValueError):
        failure(1, datetime(2025, 1, 2), datetime(2025, 1, 1))
