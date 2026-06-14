from __future__ import annotations

import os
from typing import Any, Callable, Dict

from product_agent.pipeline_utils import initial_state, repair_round_budget

from .models import ResearchState
from .nodes import (
    auditor_node,
    corrector_node,
    evolution_node,
    planner_node,
    searcher_node,
    synthesizer_node,
    taxonomy_node,
)
from .runtime import ActionSpec, execute_agent_loop


def build_action_map() -> Dict[str, ActionSpec]:
    return {
        "planner": ("Planner", "Create a plan, subgoals, and search queries.", planner_node),
        "searcher": ("Searcher", "Use external tools to collect paper evidence.", searcher_node),
        "taxonomy": ("Taxonomy", "Build or refresh the expert taxonomy.", taxonomy_node),
        "evolution": ("Evolution", "Infer or rebuild paper evolution edges.", evolution_node),
        "auditor": ("Auditor", "Audit graph quality and taxonomy coverage.", auditor_node),
        "corrector": ("Corrector", "Reflect and decide whether to repair the run.", corrector_node),
        "synthesizer": ("Synthesizer", "Generate the report, ideas, and Mermaid graph.", synthesizer_node),
    }


def controller_step_budget(state: ResearchState) -> int:
    configured = os.environ.get("AGENT_MAX_CONTROLLER_STEPS", "").strip()
    if configured:
        try:
            return max(1, int(configured))
        except ValueError:
            pass
    return 7 + 5 * repair_round_budget(state)


def run_pipeline(
    topic: str,
    max_results: int = 8,
    *,
    mode: str = "default",
    conversation_workspace_context: list[str] | None = None,
    research_context: dict[str, Any] | None = None,
    show_progress: bool = False,
    state_callback: Callable[[ResearchState], None] | None = None,
) -> ResearchState:
    """重构版主流程入口。"""

    state = initial_state(
        topic,
        max_results,
        mode=mode,
        conversation_workspace_context=conversation_workspace_context,
        research_context=research_context,
    )
    if state_callback:
        state_callback(state)
    return execute_agent_loop(
        state=state,
        action_map=build_action_map(),
        show_progress=show_progress,
        state_callback=state_callback,
        max_controller_steps=controller_step_budget(state),
    )
