from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict


@dataclass
class PaperNode:
    paper_id: str
    title: str = ""
    abstract: str = ""
    review_text: str = ""
    authors: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    publish_date: str = ""
    source: str = ""
    taxonomy_category: str = ""
    expert_taxonomy_branches: List[str] = field(default_factory=list)
    citation_count: int = 0
    citation_count_known: bool = False
    citation_source: str = ""
    url: str = ""
    doi: str = ""
    references: List[str] = field(default_factory=list)
    is_gap_candidate: bool = False
    confidence_score: float = 1.0
    is_new_this_round: bool = False
    relevance_score: float = 0.0
    relevance_tier: str = "candidate"
    relevance_reasons: List[str] = field(default_factory=list)
    paper_pool_status: str = ""
    document_id: str = ""
    origin: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "review_text": self.review_text,
            "authors": self.authors,
            "keywords": self.keywords,
            "publish_date": self.publish_date,
            "source": self.source,
            "taxonomy_category": self.taxonomy_category,
            "expert_taxonomy_branches": self.expert_taxonomy_branches,
            "citation_count": self.citation_count,
            "citation_count_known": self.citation_count_known,
            "citation_source": self.citation_source,
            "url": self.url,
            "doi": self.doi,
            "references": self.references,
            "is_gap_candidate": self.is_gap_candidate,
            "confidence_score": self.confidence_score,
            "is_new_this_round": self.is_new_this_round,
            "relevance_score": self.relevance_score,
            "relevance_tier": self.relevance_tier,
            "relevance_reasons": self.relevance_reasons,
            "paper_pool_status": self.paper_pool_status,
            "document_id": self.document_id,
            "origin": self.origin,
        }


@dataclass
class EvolutionEdge:
    source: str
    target: str
    relationship: str = ""
    reasoning: str = ""
    weight: float = 0.0
    evidence: str = ""
    provenance: str = ""
    confidence: float = 0.0
    evidence_level: str = "candidate"
    evidence_snippets: List[str] = field(default_factory=list)
    evidence_details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "reasoning": self.reasoning,
            "weight": self.weight,
            "evidence": self.evidence,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "evidence_level": self.evidence_level,
            "evidence_snippets": self.evidence_snippets,
            "evidence_details": self.evidence_details,
        }


class ResearchState(TypedDict, total=False):
    topic: str
    conversation_topic: str
    mode: str
    max_results: int
    search_queries: List[str]
    knowledge_scope: str
    research_mode: str
    query_intent: Dict[str, Any]
    retrieval_plan: Dict[str, Any]
    retrieval_outcome: Dict[str, Any]
    query_coverage: Dict[str, Any]
    evidence_coverage: Dict[str, Any]
    knowledge_context: List[str]
    knowledge_hits: List[Dict[str, Any]]
    recent_context: List[Dict[str, Any]]
    context_inputs: List[Dict[str, Any]]
    conversation_workspace_context: List[str]
    conversation_workspace_summary: str
    working_memory_summary: str
    working_memory_current_focus: str
    working_memory_findings: List[str]
    working_memory_open_questions: List[str]
    working_memory_constraints: List[str]
    previous_round_task_id: str
    previous_round_paper_ids: List[str]
    previous_round_papers: List[Dict[str, Any]]
    previous_round_query_intent: Dict[str, Any]
    research_papers: List[Dict[str, Any]]
    evidence_pool: Dict[str, PaperNode]
    paper_nodes: Dict[str, PaperNode]
    review_texts: List[str]
    expert_taxonomy: Dict[str, Any]
    evolution_graph: List[EvolutionEdge]
    alignment_score: float
    audit_reports: List[Dict[str, Any]]
    detected_gaps: List[Dict[str, Any]]
    audit_summary: Dict[str, Any]
    evidence_snapshot: Dict[str, Any]
    generated_ideas: List[Dict[str, Any]]
    final_report: str
    final_report_id: str
    final_report_text: str
    final_report_summary: Dict[str, Any]
    mermaid_graph: str
    controller_step: int
    next_action: str
    current_goal: str
    pending_actions: List[str]
    logs: List[str]
    decisions: List[Dict[str, Any]]
    error_events: List[Dict[str, Any]]
    tool_events: List[Dict[str, Any]]
    audit_events: List[Dict[str, Any]]
    graph_events: List[Dict[str, Any]]
    thought_trace: List[Dict[str, Any]]
    retry_count: int
    max_repair_rounds: int
    min_repair_alignment_gain: float
    repair_baseline: Dict[str, Any]
    repair_history: List[Dict[str, Any]]
    repair_stop_reason: str
    degraded_reason: str
    termination_reason: str
    retry_requested: bool
    correction_checked: bool
    needs_taxonomy_refresh: bool
    needs_graph_refresh: bool
    needs_audit_refresh: bool
    synthesis_completed: bool
    run_status: str
    taxonomy_built: bool
    graph_built: bool
    audit_completed: bool
    agent_plan: str
