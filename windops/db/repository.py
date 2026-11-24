"""Conversion between database rows and domain entities.

The analytics layer never touches SQLAlchemy. The repository loads rows,
filtered by tenant when asked, and returns a plain `Dataset`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from windops.core.entities import (
    Company,
    Component,
    Dataset,
    Failure,
    FailureCause,
    Maintenance,
    MaintenanceType,
    PowerCurve,
    Turbine,
    WindFarm,
)
from windops.db.models import CompanyModel, FailureModel, MaintenanceModel, TurbineModel, WindFarmModel


def to_company(row: CompanyModel) -> Company:
    return Company(id=row.id, name=row.name)


def to_farm(row: WindFarmModel) -> WindFarm:
    return WindFarm(id=row.id, company_id=row.company_id, name=row.name, state=row.state)


def to_turbine(row: TurbineModel) -> Turbine:
    return Turbine(
        id=row.id,
        farm_id=row.farm_id,
        code=row.code,
        rated_power_mw=row.rated_power_mw,
        commissioned_at=row.commissioned_at,
        power_curve=PowerCurve(row.cut_in_ms, row.rated_ms, row.cut_out_ms),
    )


def to_failure(row: FailureModel) -> Failure:
    return Failure(
        id=row.id,
        turbine_id=row.turbine_id,
        component=Component(row.component),
        cause=FailureCause(row.cause),
        start=row.started_at,
        end=row.ended_at,
        description=row.description or "",
    )


def to_maintenance(row: MaintenanceModel) -> Maintenance:
    return Maintenance(
        id=row.id,
        turbine_id=row.turbine_id,
        type=MaintenanceType(row.type),
        start=row.started_at,
        end=row.ended_at,
        technician=row.technician,
        parts_used=list(row.parts_used or []),
        failure_id=row.failure_id,
    )


def load_dataset(session: Session, company_id: int | None = None) -> Dataset:
    """Load everything (or one tenant) into memory for analytics."""
    companies = select(CompanyModel)
    farms = select(WindFarmModel)
    turbines = select(TurbineModel).join(WindFarmModel)
    failures = select(FailureModel).join(TurbineModel).join(WindFarmModel)
    maintenances = select(MaintenanceModel).join(TurbineModel).join(WindFarmModel)

    if company_id is not None:
        companies = companies.where(CompanyModel.id == company_id)
        farms = farms.where(WindFarmModel.company_id == company_id)
        turbines = turbines.where(WindFarmModel.company_id == company_id)
        failures = failures.where(WindFarmModel.company_id == company_id)
        maintenances = maintenances.where(WindFarmModel.company_id == company_id)

    return Dataset(
        companies=[to_company(r) for r in session.scalars(companies.order_by(CompanyModel.id))],
        farms=[to_farm(r) for r in session.scalars(farms.order_by(WindFarmModel.id))],
        turbines=[to_turbine(r) for r in session.scalars(turbines.order_by(TurbineModel.id))],
        failures=[to_failure(r) for r in session.scalars(failures.order_by(FailureModel.started_at))],
        maintenances=[to_maintenance(r) for r in session.scalars(maintenances.order_by(MaintenanceModel.started_at))],
    )


def save_dataset(session: Session, dataset: Dataset) -> None:
    """Insert a generated dataset, keeping its ids."""
    session.add_all(CompanyModel(id=c.id, name=c.name) for c in dataset.companies)
    session.flush()
    session.add_all(WindFarmModel(id=f.id, company_id=f.company_id, name=f.name, state=f.state) for f in dataset.farms)
    session.flush()
    session.add_all(
        TurbineModel(
            id=t.id,
            farm_id=t.farm_id,
            code=t.code,
            rated_power_mw=t.rated_power_mw,
            commissioned_at=t.commissioned_at,
            cut_in_ms=t.power_curve.cut_in_ms,
            rated_ms=t.power_curve.rated_ms,
            cut_out_ms=t.power_curve.cut_out_ms,
        )
        for t in dataset.turbines
    )
    session.flush()
    session.add_all(
        FailureModel(
            id=f.id,
            turbine_id=f.turbine_id,
            component=f.component.value,
            cause=f.cause.value,
            started_at=f.start,
            ended_at=f.end,
            description=f.description,
        )
        for f in dataset.failures
    )
    session.flush()
    session.add_all(
        MaintenanceModel(
            id=m.id,
            turbine_id=m.turbine_id,
            failure_id=m.failure_id,
            type=m.type.value,
            started_at=m.start,
            ended_at=m.end,
            technician=m.technician,
            parts_used=m.parts_used,
        )
        for m in dataset.maintenances
    )
    session.flush()
