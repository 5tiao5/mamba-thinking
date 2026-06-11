from __future__ import annotations

from observability import StageTimer, record_decision, record_tool_event
from tools import build_taxonomy

from ..models import ResearchState
from ...services.taxonomy_evidence_service import build_taxonomy_evidence_brief
from ...services.taxonomy_grounding_service import assign_papers_to_taxonomy


def taxonomy_node(state: ResearchState) -> ResearchState:
    """根据综述或摘要文本构建 taxonomy。"""

    if state.get("expert_taxonomy") and not state.get("needs_taxonomy_refresh"):
        _apply_paper_taxonomy_assignments(state)
        record_decision(
            state,
            stage="taxonomy",
            decision="Reuse existing expert taxonomy.",
            reason="A baseline taxonomy already exists in state.",
            next_step="evolution_graph",
        )
        return state

    papers = list(state.get("paper_nodes", {}).values())
    evidence_brief = build_taxonomy_evidence_brief(
        topic=state.get("topic", ""),
        papers=papers,
        review_texts=state.get("review_texts", []),
    )
    paper_text = "\n\n".join(f"{paper.title}\n{paper.abstract}" for paper in papers)
    survey_text = "\n\n".join(state.get("review_texts", []))
    source_text = "\n\n".join(part for part in [evidence_brief, survey_text, paper_text] if part)
    timer = StageTimer()
    taxonomy = build_taxonomy(source_text)

    updated = dict(state)
    updated["expert_taxonomy"] = taxonomy
    _apply_paper_taxonomy_assignments(updated)
    record_tool_event(
        updated,
        tool_name="Taxonomy builder",
        input_summary=f"text_chars={len(source_text)}",
        status="success",
        output_count=len(taxonomy.get("taxonomy", {})) if isinstance(taxonomy, dict) else 0,
        duration_sec=timer.elapsed(),
        note="Evidence-first taxonomy summary built from retrieved papers, keywords, categories, and optional review text.",
    )
    record_decision(
        updated,
        stage="taxonomy",
        decision="Build expert taxonomy from survey/paper text.",
        reason="Auditor needs a baseline taxonomy to detect missing branches and concepts.",
        next_step="evolution_graph",
    )
    updated.setdefault("logs", []).append("Taxonomy built from survey/paper text.")
    return updated


def _apply_paper_taxonomy_assignments(state: ResearchState) -> None:
    papers = state.get("paper_nodes", {})
    assignments = assign_papers_to_taxonomy(
        state.get("expert_taxonomy", {}),
        list(papers.values()),
    )
    for paper_id, paper in papers.items():
        paper.expert_taxonomy_branches = list(assignments.get(paper_id, []))
