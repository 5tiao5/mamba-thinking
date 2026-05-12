from __future__ import annotations

from product_agent.domain import ToolDescriptor


class ToolRegistry:
    """统一管理可被产品层启用的工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptor] = {}

    def register(self, descriptor: ToolDescriptor) -> None:
        self._tools[descriptor.tool_id] = descriptor

    def list_tools(self) -> list[ToolDescriptor]:
        return list(self._tools.values())

    def get(self, tool_id: str) -> ToolDescriptor | None:
        return self._tools.get(tool_id)

    def update_enabled(self, tool_id: str, enabled: bool) -> ToolDescriptor | None:
        descriptor = self._tools.get(tool_id)
        if descriptor is None:
            return None
        descriptor.enabled = enabled
        return descriptor

