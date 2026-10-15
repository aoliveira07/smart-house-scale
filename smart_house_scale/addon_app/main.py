"""Ingress UI and authenticated proxy for the central Smart House API."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
if not WEB_DIR.exists():
    WEB_DIR = BASE_DIR / "backend" / "web"
CENTRAL_API_URL = os.getenv("SMART_HOUSE_SCALE_API_URL", "http://192.168.0.201").rstrip("/")
if CENTRAL_API_URL.endswith("/api"):
    CENTRAL_API_URL = CENTRAL_API_URL[:-4]
API_TOKEN = os.getenv("SMART_HOUSE_SCALE_API_TOKEN", "")

app = FastAPI(title="Smart House Scale App", version=os.getenv("APP_VERSION", "0.2.2"))
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="smart-house-scale-static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str | bool]:
    return {"ok": True, "app": "smart_house_scale", "api_url": CENTRAL_API_URL}


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
