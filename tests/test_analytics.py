import pytest

from windops.core.analytics import build_turbine_reports, monthly_loss, summarize
from windops.core.criticality import CriticalityInput, criticality_scores
from windops.core.generator import generate_dataset, history_window


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset()


@pytest.fixture(scope="module")
def reports(dataset):
    return build_turbine_reports(dataset, *history_window())


def test_generator_is_reproducible():
    a, b = generate_dataset(seed=1), generate_dataset(seed=1)
    assert [(f.start, f.end, f.component) for f in a.failures] == [(f.start, f.end, f.component) for f in b.failures]


def test_generator_default_shape(dataset):
    assert len(dataset.companies) == 2
    assert len(dataset.farms) == 4
    assert len(dataset.turbines) == 12
    assert dataset.failures, "expected some failures"


def test_corrective_maintenance_for_every_closed_failure(dataset):
    closed = {f.id for f in dataset.failures if f.end is not None}
    corrective = {m.failure_id for m in dataset.maintenances if m.failure_id is not None}
    assert closed == corrective


def test_generated_failures_stay_inside_history(dataset):
    start, end = history_window()
    assert all(start <= f.start < end for f in dataset.failures)
    assert all(f.end is None or f.end <= end for f in dataset.failures)


def test_tenant_filter_isolates_data(dataset):
    only_first = dataset.for_company(1)
    farm_ids = {f.id for f in only_first.farms}
    assert all(f.company_id == 1 for f in only_first.farms)
    assert all(t.farm_id in farm_ids for t in only_first.turbines)
    turbine_ids = {t.id for t in only_first.turbines}
    assert all(f.turbine_id in turbine_ids for f in only_first.failures)


def test_reports_sorted_by_criticality(reports):
    scores = [r.criticality for r in reports]
    assert scores == sorted(scores, reverse=True)
    assert len(reports) == 12


def test_company_summary_adds_up(reports):
    summary = summarize(reports, "company")
    assert sum(row["loss_brl"] for row in summary) == pytest.approx(sum(r.loss_brl for r in reports), abs=0.05)


def test_monthly_loss_adds_up(reports):
    rows = monthly_loss(reports)
    assert sum(row["energy_loss_mwh"] for row in rows) == pytest.approx(
        sum(r.energy_loss_mwh for r in reports), abs=0.1
    )


def test_criticality_extremes():
    items = [
        CriticalityInput(1, loss_brl=0, failure_count=0, downtime_hours=0, mttr_hours=None),
        CriticalityInput(2, loss_brl=1000, failure_count=10, downtime_hours=100, mttr_hours=10),
    ]
    assert criticality_scores(items) == {1: 0.0, 2: 100.0}


def test_criticality_all_equal_is_zero():
    items = [CriticalityInput(i, 5, 1, 1, 1) for i in range(3)]
    assert set(criticality_scores(items).values()) == {0.0}
