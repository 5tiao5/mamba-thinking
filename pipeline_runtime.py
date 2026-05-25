from __future__ import annotations

from typing import Any, Dict


def snapshot_counts(state: Dict[str, Any]) -> Dict[str, int]:
    papers = state.get("paper_nodes", {})
    return {
        "papers": len(papers) if isinstance(papers, dict) else len(list(papers)),
        "edges": len(state.get("evolution_graph", [])),
        "gaps": len(state.get("detected_gaps", [])),
        "ideas": len(state.get("generated_ideas", [])),
    }


def record_action_start(state: Dict[str, Any], *, action: str = "") -> None:
    state.setdefault("logs", []).append(f"Action started: {action}")


def apply_post_action_updates(state: Dict[str, Any], action: str = "") -> None:
    """Mark stage-completion flags after a node runs."""
    flags: dict[str, str] = {
        "planner": "",
        "searcher": "",
        "taxonomy": "taxonomy_built",
        "evolution": "graph_built",
        "auditor": "audit_completed",
        "corrector": "",
        "synthesizer": "synthesis_completed",
    }
    flag = flags.get(action)
    if flag:
        state[flag] = True

    # Clear retry_requested after one searcher re-run so controller doesn't loop
    if action == "searcher" and state.get("retry_requested"):
        state["retry_requested"] = False
    # Clear needs_* refresh flags after the corresponding action runs
    if action == "taxonomy":
        state["needs_taxonomy_refresh"] = False
    if action == "evolution":
        state["needs_graph_refresh"] = False
    if action == "auditor":
        state["needs_audit_refresh"] = False


def record_action_observation(
    state: Dict[str, Any],
    *,
    action: str = "",
    before: Dict[str, int] | None = None,
) -> None:
    after = snapshot_counts(state)
    if before:
        deltas = {k: after[k] - before.get(k, 0) for k in after}
        state.setdefault("logs", []).append(
            f"Action {action} complete: {deltas}"
        )


def record_thought(
    state: Dict[str, Any],
    *,
    action: str = "",
    thought: str = "",
    goal: str = "",
    pending: list | None = None,
) -> None:
    state.setdefault("thought_trace", []).append(
        {
            "action": action,
            "thought": thought,
            "goal": goal,
            "pending": pending or [],
        }
    )
