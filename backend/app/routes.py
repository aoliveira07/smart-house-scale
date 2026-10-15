"""Versioned Smart House Scale API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .schemas import DeviceCreate, DevicePatch, MeasurementAction, MeasurementCreate, UserCreate, UserPatch
from .security import require_optional_token
from .service import ScaleService

router = APIRouter(prefix="/api/v1", tags=["Smart House Scale"], dependencies=[Depends(require_optional_token)])


def repository_from(request: Request) -> Any:
    return request.app.state.scale_repository


def service_from(request: Request) -> ScaleService:
    return ScaleService(repository_from(request))


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


@router.get("/scales")
async def list_scales(request: Request):
    return await repository_from(request).list_devices()


@router.post("/scales", status_code=201)
async def create_scale(payload: DeviceCreate, request: Request):
    return await repository_from(request).create_device(payload.model_dump())


@router.get("/scales/{device_id}")
async def get_scale(device_id: UUID, request: Request):
    result = await repository_from(request).get_device(device_id)
    if not result:
        raise HTTPException(404, "scale not found")
    return result


@router.patch("/scales/{device_id}")
async def patch_scale(device_id: UUID, payload: DevicePatch, request: Request):
    result = await repository_from(request).update_device(device_id, payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(404, "scale not found")
    return result


@router.get("/scale-users")
async def list_scale_users(request: Request, active: bool | None = None):
    users = await repository_from(request).list_users(active_only=active is True)
    service = service_from(request)
    enriched = []
    for user in users:
        try:
            enriched.append({**user, **(await service.summary(user["id"]))})
        except Exception:
            enriched.append(user)
    return enriched


@router.post("/scale-users", status_code=201)
async def create_scale_user(payload: UserCreate, request: Request):
    return await repository_from(request).create_user(payload.model_dump())


@router.get("/scale-users/{user_id}")
async def get_scale_user(user_id: UUID, request: Request):
    result = await repository_from(request).get_user(user_id)
    if not result:
        raise HTTPException(404, "scale user not found")
    return result


@router.patch("/scale-users/{user_id}")
async def patch_scale_user(user_id: UUID, payload: UserPatch, request: Request):
    result = await repository_from(request).update_user(user_id, payload.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(404, "scale user not found")
    return result


@router.post("/scale-measurements", status_code=201)
async def create_measurement(payload: MeasurementCreate, request: Request):
    if not payload.stable:
        raise HTTPException(422, "only stabilized measurements can be persisted")
    return await service_from(request).ingest(payload.model_dump())


@router.get("/scale-measurements")
async def list_measurements(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(assigned|pending|discarded)$"),
    user_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
):
    return await repository_from(request).list_measurements(status=status_filter, user_id=user_id, limit=limit)


@router.get("/scale-users/{user_id}/measurements")
async def user_measurements(user_id: UUID, request: Request, limit: int = Query(default=1000, ge=1, le=5000)):
    if not await repository_from(request).get_user(user_id):
        raise HTTPException(404, "scale user not found")
    return await repository_from(request).user_measurements(user_id, limit=limit)


@router.get("/scale-users/{user_id}/summary")
async def user_summary(user_id: UUID, request: Request):
    try:
        return await service_from(request).summary(user_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.get("/scale-measurements/pending")
async def pending_measurements(request: Request, limit: int = Query(default=200, ge=1, le=2000)):
    return await repository_from(request).list_measurements(status="pending", limit=limit)


@router.post("/scale-measurements/{measurement_id}/assign")
async def assign_measurement(measurement_id: UUID, payload: MeasurementAction, request: Request):
    try:
        return await service_from(request).assign(measurement_id, payload.user_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.post("/scale-measurements/{measurement_id}/discard")
async def discard_measurement(measurement_id: UUID, request: Request):
    try:
        return await service_from(request).discard(measurement_id)
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.post("/scale-measurements/{measurement_id}/reassign")
async def reassign_measurement(measurement_id: UUID, payload: MeasurementAction, request: Request):
    try:
        return await service_from(request).assign(measurement_id, payload.user_id, method="corrected")
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.get("/scale/health")
async def scale_health(request: Request):
    health = await repository_from(request).health()
    return {"ok": True, "database": health.get("database"), "last_measurement": health.get("last_measurement"), "last_communication_ha": health.get("last_communication_ha"), "queues": {"backend": 0, "ha_queue": None}, "errors": []}
