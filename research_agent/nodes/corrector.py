from __future__ import annotations

from observability import record_audit_event, record_decision
from pipeline_utils import balanced_mode, dedupe, fast_mode, gap_keywords

from ..models import ResearchState


def corrector_node(state: ResearchState) -> ResearchState:
    """根据审计结果决定是否追加一次 gap-driven 检索。"""

    retry_count = int(state.get("retry_count", 0))
    if fast_mode(state) or balanced_mode(state):
        record_audit_event(
            state,
            event_type="corrector_skipped",
            summary="Corrector skipped retry in speed-focused mode.",
            severity="info",
            recovery="Use balanced/full mode without speed restrictions for more evidence.",
        )
        record_decision(
            state,
            stage="corrector",
            decision="Skip corrective retry.",
            reason="Current mode prioritizes runtime and avoids extra external calls.",
            next_step="synthesizer",
        )
        state["correction_checked"] = True
        state["retry_requested"] = False
        return state

    gaps = state.get("detected_gaps", [])
    score = float(state.get("alignment_score", 0.0))
    if retry_count >= 1 or (score >= 0.7 and len(gaps) <= 3):
        record_audit_event(
            state,
            event_type="corrector_no_retry",
            summary=f"No retry: score={score}, gaps={len(gaps)}, retry_count={retry_count}.",
            severity="info",
            recovery="Proceed to synthesizer.",
        )
        record_decision(
            state,
            stage="corrector",
            decision="No retry needed.",
            reason="Alignment score/gap count is acceptable or retry budget exhausted.",
            next_step="synthesizer",
        )
        state["correction_checked"] = True
        state["retry_requested"] = False
        return state

    topic = state.get("topic", "")
    gap_terms = " ".join(gap_keywords(gaps, limit=8))
    updated = dict(state)
    updated["retry_count"] = retry_count + 1
    updated["search_queries"] = dedupe(
        list(state.get("search_queries", []))
        + [f"{topic} {gap_terms} survey benchmark future work"]
    )[:6]
    record_audit_event(
        updated,
        event_type="corrector_retry",
        summary=f"Added gap-driven query using keywords: {gap_terms}.",
        severity="warning",
        recovery="Run one additional search/evolution/audit loop.",
    )
    record_decision(
        updated,
        stage="corrector",
        decision="Add one gap-driven search query.",
        reason="Alignment score or gap count indicates missing evidence.",
        next_step="searcher_retry",
    )
    updated["correction_checked"] = True
    updated["retry_requested"] = True
    updated["needs_taxonomy_refresh"] = True
    updated["needs_graph_refresh"] = True
    updated["needs_audit_refresh"] = True
    updated.setdefault("logs", []).append("Corrector added one gap-driven search query.")
    return updated
