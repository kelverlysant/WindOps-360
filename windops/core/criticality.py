"""Criticality index: which turbines deserve attention first.

The financial ranking alone answers "who cost the most". The criticality
index combines four signals, each min-max normalised across the turbines
being compared, into a 0-100 score:

    financial loss   40%
    failure count    25%
    downtime hours   20%
    MTTR             15%

Because it is relative, a score only makes sense inside the group it was
computed for (e.g. one company's fleet in one period).
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_WEIGHTS: dict[str, float] = {
    "loss_brl": 0.40,
    "failure_count": 0.25,
    "downtime_hours": 0.20,
    "mttr_hours": 0.15,
}


@dataclass
class CriticalityInput:
    turbine_id: int
    loss_brl: float
    failure_count: int
    downtime_hours: float
    mttr_hours: float | None


def _normalise(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if high == low:
        return [0.0 for _ in values]
    return [(v - low) / (high - low) for v in values]


def criticality_breakdown(
    items: list[CriticalityInput], weights: dict[str, float] | None = None
) -> dict[int, dict[str, float]]:
    """Points each signal contributes to the score: {turbine_id: {signal: points}}.

    The points of one turbine add up to its 0-100 score, which makes the
    index explainable ("this turbine is critical mainly because of MTTR").
    """
    if not items:
        return {}
    weights = weights or DEFAULT_WEIGHTS
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Weights must add up to a positive number")

    columns = {
        "loss_brl": _normalise([i.loss_brl for i in items]),
        "failure_count": _normalise([float(i.failure_count) for i in items]),
        "downtime_hours": _normalise([i.downtime_hours for i in items]),
        "mttr_hours": _normalise([i.mttr_hours or 0.0 for i in items]),
    }
    return {
        item.turbine_id: {name: 100 * weights[name] * columns[name][index] / total_weight for name in weights}
        for index, item in enumerate(items)
    }


def criticality_scores(items: list[CriticalityInput], weights: dict[str, float] | None = None) -> dict[int, float]:
    """Return {turbine_id: score 0..100}."""
    return {
        turbine_id: round(sum(points.values()), 1)
        for turbine_id, points in criticality_breakdown(items, weights).items()
    }
