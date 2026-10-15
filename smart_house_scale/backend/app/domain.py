"""Assignment rules for stabilized scale readings."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class Candidate:
    user_id: str
    name: str
    baseline_kg: float
    delta_kg: float
    tolerance_kg: float


def baseline_weight(user: dict[str, Any], recent_weights: Iterable[float]) -> float:
    """Use the median of up to five assigned readings, then the initial reference."""

    values = [float(value) for value in recent_weights if value is not None][:5]
    if values:
        return float(median(values))
    return float(user["initial_reference_weight_kg"])


def find_candidates(weight_kg: float, users: Iterable[dict[str, Any]], histories: dict[str, list[float]]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for user in users:
        baseline = baseline_weight(user, histories.get(str(user["id"]), []))
        tolerance = float(user.get("auto_assign_tolerance_kg") or 3.0)
        delta = abs(float(weight_kg) - baseline)
        if delta <= tolerance:
            candidates.append(Candidate(str(user["id"]), user["name"], baseline, delta, tolerance))
    return sorted(candidates, key=lambda candidate: candidate.delta_kg)


def assignment_decision(weight_kg: float, users: Iterable[dict[str, Any]], histories: dict[str, list[float]]) -> dict[str, Any]:
    """Implement the V1 decision table without mutating a database."""

    candidates = find_candidates(weight_kg, users, histories)
    serialized = [
        {
            "user_id": candidate.user_id,
            "name": candidate.name,
            "baseline_kg": round(candidate.baseline_kg, 3),
            "delta_kg": round(candidate.delta_kg, 3),
            "tolerance_kg": round(candidate.tolerance_kg, 3),
        }
        for candidate in candidates
    ]
    if len(candidates) == 1:
        selected = candidates[0]
        return {
            "status": "assigned",
            "user_id": selected.user_id,
            "pending_reason": None,
            "assignment_method": "automatic",
            "assignment_delta_kg": round(selected.delta_kg, 3),
            "confidence": round(max(0.0, 1.0 - selected.delta_kg / selected.tolerance_kg), 4),
            "candidates": serialized,
        }
    return {
        "status": "pending",
        "user_id": None,
        "pending_reason": "multiple_candidates" if len(candidates) > 1 else "unknown_or_visitor",
        "assignment_method": None,
        "assignment_delta_kg": None,
        "confidence": None,
        "candidates": serialized,
    }
