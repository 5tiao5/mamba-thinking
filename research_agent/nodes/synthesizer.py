from __future__ import annotations

from synthesizer import synthesizer_node as legacy_synthesizer_node

from ..models import ResearchState


def synthesizer_node(state: ResearchState) -> ResearchState:
    """兼容旧版 synthesizer，后续可拆为 report/idea/graph 多服务。"""

    return legacy_synthesizer_node(state)
