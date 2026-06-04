from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateSkillRequest(BaseModel):
    skill_id: str = Field(..., description="Unique skill identifier, e.g. 'paper_compare'")
    display_name: str = Field(..., description="Human-readable skill name")
    description: str = Field(default="", description="What this skill does and when to use it")
    required_tools: List[str] = Field(default_factory=list, description="Tool IDs this skill depends on")
    enabled: bool = Field(default=True)


class UpdateSkillRequest(BaseModel):
    display_name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    required_tools: Optional[List[str]] = Field(default=None)
    enabled: Optional[bool] = Field(default=None)


class UpdateToolRequest(BaseModel):
    enabled: bool
    config: Dict[str, Any] = Field(default_factory=dict)

