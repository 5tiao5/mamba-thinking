from __future__ import annotations

from product_agent.schemas import WorkspacePaperBriefView, WorkspacePaperClaimCheckView
from product_agent.services import paper_brief_llm_service
from product_agent.services.paper_brief_llm_service import enhance_paper_brief_with_llm


def _brief() -> WorkspacePaperBriefView:
    return WorkspacePaperBriefView(
        problem="原始问题描述",
        method="原始方法描述",
        contribution="原始贡献描述",
        limitation="原始局限描述",
        relation_to_topic="原始主题关系",
        why_selected="原始入选原因",
        read_focus="原始阅读重点",
        evidence_basis="原始证据依据",
        verification_boundary="原始验证边界",
        tags=["method", "multimodal"],
        source="abstract+metadata",
        claim_checks=[
            WorkspacePaperClaimCheckView(
                claim_type="method",
                claim="论文提出一种跨模态融合方法。",
                status="partial",
                evidence="摘要提到模型融合视觉和文本表示。",
                source_level="abstract",
                confidence=0.42,
            )
        ],
    )


def test_paper_brief_llm_auto_enabled_outside_pytest_when_key_exists(monkeypatch) -> None:
    paper_brief_llm_service._CACHE.clear()
    brief = _brief()
    monkeypatch.delenv("ENABLE_PAPER_BRIEF_LLM", raising=False)
    monkeypatch.delenv("SKIP_PAPER_BRIEF_LLM", raising=False)
    monkeypatch.delenv("DISABLE_PAPER_BRIEF_LLM", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(paper_brief_llm_service.llm_client, "has_openai_key", lambda: True)
    monkeypatch.setattr(
        paper_brief_llm_service.llm_client,
        "call_openai_json",
        lambda *args, **kwargs: {"read_focus": "优先阅读融合架构、对齐策略和实验边界。"},
    )

    result = enhance_paper_brief_with_llm(
        topic="多模态融合",
        paper_title="Fusion Paper",
        abstract="This paper proposes a multimodal fusion model.",
        review_text="",
        brief=brief,
        selection_factors=["已进入核心分析池"],
    )

    assert result.read_focus == "优先阅读融合架构、对齐策略和实验边界。"


def test_paper_brief_llm_can_be_skipped(monkeypatch) -> None:
    paper_brief_llm_service._CACHE.clear()
    brief = _brief()
    monkeypatch.delenv("ENABLE_PAPER_BRIEF_LLM", raising=False)
    monkeypatch.setenv("SKIP_PAPER_BRIEF_LLM", "1")
    monkeypatch.setattr(paper_brief_llm_service.llm_client, "has_openai_key", lambda: True)

    result = enhance_paper_brief_with_llm(
        topic="多模态融合",
        paper_title="Fusion Paper",
        abstract="This paper proposes a multimodal fusion model.",
        review_text="",
        brief=brief,
        selection_factors=["已进入核心分析池"],
    )

    assert result is brief


def test_paper_brief_llm_updates_text_without_touching_evidence(monkeypatch) -> None:
    paper_brief_llm_service._CACHE.clear()
    brief = _brief()
    monkeypatch.setenv("ENABLE_PAPER_BRIEF_LLM", "1")
    monkeypatch.setattr(paper_brief_llm_service.llm_client, "has_openai_key", lambda: True)
    monkeypatch.setattr(
        paper_brief_llm_service.llm_client,
        "call_openai_json",
        lambda *args, **kwargs: {
            "problem": "这篇论文关注跨模态表示难以稳定对齐的问题。",
            "method": "它围绕融合模块组织视觉与文本表示，适合观察架构设计。",
            "contribution": "主要价值是提供一种可与现有检索或理解任务对照的融合路线。",
            "limitation": "当前仍需要回到原文确认实验设置和适用边界。",
            "relation_to_topic": "可用于支撑多模态融合架构这一分支。",
            "why_selected": "它进入核心池且与主题直接相关，适合作为优先精读对象。",
            "read_focus": "先看融合位置、对齐策略、实验指标和失败案例。",
            "evidence_basis": "判断仅来自摘要、标题、分类和已有 claim checks。",
            "verification_boundary": "当前仍是摘要级判断，不能替代全文复核。",
        },
    )

    result = enhance_paper_brief_with_llm(
        topic="多模态融合",
        paper_title="Fusion Paper",
        abstract="This paper proposes a multimodal fusion model.",
        review_text="",
        brief=brief,
        selection_factors=["已进入核心分析池"],
    )

    assert result is not brief
    assert result.problem.startswith("这篇论文关注")
    assert result.method.startswith("它围绕融合模块")
    assert result.source == "abstract+metadata"
    assert result.tags == ["method", "multimodal"]
    assert result.claim_checks[0].claim == "论文提出一种跨模态融合方法。"


def test_paper_brief_llm_rejects_internal_tokens(monkeypatch) -> None:
    paper_brief_llm_service._CACHE.clear()
    brief = _brief()
    monkeypatch.setenv("ENABLE_PAPER_BRIEF_LLM", "1")
    monkeypatch.setattr(paper_brief_llm_service.llm_client, "has_openai_key", lambda: True)
    monkeypatch.setattr(
        paper_brief_llm_service.llm_client,
        "call_openai_json",
        lambda *args, **kwargs: {
            "problem": "team_process",
            "method": "facd46944e9506d6d5252bac80fd6e28dce7b183",
        },
    )

    result = enhance_paper_brief_with_llm(
        topic="多模态融合",
        paper_title="Fusion Paper",
        abstract="This paper proposes a multimodal fusion model.",
        review_text="",
        brief=brief,
        selection_factors=["已进入核心分析池"],
    )

    assert result is brief
