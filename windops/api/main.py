"""FastAPI application entry point.

Run locally:
    uvicorn windops.api.main:app --reload
Interactive docs at http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI

from windops.api.routes import analytics, catalog, events

app = FastAPI(
    title="WindOps 360 API",
    version="0.1.0",
    description=(
        "Maintenance and performance analytics for wind farms: availability, MTTR, MTBF, "
        "lost energy, financial impact and turbine prioritisation. "
        "All demo data is synthetic."
    ),
)

app.include_router(catalog.router)
app.include_router(events.router)
app.include_router(analytics.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
