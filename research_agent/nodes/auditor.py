from __future__ import annotations

from auditor import auditor_node as legacy_auditor_node

from ..models import ResearchState


def auditor_node(state: ResearchState) -> ResearchState:
    """兼容旧版 auditor，实现已独立，后续可继续拆为 audit services。"""

    return legacy_auditor_node(state)
