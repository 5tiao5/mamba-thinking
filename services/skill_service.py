from __future__ import annotations

from product_agent.registries import SkillRegistry


class SkillService:
    """
    对外暴露 skill 列表与后续启用逻辑。

    当前阶段:
    - 只读展示已注册 skill

    待实现:
    1. 增加 skill 启用/停用开关
    2. 增加 skill 与工具依赖校验
    3. 增加“任务级 skill 选择”能力
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def list_skills(self):
        """
        返回当前已注册 skill 列表。

        后续实现提示:
        - 当 skill 有配置态时，这里应返回可直接驱动设置页的视图模型。
        """
        return self.registry.list_skills()
