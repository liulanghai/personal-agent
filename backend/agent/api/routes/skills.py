"""Capability catalog: discovered rules and skills, skill content, tool definitions."""

from typing import Any

from fastapi import APIRouter

from ...context.discovery import SkillContent
from ...tools.registry import DEFINITIONS
from .. import schemas as api
from ..deps import Services
from ..errors import not_found


def build(services: Services) -> APIRouter:
    router = APIRouter()
    tools = services.tools

    @router.get("/discovery", response_model=api.DiscoveryResult)
    async def discovery() -> dict[str, Any]:
        skills = tools.skills()
        mode = services.settings.load()["instruction_mode"]
        rules, warnings = tools.discovery.instructions(mode)
        return {
            "workspace_path": str(tools.workspace),
            "instructions": [{k: r[k] for k in ("scope", "path", "sha256")} for r in rules],
            "skills": skills,
            "warnings": warnings + tools.discovery.warnings,
        }

    @router.get("/skills", response_model=api.Skills)
    async def skills() -> dict[str, Any]:
        return {"items": tools.skills()}

    @router.get("/skills/{skill_id}", response_model=api.SkillContent)
    async def skill(skill_id: str) -> SkillContent:
        try:
            return tools.skill(skill_id)
        except ValueError:
            raise not_found("Unknown skill") from None

    @router.get("/tools", response_model=api.ToolList)
    async def tool_definitions() -> dict[str, Any]:
        return {"items": DEFINITIONS}

    return router
