from __future__ import annotations

from product_agent.observability import record_audit_event, record_decision
from product_agent.pipeline_utils import (
    balanced_mode,
    dedupe,
    fast_mode,
    gap_keywords,
    repair_min_alignment_gain,
    repair_round_budget,
)

from ..models import ResearchState


def corrector_node(state: ResearchState) -> ResearchState:
    """根据审计结果决定是否追加一次 gap-driven 检索。"""

    retry_count = int(state.get("retry_count", 0))
    max_repair_rounds = repair_round_budget(state)
    evidence_repair_reason = _evidence_repair_reason(state)
    if evidence_repair_reason:
        max_repair_rounds = max(max_repair_rounds, 1)
    if fast_mode(state) or (balanced_mode(state) and not evidence_repair_reason):
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
        state["repair_stop_reason"] = "speed_mode"
        return state

    gaps = state.get("detected_gaps", [])
    score = float(state.get("alignment_score", 0.0))
    repair_result = _evaluate_previous_repair(state, score=score, gap_count=len(gaps))
    if repair_result:
        state.setdefault("repair_history", []).append(repair_result)

    if score >= 0.7 and len(gaps) <= 3 and not evidence_repair_reason:
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
            reason="Alignment score and gap count are acceptable.",
            next_step="synthesizer",
        )
        state["correction_checked"] = True
        state["retry_requested"] = False
        state["repair_stop_reason"] = "quality_acceptable"
        state["repair_baseline"] = {}
        return state

    if repair_result and not repair_result["has_gain"]:
        return _stop_repair(
            state,
            reason="no_gain",
            summary=(
                "Targeted re-search produced no new papers and did not improve "
                "alignment or reduce detected gaps."
            ),
        )

    if retry_count >= max_repair_rounds:
        return _stop_repair(
            state,
            reason="budget_exhausted",
            summary=(
                f"Repair budget exhausted after {retry_count} targeted "
                f"re-search round(s)."
            ),
        )

    topic = state.get("topic", "")
    gap_terms = " ".join(gap_keywords(gaps, limit=8))
    plan = state.get("retrieval_plan", {})
    plan = plan if isinstance(plan, dict) else {}
    repair_focus = _repair_focus_terms(state, plan)
    repair_anchor = str(plan.get("topic_anchor", "") or topic).strip()
    repair_query = " ".join(
        part
        for part in [
            repair_anchor,
            repair_focus,
            "" if evidence_repair_reason else gap_terms,
            "methods datasets metrics",
        ]
        if str(part).strip()
    )
    current_plan = dict(plan)
    current_strict_queries = list(current_plan.get("strict_queries", []) or [])
    current_plan["strict_queries"] = dedupe(
        [repair_query, *current_strict_queries]
    )[:6]
    current_plan["rerank_signals"] = dedupe(
        [*gap_keywords(gaps, limit=6), *list(current_plan.get("rerank_signals", []) or [])]
    )[:8]
    strategy_note = str(current_plan.get("strategy_note", "") or "").strip()
    current_plan["strategy_note"] = "; ".join(
        item for item in [strategy_note, "gap_driven_retry"] if item
    )
    updated = dict(state)
    updated["retry_count"] = retry_count + 1
    updated["max_repair_rounds"] = max_repair_rounds
    updated["repair_baseline"] = {
        "retry_round": retry_count + 1,
        "alignment_score": score,
        "gap_count": len(gaps),
        "paper_ids": sorted(str(paper_id) for paper_id in state.get("paper_nodes", {})),
    }
    updated["retrieval_plan"] = current_plan
    updated["evidence_repair_reason"] = evidence_repair_reason
    updated["search_queries"] = dedupe(
        [repair_query, *list(state.get("search_queries", []))]
    )[:6]
    record_audit_event(
        updated,
        event_type="corrector_retry",
        summary=f"Promoted gap-driven strict query using keywords: {gap_terms}.",
        severity="warning",
        recovery="Run one additional search/evolution/audit loop.",
    )
    record_decision(
        updated,
        stage="corrector",
        decision="Promote one gap-driven query into the retrieval plan.",
        reason="Alignment score or gap count indicates missing evidence.",
        next_step="searcher_retry",
    )
    updated["correction_checked"] = True
    updated["retry_requested"] = True
    updated["needs_taxonomy_refresh"] = True
    updated["needs_graph_refresh"] = True
    updated["needs_audit_refresh"] = True
    updated.setdefault("logs", []).append(
        f"Corrector scheduled repair round {retry_count + 1}/{max_repair_rounds}."
    )
    return updated


def _evidence_repair_reason(state: ResearchState) -> str:
    outcome = state.get("retrieval_outcome", {})
    if not isinstance(outcome, dict):
        outcome = {}
    if (
        int(outcome.get("real_paper_count", 0) or 0) > 0
        and int(outcome.get("direct_paper_count", 0) or 0) == 0
    ):
        return "no_direct_evidence"
    coverage = outcome.get("facet_evidence_coverage", {})
    if not isinstance(coverage, dict):
        coverage = state.get("evidence_coverage", {})
    if isinstance(coverage, dict) and (
        int(coverage.get("missing_count", 0) or 0) > 0
        or int(coverage.get("weak_count", 0) or 0) > 0
        or int(coverage.get("unevaluable_count", 0) or 0) > 0
    ):
        return "required_facets_not_directly_supported"
    return ""


def _repair_focus_terms(
    state: ResearchState,
    retrieval_plan: dict,
) -> str:
    coverage = state.get("evidence_coverage", {})
    labels: list[str] = []
    if isinstance(coverage, dict):
        labels.extend(list(coverage.get("missing_facets", []) or []))
        labels.extend(list(coverage.get("weak_facets", []) or []))
        labels.extend(list(coverage.get("unevaluable_facets", []) or []))
    if not labels:
        labels.extend(list(retrieval_plan.get("rerank_signals", []) or [])[:4])
    return " ".join(dedupe([str(label) for label in labels])[:4])


def _evaluate_previous_repair(
    state: ResearchState,
    *,
    score: float,
    gap_count: int,
) -> dict | None:
    baseline = state.get("repair_baseline", {})
    if not isinstance(baseline, dict) or not baseline:
        return None

    retrieval_outcome = state.get("retrieval_outcome", {})
    if not isinstance(retrieval_outcome, dict):
        retrieval_outcome = {}
    baseline_score = float(baseline.get("alignment_score", 0.0) or 0.0)
    baseline_gap_count = int(baseline.get("gap_count", 0) or 0)
    added_papers = int(retrieval_outcome.get("search_added_paper_count", 0) or 0)
    score_gain = round(score - baseline_score, 4)
    gap_reduction = baseline_gap_count - gap_count
    min_score_gain = repair_min_alignment_gain(state)
    has_gain = added_papers > 0 or score_gain >= min_score_gain or gap_reduction > 0

    return {
        "retry_round": int(baseline.get("retry_round", state.get("retry_count", 0)) or 0),
        "added_paper_count": added_papers,
        "alignment_before": baseline_score,
        "alignment_after": score,
        "alignment_gain": score_gain,
        "gap_count_before": baseline_gap_count,
        "gap_count_after": gap_count,
        "gap_reduction": gap_reduction,
        "has_gain": has_gain,
    }


def _stop_repair(
    state: ResearchState,
    *,
    reason: str,
    summary: str,
) -> ResearchState:
    record_audit_event(
        state,
        event_type=f"corrector_{reason}",
        summary=summary,
        severity="warning",
        recovery="Proceed with synthesis and expose the evidence limitation.",
    )
    record_decision(
        state,
        stage="corrector",
        decision="Stop corrective retrieval and synthesize a degraded result.",
        reason=summary,
        next_step="synthesizer",
    )
    state["correction_checked"] = True
    state["retry_requested"] = False
    state["repair_stop_reason"] = reason
    state["degraded_reason"] = summary
    state["repair_baseline"] = {}
    state.setdefault("logs", []).append(f"Corrector stopped repair: {reason}.")
    return state
