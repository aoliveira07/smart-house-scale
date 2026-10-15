"""Standalone entry point and integration hook for the existing Smart House API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .repository import PostgresRepository
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = await PostgresRepository.from_env()
    app.state.scale_repository = repository
    try:
        yield
    finally:
        await repository.close()


def create_app(repository=None) -> FastAPI:
    app = FastAPI(title="Smart House Scale API", version="0.1.0", lifespan=None if repository else lifespan)
    if repository is not None:
        app.state.scale_repository = repository
    app.include_router(router)
    web_dir = os.path.join(os.path.dirname(__file__), "..", "web")
    app.mount("/static", StaticFiles(directory=web_dir + "/static"), name="smart-house-scale-static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(web_dir + "/index.html")

    @app.get("/health", include_in_schema=False)
    async def health(request: Request):
        return await request.app.state.scale_repository.health()

    return app


app = create_app()
