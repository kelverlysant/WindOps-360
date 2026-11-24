"""API tests against an in-memory SQLite database seeded with the synthetic scenario."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from windops.api.main import app
from windops.core.generator import generate_dataset
from windops.db.models import Base
from windops.db.repository import save_dataset
from windops.db.session import get_session


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestSession() as session:
        save_dataset(session, generate_dataset())
        session.commit()

    def override():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_catalog(client):
    assert len(client.get("/companies").json()) == 2
    assert len(client.get("/windfarms", params={"company_id": 1}).json()) == 2
    assert len(client.get("/turbines", params={"company_id": 2}).json()) == 6
    assert client.get("/companies/999").status_code == 404


def test_tenant_filter_never_leaks_other_company(client):
    farm_ids = {f["id"] for f in client.get("/windfarms", params={"company_id": 1}).json()}
    turbines = client.get("/turbines", params={"company_id": 1}).json()
    assert all(t["farm_id"] in farm_ids for t in turbines)
    turbine_ids = {t["id"] for t in turbines}
    failures = client.get("/failures", params={"company_id": 1, "limit": 2000}).json()
    assert failures and all(f["turbine_id"] in turbine_ids for f in failures)
    reports = client.get("/kpis/turbines", params={"company_id": 1}).json()
    assert {r["company_id"] for r in reports} == {1}


def test_create_and_close_failure(client):
    payload = {
        "turbine_id": 1,
        "component": "Gearbox",
        "cause": "Wear",
        "started_at": "2025-12-30T08:00:00",
    }
    created = client.post("/failures", json=payload)
    assert created.status_code == 201
    failure = created.json()
    assert failure["ended_at"] is None

    assert client.get("/failures", params={"turbine_id": 1, "state": "open"}).json()[0]["id"] == failure["id"]

    closed = client.patch(f"/failures/{failure['id']}/close", json={"ended_at": "2025-12-30T20:30:00"})
    assert closed.status_code == 200
    assert closed.json()["duration_hours"] == 12.5
    assert client.patch(f"/failures/{failure['id']}/close", json={"ended_at": "2025-12-31T00:00:00"}).status_code == 409


def test_failure_validation(client):
    bad_dates = {
        "turbine_id": 1,
        "component": "Sensor",
        "cause": "Wear",
        "started_at": "2025-12-30T08:00:00",
        "ended_at": "2025-12-29T08:00:00",
    }
    assert client.post("/failures", json=bad_dates).status_code == 422
    bad_component = {**bad_dates, "component": "Rotor", "ended_at": None}
    assert client.post("/failures", json=bad_component).status_code == 422
    missing_turbine = {**bad_dates, "turbine_id": 999, "ended_at": None}
    assert client.post("/failures", json=missing_turbine).status_code == 404


def test_corrective_maintenance_rules(client):
    base = {
        "turbine_id": 1,
        "type": "Corrective",
        "started_at": "2025-12-30T08:00:00",
        "ended_at": "2025-12-30T12:00:00",
        "technician": "Ana Lima",
    }
    assert client.post("/maintenances", json=base).status_code == 422  # missing failure_id

    other_turbine_failure = client.get("/failures", params={"turbine_id": 2}).json()[0]["id"]
    assert client.post("/maintenances", json={**base, "failure_id": other_turbine_failure}).status_code == 422

    own_failure = client.get("/failures", params={"turbine_id": 1}).json()[0]["id"]
    created = client.post("/maintenances", json={**base, "failure_id": own_failure, "parts_used": ["Oil filter"]})
    assert created.status_code == 201


def test_new_failure_increases_lost_energy(client):
    params = {"start": "2025-09-01T00:00:00", "end": "2025-10-01T00:00:00"}
    before = client.get("/overview", params=params).json()
    client.post(
        "/failures",
        json={
            "turbine_id": 1,
            "component": "Generator",
            "cause": "Wear",
            "started_at": "2025-09-10T00:00:00",
            "ended_at": "2025-09-12T00:00:00",
        },
    )
    after = client.get("/overview", params=params).json()
    assert after["energy_loss_mwh"] >= before["energy_loss_mwh"]
    assert after["failure_count"] == before["failure_count"] + 1


def test_analytics_endpoints_are_consistent(client):
    reports = client.get("/kpis/turbines").json()
    summary = client.get("/financials/summary").json()
    monthly = client.get("/financials/monthly").json()
    overview = client.get("/overview").json()
    total = sum(r["loss_brl"] for r in reports)
    assert sum(s["loss_brl"] for s in summary) == pytest.approx(total, abs=0.05)
    assert sum(m["loss_brl"] for m in monthly) == pytest.approx(total, rel=1e-3)
    assert overview["loss_brl"] == pytest.approx(total, abs=0.05)
    assert len(client.get("/financials/summary", params={"level": "farm"}).json()) == 4


def test_ranking(client):
    by_criticality = client.get("/ranking", params={"limit": 3}).json()
    assert len(by_criticality) == 3
    by_loss = client.get("/ranking", params={"by": "loss", "limit": 12}).json()
    losses = [r["loss_brl"] for r in by_loss]
    assert losses == sorted(losses, reverse=True)


def test_price_changes_financial_impact(client):
    cheap = client.get("/overview", params={"price": 100}).json()
    expensive = client.get("/overview", params={"price": 200}).json()
    assert expensive["loss_brl"] == pytest.approx(2 * cheap["loss_brl"], rel=1e-6)


def test_invalid_window(client):
    params = {"start": "2025-02-01T00:00:00", "end": "2025-01-01T00:00:00"}
    assert client.get("/overview", params=params).status_code == 422


def test_alerts_endpoint(client):
    alerts = client.get("/alerts").json()
    assert alerts, "synthetic scenario should raise at least one alert"
    severities = [a["severity"] for a in alerts]
    assert severities == sorted(severities, key=lambda s: s != "critical")
    lenient = client.get("/alerts", params={"availability_target": 0.5}).json()
    assert not [a for a in lenient if a["kind"] == "low_availability"]


def test_reports_expose_breakdown_and_monthly_loss(client):
    report = client.get("/kpis/turbines").json()[0]
    assert round(sum(report["criticality_breakdown"].values()), 1) == report["criticality"]
    assert report["loss_by_month_mwh"]


def test_event_date_filters(client):
    params = {"start": "2025-03-01T00:00:00", "end": "2025-04-01T00:00:00", "limit": 2000}
    failures = client.get("/failures", params=params).json()
    assert all("2025-03" in f["started_at"] for f in failures)
    maint = client.get("/maintenances", params=params).json()
    assert all("2025-03" in m["started_at"] for m in maint)
