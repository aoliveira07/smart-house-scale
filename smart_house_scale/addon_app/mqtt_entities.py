"""Retained MQTT Discovery publisher for per-resident Home Assistant sensors."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .ingestion import ScaleApiClient
from .user_entities import (
    STATUS_TOPIC,
    build_user_bundle,
    user_state_topic,
)

try:  # aiomqtt is present in the App image; local parser tests may omit it.
    from aiomqtt import Client as MqttClient
except ImportError:  # pragma: no cover - exercised only without optional runtime deps
    MqttClient = None  # type: ignore[assignment,misc]


_LOGGER = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


class UserEntityPublisher:
    """Synchronize central resident summaries into MQTT Discovery entities."""

    def __init__(
        self,
        api: ScaleApiClient,
        *,
        data_dir: str | Path,
        discovery_prefix: str = "homeassistant",
        mqtt_host: str | None = None,
        mqtt_port: int = 1883,
        mqtt_username: str | None = None,
        mqtt_password: str | None = None,
        poll_interval_seconds: int = 30,
        mqtt_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.api = api
        self.discovery_prefix = discovery_prefix.strip("/") or "homeassistant"
        self.mqtt_host = (mqtt_host or "").strip()
        self.mqtt_port = int(mqtt_port)
        self.mqtt_username = mqtt_username or None
        self.mqtt_password = mqtt_password or None
        self.poll_interval_seconds = max(5, int(poll_interval_seconds))
        self._mqtt_factory = mqtt_factory or MqttClient
        self._published_topics_path = Path(data_dir) / "user_entity_topics.json"
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._sync_requested = asyncio.Event()
        self._client: Any = None
        self._connected = False
        self._last_sync: str | None = None
        self._last_error: str | None = None
        self._published_entities = 0
        self._user_count = 0

    @property
    def enabled(self) -> bool:
        return bool(self.mqtt_host)

    @property
    def available(self) -> bool:
        return self.enabled and self._mqtt_factory is not None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "available": self.available,
            "connected": self._connected,
            "discovery_prefix": self.discovery_prefix,
            "published_entities": self._published_entities,
            "user_count": self._user_count,
            "last_sync": self._last_sync,
            "last_error": self._last_error,
        }

    async def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="scale-user-mqtt")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        self._sync_requested.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self._connected = False
            self._client = None

    def request_sync(self) -> None:
        """Wake the publisher after a UI/API mutation without exposing secrets."""

        self._sync_requested.set()

    async def sync_now(self) -> None:
        """Request an immediate sync and yield once to the publisher loop."""

        self.request_sync()
        await asyncio.sleep(0)

    async def _run(self) -> None:
        while not self._stop.is_set():
            if not self.enabled:
                await self._wait_for_next_cycle(60)
                continue
            if self._mqtt_factory is None:
                self._last_error = "mqtt_dependency_unavailable"
                await self._wait_for_next_cycle(60)
                continue
            try:
                async with self._mqtt_factory(
                    hostname=self.mqtt_host,
                    port=self.mqtt_port,
                    username=self.mqtt_username,
                    password=self.mqtt_password,
                    identifier="tecnohead-scale-user-entities",
                ) as client:
                    self._client = client
                    self._connected = True
                    self._last_error = None
                    await client.publish(STATUS_TOPIC, "online", qos=1, retain=True)
                    await self._sync(client)
                    while not self._stop.is_set():
                        self._sync_requested.clear()
                        try:
                            await asyncio.wait_for(
                                self._sync_requested.wait(),
                                timeout=self.poll_interval_seconds,
                            )
                        except asyncio.TimeoutError:
                            pass
                        if not self._stop.is_set():
                            await self._sync(client)
                    try:
                        await client.publish(STATUS_TOPIC, "offline", qos=1, retain=True)
                    except Exception:  # pragma: no cover - broker disconnect path
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # never log credentials or broker payloads
                self._last_error = type(exc).__name__
                _LOGGER.warning("User MQTT entity sync unavailable: %s", type(exc).__name__)
            finally:
                self._connected = False
                self._client = None
            await self._wait_for_next_cycle(10)

    async def _wait_for_next_cycle(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=max(1, seconds))
        except asyncio.TimeoutError:
            return

    async def _sync(self, client: Any) -> None:
        payload = await self.api.request("GET", "/api/v1/scale-users")
        users = payload if isinstance(payload, list) else []
        active_users = [
            user
            for user in users
            if isinstance(user, Mapping) and user.get("active", True)
        ]
        current_topics: dict[str, str] = {}
        for user in active_users:
            bundle = build_user_bundle(user, self.discovery_prefix)
            for topic, value in bundle.items():
                is_state = topic == user_state_topic(user)
                current_topics[topic] = "state" if is_state else "config"
                await client.publish(
                    topic,
                    json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                    qos=1,
                    retain=True,
                )

        previous_topics = self._load_topics()
        for topic in previous_topics:
            if topic not in current_topics:
                await client.publish(topic, "", qos=1, retain=True)

        self._save_topics(current_topics)
        self._published_entities = sum(value == "config" for value in current_topics.values())
        self._user_count = len(active_users)
        self._last_sync = _timestamp()
        self._last_error = None

    def _load_topics(self) -> set[str]:
        try:
            value = json.loads(self._published_topics_path.read_text(encoding="utf-8"))
            if isinstance(value, list):
                return {str(topic) for topic in value}
            if isinstance(value, dict):
                return {str(topic) for topic in value}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return set()

    def _save_topics(self, topics: Mapping[str, str]) -> None:
        self._published_topics_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._published_topics_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(sorted(topics), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._published_topics_path)
