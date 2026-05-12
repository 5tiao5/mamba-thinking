from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ToolView(BaseModel):
    tool_id: str
    display_name: str
    description: str
    enabled: bool
    config: Dict[str, Any] = Field(default_factory=dict)


class SkillView(BaseModel):
    skill_id: str
    display_name: str
    description: str
    enabled: bool
    required_tools: List[str] = Field(default_factory=list)


class UpdateToolRequest(BaseModel):
    enabled: bool
    config: Dict[str, Any] = Field(default_factory=dict)

