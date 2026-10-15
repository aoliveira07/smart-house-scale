"""Smart House Scale use cases backed by the existing SQLAlchemy session."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from math import fsum
from statistics import median
from typing import Any, Iterable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.scale import normalize_mac


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def baseline_weight(user: dict[str, Any], recent_weights: Iterable[float]) -> float:
    values = [float(value) for value in recent_weights if value is not None][:5]
    return float(median(values)) if values else float(user["initial_reference_weight_kg"])


def assignment_decision(
    weight_kg: float,
    users: Iterable[dict[str, Any]],
    histories: dict[str, list[float]],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for user in users:
        baseline = baseline_weight(user, histories.get(str(user["id"]), []))
        tolerance = float(user.get("auto_assign_tolerance_kg") or 3.0)
        delta = abs(float(weight_kg) - baseline)
        if delta <= tolerance:
            candidates.append(
                {
                    "user_id": str(user["id"]),
                    "name": user["name"],
                    "baseline_kg": round(baseline, 3),
                    "delta_kg": round(delta, 3),
                    "tolerance_kg": round(tolerance, 3),
                }
            )
    candidates.sort(key=lambda candidate: candidate["delta_kg"])
    if len(candidates) == 1:
        selected = candidates[0]
        return {
            "status": "assigned",
            "user_id": selected["user_id"],
            "pending_reason": None,
            "assignment_method": "automatic",
            "assignment_delta_kg": selected["delta_kg"],
            "confidence": round(
                max(0.0, 1.0 - selected["delta_kg"] / selected["tolerance_kg"]),
                4,
            ),
            "candidates": candidates,
        }
    return {
        "status": "pending",
        "user_id": None,
        "pending_reason": "multiple_candidates" if len(candidates) > 1 else "unknown_or_visitor",
        "assignment_method": None,
        "assignment_delta_kg": None,
        "confidence": None,
        "candidates": candidates,
    }


def calculate_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if weight_kg is None or not height_cm or height_cm <= 0:
        return None
    height_m = float(height_cm) / 100
    return round(float(weight_kg) / (height_m * height_m), 2)


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


def mifflin_st_jeor(
    weight_kg: float | None,
    height_cm: float | None,
    age: int | None,
    biological_sex: str | None,
) -> float | None:
    if weight_kg is None or height_cm is None or age is None or age < 18 or not biological_sex:
        return None
    sex = biological_sex.lower()
    if sex not in {"male", "female"}:
        return None
    value = 10 * float(weight_kg) + 6.25 * float(height_cm) - 5 * age + (5 if sex == "male" else -161)
    return round(value, 1)


def _daily_medians(measurements: Iterable[dict[str, Any]]) -> list[tuple[datetime, float]]:
    grouped: dict[date, list[float]] = defaultdict(list)
    for measurement in measurements:
        when = _as_datetime(measurement["measured_at"])
        grouped[when.date()].append(float(measurement["weight_kg"]))
    return [
        (datetime.combine(day, datetime.min.time(), tzinfo=UTC), float(median(values)))
        for day, values in sorted(grouped.items())
    ]


def _change(measurements: list[dict[str, Any]], current: float | None, days: int) -> float | None:
    if current is None or not measurements:
        return None
    latest_at = max(_as_datetime(item["measured_at"]) for item in measurements)
    cutoff = latest_at - timedelta(days=days)
    before = [
        float(item["weight_kg"])
        for item in measurements
        if _as_datetime(item["measured_at"]) <= cutoff
    ]
    return round(float(current) - float(median(before)), 2) if before else None


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
    return round(
        fsum((a - x_bar) * (b - y_bar) for a, b in zip(x, y)) / denominator,
        3,
    )


def summarize_user(user: dict[str, Any], measurements: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(measurements, key=lambda item: _as_datetime(item["measured_at"]))
    weights = [float(item["weight_kg"]) for item in ordered]
    current = weights[-1] if weights else None
    last_at = ordered[-1]["measured_at"] if ordered else None
    age = age_years(user.get("birth_date"), _as_datetime(last_at) if last_at else None)
    bmi = calculate_bmi(current, user.get("height_cm"))
    bmr = mifflin_st_jeor(current, user.get("height_cm"), age, user.get("biological_sex"))
    initial = user.get("initial_reference_weight_kg")
    target = user.get("target_weight_kg")
    progress = None
    if target is not None and initial is not None and current is not None and float(initial) != float(target):
        progress = round((float(initial) - current) / (float(initial) - float(target)) * 100, 1)
    days = max(
        1,
        ((_as_datetime(last_at) - _as_datetime(ordered[0]["measured_at"])).days + 1)
        if last_at and ordered
        else 1,
    )
    return {
        "user_id": str(user["id"]),
        "name": user["name"],
        "current_weight_kg": round(current, 2) if current is not None else None,
        "last_measured_at": last_at,
        "bmi": bmi,
        "bmi_classification": bmi_classification(bmi, age),
        "bmr": bmr,
        "bmr_origin": "estimated" if bmr is not None else None,
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
            "bmr": "estimated" if bmr is not None else None,
            "trend": "calculated",
        },
    }


class ScaleRepository:
    """Repository using the existing Smart House SQLAlchemy session."""

    def __init__(self, db: Session):
        self.db = db

    def list_devices(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.db.execute(
                text("SELECT * FROM health.scale_devices ORDER BY name")
            ).mappings().all()
        ]

    def get_device(self, device_id: UUID) -> dict[str, Any] | None:
        return _row(
            self.db.execute(
                text("SELECT * FROM health.scale_devices WHERE id = :id"),
                {"id": device_id},
            ).mappings().one_or_none()
        )

    def upsert_device(self, values: dict[str, Any]) -> dict[str, Any]:
        params = {
            "id": values.get("id", uuid4()),
            "name": values.get("name") or "Xiaomi Scale",
            "mac_address": normalize_mac(values["mac_address"]),
            "model": values.get("model"),
            "protocol": values.get("protocol"),
            "unit": values.get("unit", "kg"),
            "active": values.get("active", True),
            "last_seen_at": values.get("last_seen_at"),
            "last_rssi": values.get("last_rssi"),
        }
        row = self.db.execute(
            text(
                """
                INSERT INTO health.scale_devices
                    (id, name, mac_address, model, protocol, unit, active,
                     last_seen_at, last_rssi)
                VALUES
                    (:id, :name, :mac_address, :model, :protocol, :unit,
                     :active, :last_seen_at, :last_rssi)
                ON CONFLICT (mac_address) DO UPDATE SET
                    name = COALESCE(NULLIF(EXCLUDED.name, ''), health.scale_devices.name),
                    model = COALESCE(EXCLUDED.model, health.scale_devices.model),
                    protocol = COALESCE(EXCLUDED.protocol, health.scale_devices.protocol),
                    unit = COALESCE(EXCLUDED.unit, health.scale_devices.unit),
                    last_seen_at = COALESCE(EXCLUDED.last_seen_at, health.scale_devices.last_seen_at),
                    last_rssi = COALESCE(EXCLUDED.last_rssi, health.scale_devices.last_rssi),
                    updated_at = now()
                RETURNING *
                """
            ),
            params,
        ).mappings().one()
        self.db.commit()
        return dict(row)

    def create_device(self, values: dict[str, Any]) -> dict[str, Any]:
        return self.upsert_device(values)

    def update_device(self, device_id: UUID, values: dict[str, Any]) -> dict[str, Any] | None:
        return self._update("scale_devices", device_id, values)

    def list_users(self, active_only: bool = False) -> list[dict[str, Any]]:
        where = " WHERE active = TRUE" if active_only else ""
        return [
            dict(row)
            for row in self.db.execute(
                text(f"SELECT * FROM health.scale_users{where} ORDER BY name")
            ).mappings().all()
        ]

    def get_user(self, user_id: UUID) -> dict[str, Any] | None:
        return _row(
            self.db.execute(
                text("SELECT * FROM health.scale_users WHERE id = :id"),
                {"id": user_id},
            ).mappings().one_or_none()
        )

    def create_user(self, values: dict[str, Any]) -> dict[str, Any]:
        row = self.db.execute(
            text(
                """
                INSERT INTO health.scale_users
                    (id, name, avatar, birth_date, height_cm, biological_sex,
                     initial_reference_weight_kg, target_weight_kg,
                     auto_assign_tolerance_kg, active)
                VALUES
                    (:id, :name, :avatar, :birth_date, :height_cm,
                     :biological_sex, :initial_reference_weight_kg,
                     :target_weight_kg, :auto_assign_tolerance_kg, :active)
                RETURNING *
                """
            ),
            {
                "id": values.get("id", uuid4()),
                "name": values["name"],
                "avatar": values.get("avatar"),
                "birth_date": values.get("birth_date"),
                "height_cm": values.get("height_cm"),
                "biological_sex": values.get("biological_sex"),
                "initial_reference_weight_kg": values["initial_reference_weight_kg"],
                "target_weight_kg": values.get("target_weight_kg"),
                "auto_assign_tolerance_kg": values.get("auto_assign_tolerance_kg", 3.0),
                "active": values.get("active", True),
            },
        ).mappings().one()
        self.db.commit()
        return dict(row)

    def update_user(self, user_id: UUID, values: dict[str, Any]) -> dict[str, Any] | None:
        return self._update("scale_users", user_id, values)

    def _update(self, table: str, row_id: UUID, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "scale_devices": {"name", "model", "protocol", "unit", "active"},
            "scale_users": {
                "name", "avatar", "birth_date", "height_cm", "biological_sex",
                "initial_reference_weight_kg", "target_weight_kg",
                "auto_assign_tolerance_kg", "active",
            },
        }[table]
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return self.get_device(row_id) if table == "scale_devices" else self.get_user(row_id)
        assignments = ", ".join(
            f"{key} = :value_{index}" for index, key in enumerate(updates, 1)
        )
        params = {f"value_{index}": value for index, value in enumerate(updates.values(), 1)}
        params["id"] = row_id
        row = self.db.execute(
            text(
                f"UPDATE health.{table} SET {assignments}, updated_at = now() "
                "WHERE id = :id RETURNING *"
            ),
            params,
        ).mappings().one_or_none()
        self.db.commit()
        return _row(row)

    def get_measurement_by_uuid(self, measurement_uuid: UUID) -> dict[str, Any] | None:
        return _row(
            self.db.execute(
                text(
                    "SELECT * FROM health.scale_measurements "
                    "WHERE measurement_uuid = :measurement_uuid"
                ),
                {"measurement_uuid": measurement_uuid},
            ).mappings().one_or_none()
        )

    def recent_weights(self, user_id: UUID, limit: int = 5) -> list[float]:
        rows = self.db.execute(
            text(
                """
                SELECT weight_kg
                FROM health.scale_measurements
                WHERE user_id = :user_id AND status = 'assigned'
                ORDER BY measured_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        ).mappings().all()
        return [float(row["weight_kg"]) for row in rows]

    def upsert_session(self, values: dict[str, Any]) -> None:
        self.db.execute(
            text(
                """
                INSERT INTO health.scale_measurement_sessions
                    (id, session_uuid, device_id, started_at, last_seen_at,
                     finalized_at, advertisement_count, stable,
                     final_measurement_uuid, raw_payload)
                VALUES
                    (:id, :session_uuid, :device_id, :started_at, :last_seen_at,
                     :finalized_at, :advertisement_count, :stable,
                     :final_measurement_uuid, CAST(:raw_payload AS jsonb))
                ON CONFLICT (session_uuid) DO UPDATE SET
                    last_seen_at = EXCLUDED.last_seen_at,
                    finalized_at = EXCLUDED.finalized_at,
                    advertisement_count = EXCLUDED.advertisement_count,
                    stable = EXCLUDED.stable,
                    final_measurement_uuid = EXCLUDED.final_measurement_uuid,
                    raw_payload = EXCLUDED.raw_payload
                """
            ),
            {
                "id": uuid4(),
                "session_uuid": values["session_uuid"],
                "device_id": values["device_id"],
                "started_at": values["started_at"],
                "last_seen_at": values["last_seen_at"],
                "finalized_at": values.get("finalized_at"),
                "advertisement_count": values.get("advertisement_count", 1),
                "stable": values.get("stable", True),
                "final_measurement_uuid": values.get("final_measurement_uuid"),
                "raw_payload": _json(values.get("raw_payload")),
            },
        )
        self.db.commit()

    def insert_measurement(self, values: dict[str, Any]) -> dict[str, Any]:
        params = {
            "id": values.get("id", uuid4()),
            "measurement_uuid": values["measurement_uuid"],
            "device_id": values["device_id"],
            "user_id": values.get("user_id"),
            "measured_at": values["measured_at"],
            "received_at": values["received_at"],
            "weight_kg": values["weight_kg"],
            "original_unit": values["original_unit"],
            "impedance": values.get("impedance"),
            "rssi": values.get("rssi"),
            "raw_payload": _json(values.get("raw_payload")),
            "stable": values["stable"],
            "status": values["status"],
            "pending_reason": values.get("pending_reason"),
            "assignment_method": values.get("assignment_method"),
            "assignment_delta_kg": values.get("assignment_delta_kg"),
            "confidence": values.get("confidence"),
            "assigned_at": values.get("assigned_at"),
            "assignment_candidates": _json(values.get("assignment_candidates")),
            "session_uuid": values.get("session_uuid"),
            "protocol": values.get("protocol"),
            "model": values.get("model"),
        }
        row = self.db.execute(
            text(
                """
                INSERT INTO health.scale_measurements
                    (id, measurement_uuid, device_id, user_id, measured_at,
                     received_at, weight_kg, original_unit, impedance, rssi,
                     raw_payload, stable, status, pending_reason,
                     assignment_method, assignment_delta_kg, confidence,
                     assigned_at, assignment_candidates, session_uuid,
                     protocol, model)
                VALUES
                    (:id, :measurement_uuid, :device_id, :user_id, :measured_at,
                     :received_at, :weight_kg, :original_unit, :impedance, :rssi,
                     CAST(:raw_payload AS jsonb), :stable, :status,
                     :pending_reason, :assignment_method, :assignment_delta_kg,
                     :confidence, :assigned_at,
                     CAST(:assignment_candidates AS jsonb), :session_uuid,
                     :protocol, :model)
                ON CONFLICT (measurement_uuid) DO NOTHING
                RETURNING *
                """
            ),
            params,
        ).mappings().one_or_none()
        if row is None:
            self.db.rollback()
            existing = self.get_measurement_by_uuid(values["measurement_uuid"])
            if existing is None:
                raise RuntimeError("measurement conflict did not return existing row")
            return existing
        row_dict = dict(row)
        self.db.execute(
            text(
                """
                INSERT INTO health.scale_measurement_events
                    (measurement_id, action, to_status, to_user_id, metadata)
                VALUES
                    (:measurement_id, 'created', :to_status, :to_user_id,
                     CAST(:metadata AS jsonb))
                """
            ),
            {
                "measurement_id": row_dict["id"],
                "to_status": values["status"],
                "to_user_id": values.get("user_id"),
                "metadata": _json({"assignment_method": values.get("assignment_method")}),
            },
        )
        self.db.commit()
        return row_dict

    def list_measurements(
        self,
        *,
        status: str | None = None,
        user_id: UUID | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if user_id:
            clauses.append("user_id = :user_id")
            params["user_id"] = user_id
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return [
            dict(row)
            for row in self.db.execute(
                text(
                    "SELECT * FROM health.scale_measurements"
                    f"{where} ORDER BY measured_at DESC LIMIT :limit"
                ),
                params,
            ).mappings().all()
        ]

    def get_measurement(self, measurement_id: UUID) -> dict[str, Any] | None:
        return _row(
            self.db.execute(
                text("SELECT * FROM health.scale_measurements WHERE id = :id"),
                {"id": measurement_id},
            ).mappings().one_or_none()
        )

    def update_measurement_assignment(
        self,
        measurement_id: UUID,
        *,
        status: str,
        user_id: UUID | None,
        method: str | None,
    ) -> dict[str, Any] | None:
        before = self.get_measurement(measurement_id)
        if before is None:
            return None
        row = self.db.execute(
            text(
                """
                UPDATE health.scale_measurements
                SET status = :status,
                    user_id = :user_id,
                    assignment_method = :method,
                    assigned_at = CASE WHEN :status = 'assigned' THEN now() ELSE NULL END,
                    discarded_at = CASE WHEN :status = 'discarded' THEN now() ELSE NULL END,
                    pending_reason = CASE WHEN :status = 'assigned' THEN NULL ELSE pending_reason END,
                    updated_at = now()
                WHERE id = :id
                RETURNING *
                """
            ),
            {"status": status, "user_id": user_id, "method": method, "id": measurement_id},
        ).mappings().one()
        self.db.execute(
            text(
                """
                INSERT INTO health.scale_measurement_events
                    (measurement_id, action, from_status, to_status,
                     from_user_id, to_user_id, metadata)
                VALUES
                    (:measurement_id, :action, :from_status, :to_status,
                     :from_user_id, :to_user_id, CAST(:metadata AS jsonb))
                """
            ),
            {
                "measurement_id": measurement_id,
                "action": "assignment" if status == "assigned" else status,
                "from_status": before["status"],
                "to_status": status,
                "from_user_id": before.get("user_id"),
                "to_user_id": user_id,
                "metadata": _json({"assignment_method": method}),
            },
        )
        self.db.commit()
        return dict(row)

    def user_measurements(self, user_id: UUID, limit: int = 1000) -> list[dict[str, Any]]:
        return self.list_measurements(user_id=user_id, status="assigned", limit=limit)

    def health(self) -> dict[str, Any]:
        database = self.db.execute(text("SELECT current_database()")).scalar_one()
        last = self.db.execute(
            text(
                "SELECT measured_at, received_at FROM health.scale_measurements "
                "ORDER BY received_at DESC LIMIT 1"
            )
        ).mappings().one_or_none()
        ha = self.db.execute(
            text(
                "SELECT last_seen_at FROM health.scale_devices "
                "ORDER BY last_seen_at DESC NULLS LAST LIMIT 1"
            )
        ).mappings().one_or_none()
        return {
            "database": database,
            "last_measurement": _row(last),
            "last_communication_ha": _row(ha),
        }


class ScaleService:
    def __init__(self, repository: ScaleRepository):
        self.repository = repository

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self.repository.get_measurement_by_uuid(payload["measurement_uuid"])
        if existing:
            return {**existing, "idempotent": True}

        device = self.repository.upsert_device(
            {
                "name": payload.get("device_name") or payload.get("model") or "Xiaomi Scale",
                "mac_address": payload["mac_address"],
                "model": payload.get("model"),
                "protocol": payload.get("protocol"),
                "unit": payload.get("original_unit", "kg"),
                "last_seen_at": payload["received_at"],
                "last_rssi": payload.get("rssi"),
            }
        )
        if payload.get("session_uuid"):
            self.repository.upsert_session(
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

        users = self.repository.list_users(active_only=True)
        histories = {
            str(user["id"]): self.repository.recent_weights(user["id"], limit=5)
            for user in users
        }
        decision = assignment_decision(float(payload["weight_kg"]), users, histories)
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
        stored = self.repository.insert_measurement(record)
        response = {
            **stored,
            "idempotent": False,
            "candidates": decision["candidates"],
        }
        if stored.get("user_id"):
            response["user_summary"] = self.summary(stored["user_id"])
        return response

    def summary(self, user_id: UUID) -> dict[str, Any]:
        user = self.repository.get_user(user_id)
        if not user:
            raise KeyError("scale user not found")
        return summarize_user(user, self.repository.user_measurements(user_id))

    def assign(self, measurement_id: UUID, user_id: UUID, method: str = "manual") -> dict[str, Any]:
        if not self.repository.get_user(user_id):
            raise KeyError("scale user not found")
        result = self.repository.update_measurement_assignment(
            measurement_id,
            status="assigned",
            user_id=user_id,
            method=method,
        )
        if not result:
            raise KeyError("measurement not found")
        return {**result, "user_summary": self.summary(user_id)}

    def discard(self, measurement_id: UUID) -> dict[str, Any]:
        result = self.repository.update_measurement_assignment(
            measurement_id,
            status="discarded",
            user_id=None,
            method=None,
        )
        if not result:
            raise KeyError("measurement not found")
        return result
