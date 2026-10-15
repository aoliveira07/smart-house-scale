"""Smart House Scale endpoints for the central FastAPI application."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_scope
from app.db.database import get_db
from app.schemas.scale import (
    ScaleCreate,
    ScaleMeasurementAction,
    ScaleMeasurementCreate,
    ScalePatch,
    ScaleUserCreate,
    ScaleUserPatch,
)
from app.services.scale import ScaleRepository, ScaleService


router = APIRouter(prefix="/api/v1", tags=["scale"])
read_scope = Depends(require_scope("scale:read"))
write_scope = Depends(require_scope("scale:write"))


def repository(db: Session) -> ScaleRepository:
    return ScaleRepository(db)


def service(db: Session) -> ScaleService:
    return ScaleService(repository(db))


def not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


@router.get("/scales", dependencies=[read_scope])
def list_scales(db: Session = Depends(get_db)) -> list[dict]:
    return repository(db).list_devices()


@router.post("/scales", status_code=201, dependencies=[write_scope])
def create_scale(payload: ScaleCreate, db: Session = Depends(get_db)) -> dict:
    return repository(db).create_device(payload.model_dump())


@router.get("/scales/{device_id}", dependencies=[read_scope])
def get_scale(device_id: UUID, db: Session = Depends(get_db)) -> dict:
    result = repository(db).get_device(device_id)
    if result is None:
        raise HTTPException(status_code=404, detail="scale not found")
    return result


@router.patch("/scales/{device_id}", dependencies=[write_scope])
def patch_scale(
    device_id: UUID,
    payload: ScalePatch,
    db: Session = Depends(get_db),
) -> dict:
    result = repository(db).update_device(device_id, payload.model_dump(exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="scale not found")
    return result


@router.get("/scale-users", dependencies=[read_scope])
def list_scale_users(
    active: bool | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    repo = repository(db)
    scale_service = ScaleService(repo)
    result: list[dict] = []
    for user in repo.list_users(active_only=active is True):
        try:
            result.append({**user, **scale_service.summary(user["id"])})
        except Exception:
            result.append(user)
    return result


@router.post("/scale-users", status_code=201, dependencies=[write_scope])
def create_scale_user(payload: ScaleUserCreate, db: Session = Depends(get_db)) -> dict:
    return repository(db).create_user(payload.model_dump())


@router.get("/scale-users/{user_id}", dependencies=[read_scope])
def get_scale_user(user_id: UUID, db: Session = Depends(get_db)) -> dict:
    result = repository(db).get_user(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="scale user not found")
    return result


@router.patch("/scale-users/{user_id}", dependencies=[write_scope])
def patch_scale_user(
    user_id: UUID,
    payload: ScaleUserPatch,
    db: Session = Depends(get_db),
) -> dict:
    result = repository(db).update_user(user_id, payload.model_dump(exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="scale user not found")
    return result


@router.post("/scale-measurements", status_code=201, dependencies=[write_scope])
def create_measurement(
    payload: ScaleMeasurementCreate,
    db: Session = Depends(get_db),
) -> dict:
    if not payload.stable:
        raise HTTPException(status_code=422, detail="only stabilized measurements can be persisted")
    return service(db).ingest(payload.model_dump())


@router.get("/scale-measurements", dependencies=[read_scope])
def list_measurements(
    status: str | None = Query(default=None, pattern="^(assigned|pending|discarded)$"),
    user_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[dict]:
    return repository(db).list_measurements(status=status, user_id=user_id, limit=limit)


@router.get("/scale-users/{user_id}/measurements", dependencies=[read_scope])
def user_measurements(
    user_id: UUID,
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[dict]:
    repo = repository(db)
    if not repo.get_user(user_id):
        raise HTTPException(status_code=404, detail="scale user not found")
    return repo.user_measurements(user_id, limit=limit)


@router.get("/scale-users/{user_id}/summary", dependencies=[read_scope])
def user_summary(user_id: UUID, db: Session = Depends(get_db)) -> dict:
    try:
        return service(db).summary(user_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@router.get("/scale-measurements/pending", dependencies=[read_scope])
def pending_measurements(
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[dict]:
    return repository(db).list_measurements(status="pending", limit=limit)


@router.post("/scale-measurements/{measurement_id}/assign", dependencies=[write_scope])
def assign_measurement(
    measurement_id: UUID,
    payload: ScaleMeasurementAction,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return service(db).assign(measurement_id, payload.user_id, method="manual")
    except KeyError as exc:
        raise not_found(exc) from exc


@router.post("/scale-measurements/{measurement_id}/discard", dependencies=[write_scope])
def discard_measurement(measurement_id: UUID, db: Session = Depends(get_db)) -> dict:
    try:
        return service(db).discard(measurement_id)
    except KeyError as exc:
        raise not_found(exc) from exc


@router.post("/scale-measurements/{measurement_id}/reassign", dependencies=[write_scope])
def reassign_measurement(
    measurement_id: UUID,
    payload: ScaleMeasurementAction,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return service(db).assign(measurement_id, payload.user_id, method="corrected")
    except KeyError as exc:
        raise not_found(exc) from exc


@router.get("/scale/health", dependencies=[read_scope])
def scale_health(db: Session = Depends(get_db)) -> dict:
    health = repository(db).health()
    return {
        "ok": True,
        "database": health["database"],
        "last_measurement": health["last_measurement"],
        "last_communication_ha": health["last_communication_ha"],
        "queues": {"backend": 0, "ha_queue": None},
        "errors": [],
    }
