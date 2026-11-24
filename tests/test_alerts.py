from datetime import datetime, timedelta

from windops.core.alerts import CRITICAL, WARNING, AlertThresholds, build_alerts
from windops.core.analytics import build_turbine_reports
from windops.core.criticality import CriticalityInput, criticality_breakdown, criticality_scores
from windops.core.entities import Company, Component, Dataset, Failure, FailureCause, Turbine, WindFarm

START, END = datetime(2025, 1, 1), datetime(2025, 7, 1)


def fleet(failures: list[Failure]) -> Dataset:
    return Dataset(
        companies=[Company(1, "AeroVento")],
        farms=[WindFarm(1, 1, "Farm 01", "RN")],
        turbines=[Turbine(i, 1, f"WT-0{i}", 3.0, datetime(2020, 1, 1)) for i in (1, 2, 3)],
        failures=failures,
    )


def failure(fid, turbine_id, start, hours, component=Component.SENSOR):
    end = None if hours is None else start + timedelta(hours=hours)
    return Failure(fid, turbine_id, component, FailureCause.WEAR, start, end)


def alerts_for(failures, thresholds=None):
    data = fleet(failures)
    reports = build_turbine_reports(data, START, END)
    return build_alerts(data, reports, START, END, thresholds)


def test_no_failures_no_alerts():
    assert alerts_for([]) == []


def test_recent_open_failure_is_warning():
    alerts = alerts_for([failure(1, 1, END - timedelta(hours=10), None)])
    assert [(a.kind, a.severity) for a in alerts] == [("open_failure", WARNING)]


def test_old_open_failure_is_critical():
    alerts = [a for a in alerts_for([failure(1, 1, END - timedelta(hours=100), None)]) if a.kind == "open_failure"]
    assert alerts[0].severity == CRITICAL


def test_low_availability_levels():
    period = (END - START).total_seconds() / 3600
    warning = alerts_for([failure(1, 1, datetime(2025, 2, 1), 0.04 * period)])
    critical = alerts_for([failure(1, 1, datetime(2025, 2, 1), 0.06 * period)])
    assert [a.severity for a in warning if a.kind == "low_availability"] == [WARNING]
    assert [a.severity for a in critical if a.kind == "low_availability"] == [CRITICAL]


def test_slow_repair_compared_to_fleet():
    failures = [
        failure(1, 1, datetime(2025, 2, 1), 2),
        failure(2, 2, datetime(2025, 2, 1), 2),
        failure(3, 3, datetime(2025, 2, 1), 20),
    ]
    slow = [a for a in alerts_for(failures) if a.kind == "slow_repair"]
    assert [a.turbine_id for a in slow] == [3]


def test_recurrence_needs_three_in_ninety_days():
    spaced = [failure(i, 1, datetime(2025, 1, 5) + timedelta(days=60 * i), 2) for i in range(3)]
    close = [failure(i, 1, datetime(2025, 1, 5) + timedelta(days=20 * i), 2) for i in range(3)]
    assert not [a for a in alerts_for(spaced) if a.kind == "recurrence"]
    assert [a.title for a in alerts_for(close) if a.kind == "recurrence"] == ["Sensor falhou 3 vezes em 90 dias"]


def test_recurrence_ignores_other_components():
    mixed = [
        failure(1, 1, datetime(2025, 1, 5), 2, Component.SENSOR),
        failure(2, 1, datetime(2025, 1, 15), 2, Component.GEARBOX),
        failure(3, 1, datetime(2025, 1, 25), 2, Component.SENSOR),
    ]
    assert not [a for a in alerts_for(mixed) if a.kind == "recurrence"]


def test_critical_alerts_come_first():
    alerts = alerts_for(
        [failure(1, 1, END - timedelta(hours=200), None), failure(2, 2, END - timedelta(hours=5), None)],
        AlertThresholds(availability_warning=0.0, availability_critical=0.0),
    )
    assert alerts[0].severity == CRITICAL


def test_breakdown_adds_up_to_score():
    items = [CriticalityInput(1, 100, 1, 10, 5), CriticalityInput(2, 900, 4, 50, 30), CriticalityInput(3, 400, 2, 5, 1)]
    scores = criticality_scores(items)
    for turbine_id, points in criticality_breakdown(items).items():
        assert round(sum(points.values()), 1) == scores[turbine_id]


def test_stopped_at_end_flags_running_failures():
    data = fleet(
        [
            failure(1, 1, END - timedelta(hours=5), None),  # open
            failure(2, 2, END - timedelta(hours=5), 10),  # ends after the window
            failure(3, 3, START + timedelta(days=1), 5),  # closed long ago
        ]
    )
    status = {r.turbine_id: r.stopped_at_end for r in build_turbine_reports(data, START, END)}
    assert status == {1: True, 2: True, 3: False}


def test_reports_carry_farm_mean_wind():
    reports = build_turbine_reports(fleet([]), START, END)
    assert len({r.mean_wind_ms for r in reports}) == 1  # same farm, same wind
    assert reports[0].mean_wind_ms > 0
