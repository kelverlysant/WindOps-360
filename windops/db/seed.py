"""Load the synthetic scenario into the database.

Usage:
    python -m windops.db.seed            # only if the database is empty
    python -m windops.db.seed --reset    # wipe and reload
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, func, select, text

from windops.core.generator import generate_dataset
from windops.db.models import CompanyModel, FailureModel, MaintenanceModel, TurbineModel, WindFarmModel
from windops.db.repository import save_dataset
from windops.db.session import SessionLocal, engine


def _reset_postgres_sequences() -> None:
    """Explicit ids were inserted, so move each SERIAL sequence past the max id."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table in ["companies", "wind_farms", "turbines", "failures", "maintenances"]:
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
                )
            )


def seed(reset: bool = False, seed_value: int = 7) -> bool:
    """Returns True if data was inserted."""
    with SessionLocal() as session:
        if reset:
            for model in [MaintenanceModel, FailureModel, TurbineModel, WindFarmModel, CompanyModel]:
                session.execute(delete(model))
            session.commit()

        if session.scalar(select(func.count()).select_from(CompanyModel)):
            print("Database already has data. Use --reset to reload.")
            return False

        dataset = generate_dataset(seed=seed_value)
        save_dataset(session, dataset)
        session.commit()

    _reset_postgres_sequences()
    print(
        f"Seeded {len(dataset.companies)} companies, {len(dataset.farms)} farms, "
        f"{len(dataset.turbines)} turbines, {len(dataset.failures)} failures, "
        f"{len(dataset.maintenances)} maintenances."
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed WindOps with synthetic data")
    parser.add_argument("--reset", action="store_true", help="delete existing data first")
    parser.add_argument("--seed", type=int, default=7, help="random seed for the generator")
    args = parser.parse_args()
    seed(reset=args.reset, seed_value=args.seed)


if __name__ == "__main__":
    main()
