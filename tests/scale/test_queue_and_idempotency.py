import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

try:
    from smart_house_scale.backend.app.service import ScaleService
    from smart_house_scale.custom_components.smart_house_scale.queue import OfflineQueue
except ModuleNotFoundError:
    from backend.app.service import ScaleService
    from custom_components.smart_house_scale.queue import OfflineQueue


def test_offline_queue_is_durable_and_idempotent(tmp_path: Path):
    path = tmp_path / "queue.sqlite3"
    queue = OfflineQueue(path)
    payload = {"weight_kg": 61.3, "received_at": "2026-10-15T12:00:00+00:00"}
    queue.put("m-1", payload, payload["received_at"])
    queue.put("m-1", payload, payload["received_at"])
    assert len(queue) == 1
    assert queue.items()[0]["measurement_uuid"] == "m-1"
    queue.remove("m-1")
    assert len(queue) == 0


class FakeRepository:
    def __init__(self):
        self.measurements = {}
        self.users = []
        self.device = {"id": uuid4(), "mac_address": "AA:BB:CC:DD:EE:FF"}

    async def get_measurement_by_uuid(self, measurement_uuid):
        return self.measurements.get(str(measurement_uuid))

    async def upsert_device(self, values):
        return self.device

    async def list_users(self, active_only=False):
        return self.users

    async def recent_weights(self, user_id, limit=5):
        return [m["weight_kg"] for m in self.measurements.values() if m.get("user_id") == user_id and m["status"] == "assigned"][:limit]

    async def upsert_session(self, values):
        return None

    async def insert_measurement(self, values):
        value = {"id": uuid4(), **values}
        self.measurements[str(values["measurement_uuid"])] = value
        return value

    async def get_user(self, user_id):
        return next((user for user in self.users if user["id"] == user_id), None)

    async def user_measurements(self, user_id):
        return [m for m in self.measurements.values() if m.get("user_id") == user_id and m["status"] == "assigned"]


def test_api_service_is_idempotent_by_measurement_uuid():
    repo = FakeRepository()
    person = {"id": uuid4(), "name": "Alice", "initial_reference_weight_kg": 61.0, "auto_assign_tolerance_kg": 3.0, "height_cm": 170}
    repo.users.append(person)
    payload = {"measurement_uuid": uuid4(), "mac_address": "AA:BB:CC:DD:EE:FF", "measured_at": datetime.now(UTC), "received_at": datetime.now(UTC), "weight_kg": 61.3, "original_unit": "kg", "stable": True}
    service = ScaleService(repo)
    first = asyncio.run(service.ingest(payload))
    second = asyncio.run(service.ingest(payload))
    assert first["status"] == "assigned"
    assert second["idempotent"] is True
    assert len(repo.measurements) == 1
