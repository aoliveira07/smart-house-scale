import json
import asyncio
from pathlib import Path

from smart_house_scale.addon_app.home_assistant import HomeAssistantEntityBridge


class FakeSocket:
    def __init__(self, bridge: HomeAssistantEntityBridge):
        self.bridge = bridge
        self.sent = []
        self.messages = iter([
            json.dumps({"type": "auth_required", "ha_version": "2026.10.0"}),
            json.dumps({"type": "auth_ok", "ha_version": "2026.10.0"}),
        ])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def recv(self):
        return next(self.messages)

    async def send(self, message):
        self.sent.append(json.loads(message))
        if self.sent[-1].get("type") == "subscribe_events":
            self.bridge._stop.set()


class FakeApi:
    last_attempt = None
    last_success = None
    last_error = None

    async def post_measurement(self, payload):
        self.last_attempt = payload["received_at"]
        self.last_success = self.last_attempt
        return {"status": "assigned"}


def test_supervisor_websocket_authentication_and_subscription(tmp_path: Path):
    asyncio.run(_test_supervisor_websocket_authentication_and_subscription(tmp_path))


async def _test_supervisor_websocket_authentication_and_subscription(tmp_path: Path):
    api = FakeApi()
    bridge = HomeAssistantEntityBridge(
        api,  # type: ignore[arg-type]
        data_dir=tmp_path,
        entity_id="sensor.scale_weight",
        supervisor_token="supervisor-token",
        rest_json=fake_rest_json,
    )
    socket = FakeSocket(bridge)
    bridge._websocket_factory = lambda *_args, **_kwargs: socket

    await bridge._listen_once()

    assert socket.sent[0] == {"type": "auth", "access_token": "supervisor-token"}
    assert socket.sent[1]["type"] == "subscribe_events"
    assert bridge.last_measurement is None
    bridge._stop.clear()
    await bridge._handle_state(_state("81.36"))
    assert bridge.last_measurement["weight_kg"] == 81.36
    assert bridge.last_state == "assigned"


def _state(value="81.35"):
    return {
        "entity_id": "sensor.scale_weight",
        "state": value,
        "last_changed": "2026-10-16T02:24:00Z",
        "attributes": {"unit_of_measurement": "kg", "device_class": "weight"},
    }


async def fake_rest_json(_path):
    return _state()
