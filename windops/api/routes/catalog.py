"""Companies, wind farms and turbines."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from windops.api.deps import SessionDep, ensure_company
from windops.api.schemas import CompanyOut, TurbineOut, WindFarmOut
from windops.db.models import CompanyModel, TurbineModel, WindFarmModel

router = APIRouter(tags=["catalog"])


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(session: SessionDep):
    return session.scalars(select(CompanyModel).order_by(CompanyModel.id)).all()


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, session: SessionDep):
    return ensure_company(session, company_id)


@router.get("/windfarms", response_model=list[WindFarmOut])
def list_windfarms(session: SessionDep, company_id: int | None = None):
    query = select(WindFarmModel).order_by(WindFarmModel.id)
    if company_id is not None:
        ensure_company(session, company_id)
        query = query.where(WindFarmModel.company_id == company_id)
    return session.scalars(query).all()


@router.get("/turbines", response_model=list[TurbineOut])
def list_turbines(session: SessionDep, company_id: int | None = None, farm_id: int | None = None):
    query = select(TurbineModel).join(WindFarmModel).order_by(TurbineModel.id)
    if company_id is not None:
        ensure_company(session, company_id)
        query = query.where(WindFarmModel.company_id == company_id)
    if farm_id is not None:
        query = query.where(TurbineModel.farm_id == farm_id)
    return session.scalars(query).all()


@router.get("/turbines/{turbine_id}", response_model=TurbineOut)
def get_turbine(turbine_id: int, session: SessionDep):
    turbine = session.get(TurbineModel, turbine_id)
    if turbine is None:
        raise HTTPException(status_code=404, detail=f"Turbine {turbine_id} not found")
    return turbine
