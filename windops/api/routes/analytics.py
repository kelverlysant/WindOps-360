"""KPIs, financial impact and prioritisation."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from fastapi import APIRouter, Query

from windops.api.deps import AnalysisDep, AnalysisParams, SessionDep
from windops.api.schemas import AlertOut, GroupSummaryOut, MonthlyLossOut, OverviewOut, TurbineReportOut
from windops.core.alerts import AlertThresholds, build_alerts
from windops.core.analytics import TurbineReport, build_turbine_reports, monthly_loss, summarize
from windops.db.repository import load_dataset

router = APIRouter(tags=["analytics"])


def _reports(session, params: AnalysisParams) -> list[TurbineReport]:
    dataset = load_dataset(session, params.company_id)
    return build_turbine_reports(dataset, params.start, params.end, params.price)


@router.get("/kpis/turbines", response_model=list[TurbineReportOut])
def turbine_kpis(session: SessionDep, params: AnalysisDep):
    """Availability, MTTR, MTBF, downtime, lost energy and criticality per turbine."""
    return [r.to_dict() for r in _reports(session, params)]


@router.get("/financials/summary", response_model=list[GroupSummaryOut])
def financial_summary(session: SessionDep, params: AnalysisDep, level: Literal["company", "farm"] = "company"):
    return summarize(_reports(session, params), level)


@router.get("/financials/monthly", response_model=list[MonthlyLossOut])
def financial_monthly(session: SessionDep, params: AnalysisDep):
    return monthly_loss(_reports(session, params), params.price)


@router.get("/ranking", response_model=list[TurbineReportOut])
def ranking(
    session: SessionDep,
    params: AnalysisDep,
    by: Literal["criticality", "loss"] = "criticality",
    limit: int = Query(default=5, ge=1, le=100),
):
    """Turbines that deserve attention first."""
    reports = _reports(session, params)
    if by == "loss":
        reports.sort(key=lambda r: -r.loss_brl)
    return [r.to_dict() for r in reports[:limit]]


@router.get("/overview", response_model=OverviewOut)
def overview(session: SessionDep, params: AnalysisDep):
    """Fleet-level numbers for the executive view."""
    dataset = load_dataset(session, params.company_id)
    reports = build_turbine_reports(dataset, params.start, params.end, params.price)
    period = sum(r.period_hours for r in reports)
    downtime = sum(r.downtime_hours for r in reports)
    components: Counter[str] = Counter()
    for r in reports:
        components.update(r.failures_by_component)

    repairs = [
        (f.end - f.start).total_seconds() / 3600
        for f in dataset.failures
        if f.end is not None and params.start <= f.start < params.end
    ]
    return OverviewOut(
        window_start=params.start,
        window_end=params.end,
        price_brl_per_mwh=params.price,
        turbines=len(reports),
        failure_count=sum(r.failure_count for r in reports),
        open_failures=sum(r.open_failures for r in reports),
        availability=round(1 - downtime / period, 4) if period else None,
        mttr_hours=round(sum(repairs) / len(repairs), 2) if repairs else None,
        energy_loss_mwh=round(sum(r.energy_loss_mwh for r in reports), 3),
        loss_brl=round(sum(r.loss_brl for r in reports), 2),
        failures_by_component=dict(components),
    )


@router.get("/alerts", response_model=list[AlertOut])
def alerts(
    session: SessionDep,
    params: AnalysisDep,
    availability_target: float = Query(default=0.97, gt=0, le=1, description="Availability goal (0-1)"),
):
    """Situations that need attention, critical first."""
    dataset = load_dataset(session, params.company_id)
    reports = build_turbine_reports(dataset, params.start, params.end, params.price)
    # Critical when 2 percentage points below the goal (97% goal -> critical below 95%)
    thresholds = AlertThresholds(
        availability_warning=availability_target,
        availability_critical=availability_target - 0.02,
    )
    return [a.to_dict() for a in build_alerts(dataset, reports, params.start, params.end, thresholds)]
