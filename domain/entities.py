from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class Conversation:
    """一次多轮交互会话。"""

    conversation_id: str
    title: str
    topic: str
    status: str = "active"
    message_ids: List[str] = field(default_factory=list)
    latest_task_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class MessageRecord:
    """一条对话消息，既可以来自用户，也可以来自系统或 Agent。"""

    message_id: str
    conversation_id: str
    role: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class ResearchTask:
    """会话中的一次具体研究分析任务。"""

    task_id: str
    conversation_id: str
    topic: str
    status: str = "queued"
    trigger_message_id: Optional[str] = None
    mode: str = "default"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class PaperRecord:
    """工作台中展示的一篇论文。"""

    paper_id: str
    title: str
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    publish_date: str = ""
    source: str = ""
    taxonomy_category: str = ""
    citation_count: int = 0
    url: str = ""


@dataclass(slots=True)
class GapRecord:
    """审计后发现的一个 gap。"""

    gap_id: str
    task_id: str
    summary: str
    severity: str = "medium"
    evidence: List[str] = field(default_factory=list)


@dataclass(slots=True)
class ResearchIdea:
    """Agent 内部生成的结构化研究 idea 模型。"""

    idea_id: str
    title: str
    motivation: str
    approach: str
    feasibility: str
    contribution: str
    related_papers: List[str] = field(default_factory=list)
    derived_from_gaps: List[str] = field(default_factory=list)
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    raw_text: str = ""

    @property
    def id(self) -> str:
        return self.idea_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.idea_id,
            "title": self.title,
            "motivation": self.motivation,
            "approach": self.approach,
            "feasibility": self.feasibility,
            "contribution": self.contribution,
            "related_papers": list(self.related_papers),
            "derived_from_gaps": list(self.derived_from_gaps),
            "confidence": float(self.confidence),
            "tags": list(self.tags),
            "raw_text": self.raw_text,
        }


@dataclass(slots=True)
class ResearchIdeaRecord:
    """基于 gap 生成的一个研究建议。"""

    idea_id: str
    task_id: str
    title: str
    motivation: str
    approach: str
    feasibility: str
    contribution: str
    related_papers: List[str] = field(default_factory=list)
    derived_from_gaps: List[str] = field(default_factory=list)
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass(slots=True)
class ResearchWorkspace:
    """
    一次研究任务最终沉淀下来的工作台数据快照。

    说明:
    - 这是“前端工作台视角”的核心对象
    - 不要求与 Agent 内部 state 一一对应
    - 目标是给 UI 一个稳定、可渲染、可持久化的结果结构
    """

    task_id: str
    topic: str
    summary: str = ""
    summary_payload: Dict[str, Any] = field(default_factory=dict)
    papers: List[PaperRecord] = field(default_factory=list)
    taxonomy: Dict[str, Any] = field(default_factory=dict)
    graph_edges: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[GapRecord] = field(default_factory=list)
    ideas: List[ResearchIdeaRecord] = field(default_factory=list)
    alignment_score: float = 0.0
    trace: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolDescriptor:
    """一个可注册的工具定义。"""

    tool_id: str
    display_name: str
    description: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillDescriptor:
    """一个可注册的 skill 定义。"""

    skill_id: str
    display_name: str
    description: str
    enabled: bool = True
    prompts: Dict[str, str] = field(default_factory=dict)
    required_tools: List[str] = field(default_factory=list)


@dataclass(slots=True)
class KnowledgeDocument:
    """用于共享知识或后续 RAG 的知识文档。"""

    document_id: str
    title: str
    source_task_id: Optional[str] = None
    content: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
