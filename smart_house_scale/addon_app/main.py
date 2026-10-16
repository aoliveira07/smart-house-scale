"""Smart House Scale Home Assistant App.

The App is the local bridge and UI. Bluetooth discovery and Xiaomi decryption
remain entirely in Home Assistant's native integration; this process only
subscribes to the configured numeric weight entity.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .home_assistant import HomeAssistantEntityBridge, HomeAssistantUnavailable
from .ingestion import ScaleApiClient
from .mqtt_entities import UserEntityPublisher
from .settings import AppSettings, InvalidEntityId


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
if not WEB_DIR.exists():
    WEB_DIR = BASE_DIR / "backend" / "web"
CENTRAL_API_URL = os.getenv("SMART_HOUSE_SCALE_API_URL", "http://192.168.0.201").rstrip("/")
if CENTRAL_API_URL.endswith("/api"):
    CENTRAL_API_URL = CENTRAL_API_URL[:-4]
API_TOKEN = os.getenv("SMART_HOUSE_SCALE_API_TOKEN", "")
APP_VERSION = os.getenv("APP_VERSION", "0.7.4")
_MAX_AVATAR_BYTES = 5 * 1024 * 1024
_AVATAR_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _data_directory() -> Path:
    configured = Path(os.getenv("APP_DATA_DIR", "/data"))
    try:
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    except OSError:
        fallback = BASE_DIR / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


DATA_DIR = _data_directory()
AVATAR_DIR = DATA_DIR / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS = AppSettings(DATA_DIR)
CENTRAL_API = ScaleApiClient(CENTRAL_API_URL, API_TOKEN)
try:
    _MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
except ValueError:
    _MQTT_PORT = 1883
USER_ENTITIES = UserEntityPublisher(
    CENTRAL_API,
    data_dir=DATA_DIR,
    discovery_prefix=os.getenv("SMART_HOUSE_SCALE_MQTT_DISCOVERY_PREFIX", "homeassistant"),
    mqtt_host=os.getenv("MQTT_HOST"),
    mqtt_port=_MQTT_PORT,
    mqtt_username=os.getenv("MQTT_USER"),
    mqtt_password=os.getenv("MQTT_PASSWORD"),
    poll_interval_seconds=int(os.getenv("SMART_HOUSE_SCALE_MQTT_POLL_SECONDS", "30")),
)
HOME_ASSISTANT = HomeAssistantEntityBridge(
    CENTRAL_API,
    data_dir=DATA_DIR,
    entity_id=SETTINGS.weight_entity_id,
    supervisor_token=os.getenv("SUPERVISOR_TOKEN", ""),
    session_window_seconds=int(os.getenv("SMART_HOUSE_SCALE_SESSION_WINDOW", "30")),
    on_data_changed=USER_ENTITIES.request_sync,
)


class WeightEntitySelection(BaseModel):
    entity_id: str


app = FastAPI(title="Tecnohead Scale App", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="smart-house-scale-static")
app.mount("/avatars", StaticFiles(directory=AVATAR_DIR), name="smart-house-scale-avatars")


@app.on_event("startup")
async def start_home_assistant_bridge() -> None:
    """Start the Supervisor WebSocket listener and the durable queue flusher."""

    await HOME_ASSISTANT.start()
    await USER_ENTITIES.start()


@app.on_event("shutdown")
async def stop_home_assistant_bridge() -> None:
    await USER_ENTITIES.stop()
    await HOME_ASSISTANT.stop()


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


@app.get("/configuration")
async def configuration() -> dict[str, object]:
    return {
        "configuration": SETTINGS.public(),
        "home_assistant": HOME_ASSISTANT.diagnostics(),
        "user_entities": USER_ENTITIES.diagnostics(),
    }


@app.put("/configuration/weight-entity")
async def update_weight_entity(selection: WeightEntitySelection) -> dict[str, object]:
    try:
        entity_id = SETTINGS.set_weight_entity(selection.entity_id)
        await HOME_ASSISTANT.set_entity_id(entity_id)
    except InvalidEntityId as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "configuration": SETTINGS.public(),
        "home_assistant": HOME_ASSISTANT.diagnostics(),
        "user_entities": USER_ENTITIES.diagnostics(),
    }


@app.get("/home-assistant/weight-sensors")
async def weight_sensors() -> dict[str, object]:
    try:
        sensors = await HOME_ASSISTANT.list_weight_sensors()
    except (HomeAssistantUnavailable, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail="Não foi possível consultar os sensores do Home Assistant.") from exc
    return {"items": sensors, "selected_entity_id": SETTINGS.weight_entity_id}


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "app": "smart_house_scale",
        "version": APP_VERSION,
        "api_url": CENTRAL_API_URL,
        "configuration": SETTINGS.public(),
        "home_assistant": HOME_ASSISTANT.diagnostics(),
        "user_entities": USER_ENTITIES.diagnostics(),
    }


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def central_api_proxy(path: str, request: Request) -> Response:
    """Forward only the Smart House API; the browser never receives its token."""

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
    if (
        upstream.status_code < 400
        and request.method in {"POST", "PATCH", "PUT", "DELETE"}
        and (path.startswith("v1/scale-users") or path.startswith("v1/scale-measurements"))
    ):
        USER_ENTITIES.request_sync()
    response_headers = {}
    if upstream.headers.get("content-type"):
        response_headers["content-type"] = upstream.headers["content-type"]
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
