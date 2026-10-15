"""FastAPI request/response contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _mac(value: str) -> str:
    compact = "".join(ch for ch in value.upper() if ch.isalnum())
    if len(compact) != 12 or any(ch not in "0123456789ABCDEF" for ch in compact):
        raise ValueError("mac_address must contain 12 hexadecimal characters")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mac_address: str
    model: str | None = Field(default=None, max_length=120)
    protocol: str | None = Field(default=None, max_length=80)
    unit: str = Field(default="kg", max_length=10)
    active: bool = True

    _validate_mac = field_validator("mac_address")(_mac)


class DevicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    protocol: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, max_length=10)
    active: bool | None = None


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    avatar: str | None = Field(default=None, max_length=500)
    birth_date: date | None = None
    height_cm: float | None = Field(default=None, gt=0, le=300)
    biological_sex: Literal["male", "female", "other"] | None = None
    initial_reference_weight_kg: float = Field(gt=1, le=400)
    target_weight_kg: float | None = Field(default=None, gt=1, le=400)
    auto_assign_tolerance_kg: float = Field(default=3.0, gt=0, le=20)
    active: bool = True


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    avatar: str | None = Field(default=None, max_length=500)
    birth_date: date | None = None
    height_cm: float | None = Field(default=None, gt=0, le=300)
    biological_sex: Literal["male", "female", "other"] | None = None
    initial_reference_weight_kg: float | None = Field(default=None, gt=1, le=400)
    target_weight_kg: float | None = Field(default=None, gt=1, le=400)
    auto_assign_tolerance_kg: float | None = Field(default=None, gt=0, le=20)
    active: bool | None = None


class MeasurementCreate(BaseModel):
    measurement_uuid: UUID
    mac_address: str
    measured_at: datetime
    received_at: datetime
    weight_kg: float = Field(gt=1, le=400)
    original_unit: Literal["kg", "lbs", "jin"] = "kg"
    impedance: int | None = Field(default=None, ge=0)
    rssi: int | None = Field(default=None, ge=-150, le=0)
    protocol: str | None = None
    model: str | None = None
    raw_payload: dict[str, Any] | None = None
    stable: bool = True
    session_uuid: UUID | None = None

    _validate_mac = field_validator("mac_address")(_mac)


class MeasurementAction(BaseModel):
    user_id: UUID


class MeasurementQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
