from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from product_agent.domain import SkillDescriptor
from product_agent.registries import SkillRegistry

if TYPE_CHECKING:
    from product_agent.repositories.sqlite_store import SQLiteSkillRepository
    from product_agent.registries import ToolRegistry


class SkillServiceError(ValueError):
    """Skill 操作相关的业务错误。"""


class SkillService:
    """
    对外暴露 skill 的完整 CRUD 与校验逻辑。

    职责：
    - 用户可添加、可启停、可删除 skill
    - required_tools 校验（工具是否存在、是否启用）
    - 同步 registry（内存）与 repository（持久化）
    """

    def __init__(
        self,
        registry: SkillRegistry,
        *,
        repository: SQLiteSkillRepository | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.repository = repository
        self.tool_registry = tool_registry

    # ── 查询 ──────────────────────────────────────────────

    def list_skills(self) -> list[SkillDescriptor]:
        """返回所有 skill（优先从持久层读取，回退到 registry）。"""
        if self.repository is not None:
            return self.repository.list_all()
        return self.registry.list_skills()

    def get_skill(self, skill_id: str) -> SkillDescriptor | None:
        """按 ID 获取单个 skill。"""
        if self.repository is not None:
            return self.repository.get(skill_id)
        return self.registry.get(skill_id)

    # ── 创建 ──────────────────────────────────────────────

    def create_skill(
        self,
        *,
        skill_id: str,
        display_name: str,
        description: str = "",
        required_tools: list[str] | None = None,
        enabled: bool = True,
        prompts: dict[str, str] | None = None,
    ) -> SkillDescriptor:
        """创建新 skill，校验 required_tools 并持久化。"""
        required_tools = list(required_tools or [])

        existing = self.get_skill(skill_id)
        if existing is not None:
            raise SkillServiceError(f"Skill `{skill_id}` already exists.")

        self._validate_required_tools(required_tools)

        now = datetime.now(timezone.utc)
        descriptor = SkillDescriptor(
            skill_id=skill_id,
            display_name=display_name,
            description=description,
            enabled=enabled,
            required_tools=required_tools,
            prompts=dict(prompts or {}),
            created_at=now,
            updated_at=now,
        )

        if self.repository is not None:
            self.repository.save(descriptor)
        self.registry.register(descriptor)
        return descriptor

    # ── 更新 ──────────────────────────────────────────────

    def update_skill(
        self,
        skill_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        required_tools: list[str] | None = None,
        enabled: bool | None = None,
        prompts: dict[str, str] | None = None,
    ) -> SkillDescriptor:
        """部分更新 skill 字段。"""
        existing = self.get_skill(skill_id)
        if existing is None:
            raise SkillServiceError(f"Skill `{skill_id}` does not exist.")

        if required_tools is not None:
            self._validate_required_tools(required_tools)
            existing.required_tools = list(required_tools)
        if display_name is not None:
            existing.display_name = display_name
        if description is not None:
            existing.description = description
        if enabled is not None:
            existing.enabled = enabled
        if prompts is not None:
            existing.prompts = dict(prompts)

        existing.updated_at = datetime.now(timezone.utc)

        if self.repository is not None:
            self.repository.update(existing)
        self.registry.register(existing)
        return existing

    # ── 删除 ──────────────────────────────────────────────

    def delete_skill(self, skill_id: str) -> bool:
        """删除 skill。返回 True 表示删除成功，False 表示不存在。"""
        existing = self.get_skill(skill_id)
        if existing is None:
            return False
        if self.repository is not None:
            self.repository.delete(skill_id)
        return True

    # ── 校验 · 外部可调用 ─────────────────────────────────

    def validate_skills_for_task(self, skill_ids: list[str]) -> list[str]:
        """校验一组 skill 是否可被任务使用。返回错误列表（空列表表示全部合法）。"""
        errors: list[str] = []
        if not skill_ids:
            return errors

        for skill_id in skill_ids:
            descriptor = self.get_skill(skill_id)
            if descriptor is None:
                errors.append(f"Skill `{skill_id}` does not exist.")
                continue
            if not descriptor.enabled:
                errors.append(f"Skill `{skill_id}` is disabled.")
                continue
            tool_warnings = self._check_tool_warnings(descriptor.required_tools)
            errors.extend(tool_warnings)
        return errors

    def get_enabled_skill_descriptions(self, skill_ids: list[str]) -> list[str]:
        """获取已启用 skill 的描述文本，供注入 planning context。"""
        descriptions: list[str] = []
        for skill_id in skill_ids:
            descriptor = self.get_skill(skill_id)
            if descriptor is None or not descriptor.enabled:
                continue
            desc = f"[{descriptor.skill_id}] {descriptor.display_name}: {descriptor.description}"
            if descriptor.required_tools:
                desc += f" (需要工具: {', '.join(descriptor.required_tools)})"
            descriptions.append(desc)
        return descriptions

    # ── 内部校验 ──────────────────────────────────────────

    def _validate_required_tools(self, tool_ids: list[str]) -> None:
        """校验工具 ID 列表是否全部存在。"""
        if not tool_ids:
            return
        if self.tool_registry is None:
            return

        available = {t.tool_id for t in self.tool_registry.list_tools()}
        missing = [tid for tid in tool_ids if tid not in available]
        if missing:
            raise SkillServiceError(
                f"Required tools do not exist: {', '.join(missing)}. "
                f"Available tools: {', '.join(sorted(available)) if available else '(none)'}"
            )

    def _check_tool_warnings(self, tool_ids: list[str]) -> list[str]:
        """检查依赖工具是否启用，返回警告消息列表。"""
        warnings: list[str] = []
        if self.tool_registry is None or not tool_ids:
            return warnings

        for tid in tool_ids:
            tool = self.tool_registry.get(tid)
            if tool is None:
                continue
            if not tool.enabled:
                warnings.append(f"Required tool `{tid}` is currently disabled.")
        return warnings
