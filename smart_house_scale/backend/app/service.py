"""Use-case layer shared by HTTP routes and future central Smart House jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .domain import assignment_decision
from .metrics import summarize_user


class ScaleService:
    def __init__(self, repository: Any):
        self.repository = repository

    async def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = await self.repository.get_measurement_by_uuid(payload["measurement_uuid"])
        if existing:
            return {**existing, "idempotent": True}
        device = await self.repository.upsert_device(
            {
                "name": payload.get("model") or "Xiaomi Scale",
                "mac_address": payload["mac_address"],
                "model": payload.get("model"),
                "protocol": payload.get("protocol"),
                "unit": payload.get("original_unit", "kg"),
                "last_seen_at": payload["received_at"],
                "last_rssi": payload.get("rssi"),
            }
        )
        if payload.get("session_uuid") and hasattr(self.repository, "upsert_session"):
            await self.repository.upsert_session(
                {
                    "session_uuid": payload["session_uuid"],
                    "device_id": device["id"],
                    "started_at": payload.get("session_started_at") or payload["measured_at"],
                    "last_seen_at": payload.get("session_last_seen_at") or payload["received_at"],
                    "finalized_at": payload["received_at"],
                    "advertisement_count": payload.get("advertisement_count", 1),
                    "stable": payload["stable"],
                    "final_measurement_uuid": payload["measurement_uuid"],
                    "raw_payload": payload.get("raw_payload") or {},
                }
            )
        users = await self.repository.list_users(active_only=True)
        histories = {str(user["id"]): await self.repository.recent_weights(user["id"], 5) for user in users}
        decision = assignment_decision(payload["weight_kg"], users, histories)
        record = {
            **payload,
            "device_id": device["id"],
            "status": decision["status"],
            "user_id": UUID(decision["user_id"]) if decision["user_id"] else None,
            "pending_reason": decision["pending_reason"],
            "assignment_method": decision["assignment_method"],
            "assignment_delta_kg": decision["assignment_delta_kg"],
            "confidence": decision["confidence"],
            "assignment_candidates": decision["candidates"],
            "assigned_at": datetime.now(UTC) if decision["status"] == "assigned" else None,
        }
        stored = await self.repository.insert_measurement(record)
        response = {**stored, "idempotent": False, "candidates": decision["candidates"]}
        if stored.get("user_id"):
            response["user_summary"] = await self.summary(stored["user_id"])
        return response

    async def summary(self, user_id: UUID) -> dict[str, Any]:
        user = await self.repository.get_user(user_id)
        if not user:
            raise KeyError("scale user not found")
        measurements = await self.repository.user_measurements(user_id)
        return summarize_user(user, measurements)

    async def assign(self, measurement_id: UUID, user_id: UUID, *, method: str = "manual") -> dict[str, Any]:
        user = await self.repository.get_user(user_id)
        if not user:
            raise KeyError("scale user not found")
        result = await self.repository.update_measurement_assignment(measurement_id, status="assigned", user_id=user_id, method=method)
        if not result:
            raise KeyError("measurement not found")
        return {**result, "user_summary": await self.summary(user_id)}

    async def discard(self, measurement_id: UUID) -> dict[str, Any]:
        result = await self.repository.update_measurement_assignment(measurement_id, status="discarded", user_id=None, method=None)
        if not result:
            raise KeyError("measurement not found")
        return result
