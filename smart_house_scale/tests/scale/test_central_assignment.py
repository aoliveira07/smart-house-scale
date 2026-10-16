from datetime import UTC, datetime
from pathlib import Path
import sys
from uuid import uuid4


CENTRAL_ROOT = Path(__file__).parents[2] / "backend" / "central_api"
if str(CENTRAL_ROOT) not in sys.path:
    sys.path.insert(0, str(CENTRAL_ROOT))

from app.services.scale import ScaleService  # noqa: E402


class CentralFakeRepository:
    def __init__(self):
        self.user = {
            "id": uuid4(),
            "name": "Léa",
            "birth_date": "1972-01-31",
            "height_cm": 150,
            "biological_sex": "female",
            "initial_reference_weight_kg": 63,
            "target_weight_kg": 59,
        }
        self.measurement = {
            "id": uuid4(),
            "user_id": None,
            "status": "pending",
            "weight_kg": 69.1,
            "measured_at": datetime(2026, 10, 16, 10, 0, tzinfo=UTC),
            "assignment_method": None,
        }

    def get_user(self, user_id):
        return self.user if user_id == self.user["id"] else None

    def get_measurement(self, measurement_id):
        return self.measurement if measurement_id == self.measurement["id"] else None

    def update_measurement_assignment(self, measurement_id, *, status, user_id, method):
        if measurement_id != self.measurement["id"]:
            return None
        self.measurement.update(
            status=status,
            user_id=user_id,
            assignment_method=method,
        )
        return dict(self.measurement)

    def user_measurements(self, user_id, limit=1000):
        return [
            dict(self.measurement)
        ] if self.measurement["user_id"] == user_id and self.measurement["status"] == "assigned" else []


def test_central_manual_assignment_updates_history_and_method():
    repository = CentralFakeRepository()
    result = ScaleService(repository).assign(
        repository.measurement["id"], repository.user["id"], method="manual"
    )

    assert result["status"] == "assigned"
    assert result["user_id"] == repository.user["id"]
    assert result["assignment_method"] == "manual"
    assert result["user_summary"]["current_weight_kg"] == 69.1
