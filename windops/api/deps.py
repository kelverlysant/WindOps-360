"""Shared query parameters and lookups for the routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from windops.config import ENERGY_PRICE_BRL_PER_MWH
from windops.core.generator import history_window
from windops.db.models import CompanyModel
from windops.db.session import get_session

SessionDep = Annotated[Session, Depends(get_session)]

_DEFAULT_START, _DEFAULT_END = history_window()


@dataclass
class AnalysisParams:
    company_id: int | None
    start: datetime
    end: datetime
    price: float


def analysis_params(
    session: SessionDep,
    company_id: Annotated[int | None, Query(description="Filter by company (tenant)")] = None,
    start: Annotated[datetime, Query(description="Window start (inclusive)")] = _DEFAULT_START,
    end: Annotated[datetime, Query(description="Window end (exclusive)")] = _DEFAULT_END,
    price: Annotated[float, Query(ge=0, description="Energy price in R$/MWh")] = ENERGY_PRICE_BRL_PER_MWH,
) -> AnalysisParams:
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    if company_id is not None:
        ensure_company(session, company_id)
    return AnalysisParams(company_id, start, end, price)


AnalysisDep = Annotated[AnalysisParams, Depends(analysis_params)]


def ensure_company(session: Session, company_id: int) -> CompanyModel:
    company = session.get(CompanyModel, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    return company
