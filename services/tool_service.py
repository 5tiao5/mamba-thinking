from __future__ import annotations

from product_agent.registries import ToolRegistry


class ToolService:
    """
    对外暴露工具列表和启用/停用逻辑。

    当前阶段:
    - 仅直接代理 `ToolRegistry`

    待实现:
    1. 增加工具配置持久化
    2. 增加工具可用性校验
       - 例如 API key、网络能力、配额状态
    3. 增加“任务级启用工具集”解析
       - 把前端传入的 enabled_tools 变成运行期 tool policy
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def list_tools(self):
        """
        返回当前已注册工具列表。

        后续实现提示:
        - 如果工具配置开始持久化，这里优先返回“持久化状态 + registry 默认值”合并后的结果。
        """
        return self.registry.list_tools()

    def update_tool_enabled(self, tool_id: str, enabled: bool):
        """
        更新某个工具的启用状态。

        当前限制:
        - 仅更新 registry 内存态

        后续实现提示:
        - 应补充 `update_tool_config`
        - 应在 repository 落地后同步写库
        """
        return self.registry.update_enabled(tool_id, enabled)
