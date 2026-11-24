"""Synthetic data factory.

Builds a reproducible multi-tenant scenario: by default 2 companies,
2 farms each, 3 turbines per farm and 24 months of history.

Rules
-----
* Failures follow a Poisson process whose monthly rate grows with age.
* Component is drawn with weights; cause is drawn from causes that make
  sense for that component; duration range depends on the component.
* Failures still running at the end of the history stay open (end = None),
  and recent ones (last 14 days) stay open half of the time (awaiting parts).
* Every closed failure gets a corrective maintenance record.
* Preventive maintenance happens roughly every 180 days.

All numbers are illustrative. They do not represent a real operation.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from windops.core.entities import (
    Company,
    Component,
    Dataset,
    Failure,
    FailureCause,
    Maintenance,
    MaintenanceType,
    Turbine,
    WindFarm,
)

DEFAULT_HISTORY_END = datetime(2026, 1, 1)
DEFAULT_HISTORY_MONTHS = 24

COMPANY_NAMES = ["AeroVento", "Ventus", "Brisa Norte", "Alísios Energia"]
FARM_STATES = ["RN", "CE", "BA", "PI", "PE", "PB"]

COMPONENT_WEIGHTS: dict[Component, float] = {
    Component.ELECTRICAL: 0.30,
    Component.SENSOR: 0.25,
    Component.GENERATOR: 0.15,
    Component.GEARBOX: 0.15,
    Component.BLADE: 0.15,
}

COMPONENT_CAUSES: dict[Component, list[FailureCause]] = {
    Component.ELECTRICAL: [FailureCause.ELECTRICAL_FAULT, FailureCause.WEATHER, FailureCause.OPERATIONAL_ERROR],
    Component.SENSOR: [FailureCause.ELECTRICAL_FAULT, FailureCause.WEAR, FailureCause.MANUFACTURING_DEFECT],
    Component.GENERATOR: [FailureCause.WEAR, FailureCause.ELECTRICAL_FAULT, FailureCause.MANUFACTURING_DEFECT],
    Component.GEARBOX: [FailureCause.WEAR, FailureCause.MANUFACTURING_DEFECT, FailureCause.OPERATIONAL_ERROR],
    Component.BLADE: [FailureCause.WEATHER, FailureCause.WEAR, FailureCause.MANUFACTURING_DEFECT],
}

# Repair duration range in hours
COMPONENT_DURATION_H: dict[Component, tuple[int, int]] = {
    Component.SENSOR: (2, 12),
    Component.ELECTRICAL: (4, 36),
    Component.GENERATOR: (24, 120),
    Component.BLADE: (48, 240),
    Component.GEARBOX: (72, 336),
}

COMPONENT_PARTS: dict[Component, list[str]] = {
    Component.SENSOR: ["Anemometer", "Vibration sensor", "Temperature probe"],
    Component.ELECTRICAL: ["Converter module", "Contactor", "Cable kit"],
    Component.GENERATOR: ["Generator bearing", "Slip ring", "Brush set"],
    Component.GEARBOX: ["Gearbox bearing", "Oil filter", "Planetary gear"],
    Component.BLADE: ["Leading-edge tape", "Pitch bearing", "Resin kit"],
}

TECHNICIANS = ["Ana Lima", "Bruno Costa", "Carla Souza", "Diego Alves", "Eduarda Rocha", "Felipe Nunes"]

BASE_FAILURES_PER_MONTH = 0.12
AGE_FAILURES_PER_MONTH = 0.025
PREVENTIVE_INTERVAL_DAYS = 180
HOURS_PER_MONTH = 730.0


OPEN_FAILURE_RECENT_DAYS = 14


def _stays_open(rng: random.Random, start: datetime, end: datetime, history_end: datetime) -> bool:
    """Open if still running at the end of history, or recent and awaiting parts (50%)."""
    if end > history_end:
        return True
    return history_end - start < timedelta(days=OPEN_FAILURE_RECENT_DAYS) and rng.random() < 0.5


def _failures_per_month(age_years: float) -> float:
    return BASE_FAILURES_PER_MONTH + AGE_FAILURES_PER_MONTH * age_years


def generate_dataset(
    seed: int = 7,
    companies: int = 2,
    farms_per_company: int = 2,
    turbines_per_farm: int = 3,
    history_months: int = DEFAULT_HISTORY_MONTHS,
    history_end: datetime = DEFAULT_HISTORY_END,
) -> Dataset:
    if companies > len(COMPANY_NAMES):
        raise ValueError(f"At most {len(COMPANY_NAMES)} companies are supported")

    rng = random.Random(seed)
    history_start, history_end = history_window(history_months, history_end)
    data = Dataset()

    farm_id = turbine_id = failure_id = maintenance_id = 0
    for company_index in range(companies):
        company = Company(id=company_index + 1, name=COMPANY_NAMES[company_index])
        data.companies.append(company)

        for farm_index in range(farms_per_company):
            farm_id += 1
            data.farms.append(
                WindFarm(
                    id=farm_id,
                    company_id=company.id,
                    name=f"Farm {farm_index + 1:02d}",
                    state=rng.choice(FARM_STATES),
                )
            )

            for turbine_index in range(turbines_per_farm):
                turbine_id += 1
                age_at_start = rng.uniform(1, 10)
                turbine = Turbine(
                    id=turbine_id,
                    farm_id=farm_id,
                    code=f"WT-{turbine_index + 1:02d}",
                    rated_power_mw=rng.choice([2.1, 3.0, 3.0, 4.2]),
                    commissioned_at=history_start - timedelta(days=round(age_at_start * 365.25)),
                )
                data.turbines.append(turbine)

                # --- failures (Poisson process) ---
                cursor = history_start
                while True:
                    rate_per_hour = _failures_per_month(turbine.age_years(cursor)) / HOURS_PER_MONTH
                    cursor += timedelta(hours=rng.expovariate(rate_per_hour))
                    if cursor >= history_end:
                        break
                    cursor = cursor.replace(second=0, microsecond=0)

                    component = rng.choices(list(COMPONENT_WEIGHTS), weights=list(COMPONENT_WEIGHTS.values()))[0]
                    low, high = COMPONENT_DURATION_H[component]
                    end = cursor + timedelta(minutes=rng.randint(low * 60, high * 60))
                    failure_id += 1
                    failure = Failure(
                        id=failure_id,
                        turbine_id=turbine.id,
                        component=component,
                        cause=rng.choice(COMPONENT_CAUSES[component]),
                        start=cursor,
                        end=None if _stays_open(rng, cursor, end, history_end) else end,
                    )
                    data.failures.append(failure)

                    if failure.end is not None:
                        maintenance_id += 1
                        data.maintenances.append(
                            Maintenance(
                                id=maintenance_id,
                                turbine_id=turbine.id,
                                type=MaintenanceType.CORRECTIVE,
                                start=min(failure.start + timedelta(minutes=rng.randint(15, 240)), failure.end),
                                end=failure.end,
                                technician=rng.choice(TECHNICIANS),
                                parts_used=rng.sample(COMPONENT_PARTS[component], k=rng.randint(1, 2)),
                                failure_id=failure.id,
                            )
                        )

                # --- preventive maintenance ---
                next_preventive = history_start + timedelta(days=rng.randint(0, PREVENTIVE_INTERVAL_DAYS))
                while next_preventive < history_end:
                    start = next_preventive.replace(hour=8, minute=0, second=0, microsecond=0)
                    maintenance_id += 1
                    data.maintenances.append(
                        Maintenance(
                            id=maintenance_id,
                            turbine_id=turbine.id,
                            type=MaintenanceType.PREVENTIVE,
                            start=start,
                            end=start + timedelta(hours=rng.randint(6, 10)),
                            technician=rng.choice(TECHNICIANS),
                            parts_used=["Oil filter", "Grease kit"],
                        )
                    )
                    next_preventive += timedelta(days=PREVENTIVE_INTERVAL_DAYS + rng.randint(-15, 15))

    return data


def history_window(
    history_months: int = DEFAULT_HISTORY_MONTHS, history_end: datetime = DEFAULT_HISTORY_END
) -> tuple[datetime, datetime]:
    """Exact calendar window: e.g. 24 months ending 2026-01-01 starts 2024-01-01."""
    total = history_end.year * 12 + (history_end.month - 1) - history_months
    start = history_end.replace(year=total // 12, month=total % 12 + 1)
    return start, history_end
