"""PostgreSQL repository.

The module uses asyncpg directly so it can be mounted into the existing Smart
House FastAPI service without imposing an ORM or a parallel database.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


class PostgresRepository:
    def __init__(self, pool: Any):
        self.pool = pool

    @classmethod
    async def from_env(cls) -> "PostgresRepository":
        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError("Install backend/requirements.txt before starting the central API") from exc
        dsn = os.environ.get("SMART_HOUSE_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("SMART_HOUSE_DATABASE_URL or DATABASE_URL is required")
        return cls(await asyncpg.create_pool(dsn, min_size=1, max_size=5))

    async def close(self) -> None:
        await self.pool.close()

    @staticmethod
    def _dict(row: Any) -> dict[str, Any] | None:
        return dict(row) if row else None

    async def list_devices(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await conn.fetch("SELECT * FROM health.scale_devices ORDER BY name")]

    async def get_device(self, device_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            return self._dict(await conn.fetchrow("SELECT * FROM health.scale_devices WHERE id=$1", device_id))

    async def upsert_device(self, values: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO health.scale_devices(id, name, mac_address, model, protocol, unit, active, last_seen_at, last_rssi)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                   ON CONFLICT(mac_address) DO UPDATE SET
                     model=COALESCE(EXCLUDED.model, health.scale_devices.model),
                     protocol=COALESCE(EXCLUDED.protocol, health.scale_devices.protocol),
                     unit=COALESCE(EXCLUDED.unit, health.scale_devices.unit),
                     last_seen_at=COALESCE(EXCLUDED.last_seen_at, health.scale_devices.last_seen_at),
                     last_rssi=COALESCE(EXCLUDED.last_rssi, health.scale_devices.last_rssi),
                     updated_at=now()
                   RETURNING *""",
                values.get("id", uuid4()), values["name"], values["mac_address"], values.get("model"), values.get("protocol"), values.get("unit", "kg"),
                values.get("active", True), values.get("last_seen_at"), values.get("last_rssi"),
            )
            return dict(row)

    async def create_device(self, values: dict[str, Any]) -> dict[str, Any]:
        return await self.upsert_device(values)

    async def update_device(self, device_id: UUID, values: dict[str, Any]) -> dict[str, Any] | None:
        return await self._update("scale_devices", device_id, values)

    async def list_users(self, active_only: bool = False) -> list[dict[str, Any]]:
        where = " WHERE active=true" if active_only else ""
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await conn.fetch(f"SELECT * FROM health.scale_users{where} ORDER BY name")]

    async def get_user(self, user_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            return self._dict(await conn.fetchrow("SELECT * FROM health.scale_users WHERE id=$1", user_id))

    async def create_user(self, values: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO health.scale_users(id, name, avatar, birth_date, height_cm, biological_sex,
                   initial_reference_weight_kg, target_weight_kg, auto_assign_tolerance_kg, active)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
                values.get("id", uuid4()), values["name"], values.get("avatar"), values.get("birth_date"), values.get("height_cm"), values.get("biological_sex"),
                values["initial_reference_weight_kg"], values.get("target_weight_kg"), values.get("auto_assign_tolerance_kg", 3.0), values.get("active", True),
            )
            return dict(row)

    async def update_user(self, user_id: UUID, values: dict[str, Any]) -> dict[str, Any] | None:
        return await self._update("scale_users", user_id, values)

    async def _update(self, table: str, row_id: UUID, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "scale_devices": {"name", "model", "protocol", "unit", "active"},
            "scale_users": {"name", "avatar", "birth_date", "height_cm", "biological_sex", "initial_reference_weight_kg", "target_weight_kg", "auto_assign_tolerance_kg", "active"},
        }[table]
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return await (self.get_device(row_id) if table == "scale_devices" else self.get_user(row_id))
        clauses = ", ".join(f"{key}=${index}" for index, key in enumerate(updates, 1))
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f"UPDATE health.{table} SET {clauses}, updated_at=now() WHERE id=${len(updates)+1} RETURNING *", *updates.values(), row_id)
            return self._dict(row)

    async def get_measurement_by_uuid(self, measurement_uuid: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            return self._dict(await conn.fetchrow("SELECT * FROM health.scale_measurements WHERE measurement_uuid=$1", measurement_uuid))

    async def recent_weights(self, user_id: UUID, limit: int = 5) -> list[float]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT weight_kg FROM health.scale_measurements WHERE user_id=$1 AND status='assigned' ORDER BY measured_at DESC LIMIT $2", user_id, limit)
            return [float(row["weight_kg"]) for row in rows]

    async def upsert_session(self, values: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO health.scale_measurement_sessions(
                   id, session_uuid, device_id, started_at, last_seen_at, finalized_at,
                   advertisement_count, stable, final_measurement_uuid, raw_payload)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
                   ON CONFLICT(session_uuid) DO UPDATE SET
                     last_seen_at=EXCLUDED.last_seen_at,
                     finalized_at=EXCLUDED.finalized_at,
                     advertisement_count=EXCLUDED.advertisement_count,
                     stable=EXCLUDED.stable,
                     final_measurement_uuid=EXCLUDED.final_measurement_uuid,
                     raw_payload=EXCLUDED.raw_payload""",
                uuid4(), values["session_uuid"], values["device_id"], values["started_at"], values["last_seen_at"], values.get("finalized_at"),
                values.get("advertisement_count", 1), values.get("stable", False), values.get("final_measurement_uuid"), json.dumps(values.get("raw_payload") or {}),
            )

    async def insert_measurement(self, values: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                insert_result = await conn.execute(
                    """INSERT INTO health.scale_measurements(
                       id, measurement_uuid, device_id, user_id, measured_at, received_at, weight_kg,
                       original_unit, impedance, rssi, raw_payload, stable, status, pending_reason,
                       assignment_method, assignment_delta_kg, confidence, assigned_at, assignment_candidates,
                       session_uuid, protocol, model)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13,$14,$15,$16,$17,$18,$19,$20::jsonb,$21,$22,$23)
                       ON CONFLICT(measurement_uuid) DO NOTHING""",
                    values.get("id", uuid4()), values["measurement_uuid"], values["device_id"], values.get("user_id"), values["measured_at"], values["received_at"], values["weight_kg"],
                    values["original_unit"], values.get("impedance"), values.get("rssi"), json.dumps(values.get("raw_payload") or {}), values["stable"], values["status"],
                    values.get("pending_reason"), values.get("assignment_method"), values.get("assignment_delta_kg"), values.get("confidence"), values.get("assigned_at"),
                    json.dumps(values.get("assignment_candidates") or []), values.get("session_uuid"), values.get("protocol"), values.get("model"),
                )
                row = await conn.fetchrow("SELECT * FROM health.scale_measurements WHERE measurement_uuid=$1", values["measurement_uuid"])
                if insert_result.endswith("1"):
                    await conn.execute(
                        """INSERT INTO health.scale_measurement_events(measurement_id, action, to_status, to_user_id, metadata)
                           VALUES($1,'created',$2,$3,$4::jsonb)""",
                        row["id"], values["status"], values.get("user_id"), json.dumps({"assignment_method": values.get("assignment_method")}),
                    )
            return dict(row)

    async def list_measurements(self, *, status: str | None = None, user_id: UUID | None = None, limit: int = 200) -> list[dict[str, Any]]:
        clauses, params = [], []
        if status:
            params.append(status); clauses.append(f"status=${len(params)}")
        if user_id:
            params.append(user_id); clauses.append(f"user_id=${len(params)}")
        params.append(limit)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await conn.fetch(f"SELECT * FROM health.scale_measurements{where} ORDER BY measured_at DESC LIMIT ${len(params)}", *params)]

    async def get_measurement(self, measurement_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            return self._dict(await conn.fetchrow("SELECT * FROM health.scale_measurements WHERE id=$1", measurement_id))

    async def update_measurement_assignment(self, measurement_id: UUID, *, status: str, user_id: UUID | None, method: str | None) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE health.scale_measurements SET status=$1, user_id=$2, assignment_method=$3,
                   assigned_at=CASE WHEN $1='assigned' THEN now() ELSE NULL END,
                   discarded_at=CASE WHEN $1='discarded' THEN now() ELSE NULL END, updated_at=now()
                   WHERE id=$4 RETURNING *""", status, user_id, method, measurement_id
            )
            if row:
                await conn.execute(
                    """INSERT INTO health.scale_measurement_events(measurement_id, action, to_status, to_user_id, metadata)
                       VALUES($1,$2,$3,$4,$5::jsonb)""",
                    measurement_id, "assignment" if status == "assigned" else status, status, user_id, json.dumps({"assignment_method": method}),
                )
            return self._dict(row)

    async def user_measurements(self, user_id: UUID, *, limit: int = 1000) -> list[dict[str, Any]]:
        return await self.list_measurements(user_id=user_id, status="assigned", limit=limit)

    async def health(self) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            db = await conn.fetchval("SELECT current_database()")
            last = await conn.fetchrow("SELECT measured_at, received_at FROM health.scale_measurements ORDER BY received_at DESC LIMIT 1")
            ha = await conn.fetchrow("SELECT last_seen_at FROM health.scale_devices ORDER BY last_seen_at DESC NULLS LAST LIMIT 1")
            return {"database": db, "last_measurement": dict(last) if last else None, "last_communication_ha": dict(ha) if ha else None}
