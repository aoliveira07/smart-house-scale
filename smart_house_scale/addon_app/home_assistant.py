"""Home Assistant Supervisor bridge for the Smart House Scale App."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import quote
from uuid import uuid4

import httpx
import websockets

from .ingestion import OfflineQueue, ScaleApiClient, SessionAggregator, parse_weight_entity_state
from .settings import validate_weight_entity_id


_LOGGER = logging.getLogger(__name__)
SUPERVISOR_REST_URL = "http://supervisor/core/api"
SUPERVISOR_WEBSOCKET_URL = "ws://supervisor/core/websocket"


class HomeAssistantUnavailable(RuntimeError):
    """Raised when the Supervisor proxy cannot be used."""


class HomeAssistantEntityBridge:
    """Listen to one configured HA state entity and forward finalized weights."""

    def __init__(
        self,
        api: ScaleApiClient,
        *,
        data_dir: str | Path,
        entity_id: str,
        supervisor_token: str | None = None,
        session_window_seconds: int = 30,
        websocket_factory: Callable[..., Any] | None = None,
        rest_json: Callable[[str], Awaitable[Any]] | None = None,
    ):
        self.api = api
        self.entity_id = validate_weight_entity_id(entity_id)
        self.supervisor_token = supervisor_token or os.getenv("SUPERVISOR_TOKEN", "")
        self.websocket_url = os.getenv("SMART_HOUSE_SCALE_HA_WEBSOCKET_URL", SUPERVISOR_WEBSOCKET_URL)
        self.rest_url = os.getenv("SMART_HOUSE_SCALE_HA_REST_URL", SUPERVISOR_REST_URL).rstrip("/")
        self.queue = OfflineQueue(Path(data_dir) / "measurement_queue.sqlite3")
        self.sessions = SessionAggregator(session_window_seconds)
        self._websocket_factory = websocket_factory or websockets.connect
        self._rest_json_override = rest_json
        self._stop = asyncio.Event()
        self._run_task: asyncio.Task[None] | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._started = False
        self._state_signature: tuple[Any, ...] | None = None
        self._subscription_id = 100
        self.connected = False
        self.last_state = "not_configured" if not self.supervisor_token else "starting"
        self.last_seen_at: str | None = None
        self.last_measurement: dict[str, Any] | None = None
        self.last_entity_state: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_connection_attempt: str | None = None
        self.last_result: dict[str, Any] | None = None

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop.clear()
        self._run_task = asyncio.create_task(self._listen_loop(), name="smart-house-scale-ha-listener")
        self._flush_task = asyncio.create_task(self._flush_loop(), name="smart-house-scale-queue-flush")
        await self.flush_queue()

    async def stop(self) -> None:
        self._started = False
        self._stop.set()
        for task in (self._run_task, self._flush_task):
            if task:
                task.cancel()
        await asyncio.gather(*(task for task in (self._run_task, self._flush_task) if task), return_exceptions=True)
        self._run_task = None
        self._flush_task = None
        self.connected = False

    async def set_entity_id(self, entity_id: str) -> None:
        normalized = validate_weight_entity_id(entity_id)
        if normalized == self.entity_id:
            return
        self.entity_id = normalized
        self._state_signature = None
        self.sessions.reset()
        self.last_entity_state = None
        self.last_state = "reconfiguring"
        if self._started:
            if self._run_task:
                self._run_task.cancel()
                await asyncio.gather(self._run_task, return_exceptions=True)
            self._run_task = asyncio.create_task(self._listen_loop(), name="smart-house-scale-ha-listener")

    async def _listen_loop(self) -> None:
        if not self.supervisor_token:
            self.connected = False
            self.last_state = "not_configured"
        while not self._stop.is_set():
            if not self.supervisor_token:
                await self._wait(30)
                continue
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                self.last_state = "connection_error"
                self.last_error = type(exc).__name__
                _LOGGER.warning("Home Assistant state bridge unavailable: %s", type(exc).__name__)
                await self._wait(5)

    async def _listen_once(self) -> None:
        self.last_connection_attempt = datetime.now(UTC).isoformat()
        async with self._websocket_factory(
            self.websocket_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_size=2**20,
        ) as websocket:
            greeting = await self._receive_json(websocket)
            if greeting.get("type") == "auth_required":
                await websocket.send(json.dumps({"type": "auth", "access_token": self.supervisor_token}))
                authenticated = await self._receive_json(websocket)
                if authenticated.get("type") != "auth_ok":
                    raise HomeAssistantUnavailable("Home Assistant rejected the Supervisor websocket token")
            elif greeting.get("type") != "auth_ok":
                raise HomeAssistantUnavailable("Unexpected Home Assistant websocket handshake")

            self.connected = True
            self.last_state = "connected"
            self.last_error = None
            self._subscription_id += 1
            await websocket.send(
                json.dumps(
                    {
                        "id": self._subscription_id,
                        "type": "subscribe_events",
                        "event_type": "state_changed",
                    }
                )
            )
            try:
                current = await self._rest_json(f"/states/{quote(self.entity_id, safe='')}")
                await self._handle_state(current)
            except Exception as exc:
                # WebSocket events remain useful if the initial REST snapshot
                # is temporarily unavailable.
                self.last_error = type(exc).__name__

            while not self._stop.is_set():
                message = await self._receive_json(websocket)
                if message.get("type") != "event":
                    continue
                event = message.get("event") or {}
                data = event.get("data") or {}
                if data.get("entity_id") != self.entity_id:
                    continue
                new_state = data.get("new_state")
                if new_state:
                    await self._handle_state(new_state)

    async def _handle_state(self, state: Any) -> None:
        if not isinstance(state, Mapping):
            return
        actual_entity_id = str(state.get("entity_id") or self.entity_id)
        if actual_entity_id != self.entity_id:
            return
        attributes = state.get("attributes") or {}
        signature = (
            str(state.get("state")),
            str(state.get("last_changed") or ""),
            str(state.get("last_updated") or ""),
            json.dumps(attributes, sort_keys=True, default=str),
        )
        if signature == self._state_signature:
            return
        self._state_signature = signature
        self.last_entity_state = {
            "entity_id": actual_entity_id,
            "state": state.get("state"),
            "last_changed": state.get("last_changed"),
            "last_updated": state.get("last_updated"),
            "attributes": dict(attributes) if isinstance(attributes, Mapping) else {},
        }
        reading = parse_weight_entity_state(state, entity_id=self.entity_id)
        if reading is None:
            self.last_state = "waiting_for_numeric_weight"
            return
        self.last_seen_at = datetime.now(UTC).isoformat()
        final = self.sessions.ingest(reading)
        if final is None:
            self.last_state = "duplicate_in_session"
            return
        await self._finalize(final)

    async def _finalize(self, reading: Any) -> None:
        session = self.sessions.last_finalized
        received_at = datetime.now(UTC).isoformat()
        raw_payload = dict(reading.raw_payload)
        payload = {
            "measurement_uuid": str(uuid4()),
            "session_uuid": str(session.session_uuid) if session else None,
            "session_started_at": session.started_at.isoformat() if session else None,
            "session_last_seen_at": session.last_seen_at.isoformat() if session else None,
            "advertisement_count": session.advertisement_count if session else 1,
            "mac_address": reading.mac_address,
            "device_name": raw_payload.get("friendly_name") or self.entity_id,
            "measured_at": reading.measured_at.isoformat(),
            "received_at": received_at,
            "weight_kg": reading.weight_kg,
            "original_unit": reading.original_unit,
            "impedance": reading.impedance,
            "rssi": reading.rssi,
            "protocol": reading.protocol,
            "model": reading.model,
            "raw_payload": raw_payload,
            "stable": reading.stable,
        }
        self.last_measurement = payload
        try:
            self.last_result = await self.api.post_measurement(payload)
            self.last_state = str(self.last_result.get("status", "assigned"))
            self.last_error = None
        except Exception as exc:
            self.last_state = "queued"
            self.last_error = type(exc).__name__
            self.queue.put(payload["measurement_uuid"], payload, received_at)

    async def flush_queue(self) -> None:
        for item in self.queue.items():
            try:
                self.last_result = await self.api.post_measurement(item)
            except Exception as exc:
                self.last_error = type(exc).__name__
                break
            self.queue.remove(item["measurement_uuid"])
        if len(self.queue) == 0 and self.last_result:
            self.last_state = str(self.last_result.get("status", self.last_state))

    async def _flush_loop(self) -> None:
        while not self._stop.is_set():
            await self._wait(60)
            if not self._stop.is_set():
                await self.flush_queue()

    async def _wait(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    async def _receive_json(self, websocket: Any) -> dict[str, Any]:
        value = await websocket.recv()
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise HomeAssistantUnavailable("Invalid Home Assistant websocket message")
        return parsed

    async def _rest_json(self, path: str) -> Any:
        if self._rest_json_override:
            return await self._rest_json_override(path)
        if not self.supervisor_token:
            raise HomeAssistantUnavailable("SUPERVISOR_TOKEN is not available")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.rest_url + path,
                headers={"Authorization": f"Bearer {self.supervisor_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def list_weight_sensors(self) -> list[dict[str, Any]]:
        states = await self._rest_json("/states")
        if not isinstance(states, list):
            return []
        result: list[dict[str, Any]] = []
        accepted_units = {"kg", "g", "lb", "lbs", "jin", "市斤"}
        for item in states:
            if not isinstance(item, Mapping) or not str(item.get("entity_id", "")).startswith("sensor."):
                continue
            attributes = item.get("attributes") or {}
            if not isinstance(attributes, Mapping):
                attributes = {}
            try:
                float(str(item.get("state", "")).replace(",", "."))
            except (TypeError, ValueError):
                continue
            unit = str(attributes.get("unit_of_measurement") or "").strip().lower()
            device_class = str(attributes.get("device_class") or "").strip().lower()
            friendly_name = str(attributes.get("friendly_name") or item["entity_id"])
            searchable = f"{item['entity_id']} {friendly_name}".lower()
            if device_class != "weight" and unit not in accepted_units and not any(
                word in searchable for word in ("weight", "peso", "scale", "balanc")
            ):
                continue
            result.append(
                {
                    "entity_id": item["entity_id"],
                    "friendly_name": friendly_name,
                    "state": item.get("state"),
                    "unit_of_measurement": unit or "kg",
                    "device_class": attributes.get("device_class"),
                    "model": attributes.get("model") or attributes.get("model_name"),
                    "last_changed": item.get("last_changed"),
                }
            )
        return sorted(result, key=lambda item: (str(item["friendly_name"]).lower(), item["entity_id"]))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "source": "home_assistant_state_entity",
            "configured_entity_id": self.entity_id,
            "websocket_url": self.websocket_url,
            "connection": "connected" if self.connected else self.last_state,
            "state": self.last_state,
            "last_connection_attempt": self.last_connection_attempt,
            "last_seen_at": self.last_seen_at,
            "last_entity_state": self.last_entity_state,
            "last_measurement": self.last_measurement,
            "last_attempt": self.api.last_attempt,
            "last_sync": self.api.last_success,
            "queue_items": len(self.queue),
            "last_error": self.last_error or self.api.last_error,
        }
