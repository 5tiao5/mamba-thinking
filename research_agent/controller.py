from __future__ import annotations

from .models import ResearchState
from product_agent.observability import record_decision
from product_agent.pipeline_runtime import record_thought


def controller_node(state: ResearchState) -> ResearchState:
    """根据当前全局状态决定下一步动作。"""

    updated = dict(state)
    updated["controller_step"] = int(updated.get("controller_step", 0)) + 1

    if not updated.get("search_queries"):
        action = "planner"
        thought = "The agent has no search plan yet, so it should plan before using tools."
        goal = "Plan subgoals and search strategy."
        pending = ["searcher", "taxonomy", "evolution", "auditor", "corrector", "synthesizer"]
    elif not updated.get("paper_nodes"):
        action = "searcher"
        thought = "Evidence is missing, so the next best action is retrieving papers from external tools."
        goal = "Collect paper evidence."
        pending = ["taxonomy", "evolution", "auditor", "corrector", "synthesizer"]
    elif updated.get("retry_requested"):
        action = "searcher"
        thought = "The audit found gaps, so the agent should run one targeted retrieval round."
        goal = "Repair evidence gaps with focused search."
        pending = ["taxonomy", "evolution", "auditor", "synthesizer"]
    elif not updated.get("taxonomy_built") or updated.get("needs_taxonomy_refresh"):
        action = "taxonomy"
        thought = "The taxonomy baseline is missing or stale, so it should be rebuilt from the current evidence."
        goal = "Build an expert taxonomy."
        pending = ["evolution", "auditor", "corrector", "synthesizer"]
    elif not updated.get("graph_built") or updated.get("needs_graph_refresh"):
        action = "evolution"
        thought = "The paper relationship graph is incomplete, so the next action is graph construction."
        goal = "Infer evolution edges between papers."
        pending = ["auditor", "corrector", "synthesizer"]
    elif not updated.get("audit_completed") or updated.get("needs_audit_refresh"):
        action = "auditor"
        thought = "The agent needs an audit before it can decide whether to stop or repair the run."
        goal = "Audit coverage and graph quality."
        pending = ["corrector", "synthesizer"]
    elif not updated.get("correction_checked"):
        action = "corrector"
        thought = "The current result needs self-reflection to decide whether more evidence is required."
        goal = "Reflect and decide whether to repair."
        pending = ["searcher", "synthesizer"]
    elif not updated.get("synthesis_completed"):
        action = "synthesizer"
        thought = "The evidence and audit are ready, so the agent should synthesize final deliverables."
        goal = "Produce ideas, report, and visual outputs."
        pending = ["finish"]
    else:
        action = "finish"
        thought = "The required outputs already exist, so the agent can stop."
        goal = "Finish the run."
        pending = []

    updated["next_action"] = action
    updated["current_goal"] = goal
    updated["pending_actions"] = pending
    record_thought(updated, action=action, thought=thought, goal=goal, pending=pending)
    record_decision(
        updated,
        stage="controller",
        decision=f"Route to {action}.",
        reason=thought,
        next_step=action,
    )
    return updated
