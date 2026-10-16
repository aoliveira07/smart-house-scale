"""Ingress UI and authenticated proxy for the central Smart House API."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .integration_installer import IntegrationInstallResult, ensure_integration_from_environment


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
if not WEB_DIR.exists():
    WEB_DIR = BASE_DIR / "backend" / "web"
CENTRAL_API_URL = os.getenv("SMART_HOUSE_SCALE_API_URL", "http://192.168.0.201").rstrip("/")
if CENTRAL_API_URL.endswith("/api"):
    CENTRAL_API_URL = CENTRAL_API_URL[:-4]
API_TOKEN = os.getenv("SMART_HOUSE_SCALE_API_TOKEN", "")
_LOGGER = logging.getLogger(__name__)
_MAX_AVATAR_BYTES = 5 * 1024 * 1024
_AVATAR_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _avatar_directory() -> Path:
    configured = Path(os.getenv("APP_DATA_DIR", "/data")) / "avatars"
    try:
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    except OSError:
        # Local development can run outside the App container where /data is
        # not writable.  The add-on always uses the persistent /data path.
        fallback = BASE_DIR / "data" / "avatars"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


AVATAR_DIR = _avatar_directory()
_integration_status: dict[str, object] = {
    "status": "not_started",
    "version": None,
    "target": None,
    "restart_required": False,
    "message": "A instalação automática ainda não foi executada.",
}
_restart_task: asyncio.Task[None] | None = None

app = FastAPI(title="Smart House Scale App", version=os.getenv("APP_VERSION", "0.4.3"))
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="smart-house-scale-static")
app.mount("/avatars", StaticFiles(directory=AVATAR_DIR), name="smart-house-scale-avatars")


@app.on_event("startup")
async def bootstrap_home_assistant_integration() -> None:
    """Install the native HA integration when the App is first started."""

    global _integration_status, _restart_task
    result: IntegrationInstallResult = await asyncio.to_thread(ensure_integration_from_environment)
    _integration_status = result.as_dict()
    if result.restart_required:
        _restart_task = asyncio.create_task(_restart_home_assistant_core())


async def _restart_home_assistant_core() -> None:
    """Ask the Supervisor's Core API to reload custom_components once."""

    token = os.getenv("SUPERVISOR_TOKEN", "")
    if not token:
        _LOGGER.warning("Integration installed; SUPERVISOR_TOKEN unavailable for automatic Core restart")
        _integration_status.update(
            {
                "restart_required": True,
                "restart_status": "manual_required",
            }
        )
        return

    # Let the App finish its startup and watchdog health check before asking
    # Core to restart.  The marker written by the installer makes this a
    # one-time action on the first start or after an App-managed update.
    await asyncio.sleep(5)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "http://supervisor/core/api/services/homeassistant/restart",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
            response.raise_for_status()
    except Exception as exc:  # the integration remains installed if restart fails
        _LOGGER.warning("Integration installed but automatic Core restart failed: %s", type(exc).__name__)
        _integration_status.update(
            {
                "restart_required": True,
                "restart_status": "restart_failed",
            }
        )
        return

    _integration_status.update(
        {
            "restart_required": False,
            "restart_status": "requested",
        }
    )


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.post("/avatar-upload/{user_id}", include_in_schema=False)
async def upload_avatar(user_id: UUID, file: UploadFile = File(...)) -> dict[str, str]:
    """Persist a private per-installation avatar under the App data volume."""

    extension = _AVATAR_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="Use PNG, JPEG ou WebP para o avatar.")

    payload = await file.read(_MAX_AVATAR_BYTES + 1)
    if len(payload) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="O avatar deve ter no máximo 5 MB.")
    if not payload:
        raise HTTPException(status_code=400, detail="O arquivo do avatar está vazio.")

    target = AVATAR_DIR / f"{user_id}{extension}"
    temporary = AVATAR_DIR / f".{user_id}.upload"
    temporary.write_bytes(payload)
    temporary.replace(target)

    return {"url": f"/avatars/{user_id}{extension}", "content_type": file.content_type or ""}


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "app": "smart_house_scale",
        "api_url": CENTRAL_API_URL,
        "home_assistant_integration": _integration_status,
    }


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def central_api_proxy(path: str, request: Request) -> Response:
    """Forward only the Smart House API through the add-on.

    The browser never receives the API token.  It stays in the add-on option
    storage and is attached only to requests sent to the central LAN API.
    """

    target = f"{CENTRAL_API_URL}/api/{path}"
    headers = {"Accept": "application/json"}
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    body = await request.body()

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        upstream = await client.request(request.method, target, content=body or None, headers=headers)

    response_headers = {}
    if upstream.headers.get("content-type"):
        response_headers["content-type"] = upstream.headers["content-type"]
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
