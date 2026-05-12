from __future__ import annotations

from product_agent.registries import SkillRegistry


class SkillService:
    """对外暴露 skill 列表与后续启用逻辑。"""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def list_skills(self):
        return self.registry.list_skills()

