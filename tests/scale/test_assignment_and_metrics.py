from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

try:
    from smart_house_scale.backend.app.domain import assignment_decision, baseline_weight
    from smart_house_scale.backend.app.metrics import calculate_bmi, bmi_classification, mifflin_st_jeor, summarize_user
except ModuleNotFoundError:
    from backend.app.domain import assignment_decision, baseline_weight
    from backend.app.metrics import calculate_bmi, bmi_classification, mifflin_st_jeor, summarize_user


def user(name, weight, user_id=None, tolerance=3.0):
    return {"id": user_id or uuid4(), "name": name, "initial_reference_weight_kg": weight, "auto_assign_tolerance_kg": tolerance, "height_cm": 170, "birth_date": "1990-01-01", "biological_sex": "female"}


def test_case_a_auto_assignment_and_dynamic_baseline():
    person = user("Alice", 61.0)
    assert baseline_weight(person, [61.8, 61.0, 60.9, 61.2, 61.1]) == 61.1
    result = assignment_decision(61.3, [person], {str(person["id"]): [61.0]})
    assert result["status"] == "assigned"
    assert result["assignment_method"] == "automatic"


def test_case_b_discrepant_reading_does_not_assign_or_change_baseline():
    person = user("Alice", 61.0)
    result = assignment_decision(70.0, [person], {str(person["id"]): [61.0, 61.2]})
    assert result["status"] == "pending"
    assert result["pending_reason"] == "unknown_or_visitor"
    assert baseline_weight(person, [61.0, 61.2]) == 61.1


def test_case_c_multiple_candidates_is_pending():
    alice = user("Alice", 61)
    bob = user("Bob", 63)
    result = assignment_decision(62, [alice, bob], {str(alice["id"]): [], str(bob["id"]): []})
    assert result["status"] == "pending"
    assert result["pending_reason"] == "multiple_candidates"
    assert len(result["candidates"]) == 2


def test_metrics_measured_calculated_and_estimated():
    person = user("Alice", 61, tolerance=3)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    measurements = [{"measured_at": start + timedelta(days=day), "weight_kg": weight} for day, weight in [(0, 61), (1, 61.4), (2, 60.8), (8, 60.5), (31, 59.8)]]
    summary = summarize_user(person, measurements)
    assert calculate_bmi(61, 170) == 21.11
    assert bmi_classification(21.1, 36) == "normal"
    assert bmi_classification(21.1, 12) is None
    assert mifflin_st_jeor(61, 170, 36, "female") is not None
    assert summary["metric_origins"]["weight"] == "measured"
    assert summary["metric_origins"]["bmi"] == "calculated"
    assert summary["bmr_origin"] == "estimated"
    assert summary["trend_kg_per_day"] is not None
