"""Persistent configuration for the Smart House Scale App."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


DEFAULT_WEIGHT_ENTITY = "sensor.casal_balanca_peso"
_ENTITY_ID = re.compile(r"^sensor\.[a-z0-9_]+$")


class InvalidEntityId(ValueError):
    """Raised when an App setting is not a Home Assistant sensor entity."""


def validate_weight_entity_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _ENTITY_ID.fullmatch(normalized):
        raise InvalidEntityId("Informe uma entidade de sensor, por exemplo sensor.balanca_peso.")
    return normalized


class AppSettings:
    """Store App settings in the persistent Home Assistant App data volume."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "settings.json"
        self._data: dict[str, Any] = {
            "weight_entity_id": os.getenv("SMART_HOUSE_SCALE_WEIGHT_ENTITY") or DEFAULT_WEIGHT_ENTITY,
        }
        self._load()

    @property
    def weight_entity_id(self) -> str:
        return validate_weight_entity_id(self._data["weight_entity_id"])

    def _load(self) -> None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                self._data.update(value)
                self._data["weight_entity_id"] = validate_weight_entity_id(self._data["weight_entity_id"])
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # A malformed local settings file must not prevent the App from
            # starting. The configured add-on option remains the fallback.
            self._data["weight_entity_id"] = validate_weight_entity_id(
                os.getenv("SMART_HOUSE_SCALE_WEIGHT_ENTITY") or DEFAULT_WEIGHT_ENTITY
            )

    def set_weight_entity(self, entity_id: str) -> str:
        normalized = validate_weight_entity_id(entity_id)
        self._data["weight_entity_id"] = normalized
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return normalized

    def public(self) -> dict[str, str]:
        return {
            "weight_entity_id": self.weight_entity_id,
            "source": "home_assistant_state_entity",
        }
