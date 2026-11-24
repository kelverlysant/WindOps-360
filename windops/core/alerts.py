"""Operational alerts: situations that need someone's attention.

Rules (thresholds are configurable through `AlertThresholds`):

* Open failure        - warning while open; critical after 72 h without repair.
* Low availability    - warning below 97%; critical below 95%.
* Slow repairs        - warning when a turbine's MTTR is 1.5x the fleet average.
* Recurring component - warning when the same component fails 3+ times
                        within 90 days on the same turbine.

All checks look at the analysis window and are evaluated "as of" its end.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from windops.core.entities import Dataset, Failure

if TYPE_CHECKING:
    from windops.core.analytics import TurbineReport

# Alert texts are shown to Brazilian operators, so they are written in Portuguese.
COMPONENT_PT = {
    "Generator": "Gerador",
    "Gearbox": "Caixa multiplicadora",
    "Electrical": "Sistema elétrico",
    "Sensor": "Sensor",
    "Blade": "Pá",
}
CAUSE_PT = {
    "Wear": "desgaste",
    "Weather": "clima",
    "Electrical Fault": "falha elétrica",
    "Manufacturing Defect": "defeito de fabricação",
    "Operational Error": "erro operacional",
}

CRITICAL = "critical"
WARNING = "warning"


@dataclass(frozen=True)
class AlertThresholds:
    open_failure_critical_hours: float = 72.0
    availability_warning: float = 0.97
    availability_critical: float = 0.95
    mttr_factor: float = 1.5
    recurrence_count: int = 3
    recurrence_days: int = 90


@dataclass
class Alert:
    severity: str  # "critical" | "warning"
    kind: str  # "open_failure" | "low_availability" | "slow_repair" | "recurrence"
    turbine_id: int
    turbine_label: str
    title: str
    detail: str
    since: datetime | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _pt(value: float, decimals: int = 0) -> str:
    """Brazilian number format: 1.234,5"""
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _recurrences(failures: list[Failure], count: int, days: int) -> list[tuple[str, list[Failure]]]:
    """Groups of `count`+ failures of one component inside a `days` window."""
    by_component: dict[str, list[Failure]] = defaultdict(list)
    for failure in sorted(failures, key=lambda f: f.start):
        by_component[failure.component.value].append(failure)

    found = []
    window = timedelta(days=days)
    for component, items in by_component.items():
        best: list[Failure] = []
        left = 0
        for right in range(len(items)):
            while items[right].start - items[left].start > window:
                left += 1
            if right - left + 1 > len(best):
                best = items[left : right + 1]
        if len(best) >= count:
            found.append((component, best))
    return found


def build_alerts(
    dataset: Dataset,
    reports: list[TurbineReport],
    window_start: datetime,
    window_end: datetime,
    thresholds: AlertThresholds | None = None,
) -> list[Alert]:
    t = thresholds or AlertThresholds()
    labels = {r.turbine_id: f"{r.turbine_code} ({r.company_name}, {r.farm_name})" for r in reports}
    failures = dataset.failures_by_turbine()
    alerts: list[Alert] = []

    # Open failures
    for turbine_id, items in failures.items():
        for f in items:
            if f.is_open and window_start <= f.start < window_end:
                hours = (window_end - f.start).total_seconds() / 3600
                critical = hours >= t.open_failure_critical_hours
                alerts.append(
                    Alert(
                        severity=CRITICAL if critical else WARNING,
                        kind="open_failure",
                        turbine_id=turbine_id,
                        turbine_label=labels.get(turbine_id, str(turbine_id)),
                        title=f"Falha aberta há {_pt(hours)} h ({COMPONENT_PT[f.component.value]})",
                        detail=(
                            f"Falha #{f.id}, causa: {CAUSE_PT[f.cause.value]}. "
                            f"Turbina parada desde {f.start:%d/%m %H:%M}."
                        ),
                        since=f.start,
                    )
                )

    # Low availability
    for r in reports:
        if r.availability < t.availability_warning:
            critical = r.availability < t.availability_critical
            alerts.append(
                Alert(
                    severity=CRITICAL if critical else WARNING,
                    kind="low_availability",
                    turbine_id=r.turbine_id,
                    turbine_label=labels[r.turbine_id],
                    title=f"Disponibilidade de {_pt(r.availability * 100, 2)}%",
                    detail=(
                        f"Meta de {_pt(t.availability_warning * 100, 1)}%. "
                        f"{_pt(r.downtime_hours)} h paradas no período."
                    ),
                )
            )

    # Slow repairs
    mttrs = [r.mttr_hours for r in reports if r.mttr_hours is not None]
    if mttrs:
        fleet_mttr = sum(mttrs) / len(mttrs)
        for r in reports:
            if r.mttr_hours is not None and r.mttr_hours > t.mttr_factor * fleet_mttr:
                alerts.append(
                    Alert(
                        severity=WARNING,
                        kind="slow_repair",
                        turbine_id=r.turbine_id,
                        turbine_label=labels[r.turbine_id],
                        title=f"Reparo lento: MTTR de {_pt(r.mttr_hours)} h",
                        detail=f"A média da frota é {_pt(fleet_mttr)} h ({_pt(r.mttr_hours / fleet_mttr, 1)}×).",
                    )
                )

    # Recurring component failures
    for turbine_id, items in failures.items():
        in_window = [f for f in items if window_start <= f.start < window_end]
        for component, group in _recurrences(in_window, t.recurrence_count, t.recurrence_days):
            alerts.append(
                Alert(
                    severity=WARNING,
                    kind="recurrence",
                    turbine_id=turbine_id,
                    turbine_label=labels.get(turbine_id, str(turbine_id)),
                    title=f"{COMPONENT_PT[component]} falhou {len(group)} vezes em {t.recurrence_days} dias",
                    detail=(
                        f"Entre {group[0].start:%d/%m/%Y} e {group[-1].start:%d/%m/%Y}. "
                        "Investigar causa raiz em vez de só reparar."
                    ),
                    since=group[0].start,
                )
            )

    alerts.sort(key=lambda a: (a.severity != CRITICAL, a.kind, a.turbine_label))
    return alerts
