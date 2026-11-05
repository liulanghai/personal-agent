"""Model settings. The API key is write-only: responses expose ``has_api_key`` only."""

from typing import Any

from fastapi import APIRouter, HTTPException

from ...config import Settings, SettingsError
from .. import schemas as api
from ..deps import Services


def public_settings(config: Settings, workspace: str) -> dict[str, Any]:
    return {
        "base_url": config["base_url"],
        "model": config["model"],
        "timezone": config["timezone"],
        "instruction_mode": config["instruction_mode"],
        "has_api_key": bool(config.get("api_key")),
        "workspace_path": workspace,
        "record_model_calls": config.get("record_model_calls", False),
    }


def build(services: Services) -> APIRouter:
    router = APIRouter()
    workspace = str(services.tools.workspace)

    @router.get("/settings", response_model=api.Settings)
    async def get_settings() -> dict[str, Any]:
        return public_settings(services.settings.load(), workspace)

    @router.put("/settings", response_model=api.Settings)
    async def put_settings(body: api.SettingsInput) -> dict[str, Any]:
        try:
            saved = services.settings.update(
                {
                    "base_url": body.base_url,
                    "model": body.model,
                    "api_key": body.api_key,
                    "timezone": body.timezone,
                    "instruction_mode": body.instruction_mode,
                    "record_model_calls": body.record_model_calls,
                }
            )
        except SettingsError as exc:
            raise HTTPException(422, str(exc)) from None
        return public_settings(saved, workspace)

    return router
