from __future__ import annotations

from product_agent.domain import GapRecord, PaperRecord, ResearchIdeaRecord
from product_agent.schemas import WorkspaceBriefItemView, WorkspaceBriefPaperView
from product_agent.services.workspace_service import (
    _brief_paper_reason,
    _build_research_follow_up_prompts,
    _build_workspace_research_brief,
)


def test_research_brief_explains_progress_evidence_and_next_step(monkeypatch) -> None:
    monkeypatch.setenv("SKIP_RESEARCH_BRIEF_LLM", "1")
    papers = [
        PaperRecord(
            paper_id="paper-core",
            title="Universal Multimodal Retrieval with Large Language Models",
            source="arxiv",
            publish_date="2025-04-10",
            taxonomy_category="Multimodal Retrieval",
            citation_count=88,
            citation_count_known=True,
            relevance_score=0.92,
            relevance_tier="direct",
            relevance_reasons=["直接讨论大模型多模态检索框架。"],
            paper_pool_status="core",
            is_new_this_round=True,
        ),
        PaperRecord(
            paper_id="paper-upload",
            title="Local Notes on Cross-modal Alignment",
            source="user_upload",
            origin="user_upload",
            review_text="This note compares cross-modal alignment failures.",
            relevance_score=0.82,
            relevance_tier="direct",
            paper_pool_status="core",
        ),
    ]
    taxonomy = {
        "branches": [
            {
                "branch_id": "retrieval",
                "name": "大模型多模态检索",
                "description": "用 LLM 改造跨模态查询、对齐和排序。",
                "paper_count": 2,
                "matched_paper_ids": ["paper-core", "paper-upload"],
                "coverage_score": 0.82,
                "evidence_tier": "strong",
            }
        ],
        "coverage": {},
    }
    gaps = [
        GapRecord(
            gap_id="gap-1",
            task_id="task-1",
            summary="缺少对缺失模态鲁棒性的系统验证。",
            supporting_paper_ids=["paper-core"],
            evidence_level="indirect",
        )
    ]
    ideas = [
        ResearchIdeaRecord(
            idea_id="idea-1",
            task_id="task-1",
            title="构建缺失模态鲁棒性评测协议",
            motivation="现有论文主要验证标准场景，失败恢复证据仍薄。",
            approach="比较不同缺失模态比例下的检索稳定性。",
            feasibility="medium",
            contribution="给出更可复现的鲁棒性评测框架。",
            supporting_paper_ids=["paper-core", "paper-upload"],
            evidence_level="indirect",
        )
    ]

    brief = _build_workspace_research_brief(
        mode="task",
        topic="基于大模型的多模态检索",
        task_id="task-1",
        summary="本轮分析共得到论文 2 篇，研究空白 1 条。",
        papers=papers,
        analysis_paper_ids=["paper-core", "paper-upload"],
        taxonomy=taxonomy,
        gaps=gaps,
        ideas=ideas,
        evidence_status={
            "insufficient": False,
            "fallback_paper_count": 0,
            "message": "",
        },
        source_trace=None,
    )

    assert "大模型多模态检索" in brief.executive_summary
    assert "证据骨架由 2 篇核心论文" in brief.executive_summary
    assert "本轮分析共得到" not in brief.executive_summary
    assert "主流路线" in brief.landscape_overview or "当前证据显示主题主要分布" in brief.landscape_overview
    assert "核心论文优先从 2 篇分析池中选择" in brief.evidence_rationale
    assert "下一步优先执行" in brief.decision_advice
    assert brief.must_read_papers
    assert brief.must_read_papers[0].contribution
    assert brief.must_read_papers[0].read_focus
    assert "选择依据" in brief.must_read_papers[0].reason
    assert "引用较高" in brief.must_read_papers[0].reason
    assert "证据依据：1 篇论文" in brief.open_gaps[0].text
    assert "间接证据，需复核" in brief.recommended_next_steps[0].text
    assert brief.recommended_next_steps[0].evidence_level == "indirect"
    assert brief.follow_up_prompts
    assert all("待验证假设" not in prompt and "选择依据" not in prompt for prompt in brief.follow_up_prompts)


def test_research_brief_generates_action_when_no_idea_is_stable(monkeypatch) -> None:
    monkeypatch.setenv("SKIP_RESEARCH_BRIEF_LLM", "1")
    papers = [
        PaperRecord(
            paper_id="paper-core",
            title="Lightweight Multimodal Retrieval Survey",
            source="arxiv",
            relevance_tier="direct",
            paper_pool_status="core",
        )
    ]

    brief = _build_workspace_research_brief(
        mode="task",
        topic="轻量级多模态检索",
        task_id="task-2",
        summary="",
        papers=papers,
        analysis_paper_ids=["paper-core"],
        taxonomy={},
        gaps=[],
        ideas=[],
        evidence_status={
            "insufficient": True,
            "fallback_paper_count": 0,
            "message": "核心分析论文偏少。",
        },
        source_trace=None,
    )

    assert brief.recommended_next_steps
    assert "建议先精读" in brief.recommended_next_steps[0].text
    assert brief.recommended_next_steps[0].evidence_level == "indirect"
    assert any("核心分析论文偏少" in warning for warning in brief.evidence_warnings)


def test_uploaded_must_read_reason_names_local_anchor_and_method_signal() -> None:
    paper = PaperRecord(
        paper_id="uploaded-orchestration",
        title="TokenWeave: Efficient Compute-Communication Overlap for Distributed LLM Inference",
        abstract="",
        review_text="Method. The paper introduces a compute-communication overlap scheduler for distributed LLM inference.",
        source="user_upload",
        origin="user_upload",
        relevance_tier="direct",
        paper_pool_status="core",
        document_id="doc-1",
    )

    reason = _brief_paper_reason(paper)

    assert "用户上传" in reason
    assert "本地阅读上下文" in reason
    assert "通信/计算协同" in reason or "系统编排" in reason
    assert "选择依据" in reason


def test_follow_up_prompts_hide_internal_caveats() -> None:
    prompts = _build_research_follow_up_prompts(
        must_read_papers=[
            WorkspaceBriefPaperView(
                paper_id="paper-1",
                title="Orchestrating Multimodal DNN Workloads in Wireless Neural Processing",
            )
        ],
        open_gaps=[
            WorkspaceBriefItemView(
                text=(
                    "方向“Communication Strategies for Large-Scale Deep Learning”缺少关键概念："
                    "communication overlap。该方向当前缺少分支级直接论文证据，以下内容仅作为待验证假设"
                ),
                evidence_level="indirect",
            )
        ],
        recommended_next_steps=[],
        top_routes=[],
    )

    assert prompts
    assert prompts[0].startswith("补充“Communication Strategies")
    assert "待验证假设" not in prompts[0]
    assert "选择依据" not in prompts[0]
    assert not prompts[0].endswith("commu")
