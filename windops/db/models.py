"""SQLAlchemy ORM models (one table per domain entity)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CompanyModel(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

    farms: Mapped[list[WindFarmModel]] = relationship(back_populates="company", cascade="all, delete-orphan")


class WindFarmModel(Base):
    __tablename__ = "wind_farms"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_farm_name_per_company"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(2))

    company: Mapped[CompanyModel] = relationship(back_populates="farms")
    turbines: Mapped[list[TurbineModel]] = relationship(back_populates="farm", cascade="all, delete-orphan")


class TurbineModel(Base):
    __tablename__ = "turbines"
    __table_args__ = (
        UniqueConstraint("farm_id", "code", name="uq_turbine_code_per_farm"),
        CheckConstraint("rated_power_mw > 0", name="ck_turbine_rated_power_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("wind_farms.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    rated_power_mw: Mapped[float] = mapped_column(Float)
    commissioned_at: Mapped[datetime] = mapped_column(DateTime)
    cut_in_ms: Mapped[float] = mapped_column(Float, default=3.0)
    rated_ms: Mapped[float] = mapped_column(Float, default=12.0)
    cut_out_ms: Mapped[float] = mapped_column(Float, default=25.0)

    farm: Mapped[WindFarmModel] = relationship(back_populates="turbines")
    failures: Mapped[list[FailureModel]] = relationship(back_populates="turbine", cascade="all, delete-orphan")


class FailureModel(Base):
    __tablename__ = "failures"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_failure_end_after_start"),
        Index("ix_failures_turbine_started", "turbine_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    turbine_id: Mapped[int] = mapped_column(ForeignKey("turbines.id", ondelete="CASCADE"))
    component: Mapped[str] = mapped_column(String(32))
    cause: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    description: Mapped[str] = mapped_column(String(500), default="")

    turbine: Mapped[TurbineModel] = relationship(back_populates="failures")


class MaintenanceModel(Base):
    __tablename__ = "maintenances"
    __table_args__ = (
        CheckConstraint("ended_at >= started_at", name="ck_maintenance_end_after_start"),
        Index("ix_maintenances_turbine_started", "turbine_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    turbine_id: Mapped[int] = mapped_column(ForeignKey("turbines.id", ondelete="CASCADE"))
    failure_id: Mapped[int | None] = mapped_column(ForeignKey("failures.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime] = mapped_column(DateTime)
    technician: Mapped[str] = mapped_column(String(120))
    parts_used: Mapped[list[str]] = mapped_column(JSON, default=list)
