"""Failures and maintenances: query and registration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from windops.api.deps import SessionDep, ensure_company
from windops.api.schemas import FailureClose, FailureCreate, FailureOut, MaintenanceCreate, MaintenanceOut
from windops.core.entities import Component, MaintenanceType
from windops.db.models import FailureModel, MaintenanceModel, TurbineModel, WindFarmModel

router = APIRouter(tags=["events"])


def _failure_out(row: FailureModel) -> FailureOut:
    out = FailureOut.model_validate(row)
    if row.ended_at is not None:
        out.duration_hours = round((row.ended_at - row.started_at).total_seconds() / 3600, 2)
    return out


def _require_turbine(session, turbine_id: int) -> TurbineModel:
    turbine = session.get(TurbineModel, turbine_id)
    if turbine is None:
        raise HTTPException(status_code=404, detail=f"Turbine {turbine_id} not found")
    return turbine


# ---------- failures ----------
@router.get("/failures", response_model=list[FailureOut])
def list_failures(
    session: SessionDep,
    company_id: int | None = None,
    turbine_id: int | None = None,
    component: Component | None = None,
    state: Literal["all", "open", "closed"] = "all",
    start: datetime | None = Query(default=None, description="Only failures that started at or after"),
    end: datetime | None = Query(default=None, description="Only failures that started before"),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    query = select(FailureModel).join(TurbineModel).join(WindFarmModel)
    if company_id is not None:
        ensure_company(session, company_id)
        query = query.where(WindFarmModel.company_id == company_id)
    if turbine_id is not None:
        query = query.where(FailureModel.turbine_id == turbine_id)
    if component is not None:
        query = query.where(FailureModel.component == component.value)
    if start is not None:
        query = query.where(FailureModel.started_at >= start)
    if end is not None:
        query = query.where(FailureModel.started_at < end)
    if state == "open":
        query = query.where(FailureModel.ended_at.is_(None))
    elif state == "closed":
        query = query.where(FailureModel.ended_at.is_not(None))
    rows = session.scalars(query.order_by(FailureModel.started_at.desc()).limit(limit).offset(offset))
    return [_failure_out(row) for row in rows]


@router.post("/failures", response_model=FailureOut, status_code=status.HTTP_201_CREATED)
def create_failure(payload: FailureCreate, session: SessionDep):
    _require_turbine(session, payload.turbine_id)
    row = FailureModel(
        turbine_id=payload.turbine_id,
        component=payload.component.value,
        cause=payload.cause.value,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        description=payload.description,
    )
    session.add(row)
    session.commit()
    return _failure_out(row)


@router.patch("/failures/{failure_id}/close", response_model=FailureOut)
def close_failure(failure_id: int, payload: FailureClose, session: SessionDep):
    row = session.get(FailureModel, failure_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Failure {failure_id} not found")
    if row.ended_at is not None:
        raise HTTPException(status_code=409, detail="Failure is already closed")
    if payload.ended_at < row.started_at:
        raise HTTPException(status_code=422, detail="ended_at cannot be before started_at")
    row.ended_at = payload.ended_at
    session.commit()
    return _failure_out(row)


# ---------- maintenances ----------
@router.get("/maintenances", response_model=list[MaintenanceOut])
def list_maintenances(
    session: SessionDep,
    company_id: int | None = None,
    turbine_id: int | None = None,
    type: MaintenanceType | None = None,
    start: datetime | None = Query(default=None, description="Only maintenances that started at or after"),
    end: datetime | None = Query(default=None, description="Only maintenances that started before"),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    query = select(MaintenanceModel).join(TurbineModel).join(WindFarmModel)
    if company_id is not None:
        ensure_company(session, company_id)
        query = query.where(WindFarmModel.company_id == company_id)
    if turbine_id is not None:
        query = query.where(MaintenanceModel.turbine_id == turbine_id)
    if type is not None:
        query = query.where(MaintenanceModel.type == type.value)
    if start is not None:
        query = query.where(MaintenanceModel.started_at >= start)
    if end is not None:
        query = query.where(MaintenanceModel.started_at < end)
    return session.scalars(query.order_by(MaintenanceModel.started_at.desc()).limit(limit).offset(offset)).all()


@router.post("/maintenances", response_model=MaintenanceOut, status_code=status.HTTP_201_CREATED)
def create_maintenance(payload: MaintenanceCreate, session: SessionDep):
    _require_turbine(session, payload.turbine_id)
    if payload.failure_id is not None:
        failure = session.get(FailureModel, payload.failure_id)
        if failure is None:
            raise HTTPException(status_code=404, detail=f"Failure {payload.failure_id} not found")
        if failure.turbine_id != payload.turbine_id:
            raise HTTPException(status_code=422, detail="failure_id belongs to a different turbine")
    row = MaintenanceModel(
        turbine_id=payload.turbine_id,
        failure_id=payload.failure_id,
        type=payload.type.value,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        technician=payload.technician,
        parts_used=payload.parts_used,
    )
    session.add(row)
    session.commit()
    return row
