from __future__ import annotations

from typing import Callable, Dict, Tuple

from pipeline_runtime import (
    apply_post_action_updates,
    record_action_observation,
    record_action_start,
    snapshot_counts,
)
from pipeline_utils import ProgressPrinter, progress_summary

from .controller import controller_node
from .models import ResearchState


ActionSpec = Tuple[str, str, Callable[[ResearchState], ResearchState]]


def execute_agent_loop(
    *,
    state: ResearchState,
    action_map: Dict[str, ActionSpec],
    show_progress: bool,
    state_callback: Callable[[ResearchState], None] | None = None,
    max_controller_steps: int = 12,
) -> ResearchState:
    """运行 controller 驱动的多节点循环。"""

    progress = ProgressPrinter(enabled=show_progress)
    for step in range(1, max_controller_steps + 1):
        state = controller_node(state)
        action = state.get("next_action", "finish")
        if action == "finish":
            break

        name, detail, node = action_map[action]
        progress.start(step, max_controller_steps, name, detail)
        before = snapshot_counts(state)
        record_action_start(state, action=action)
        if state_callback:
            state_callback(state)
        state = node(state)
        apply_post_action_updates(state, action)
        record_action_observation(state, action=action, before=before)
        progress.finish(step, max_controller_steps, name, progress_summary(state))
        if state_callback:
            state_callback(state)

    state["run_status"] = "completed"
    if state_callback:
        state_callback(state)
    progress.done()
    return state
