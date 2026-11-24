"""Pydantic models for request validation and response documentation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from windops.core.entities import Component, FailureCause, MaintenanceType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- catalog ----------
class CompanyOut(ORMModel):
    id: int
    name: str


class WindFarmOut(ORMModel):
    id: int
    company_id: int
    name: str
    state: str


class TurbineOut(ORMModel):
    id: int
    farm_id: int
    code: str
    rated_power_mw: float
    commissioned_at: datetime
    cut_in_ms: float
    rated_ms: float
    cut_out_ms: float


# ---------- events ----------
class FailureCreate(BaseModel):
    turbine_id: int
    component: Component
    cause: FailureCause
    started_at: datetime
    ended_at: datetime | None = None
    description: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def check_dates(self) -> FailureCreate:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at cannot be before started_at")
        return self


class FailureClose(BaseModel):
    ended_at: datetime


class FailureOut(ORMModel):
    id: int
    turbine_id: int
    component: Component
    cause: FailureCause
    started_at: datetime
    ended_at: datetime | None
    description: str
    duration_hours: float | None = None


class MaintenanceCreate(BaseModel):
    turbine_id: int
    type: MaintenanceType
    started_at: datetime
    ended_at: datetime
    technician: str = Field(min_length=1, max_length=120)
    parts_used: list[str] = Field(default_factory=list)
    failure_id: int | None = None

    @model_validator(mode="after")
    def check_rules(self) -> MaintenanceCreate:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at cannot be before started_at")
        if self.type is MaintenanceType.CORRECTIVE and self.failure_id is None:
            raise ValueError("corrective maintenance must reference a failure_id")
        return self


class MaintenanceOut(ORMModel):
    id: int
    turbine_id: int
    failure_id: int | None
    type: MaintenanceType
    started_at: datetime
    ended_at: datetime
    technician: str
    parts_used: list[str]


# ---------- analytics ----------
class TurbineReportOut(BaseModel):
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
    criticality_breakdown: dict[str, float]
    mean_wind_ms: float
    stopped_at_end: bool


class GroupSummaryOut(BaseModel):
    company_id: int
    company_name: str
    farm_id: int | None = None
    farm_name: str | None = None
    turbines: int
    failure_count: int
    open_failures: int
    downtime_hours: float
    availability: float | None
    energy_loss_mwh: float
    loss_brl: float


class MonthlyLossOut(BaseModel):
    month: str
    company_name: str
    energy_loss_mwh: float
    loss_brl: float


class OverviewOut(BaseModel):
    window_start: datetime
    window_end: datetime
    price_brl_per_mwh: float
    turbines: int
    failure_count: int
    open_failures: int
    availability: float | None
    mttr_hours: float | None
    energy_loss_mwh: float
    loss_brl: float
    failures_by_component: dict[str, int]


class AlertOut(BaseModel):
    severity: Literal["critical", "warning"]
    kind: Literal["open_failure", "low_availability", "slow_repair", "recurrence"]
    turbine_id: int
    turbine_label: str
    title: str
    detail: str
    since: datetime | None
