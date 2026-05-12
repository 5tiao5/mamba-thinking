from __future__ import annotations

from product_agent.domain import SkillDescriptor


class SkillRegistry:
    """统一管理可供 Agent 使用的 skill。"""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDescriptor] = {}

    def register(self, descriptor: SkillDescriptor) -> None:
        self._skills[descriptor.skill_id] = descriptor

    def list_skills(self) -> list[SkillDescriptor]:
        return list(self._skills.values())

    def get(self, skill_id: str) -> SkillDescriptor | None:
        return self._skills.get(skill_id)

