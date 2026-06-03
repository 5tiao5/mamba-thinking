from __future__ import annotations

import os
import random
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models import EvolutionEdge, PaperNode, ResearchState

SEED_PAPERS: Dict[str, List[Dict[str, Any]]] = {
    "agent tool use": [
        {
            "paper_id": "seed_tool_001",
            "title": "Tool Learning with Foundation Models: A Survey",
            "abstract": "Comprehensive survey of tool-augmented LLMs covering planning, grounding, and execution paradigms.",
            "authors": ["Survey Authors"],
            "keywords": ["tool learning", "LLM agent", "tool use"],
            "source": "seed",
            "taxonomy_category": "cs.AI",
        },
        {
            "paper_id": "seed_tool_002",
            "title": "Gorilla: Large Language Model Connected with Massive APIs",
            "abstract": "Introduces a retrieve-aware fine-tuned LLaMA model for generating accurate API calls with reduced hallucination.",
            "authors": ["Patil et al."],
            "keywords": ["API call", "LLM", "tool use"],
            "source": "seed",
            "taxonomy_category": "cs.CL",
        },
        {
            "paper_id": "seed_tool_003",
            "title": "Toolformer: Language Models Can Teach Themselves to Use Tools",
            "abstract": "Demonstrates LMs can learn to use external tools via self-supervised fine-tuning without human demonstrations.",
            "authors": ["Schick et al."],
            "keywords": ["tool use", "self-supervised", "language model"],
            "source": "seed",
            "taxonomy_category": "cs.CL",
        },
    ],
    "rag": [
        {
            "paper_id": "seed_rag_001",
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "abstract": "Introduces RAG combining pretrained parametric and non-parametric memory for knowledge-intensive tasks.",
            "authors": ["Lewis et al."],
            "keywords": ["RAG", "retrieval", "knowledge"],
            "source": "seed",
            "taxonomy_category": "cs.CL",
        },
        {
            "paper_id": "seed_rag_002",
            "title": "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
            "abstract": "Trains an LM to adaptively retrieve passages on-demand and reflect on retrieved passages to improve generation quality.",
            "authors": ["Asai et al."],
            "keywords": ["RAG", "self-reflection", "retrieval"],
            "source": "seed",
            "taxonomy_category": "cs.CL",
        },
    ],
    "code agent": [
        {
            "paper_id": "seed_code_001",
            "title": "SWE-Agent: Agent-Computer Interfaces for Automated Software Engineering",
            "abstract": "Introduces agent-computer interfaces enabling LM agents to navigate repositories, edit code, and execute commands for software engineering tasks.",
            "authors": ["Yang et al."],
            "keywords": ["code agent", "software engineering", "LM agent"],
            "source": "seed",
            "taxonomy_category": "cs.SE",
        },
        {
            "paper_id": "seed_code_002",
            "title": "Devin: The AI Software Engineer - An Analysis of Autonomous Coding Agents",
            "abstract": "Analyzes the architecture and capabilities of autonomous coding agents in real-world software development scenarios.",
            "authors": ["Analysis Team"],
            "keywords": ["autonomous coding", "software engineering", "AI agent"],
            "source": "seed",
            "taxonomy_category": "cs.SE",
        },
    ],
}

_DEFAULT_SEEDS = [
    {
        "paper_id": "seed_gen_001",
        "title": "A Survey of Recent Advances in the Field",
        "abstract": "This seed paper is a placeholder — real search results were not available. Consider running with a more specific topic or checking API access.",
        "authors": ["Seed Paper"],
        "keywords": ["survey"],
        "source": "seed",
        "taxonomy_category": "",
    },
    {
        "paper_id": "seed_gen_002",
        "title": "Key Challenges and Open Problems",
        "abstract": "Seed paper for evidence-insufficient mode. The pipeline can proceed but results should be treated as suggestive rather than definitive.",
        "authors": ["Seed Paper"],
        "keywords": ["challenges"],
        "source": "seed",
        "taxonomy_category": "",
    },
    {
        "paper_id": "seed_gen_003",
        "title": "Emerging Methods and Future Directions",
        "abstract": "Seed paper — indicates that the search tier returned no results. This workspace shows the pipeline's best-effort output with limited evidence.",
        "authors": ["Seed Paper"],
        "keywords": ["future directions"],
        "source": "seed",
        "taxonomy_category": "",
    },
]


# ── Mode checks ───────────────────────────────────────────────────────────────

def _state_mode(state: Optional[Dict[str, Any]] = None) -> str:
    mode = str((state or {}).get("mode", "")).strip().lower()
    if mode in {"fast", "balanced", "default"}:
        return mode
    if os.environ.get("FAST_MODE") == "1":
        return "fast"
    if os.environ.get("BALANCED_MODE") == "1":
        return "balanced"
    return "default"


def fast_mode(state: Optional[Dict[str, Any]] = None) -> bool:
    return _state_mode(state) == "fast"


def balanced_mode(state: Optional[Dict[str, Any]] = None) -> bool:
    return _state_mode(state) == "balanced"


# ── State helpers ─────────────────────────────────────────────────────────────

def initial_state(
    topic: str,
    max_results: int = 8,
    mode: str = "default",
    conversation_workspace_context: List[str] | None = None,
    research_context: Dict[str, Any] | None = None,
) -> ResearchState:
    context = dict(research_context or {})
    workspace_context = context.get("conversation_workspace_context", conversation_workspace_context or [])
    return ResearchState(
        topic=topic,
        conversation_topic=str(context.get("conversation_topic", topic)),
        mode=mode,
        knowledge_scope=str(context.get("knowledge_scope", "shared")),
        query_intent=dict(context.get("query_intent", {}) or {}),
        retrieval_plan=dict(context.get("retrieval_plan", {}) or {}),
        retrieval_outcome=dict(context.get("retrieval_outcome", {}) or {}),
        knowledge_context=list(context.get("knowledge_context", [])),
        knowledge_hits=list(context.get("knowledge_hits", [])),
        recent_context=list(context.get("recent_context", [])),
        context_inputs=list(context.get("context_inputs", [])),
        conversation_workspace_context=list(workspace_context or []),
        conversation_workspace_summary=str(context.get("conversation_workspace_summary", "")),
        working_memory_summary=str(context.get("working_memory_summary", "")),
        working_memory_current_focus=str(context.get("working_memory_current_focus", "")),
        working_memory_findings=list(context.get("working_memory_findings", [])),
        working_memory_open_questions=list(context.get("working_memory_open_questions", [])),
        working_memory_constraints=list(context.get("working_memory_constraints", [])),
        previous_round_task_id=str(context.get("previous_round_task_id", "") or ""),
        previous_round_paper_ids=list(context.get("previous_round_paper_ids", [])),
        previous_round_query_intent=dict(context.get("previous_round_query_intent", {}) or {}),
        max_results=max_results,
        search_queries=[],
        paper_nodes={},
        review_texts=[],
        expert_taxonomy={},
        evolution_graph=[],
        alignment_score=0.0,
        audit_reports=[],
        detected_gaps=[],
        generated_ideas=[],
        final_report="",
        final_report_text="",
        final_report_summary={},
        mermaid_graph="",
        controller_step=0,
        next_action="planner",
        current_goal="",
        pending_actions=[],
        logs=[],
        decisions=[],
        error_events=[],
        tool_events=[],
        audit_events=[],
        graph_events=[],
        thought_trace=[],
        retry_count=0,
        retry_requested=False,
        correction_checked=False,
        needs_taxonomy_refresh=False,
        needs_graph_refresh=False,
        needs_audit_refresh=False,
        synthesis_completed=False,
        run_status="running",
        taxonomy_built=False,
        graph_built=False,
        audit_completed=False,
        agent_plan="",
    )


def build_agent_plan(topic: str, tool_names: List[str], mode: str) -> str:
    tools = ", ".join(tool_names)
    return f"Plan [{mode}]: research '{topic}' using {tools}."


# ── Paper selection ───────────────────────────────────────────────────────────

def select_relevant_papers(
    topic: str,
    query: str,
    raw_results: List[PaperNode],
    limit: int = 5,
    relaxed: bool = False,
) -> List[PaperNode]:
    """Score papers by relevance to topic/query and return top N."""
    if not raw_results:
        return []

    topic_terms = _tokenize(topic)
    query_terms = _tokenize(query)
    all_terms = set(topic_terms + query_terms)

    scored: List[Tuple[float, PaperNode]] = []
    for paper in raw_results:
        score = _relevance_score(paper, all_terms)
        # Source bonus: arxiv papers get slight boost
        if paper.source == "arxiv":
            score += 0.05
        scored.append((score, paper))

    scored.sort(key=lambda x: x[0], reverse=True)

    threshold = 0.0 if relaxed else 0.1
    selected = [p for s, p in scored if s >= threshold]
    return selected[:max(limit, 1)]


def _relevance_score(paper: PaperNode, terms: set) -> float:
    if not terms:
        return 0.5
    title_lower = paper.title.lower()
    abstract_lower = paper.abstract.lower()
    kw_lower = {k.lower() for k in paper.keywords}

    score = 0.0
    for term in terms:
        if term in title_lower:
            score += 3.0
        if term in abstract_lower:
            score += 1.0
        if term in kw_lower:
            score += 2.0

    # Normalize by number of terms
    score /= max(1, len(terms))

    # 🎯 Citation bonus: highly-cited papers are more influential
    if paper.citation_count >= 500:
        score += 0.8
    elif paper.citation_count >= 100:
        score += 0.5
    elif paper.citation_count >= 10:
        score += 0.2

    # 🎯 Source quality bonus: prioritize real papers over seed/fallback
    source_lower = (paper.source or "").lower()
    if source_lower in ("arxiv", "semantic_scholar"):
        score += 0.5
    elif source_lower == "seed":
        score -= 0.3  # penalize synthetic seed papers

    # 🎯 Recency bonus: prefer newer papers (publish_date like "2024")
    pub_year = (paper.publish_date or "")[:4]
    if pub_year.isdigit():
        year = int(pub_year)
        current_year = 2026
        if year >= current_year - 1:
            score += 0.3
        elif year >= current_year - 3:
            score += 0.15

    # Bonus for papers with non-empty abstracts
    if paper.abstract:
        score += 0.5

    return max(0.0, score)


def _tokenize(text: str) -> List[str]:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    words = text.split()
    stop = {
        "a", "an", "the", "of", "in", "on", "to", "for", "and", "or", "is",
        "are", "be", "with", "using", "from", "by", "as", "at", "that", "this",
        "which", "it", "its", "can", "has", "have", "been", "was", "were",
    }
    # Extract unigrams and bigrams
    unigrams = [w for w in words if w not in stop and len(w) > 2]
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    return unigrams + bigrams


# ── Paper merging ─────────────────────────────────────────────────────────────

def merge_paper(papers: Dict[str, PaperNode], paper: PaperNode) -> None:
    """Merge a paper into the collection, keeping richer metadata on collision."""
    key = paper.paper_id
    if key in papers:
        existing = papers[key]
        # Keep longer abstract
        if len(paper.abstract) > len(existing.abstract):
            existing.abstract = paper.abstract
        # Merge keywords
        existing_kw = {k.lower() for k in existing.keywords}
        for kw in paper.keywords:
            if kw.lower() not in existing_kw:
                existing.keywords.append(kw)
        # Keep higher citation count
        if paper.citation_count > existing.citation_count:
            existing.citation_count = paper.citation_count
        # Merge references
        existing_refs = set(existing.references)
        for ref in paper.references:
            if ref not in existing_refs:
                existing.references.append(ref)
    else:
        papers[key] = paper


def dedupe(items: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in items:
        clean = " ".join(str(item).split()).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


# ── Fallback papers ───────────────────────────────────────────────────────────

def fallback_papers(topic: str) -> Dict[str, PaperNode]:
    """Return seed papers matching the topic, or generic placeholders."""
    topic_lower = topic.lower()
    for key, seeds in SEED_PAPERS.items():
        if key in topic_lower:
            papers: Dict[str, PaperNode] = {}
            for s in seeds:
                p = PaperNode(**s)
                papers[p.paper_id] = p
            return papers

    papers: Dict[str, PaperNode] = {}
    for s in _DEFAULT_SEEDS:
        p = PaperNode(**s)
        papers[p.paper_id] = p
    return papers


# ── Supplement functions ──────────────────────────────────────────────────────

def supplement_balanced_papers(
    topic: str,
    papers: Dict[str, PaperNode],
    candidate_pool: List[PaperNode],
    target_count: int = 3,
) -> Dict[str, PaperNode]:
    """Backfill papers from candidate pool with relaxed matching for demo stability."""
    if len(papers) >= target_count or not candidate_pool:
        return papers

    existing_ids = set(papers.keys())
    topic_terms = set(_tokenize(topic))
    remaining = [p for p in candidate_pool if p.paper_id not in existing_ids]
    scored = [(_relevance_score(p, topic_terms), p) for p in remaining]
    scored.sort(key=lambda x: x[0], reverse=True)

    for _, paper in scored:
        if len(papers) >= target_count:
            break
        papers[paper.paper_id] = paper
    return papers


def supplement_full_mode_papers(
    topic: str,
    papers: Dict[str, PaperNode],
    candidate_pool: List[PaperNode],
    target_count: int = 6,
) -> Dict[str, PaperNode]:
    """Selective backfill using stricter relevance for full mode coverage."""
    if len(papers) >= target_count or not candidate_pool:
        return papers

    existing_ids = set(papers.keys())
    topic_terms = set(_tokenize(topic))
    remaining = [p for p in candidate_pool if p.paper_id not in existing_ids]
    scored = [(_relevance_score(p, topic_terms), p) for p in remaining]
    scored.sort(key=lambda x: x[0], reverse=True)

    for score, paper in scored:
        if len(papers) >= target_count:
            break
        if score >= 0.3:
            papers[paper.paper_id] = paper
    return papers


# ── Paper relationship ────────────────────────────────────────────────────────

def keyword_overlap(left: PaperNode, right: PaperNode) -> float:
    """Jaccard similarity between two papers' keyword sets."""
    left_kw = {canonical(k) for k in (left.keywords or [])}
    right_kw = {canonical(k) for k in (right.keywords or [])}

    if left.taxonomy_category:
        left_kw.add(canonical(left.taxonomy_category))
    if right.taxonomy_category:
        right_kw.add(canonical(right.taxonomy_category))

    # Also add keywords extracted from title
    left_kw.update(_tokenize(left.title))
    right_kw.update(_tokenize(right.title))

    union = left_kw | right_kw
    if not union:
        return 0.0
    intersection = left_kw & right_kw
    return len(intersection) / max(1, len(union))


def infer_relationship(source: PaperNode, target: PaperNode) -> str:
    """Infer the relationship direction: improves, extends, references, or compares."""
    overlap = keyword_overlap(source, target)
    if overlap >= 0.5:
        return "extends"
    if overlap >= 0.3:
        return "improves"
    if overlap >= 0.15:
        return "compares"
    return "references"


def canonical(value: str) -> str:
    return " ".join(str(value).lower().strip().split())


def order_by_date(left: PaperNode, right: PaperNode) -> Tuple[PaperNode, PaperNode]:
    left_date = left.publish_date or "0000"
    right_date = right.publish_date or "0000"
    if left_date <= right_date:
        return left, right
    return right, left


# ── Gap keywords ──────────────────────────────────────────────────────────────

def gap_keywords(gaps: List[Dict[str, Any]], limit: int = 8) -> List[str]:
    """Extract distinct keywords from gap descriptions for query expansion."""
    words: List[str] = []
    for gap in gaps:
        desc = str(gap.get("description", ""))
        words.extend(_tokenize(desc))
    return dedupe(words)[:limit]


# ── Balanced fallback pairs ───────────────────────────────────────────────────

def balanced_fallback_pairs(
    papers_list: List[PaperNode],
    topic: str,
) -> List[Tuple[PaperNode, PaperNode, float]]:
    """Generate weak edge pairs for balanced mode when references are unavailable."""
    if len(papers_list) < 2:
        return []
    pairs: List[Tuple[PaperNode, PaperNode, float]] = []
    for i in range(len(papers_list)):
        for j in range(i + 1, len(papers_list)):
            left, right = papers_list[i], papers_list[j]
            overlap = keyword_overlap(left, right)
            pairs.append((left, right, overlap))
    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs[:min(len(pairs), 5)]


# ── Progress display ──────────────────────────────────────────────────────────

class ProgressPrinter:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self._step = 0
        self._total = 0

    def start(self, step: int, total: int, name: str, detail: str) -> None:
        self._step = step
        self._total = total
        if self._enabled:
            print(f"[{step}/{total}] {name}: {detail}")

    def finish(self, step: int, total: int, name: str, summary: str) -> None:
        if self._enabled:
            print(f"[{step}/{total}] {name} done — {summary}")

    def done(self) -> None:
        if self._enabled:
            print("Pipeline complete.")


def progress_summary(state: Dict[str, Any]) -> str:
    papers = state.get("paper_nodes", {})
    paper_count = len(papers) if isinstance(papers, dict) else 0
    edge_count = len(state.get("evolution_graph", []))
    gap_count = len(state.get("detected_gaps", []))
    return f"papers={paper_count}, edges={edge_count}, gaps={gap_count}"


# ── Tool name mapping ─────────────────────────────────────────────────────────

def tool_name(func_name: str) -> str:
    mapping = {
        "search_papers": "ArXiv search",
        "search_semantic_scholar": "Semantic Scholar",
        "search_survey_papers": "ArXiv survey search",
        "enrich_paper_references": "Semantic Scholar citation enrichment",
    }
    return mapping.get(func_name, func_name)
