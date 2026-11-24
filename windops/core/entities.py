"""Domain entities for WindOps 360.

These are plain dataclasses with no database or framework dependency.
The analytics layer (KPIs, financials, criticality) works only with them,
so the same rules run in tests, in the API and in the seed script.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Component(StrEnum):
    GENERATOR = "Generator"
    GEARBOX = "Gearbox"
    ELECTRICAL = "Electrical"
    SENSOR = "Sensor"
    BLADE = "Blade"


class MaintenanceType(StrEnum):
    PREVENTIVE = "Preventive"
    CORRECTIVE = "Corrective"


class FailureCause(StrEnum):
    WEAR = "Wear"
    WEATHER = "Weather"
    ELECTRICAL_FAULT = "Electrical Fault"
    MANUFACTURING_DEFECT = "Manufacturing Defect"
    OPERATIONAL_ERROR = "Operational Error"


@dataclass
class Company:
    id: int
    name: str


@dataclass
class WindFarm:
    id: int
    company_id: int
    name: str
    state: str  # Brazilian state code, e.g. "RN"


@dataclass
class PowerCurve:
    """Simplified turbine power curve (all speeds in m/s)."""

    cut_in_ms: float = 3.0
    rated_ms: float = 12.0
    cut_out_ms: float = 25.0


@dataclass
class Turbine:
    id: int
    farm_id: int
    code: str  # e.g. "WT-01"
    rated_power_mw: float
    commissioned_at: datetime
    power_curve: PowerCurve = field(default_factory=PowerCurve)

    def age_years(self, at: datetime) -> float:
        return (at - self.commissioned_at).days / 365.25


@dataclass
class Failure:
    id: int
    turbine_id: int
    component: Component
    cause: FailureCause
    start: datetime
    end: datetime | None = None  # None means the failure is still open
    description: str = ""

    @property
    def is_open(self) -> bool:
        return self.end is None

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise ValueError("Failure end cannot be before start")


@dataclass
class Maintenance:
    id: int
    turbine_id: int
    type: MaintenanceType
    start: datetime
    end: datetime
    technician: str
    parts_used: list[str] = field(default_factory=list)
    failure_id: int | None = None  # set for corrective maintenance

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("Maintenance end cannot be before start")
        if self.type is MaintenanceType.CORRECTIVE and self.failure_id is None:
            raise ValueError("Corrective maintenance must reference a failure")


@dataclass
class Dataset:
    """In-memory snapshot of everything the analytics layer needs."""

    companies: list[Company] = field(default_factory=list)
    farms: list[WindFarm] = field(default_factory=list)
    turbines: list[Turbine] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    maintenances: list[Maintenance] = field(default_factory=list)

    def farm_by_id(self) -> dict[int, WindFarm]:
        return {f.id: f for f in self.farms}

    def company_by_id(self) -> dict[int, Company]:
        return {c.id: c for c in self.companies}

    def failures_by_turbine(self) -> dict[int, list[Failure]]:
        grouped: dict[int, list[Failure]] = {t.id: [] for t in self.turbines}
        for failure in self.failures:
            grouped.setdefault(failure.turbine_id, []).append(failure)
        return grouped

    def for_company(self, company_id: int) -> Dataset:
        """Return a copy containing only one tenant's data."""
        farms = [f for f in self.farms if f.company_id == company_id]
        farm_ids = {f.id for f in farms}
        turbines = [t for t in self.turbines if t.farm_id in farm_ids]
        turbine_ids = {t.id for t in turbines}
        return Dataset(
            companies=[c for c in self.companies if c.id == company_id],
            farms=farms,
            turbines=turbines,
            failures=[f for f in self.failures if f.turbine_id in turbine_ids],
            maintenances=[m for m in self.maintenances if m.turbine_id in turbine_ids],
        )
