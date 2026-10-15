"""Measured, calculated and estimated health indicators."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from math import fsum
from statistics import median
from typing import Any, Iterable


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def calculate_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if weight_kg is None or not height_cm or height_cm <= 0:
        return None
    height_m = height_cm / 100
    return round(weight_kg / (height_m * height_m), 2)


def age_years(birth_date: date | str | None, at: datetime | None = None) -> int | None:
    if not birth_date:
        return None
    if isinstance(birth_date, str):
        birth_date = date.fromisoformat(birth_date)
    today = (at or datetime.now(UTC)).date()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def bmi_classification(bmi: float | None, age: int | None) -> str | None:
    if bmi is None or age is None or age < 18:
        return None
    if bmi < 18.5:
        return "underweight"
    if bmi < 25:
        return "normal"
    if bmi < 30:
        return "overweight"
    return "obesity"


def mifflin_st_jeor(weight_kg: float | None, height_cm: float | None, age: int | None, biological_sex: str | None) -> float | None:
    if weight_kg is None or height_cm is None or age is None or age < 18 or not biological_sex:
        return None
    sex = biological_sex.lower()
    if sex not in {"male", "female"}:
        return None
    value = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == "male" else -161)
    return round(value, 1)


def _daily_medians(measurements: Iterable[dict[str, Any]]) -> list[tuple[datetime, float]]:
    grouped: dict[date, list[float]] = defaultdict(list)
    for measurement in measurements:
        when = _as_datetime(measurement["measured_at"])
        grouped[when.date()].append(float(measurement["weight_kg"]))
    return [(datetime.combine(day, datetime.min.time(), tzinfo=UTC), float(median(values))) for day, values in sorted(grouped.items())]


def _change(measurements: list[dict[str, Any]], current: float | None, days: int) -> float | None:
    if current is None or not measurements:
        return None
    latest_at = max(_as_datetime(item["measured_at"]) for item in measurements)
    cutoff = latest_at - timedelta(days=days)
    before = [float(item["weight_kg"]) for item in measurements if _as_datetime(item["measured_at"]) <= cutoff]
    return round(current - float(median(before)), 2) if before else None


def trend_per_day(measurements: Iterable[dict[str, Any]]) -> float | None:
    points = _daily_medians(measurements)
    if len(points) < 2:
        return None
    x = [point[0].timestamp() / 86400 for point in points]
    y = [point[1] for point in points]
    x_bar, y_bar = fsum(x) / len(x), fsum(y) / len(y)
    denominator = fsum((value - x_bar) ** 2 for value in x)
    if not denominator:
        return 0.0
    return round(fsum((a - x_bar) * (b - y_bar) for a, b in zip(x, y)) / denominator, 3)


def summarize_user(user: dict[str, Any], measurements: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(measurements, key=lambda item: _as_datetime(item["measured_at"]))
    weights = [float(item["weight_kg"]) for item in ordered]
    current = weights[-1] if weights else None
    last_at = ordered[-1]["measured_at"] if ordered else None
    bmi = calculate_bmi(current, user.get("height_cm"))
    age = age_years(user.get("birth_date"), _as_datetime(last_at) if last_at else None)
    days = max(1, ((_as_datetime(last_at) - _as_datetime(ordered[0]["measured_at"])).days + 1) if last_at and ordered else 1)
    target = user.get("target_weight_kg")
    initial = user.get("initial_reference_weight_kg")
    progress = None
    if target is not None and initial is not None and current is not None and float(initial) != float(target):
        progress = round((float(initial) - current) / (float(initial) - float(target)) * 100, 1)
    return {
        "user_id": str(user["id"]),
        "name": user["name"],
        "current_weight_kg": round(current, 2) if current is not None else None,
        "last_measured_at": last_at,
        "bmi": bmi,
        "bmi_classification": bmi_classification(bmi, age),
        "bmr": mifflin_st_jeor(current, user.get("height_cm"), age, user.get("biological_sex")),
        "bmr_origin": "estimated" if mifflin_st_jeor(current, user.get("height_cm"), age, user.get("biological_sex")) is not None else None,
        "change_7d_kg": _change(ordered, current, 7),
        "change_30d_kg": _change(ordered, current, 30),
        "change_90d_kg": _change(ordered, current, 90),
        "change_since_start_kg": round(current - float(initial), 2) if current is not None and initial is not None else None,
        "change_since_start_percent": round((current - float(initial)) / float(initial) * 100, 1) if current is not None and initial else None,
        "trend_kg_per_day": trend_per_day(ordered),
        "average_kg": round(fsum(weights) / len(weights), 2) if weights else None,
        "median_kg": round(float(median(weights)), 2) if weights else None,
        "minimum_kg": min(weights) if weights else None,
        "maximum_kg": max(weights) if weights else None,
        "frequency_per_week": round(len(weights) / days * 7, 2) if weights else 0,
        "measurement_count": len(weights),
        "target_weight_kg": target,
        "target_progress_percent": progress,
        "metric_origins": {
            "weight": "measured",
            "bmi": "calculated",
            "bmr": "estimated" if age is not None and age >= 18 else None,
            "trend": "calculated",
        },
    }
