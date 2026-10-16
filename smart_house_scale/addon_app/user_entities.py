"""Home Assistant MQTT Discovery payloads for resident health metrics.

The App owns the central API view of each resident.  This module only turns
that view into retained MQTT Discovery and state payloads; it does not expose
the scale, Bluetooth, queue, or API diagnostics as user entities.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping


STATUS_TOPIC = "smart_house_scale/status"
BASE_STATE_TOPIC = "smart_house_scale/user"


@dataclass(frozen=True, slots=True)
class UserMetric:
    """One resident metric represented as an MQTT sensor."""

    key: str
    slug: str
    name: str
    icon: str
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    precision: int | None = 2


# Keep these slugs stable.  They become part of unique_id and therefore must
# not be renamed casually after an installation has created entities.
USER_METRICS: tuple[UserMetric, ...] = (
    UserMetric(
        "current_weight_kg",
        "weight",
        "Peso",
        "mdi:scale-bathroom",
        unit="kg",
        device_class="weight",
        state_class="measurement",
    ),
    UserMetric("bmi", "bmi", "IMC", "mdi:human", precision=2),
    UserMetric(
        "bmi_classification",
        "bmi_classification",
        "Classificação do IMC",
        "mdi:human-check",
        precision=None,
    ),
    UserMetric(
        "trend_kg_per_day",
        "weight_trend",
        "Tendência de peso",
        "mdi:chart-line",
        unit="kg/d",
        precision=3,
    ),
    UserMetric(
        "change_7d_kg",
        "weight_change_7d",
        "Variação 7 dias",
        "mdi:calendar-week",
        unit="kg",
    ),
    UserMetric(
        "change_30d_kg",
        "weight_change_30d",
        "Variação 30 dias",
        "mdi:calendar-month",
        unit="kg",
    ),
    UserMetric(
        "change_90d_kg",
        "weight_change_90d",
        "Variação 90 dias",
        "mdi:calendar-range",
        unit="kg",
    ),
    UserMetric(
        "change_since_start_kg",
        "weight_change_since_start",
        "Variação desde o início",
        "mdi:scale-balance",
        unit="kg",
    ),
    UserMetric(
        "change_since_start_percent",
        "weight_change_since_start_percent",
        "Variação percentual desde o início",
        "mdi:percent",
        unit="%",
        precision=1,
    ),
    UserMetric(
        "average_kg",
        "weight_average",
        "Peso médio",
        "mdi:chart-bell-curve",
        unit="kg",
    ),
    UserMetric(
        "median_kg",
        "weight_median",
        "Peso mediano",
        "mdi:chart-bell-curve",
        unit="kg",
    ),
    UserMetric(
        "minimum_kg",
        "weight_minimum",
        "Menor peso",
        "mdi:arrow-down-bold",
        unit="kg",
    ),
    UserMetric(
        "maximum_kg",
        "weight_maximum",
        "Maior peso",
        "mdi:arrow-up-bold",
        unit="kg",
    ),
    UserMetric(
        "frequency_per_week",
        "weighing_frequency",
        "Frequência de pesagens",
        "mdi:calendar-check",
        unit="pesagens/semana",
        precision=2,
    ),
    UserMetric(
        "measurement_count",
        "measurement_count",
        "Quantidade de pesagens",
        "mdi:counter",
        unit="pesagens",
        precision=0,
    ),
    UserMetric(
        "target_weight_kg",
        "target_weight",
        "Meta de peso",
        "mdi:target",
        unit="kg",
    ),
    UserMetric(
        "target_progress_percent",
        "target_progress",
        "Progresso para a meta",
        "mdi:progress-check",
        unit="%",
        precision=1,
    ),
    UserMetric(
        "bmr",
        "basal_metabolism",
        "Metabolismo basal estimado",
        "mdi:fire",
        unit="kcal/d",
        precision=1,
    ),
)


def slugify(value: str) -> str:
    """Create a readable, stable Home Assistant object-id fragment."""

    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    result = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return result or "usuario"


def _user_id(user: Mapping[str, Any]) -> str:
    value = str(user.get("user_id") or user.get("id") or "").strip()
    if not value:
        raise ValueError("A user payload needs an id")
    return value


def user_state_topic(user: Mapping[str, Any]) -> str:
    return f"{BASE_STATE_TOPIC}/{_user_id(user)}/state"


def discovery_topic(
    user: Mapping[str, Any],
    metric: UserMetric,
    discovery_prefix: str = "homeassistant",
) -> str:
    unique_id = f"smart_house_scale_{_user_id(user)}_{metric.slug}"
    return f"{discovery_prefix.rstrip('/')}/sensor/{unique_id}/config"


def _value_template(metric: UserMetric) -> str:
    return (
        "{{ value_json."
        f"{metric.key}"
        " if value_json."
        f"{metric.key}"
        " is not none else 'unknown' }}"
    )


def build_user_state(user: Mapping[str, Any]) -> dict[str, Any]:
    """Return the retained JSON state shared by all sensors of one resident."""

    state: dict[str, Any] = {
        "user_id": _user_id(user),
        "name": str(user.get("name") or "Usuário"),
        "bmi_classification": user.get("bmi_classification"),
        "last_measured_at": user.get("last_measured_at"),
        "metric_origins": user.get("metric_origins") or {},
    }
    for metric in USER_METRICS:
        state[metric.key] = user.get(metric.key)
    return state


def build_user_discovery(
    user: Mapping[str, Any],
    metric: UserMetric,
    discovery_prefix: str = "homeassistant",
) -> dict[str, Any]:
    """Build a Home Assistant MQTT sensor discovery document."""

    user_id = _user_id(user)
    name = str(user.get("name") or "Usuário")
    user_slug = slugify(name)
    unique_id = f"smart_house_scale_{user_id}_{metric.slug}"
    state_topic = user_state_topic(user)
    payload: dict[str, Any] = {
        "name": f"{name} {metric.name}",
        "unique_id": unique_id,
        "object_id": f"{user_slug}_{metric.slug}",
        "state_topic": state_topic,
        "value_template": _value_template(metric),
        "json_attributes_topic": state_topic,
        "availability_topic": STATUS_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
        "icon": metric.icon,
        "device": {
            "identifiers": [f"smart_house_scale_user_{user_id}"],
            "name": f"{name} · Tecnohead Scale",
            "manufacturer": "Tecnohead",
            "model": "Tecnohead Scale",
        },
    }
    if metric.unit is not None:
        payload["unit_of_measurement"] = metric.unit
    if metric.device_class is not None:
        payload["device_class"] = metric.device_class
    if metric.state_class is not None:
        payload["state_class"] = metric.state_class
    if metric.precision is not None:
        payload["suggested_display_precision"] = metric.precision
    return payload


def build_user_bundle(
    user: Mapping[str, Any],
    discovery_prefix: str = "homeassistant",
) -> dict[str, dict[str, Any]]:
    """Return all retained discovery/state payloads for one active resident."""

    payloads = {
        discovery_topic(user, metric, discovery_prefix): build_user_discovery(
            user, metric, discovery_prefix
        )
        for metric in USER_METRICS
    }
    payloads[user_state_topic(user)] = build_user_state(user)
    return payloads
