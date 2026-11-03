"""Skill tools: list_skills / read_skill / read_skill_resource.

Skills are workflow documents. Loading one never grants permissions or runs scripts.
"""

from typing import Any

from ..context.discovery import Discovery, SkillContent, SkillInfo


class SkillTools:
    def __init__(self, discovery: Discovery) -> None:
        self.discovery = discovery

    def list_skills(self) -> list[SkillInfo]:
        return self.discovery.skills()

    def read_skill(self, skill_id: str) -> SkillContent:
        return self.discovery.skill(skill_id)

    def read_skill_resource(self, skill_id: str, path: str) -> dict[str, Any]:
        return self.discovery.resource(skill_id, path)
