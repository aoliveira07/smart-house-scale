"""Home Assistant entity ingestion primitives.

The App deliberately does not open Bluetooth and does not decrypt Xiaomi
advertisements. Home Assistant's native integration owns that work. This
module converts the resulting state entity into the central API contract,
keeps one reading per session, and persists an offline spool.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib import error, request
from uuid import UUID, uuid4


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParsedMeasurement:
    weight_kg: float
    original_unit: str
    measured_at: datetime
    stable: bool
    impedance: int | None
    protocol: str
    model: str | None
    mac_address: str
    rssi: int | None
    raw_payload: dict[str, Any]


def normalize_mac(address: str) -> str:
    """Return canonical uppercase colon-separated MAC notation."""

    compact = "".join(ch for ch in str(address).strip().upper() if ch.isalnum())
    if len(compact) != 12 or any(ch not in "0123456789ABCDEF" for ch in compact):
        raise ValueError("Invalid Bluetooth MAC address")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def _synthetic_entity_mac(entity_id: str) -> str:
    """Create a stable local MAC for entities that expose no MAC attribute.

    The central schema historically keys devices by MAC. Generic Home
    Assistant entities do not always expose their underlying device address,
    so a locally administered, deterministic identifier keeps the existing
    idempotency contract without pretending to be a physical MAC. The real
    address is still used whenever the entity exposes one.
    """

    digest = hashlib.sha256(entity_id.encode("utf-8")).digest()
    return "02:" + ":".join(f"{part:02X}" for part in digest[:5])


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.now(UTC)
    else:
        parsed = datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _numeric_state(value: Any) -> float | None:
    if value is None or str(value).strip().lower() in {"", "unknown", "unavailable", "none", "null"}:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _mac_from_attributes(attributes: Mapping[str, Any], entity_id: str) -> str:
    for key in ("mac_address", "bluetooth_address", "address", "mac"):
        value = attributes.get(key)
        if value:
            try:
                return normalize_mac(str(value))
            except ValueError:
                continue
    return _synthetic_entity_mac(entity_id)


def parse_weight_entity_state(state: Any, *, entity_id: str) -> ParsedMeasurement | None:
    """Parse any numeric Home Assistant weight sensor state.

    Native Xiaomi entities normally publish kilograms and may include the
    physical Bluetooth address in their attributes. Other integrations are
    accepted as well; when no address is available the entity ID receives a
    stable local device key so the API remains idempotent.
    """

    if isinstance(state, Mapping):
        value = state.get("state")
        attributes = state.get("attributes") or {}
        measured_at = state.get("last_changed") or state.get("last_updated")
        actual_entity_id = str(state.get("entity_id") or entity_id)
    else:
        value = getattr(state, "state", None)
        attributes = getattr(state, "attributes", {}) or {}
        measured_at = getattr(state, "last_changed", None) or getattr(state, "last_updated", None)
        actual_entity_id = entity_id
    if not isinstance(attributes, Mapping):
        attributes = {}
    native_weight = _numeric_state(value)
    if native_weight is None:
        return None

    raw_unit = str(attributes.get("unit_of_measurement") or "kg").strip().lower()
    if raw_unit in {"lb", "lbs", "pound", "pounds"}:
        original_unit = "lbs"
        weight_kg = native_weight * 0.45359237
    elif raw_unit in {"jin", "市斤"}:
        original_unit = "jin"
        weight_kg = native_weight * 0.5
    elif raw_unit in {"g", "gram", "grams"}:
        original_unit = "kg"
        weight_kg = native_weight / 1000
    elif raw_unit in {"kg", "kilogram", "kilograms", ""}:
        original_unit = "kg"
        weight_kg = native_weight
    else:
        # A weight-class sensor without a known unit is treated as kilograms;
        # a random numeric sensor is ignored by the caller's sensor filter.
        if str(attributes.get("device_class") or "").lower() != "weight":
            return None
        original_unit = "kg"
        weight_kg = native_weight
    if not 5 <= weight_kg <= 400:
        return None

    rssi_value = attributes.get("rssi", attributes.get("signal_strength"))
    try:
        rssi = int(rssi_value) if rssi_value is not None else None
    except (TypeError, ValueError):
        rssi = None
    model_value = attributes.get("model") or attributes.get("model_name") or attributes.get("device_model")
    manufacturer = attributes.get("manufacturer")
    model = str(model_value or manufacturer or "") or None
    friendly_name = str(attributes.get("friendly_name") or actual_entity_id)
    impedance = attributes.get("impedance")
    try:
        impedance = int(impedance) if impedance is not None else None
    except (TypeError, ValueError):
        impedance = None

    return ParsedMeasurement(
        weight_kg=round(weight_kg, 3),
        original_unit=original_unit,
        measured_at=_parse_datetime(measured_at),
        stable=True,
        impedance=impedance,
        protocol=str(attributes.get("protocol") or "home_assistant_entity"),
        model=model,
        mac_address=_mac_from_attributes(attributes, actual_entity_id),
        rssi=rssi,
        raw_payload={
            "source": "home_assistant_state_entity",
            "entity_id": actual_entity_id,
            "friendly_name": friendly_name,
            "state": str(value),
            "unit_of_measurement": raw_unit or "kg",
            "device_class": attributes.get("device_class"),
            "mac_address_source": "entity_attribute"
            if any(attributes.get(key) for key in ("mac_address", "bluetooth_address", "address", "mac"))
            else "entity_id_fallback",
        },
    )


@dataclass(slots=True)
class MeasurementSession:
    session_uuid: UUID
    started_at: datetime
    last_seen_at: datetime
    latest: ParsedMeasurement
    advertisement_count: int = 1
    finalized: bool = False


class SessionAggregator:
    """Finalize one stable measurement per entity/device window."""

    def __init__(self, window_seconds: int = 30, clock: Callable[[], datetime] | None = None):
        self.window = timedelta(seconds=max(1, int(window_seconds)))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[str, MeasurementSession] = {}
        self.last_finalized: MeasurementSession | None = None

    def ingest(self, reading: ParsedMeasurement) -> ParsedMeasurement | None:
        now = self._clock()
        current = self._sessions.get(reading.mac_address)
        if current is None or now - current.last_seen_at > self.window:
            current = MeasurementSession(uuid4(), now, now, reading)
            self._sessions[reading.mac_address] = current
        else:
            current.last_seen_at = now
            current.latest = reading
            current.advertisement_count += 1
        if not reading.stable or current.finalized:
            return None
        current.finalized = True
        self.last_finalized = current
        return current.latest

    def reset(self) -> None:
        self._sessions.clear()
        self.last_finalized = None

    def expire(self) -> None:
        now = self._clock()
        for mac, current in list(self._sessions.items()):
            if now - current.last_seen_at > self.window:
                self._sessions.pop(mac, None)


class OfflineQueue:
    """Durable local spool; official history remains central PostgreSQL."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS queue (measurement_uuid TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def put(self, measurement_uuid: str, payload: dict[str, Any], created_at: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO queue(measurement_uuid, payload, created_at) VALUES (?, ?, ?)",
                (measurement_uuid, json.dumps(payload, ensure_ascii=False, default=str), created_at),
            )

    def items(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT measurement_uuid, payload FROM queue ORDER BY created_at").fetchall()
        return [{"measurement_uuid": uuid, **json.loads(payload)} for uuid, payload in rows]

    def remove(self, measurement_uuid: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM queue WHERE measurement_uuid = ?", (measurement_uuid,))

    def __len__(self) -> int:
        with sqlite3.connect(self.path) as db:
            return int(db.execute("SELECT COUNT(*) FROM queue").fetchone()[0])


class ScaleApiClient:
    """Small central API client; credentials never enter logs."""

    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.last_attempt: str | None = None
        self.last_success: str | None = None
        self.last_error: str | None = None

    async def post_measurement(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._request, "POST", "/api/v1/scale-measurements", payload)

    async def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        return await asyncio.to_thread(self._request, method, path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.last_attempt = payload.get("received_at") if payload else datetime.now(UTC).isoformat()
        try:
            req = request.Request(self.base_url + path, data=body, headers=headers, method=method)
            with request.urlopen(req, timeout=8) as response:
                value = json.loads(response.read().decode("utf-8"))
            self.last_success = self.last_attempt
            self.last_error = None
            return value
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            self.last_error = type(exc).__name__
            raise
