from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateResearchTaskRequest(BaseModel):
    conversation_id: str
    topic: str
    mode: str = Field(default="default", description="default / fast / balanced 等")
    use_shared_knowledge: bool = Field(default=False)
    enabled_tools: List[str] = Field(default_factory=list)


class CreateResearchTaskResponse(BaseModel):
    task_id: str
    conversation_id: str
    status: str


class WorkspacePaperView(BaseModel):
    paper_id: str
    title: str
    publish_date: str = ""
    source: str = ""
    taxonomy_category: str = ""
    citation_count: int = 0
    url: str = ""


class WorkspaceGraphEdgeView(BaseModel):
    source: str
    target: str
    relationship: str
    reasoning: str = ""


class WorkspaceGapView(BaseModel):
    summary: str
    severity: str = "medium"
    evidence: List[str] = Field(default_factory=list)


class WorkspaceIdeaView(BaseModel):
    title: str
    motivation: str = ""
    approach: str = ""
    feasibility: str = ""
    contribution: str = ""
    raw_text: str = ""


class WorkspaceTraceView(BaseModel):
    thought_trace: List[Dict[str, Any]] = Field(default_factory=list)
    action_history: List[Dict[str, Any]] = Field(default_factory=list)
    context_inputs: List[Dict[str, Any]] = Field(default_factory=list)


class WorkspaceSnapshotResponse(BaseModel):
    task_id: str
    topic: str
    summary: str = ""
    papers: List[WorkspacePaperView] = Field(default_factory=list)
    taxonomy: Dict[str, Any] = Field(default_factory=dict)
    graph_edges: List[WorkspaceGraphEdgeView] = Field(default_factory=list)
    gaps: List[WorkspaceGapView] = Field(default_factory=list)
    ideas: List[WorkspaceIdeaView] = Field(default_factory=list)
    alignment_score: float = 0.0
    trace: Optional[WorkspaceTraceView] = None
