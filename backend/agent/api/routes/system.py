"""Health check."""

from typing import Any

from fastapi import APIRouter

from .. import schemas as api

VERSION = "0.1.0"


def build() -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=api.Health)
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": VERSION}

    return router
