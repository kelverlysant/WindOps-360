"""High-level reports that combine KPIs, lost energy and criticality.

This is the single entry point used by the API and the dashboard, so every
screen shows numbers produced by the same rules.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime

from windops.core.criticality import CriticalityInput, criticality_breakdown
from windops.core.entities import Dataset
from windops.core.financials import DEFAULT_PRICE_BRL_PER_MWH, energy_loss_by_month, energy_loss_cost_brl
from windops.core.kpis import downtime_intervals, turbine_kpis
from windops.core.wind import mean_wind_speed


@dataclass
class TurbineReport:
    company_id: int
    company_name: str
    farm_id: int
    farm_name: str
    turbine_id: int
    turbine_code: str
    rated_power_mw: float
    period_hours: float
    downtime_hours: float
    availability: float
    failure_count: int
    open_failures: int
    mttr_hours: float | None
    mtbf_hours: float | None
    energy_loss_mwh: float
    loss_brl: float
    criticality: float
    failures_by_component: dict[str, int]
    loss_by_month_mwh: dict[str, float]
    criticality_breakdown: dict[str, float] = field(default_factory=dict)
    mean_wind_ms: float = 0.0  # farm's average wind in the window
    stopped_at_end: bool = False  # a failure is still running at the end of the window

    def to_dict(self) -> dict:
        return asdict(self)


def build_turbine_reports(
    dataset: Dataset,
    window_start: datetime,
    window_end: datetime,
    price_brl_per_mwh: float = DEFAULT_PRICE_BRL_PER_MWH,
) -> list[TurbineReport]:
    """One report per turbine, sorted by criticality (highest first)."""
    farms = dataset.farm_by_id()
    companies = dataset.company_by_id()
    failures = dataset.failures_by_turbine()

    wind_by_farm = {farm_id: mean_wind_speed(farm_id, window_start, window_end) for farm_id in farms}

    reports: list[TurbineReport] = []
    for turbine in dataset.turbines:
        farm = farms[turbine.farm_id]
        company = companies[farm.company_id]
        turbine_failures = failures.get(turbine.id, [])

        kpis = turbine_kpis(turbine.id, turbine_failures, window_start, window_end)
        intervals = downtime_intervals(turbine_failures, window_start, window_end)
        by_month = energy_loss_by_month(turbine, farm.id, intervals)
        energy = sum(by_month.values())

        reports.append(
            TurbineReport(
                company_id=company.id,
                company_name=company.name,
                farm_id=farm.id,
                farm_name=farm.name,
                turbine_id=turbine.id,
                turbine_code=turbine.code,
                rated_power_mw=turbine.rated_power_mw,
                period_hours=kpis.period_hours,
                downtime_hours=kpis.downtime_hours,
                availability=kpis.availability,
                failure_count=kpis.failure_count,
                open_failures=kpis.open_failures,
                mttr_hours=kpis.mttr_hours,
                mtbf_hours=kpis.mtbf_hours,
                energy_loss_mwh=round(energy, 3),
                loss_brl=round(energy_loss_cost_brl(energy, price_brl_per_mwh), 2),
                criticality=0.0,
                failures_by_component=kpis.failures_by_component,
                loss_by_month_mwh={k: round(v, 3) for k, v in sorted(by_month.items())},
                mean_wind_ms=round(wind_by_farm[farm.id], 2),
                stopped_at_end=any(
                    f.start < window_end and (f.end is None or f.end > window_end) for f in turbine_failures
                ),
            )
        )

    breakdown = criticality_breakdown(
        [CriticalityInput(r.turbine_id, r.loss_brl, r.failure_count, r.downtime_hours, r.mttr_hours) for r in reports]
    )
    for report in reports:
        points = breakdown[report.turbine_id]
        report.criticality = round(sum(points.values()), 1)
        report.criticality_breakdown = {name: round(value, 2) for name, value in points.items()}

    reports.sort(key=lambda r: (-r.criticality, -r.loss_brl))
    return reports


def summarize(reports: list[TurbineReport], level: str) -> list[dict]:
    """Aggregate turbine reports by 'company' or 'farm'."""
    if level not in {"company", "farm"}:
        raise ValueError("level must be 'company' or 'farm'")

    groups: dict[int, list[TurbineReport]] = defaultdict(list)
    for report in reports:
        groups[report.company_id if level == "company" else report.farm_id].append(report)

    rows = []
    for key, items in groups.items():
        period = sum(r.period_hours for r in items)
        downtime = sum(r.downtime_hours for r in items)
        row = {
            "company_id": items[0].company_id,
            "company_name": items[0].company_name,
            "turbines": len(items),
            "failure_count": sum(r.failure_count for r in items),
            "open_failures": sum(r.open_failures for r in items),
            "downtime_hours": round(downtime, 2),
            "availability": round(1 - downtime / period, 4) if period else None,
            "energy_loss_mwh": round(sum(r.energy_loss_mwh for r in items), 3),
            "loss_brl": round(sum(r.loss_brl for r in items), 2),
        }
        if level == "farm":
            row = {"farm_id": key, "farm_name": items[0].farm_name, **row}
        rows.append(row)
    rows.sort(key=lambda row: -row["loss_brl"])
    return rows


def monthly_loss(reports: list[TurbineReport], price_brl_per_mwh: float = DEFAULT_PRICE_BRL_PER_MWH) -> list[dict]:
    """Lost energy and cost per month and company."""
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for report in reports:
        for month, mwh in report.loss_by_month_mwh.items():
            totals[(month, report.company_name)] += mwh
    return [
        {
            "month": month,
            "company_name": company,
            "energy_loss_mwh": round(mwh, 3),
            "loss_brl": round(energy_loss_cost_brl(mwh, price_brl_per_mwh), 2),
        }
        for (month, company), mwh in sorted(totals.items())
    ]
