from __future__ import annotations

from observability import StageTimer, record_decision, record_tool_event
from tools import build_taxonomy

from ..models import ResearchState


def taxonomy_node(state: ResearchState) -> ResearchState:
    """根据综述或摘要文本构建 taxonomy。"""

    if state.get("expert_taxonomy"):
        record_decision(
            state,
            stage="taxonomy",
            decision="Reuse existing expert taxonomy.",
            reason="A baseline taxonomy already exists in state.",
            next_step="evolution_graph",
        )
        return state

    paper_text = "\n\n".join(f"{paper.title}\n{paper.abstract}" for paper in state.get("paper_nodes", {}).values())
    source_text = "\n\n".join(state.get("review_texts", [])) or paper_text
    timer = StageTimer()
    taxonomy = build_taxonomy(source_text)

    updated = dict(state)
    updated["expert_taxonomy"] = taxonomy
    record_tool_event(
        updated,
        tool_name="Taxonomy builder",
        input_summary=f"text_chars={len(source_text)}",
        status="success",
        output_count=len(taxonomy.get("taxonomy", {})) if isinstance(taxonomy, dict) else 0,
        duration_sec=timer.elapsed(),
        note="LLM or rule-based fallback depending on mode/API availability.",
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
