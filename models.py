from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict


@dataclass
class PaperNode:
    paper_id: str
    title: str = ""
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    publish_date: str = ""
    source: str = ""
    taxonomy_category: str = ""
    citation_count: int = 0
    url: str = ""
    doi: str = ""
    references: List[str] = field(default_factory=list)
    is_gap_candidate: bool = False
    confidence_score: float = 1.0
    is_new_this_round: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "keywords": self.keywords,
            "publish_date": self.publish_date,
            "source": self.source,
            "taxonomy_category": self.taxonomy_category,
            "citation_count": self.citation_count,
            "url": self.url,
            "doi": self.doi,
            "references": self.references,
            "is_gap_candidate": self.is_gap_candidate,
            "confidence_score": self.confidence_score,
            "is_new_this_round": self.is_new_this_round,
        }


@dataclass
class EvolutionEdge:
    source: str
    target: str
    relationship: str = ""
    reasoning: str = ""
    weight: float = 0.0
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "reasoning": self.reasoning,
            "weight": self.weight,
            "evidence": self.evidence,
        }


class ResearchState(TypedDict, total=False):
    topic: str
    conversation_topic: str
    mode: str
    max_results: int
    search_queries: List[str]
    knowledge_scope: str
    query_intent: Dict[str, Any]
    retrieval_plan: Dict[str, Any]
    retrieval_outcome: Dict[str, Any]
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
    previous_round_query_intent: Dict[str, Any]
    paper_nodes: Dict[str, PaperNode]
    review_texts: List[str]
    expert_taxonomy: Dict[str, Any]
    evolution_graph: List[EvolutionEdge]
    alignment_score: float
    audit_reports: List[Dict[str, Any]]
    detected_gaps: List[Dict[str, Any]]
    audit_summary: Dict[str, Any]
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
