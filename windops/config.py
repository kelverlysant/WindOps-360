"""Runtime configuration read from environment variables."""

from __future__ import annotations

import os

# Local default is SQLite so the project runs with zero setup.
# Docker Compose sets this to PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./windops.db")

ENERGY_PRICE_BRL_PER_MWH = float(os.getenv("ENERGY_PRICE_BRL_PER_MWH", "250"))

API_URL = os.getenv("API_URL", "http://localhost:8000")
