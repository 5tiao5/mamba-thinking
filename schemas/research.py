from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


KnowledgeScopeLiteral = Literal["none", "conversation_only", "shared"]
ResearchModeLiteral = Literal["hybrid", "imported_only", "search_only"]


class CreateResearchTaskRequest(BaseModel):
    conversation_id: str
    topic: str
    mode: str = Field(default="default", description="Task execution mode: default / fast / balanced")
    use_shared_knowledge: bool = Field(default=False)
    knowledge_scope: Optional[KnowledgeScopeLiteral] = Field(
        default=None,
        description="Knowledge scope for this task: none / conversation_only / shared.",
    )
    research_mode: ResearchModeLiteral = Field(
        default="hybrid",
        description="Paper evidence mode: hybrid / imported_only / search_only.",
    )
    enabled_tools: List[str] = Field(default_factory=list)
    selected_skill_ids: List[str] = Field(default_factory=list, description="Skill IDs to activate for this task")

    def resolve_knowledge_scope(self) -> str:
        if self.knowledge_scope is not None:
            return self.knowledge_scope
        return "shared" if self.use_shared_knowledge else "conversation_only"


class CreateResearchTaskResponse(BaseModel):
    task_id: str
    conversation_id: str
    status: str
    knowledge_scope: KnowledgeScopeLiteral = "shared"
    research_mode: ResearchModeLiteral = "hybrid"


class ResearchTaskSummaryView(BaseModel):
    task_id: str
    conversation_id: str
    topic: str
    status: str
    mode: str
    knowledge_scope: KnowledgeScopeLiteral = "shared"
    research_mode: ResearchModeLiteral = "hybrid"
    trigger_message_id: Optional[str] = None
    created_at: str
    updated_at: str


class ListResearchTasksResponse(BaseModel):
    items: List[ResearchTaskSummaryView] = Field(default_factory=list)


class WorkspacePaperView(BaseModel):
    paper_id: str
    title: str
    publish_date: str = ""
    source: str = ""
    taxonomy_category: str = ""
    citation_count: int = 0
    citation_count_known: bool = False
    citation_source: str = ""
    url: str = ""
    is_new_this_round: bool = False
    relevance_score: float = 0.0
    relevance_tier: str = "candidate"
    relevance_reasons: List[str] = Field(default_factory=list)
    paper_pool_status: str = ""
    document_id: str = ""
    origin: str = ""


class WorkspaceGraphEdgeView(BaseModel):
    source: str
    target: str
    relationship: str
    reasoning: str = ""
    provenance: str = ""
    confidence: float = 0.0
    evidence_level: str = "candidate"
    evidence: str = ""
    evidence_snippets: List[str] = Field(default_factory=list)
    evidence_details: List[Dict[str, Any]] = Field(default_factory=list)


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
    run_status: str = "completed"
    termination_reason: str = ""
    degraded_reason: str = ""
    repair_count: int = 0
    max_repair_rounds: int = 0
    repair_stop_reason: str = ""
    repair_history: List[Dict[str, Any]] = Field(default_factory=list)


class WorkspaceKnowledgeHitView(BaseModel):
    title: str = ""
    snippet: str = ""
    scope: str = "shared"
    source_type: str = ""
    source_task_id: Optional[str] = None
    score: float = 0.0
    evidence_level: str = "candidate"
    matched_chunk_count: int = 0
    supporting_snippets: List[str] = Field(default_factory=list)


class WorkspaceSourceTraceView(BaseModel):
    knowledge_scope: KnowledgeScopeLiteral = "shared"
    research_mode: ResearchModeLiteral = "hybrid"
    retrieval_plan: str = ""
    retrieval_status: str = ""
    retrieval_message: str = ""
    filtered_out_count: int = 0
    fallback_used: bool = False
    external_search_skipped: bool = False
    refresh_triggered: bool = False
    novel_paper_count: int = 0
    reused_paper_count: int = 0
    direct_paper_count: int = 0
    adjacent_paper_count: int = 0
    low_relevance_filtered_count: int = 0
    knowledge_hit_count: int = 0
    knowledge_hits: List[WorkspaceKnowledgeHitView] = Field(default_factory=list)
    workspace_hint_count: int = 0
    workspace_hints: List[str] = Field(default_factory=list)
    recent_turn_count: int = 0
    recent_user_turns: List[str] = Field(default_factory=list)


class WorkspaceInheritedContextView(BaseModel):
    conversation_topic: str = ""
    workspace_summary: str = ""
    workspace_hints: List[str] = Field(default_factory=list)
    recent_turns: List[str] = Field(default_factory=list)


class WorkspaceWorkingMemoryView(BaseModel):
    current_focus: str = ""
    summary: str = ""
    stable_findings: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    active_constraints: List[str] = Field(default_factory=list)
    supporting_task_ids: List[str] = Field(default_factory=list)
    source_task_id: Optional[str] = None
    updated_at: str = ""


class WorkspaceEvidenceStatusView(BaseModel):
    insufficient: bool = False
    total_papers: int = 0
    real_paper_count: int = 0
    direct_paper_count: int = 0
    adjacent_paper_count: int = 0
    fallback_paper_count: int = 0
    fallback_ratio: float = 0.0
    covered_branch_count: int = 0
    candidate_branches: List[str] = Field(default_factory=list)
    message: str = ""


class WorkspaceEvidenceSnapshotView(BaseModel):
    snapshot_id: str = ""
    version: str = "v1"
    created_at: str = ""
    topic: str = ""
    stats: Dict[str, Any] = Field(default_factory=dict)
    retrieval_plan: Dict[str, Any] = Field(default_factory=dict)
    retrieval_outcome: Dict[str, Any] = Field(default_factory=dict)
    alignment_score: float = 0.0


class WorkspaceSnapshotResponse(BaseModel):
    task_id: str
    topic: str
    summary: str = ""
    papers: List[WorkspacePaperView] = Field(default_factory=list)
    analysis_paper_ids: List[str] = Field(default_factory=list)
    taxonomy: Dict[str, Any] = Field(default_factory=dict)
    graph_edges: List[WorkspaceGraphEdgeView] = Field(default_factory=list)
    gaps: List[WorkspaceGapView] = Field(default_factory=list)
    ideas: List[WorkspaceIdeaView] = Field(default_factory=list)
    alignment_score: float = 0.0
    evidence_status: WorkspaceEvidenceStatusView = Field(default_factory=WorkspaceEvidenceStatusView)
    evidence_snapshot: Optional[WorkspaceEvidenceSnapshotView] = None
    source_trace: Optional[WorkspaceSourceTraceView] = None
    inherited_context: Optional[WorkspaceInheritedContextView] = None
    working_memory: Optional[WorkspaceWorkingMemoryView] = None
    trace: Optional[WorkspaceTraceView] = None

