from __future__ import annotations

from product_agent.registries import ToolRegistry


class ToolService:
    """对外暴露工具列表和启用/禁用逻辑。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def list_tools(self):
        return self.registry.list_tools()

    def update_tool_enabled(self, tool_id: str, enabled: bool):
        return self.registry.update_enabled(tool_id, enabled)

