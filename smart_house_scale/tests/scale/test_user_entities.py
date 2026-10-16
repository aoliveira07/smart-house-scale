import asyncio
import json
from pathlib import Path

from smart_house_scale.addon_app.mqtt_entities import UserEntityPublisher
from smart_house_scale.addon_app.user_entities import (
    STATUS_TOPIC,
    USER_METRICS,
    build_user_bundle,
    build_user_discovery,
    build_user_state,
    discovery_topic,
    slugify,
    user_state_topic,
)


def _user(*, active: bool = True, name: str = "Léa") -> dict:
    return {
        "id": "7d70ad69-58dc-4d88-9b53-9c64f25e2a1b",
        "user_id": "7d70ad69-58dc-4d88-9b53-9c64f25e2a1b",
        "name": name,
        "active": active,
        "current_weight_kg": 63.0,
        "bmi": 28.0,
        "bmi_classification": "overweight",
        "bmr": 1210.5,
        "change_7d_kg": -0.4,
        "change_30d_kg": -1.2,
        "change_90d_kg": None,
        "change_since_start_kg": 0.0,
        "average_kg": 63.2,
        "median_kg": 63.0,
        "minimum_kg": 62.8,
        "maximum_kg": 63.7,
        "frequency_per_week": 4.0,
        "measurement_count": 8,
        "target_weight_kg": 59.0,
        "target_progress_percent": 0.0,
        "trend_kg_per_day": -0.01,
        "last_measured_at": "2026-10-16T10:00:00+00:00",
        "metric_origins": {
            "weight": "measured",
            "bmi": "calculated",
            "bmr": "estimated",
        },
    }


def test_user_entity_ids_and_payloads_are_stable_and_user_only():
    user = _user()

    assert slugify("Léa Nascimento") == "lea_nascimento"
    assert user_state_topic(user).endswith(f"/{user['user_id']}/state")

    state = build_user_state(user)
    assert state["current_weight_kg"] == 63.0
    assert state["metric_origins"]["weight"] == "measured"
    assert "mac_address" not in state
    assert "pending_measurements" not in state

    metric = USER_METRICS[0]
    discovery = build_user_discovery(user, metric)
    assert discovery["unique_id"] == (
        f"smart_house_scale_{user['user_id']}_{metric.slug}"
    )
    assert discovery["state_topic"] == user_state_topic(user)
    assert discovery["availability_topic"] == STATUS_TOPIC
    assert discovery["device"]["identifiers"] == [
        f"smart_house_scale_user_{user['user_id']}"
    ]
    assert discovery["value_template"] == (
        "{{ value_json.current_weight_kg if value_json.current_weight_kg "
        "is not none else 'unknown' }}"
    )

    bundle = build_user_bundle(user)
    assert len(bundle) == len(USER_METRICS) + 1
    assert discovery_topic(user, metric) in bundle
    assert user_state_topic(user) in bundle


class _FakeApi:
    def __init__(self, users):
        self.users = users

    async def request(self, method, path):
        assert method == "GET"
        assert path == "/api/v1/scale-users"
        return self.users


class _FakeMqtt:
    def __init__(self):
        self.messages: list[tuple[str, str, int, bool]] = []

    async def publish(self, topic, payload, *, qos, retain):
        self.messages.append((topic, payload, qos, retain))


def test_publisher_syncs_active_users_and_clears_removed_entities(tmp_path: Path):
    user = _user()
    api = _FakeApi(
        [
            user,
            {**user, "id": "inactive", "user_id": "inactive", "active": False},
        ]
    )
    publisher = UserEntityPublisher(
        api,  # type: ignore[arg-type]
        data_dir=tmp_path,
        mqtt_host="mqtt",
        mqtt_factory=object,
    )
    mqtt = _FakeMqtt()

    asyncio.run(publisher._sync(mqtt))

    assert publisher.diagnostics()["published_entities"] == len(USER_METRICS)
    assert publisher.diagnostics()["user_count"] == 1
    retained = {topic: payload for topic, payload, _qos, _retain in mqtt.messages}
    assert user_state_topic(user) in retained
    assert json.loads(retained[user_state_topic(user)])["bmi"] == 28.0
    assert all(
        topic.startswith("homeassistant/sensor/")
        for topic in retained
        if topic != user_state_topic(user)
    )

    api.users = []
    mqtt.messages.clear()
    asyncio.run(publisher._sync(mqtt))

    assert publisher.diagnostics()["published_entities"] == 0
    assert publisher.diagnostics()["user_count"] == 0
    assert mqtt.messages
    assert all(payload == "" for _topic, payload, _qos, _retain in mqtt.messages)
