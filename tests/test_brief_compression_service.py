from __future__ import annotations

from product_agent.schemas import WorkspaceBriefItemView, WorkspaceBriefPaperView, WorkspaceResearchBriefView
from product_agent.services import brief_compression_service
from product_agent.services.brief_compression_service import compress_research_brief_with_llm


def test_brief_compression_falls_back_without_api_key(monkeypatch) -> None:
    brief = WorkspaceResearchBriefView(
        headline="原始标题",
        executive_summary="原始简报",
        must_read_papers=[WorkspaceBriefPaperView(paper_id="p1", title="Paper One")],
    )
    monkeypatch.setattr(brief_compression_service.llm_client, "has_openai_key", lambda: False)

    result = compress_research_brief_with_llm(topic="topic", brief=brief)

    assert result is brief


def test_brief_compression_updates_text_only(monkeypatch) -> None:
    brief = WorkspaceResearchBriefView(
        headline="旧标题",
        executive_summary="旧简报内容",
        landscape_overview="旧领域格局",
        evidence_rationale="旧证据依据",
        decision_advice="旧建议",
        must_read_papers=[WorkspaceBriefPaperView(paper_id="paper-1", title="Paper One")],
        recommended_next_steps=[
            WorkspaceBriefItemView(text="继续验证", supporting_paper_ids=["paper-1"], evidence_level="indirect")
        ],
        follow_up_prompts=["继续验证 Paper One"],
    )
    monkeypatch.setattr(brief_compression_service.llm_client, "has_openai_key", lambda: True)
    monkeypatch.setattr(
        brief_compression_service.llm_client,
        "call_openai_json",
        lambda *args, **kwargs: {
            "headline": "压缩标题",
            "executive_summary": "压缩后的研究决策简报。",
            "landscape_overview": "压缩后的领域格局。",
            "evidence_rationale": "压缩后的证据依据。",
            "decision_advice": "压缩后的下一步建议。",
            "follow_up_prompts": ["验证核心路线", "补充直接证据"],
        },
    )

    result = compress_research_brief_with_llm(topic="topic", brief=brief)

    assert result.source == "llm_compressed"
    assert result.executive_summary == "压缩后的研究决策简报。"
    assert result.must_read_papers[0].paper_id == "paper-1"
    assert result.recommended_next_steps[0].supporting_paper_ids == ["paper-1"]
    assert result.follow_up_prompts == ["验证核心路线", "补充直接证据"]
