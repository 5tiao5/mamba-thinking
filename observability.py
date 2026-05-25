from __future__ import annotations

import time
from typing import Any, Dict, List


class StageTimer:
    """Context manager that records elapsed wall-clock time."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self._end: float = 0.0

    def __enter__(self) -> StageTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self._end = time.perf_counter()

    def elapsed(self) -> float:
        end = self._end if self._end > 0 else time.perf_counter()
        return round(end - self._start, 4)


def _ensure_list(state: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    if key not in state:
        state[key] = []
    return state[key]


def live_status(message: str) -> None:
    """Lightweight status output for long-running LLM calls."""
    # Print to stderr so it doesn't interfere with pipeline output
    import sys
    print(f"[status] {message}", file=sys.stderr, flush=True)


def record_decision(
    state: Dict[str, Any],
    *,
    stage: str,
    decision: str,
    reason: str = "",
    next_step: str = "",
) -> None:
    _ensure_list(state, "decisions").append(
        {
            "stage": stage,
            "decision": decision,
            "reason": reason,
            "next_step": next_step,
        }
    )


def record_error_event(
    state: Dict[str, Any],
    *,
    stage: str,
    error_type: str = "",
    message: str = "",
    recovery: str = "",
) -> None:
    _ensure_list(state, "error_events").append(
        {
            "stage": stage,
            "error_type": error_type,
            "message": message,
            "recovery": recovery,
        }
    )


def record_tool_event(
    state: Dict[str, Any],
    *,
    tool_name: str = "",
    input_summary: str = "",
    status: str = "",
    output_count: int = 0,
    duration_sec: float = 0.0,
    note: str = "",
) -> None:
    _ensure_list(state, "tool_events").append(
        {
            "tool_name": tool_name,
            "input_summary": input_summary,
            "status": status,
            "output_count": output_count,
            "duration_sec": duration_sec,
            "note": note,
        }
    )


def record_audit_event(
    state: Dict[str, Any],
    *,
    event_type: str = "",
    summary: str = "",
    severity: str = "info",
    recovery: str = "",
) -> None:
    _ensure_list(state, "audit_events").append(
        {
            "event_type": event_type,
            "summary": summary,
            "severity": severity,
            "recovery": recovery,
        }
    )


def record_graph_event(
    state: Dict[str, Any],
    *,
    event_type: str = "",
    source: str = "",
    target: str = "",
    relationship: str = "",
    reason: str = "",
    score: float = 0.0,
) -> None:
    _ensure_list(state, "graph_events").append(
        {
            "event_type": event_type,
            "source": source,
            "target": target,
            "relationship": relationship,
            "reason": reason,
            "score": score,
        }
    )
