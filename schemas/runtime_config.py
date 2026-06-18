from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


ApiKeyProviderLiteral = Literal["openai", "deepseek", "s2"]
ApiKeyActionLiteral = Literal["set", "clear"]


class RuntimeApiKeyStatusView(BaseModel):
    provider: ApiKeyProviderLiteral
    env_key: str
    label: str
    configured: bool = False
    source: str = "missing"
    fingerprint: str = ""
    help_text: str = ""


class RuntimeFlagView(BaseModel):
    key: str
    label: str
    value: str = ""
    effective_value: str = ""
    description: str = ""


class RuntimeConfigStatusResponse(BaseModel):
    env_file_path: str
    env_file_exists: bool = False
    active_provider: str = "none"
    default_model: str = ""
    llm_available: bool = False
    paper_brief_llm_enabled: bool = False
    research_brief_llm_enabled: bool = False
    semantic_scholar_available: bool = False
    api_keys: List[RuntimeApiKeyStatusView] = Field(default_factory=list)
    runtime_flags: List[RuntimeFlagView] = Field(default_factory=list)
    safety_notes: List[str] = Field(default_factory=list)


class UpdateRuntimeApiKeyRequest(BaseModel):
    provider: ApiKeyProviderLiteral
    action: ApiKeyActionLiteral = "set"
    api_key: str = Field(default="", description="Only used when action is set; never returned by status APIs.")
