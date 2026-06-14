from __future__ import annotations

from product_agent.domain import GapRecord, PaperRecord, ResearchIdeaRecord, ResearchWorkspace
from product_agent.services import conversation_synthesis_service


def _workspaces() -> list[ResearchWorkspace]:
    return [
        ResearchWorkspace(
            task_id="task-follow-up",
            topic="multimodal fusion robustness",
            summary="The follow-up adds missing-modality evidence.",
            papers=[
                PaperRecord(
                    paper_id="paper-new",
                    title="Robust Multimodal Fusion",
                    relevance_tier="direct",
                )
            ],
            gaps=[
                GapRecord(
                    gap_id="gap_1",
                    task_id="task-follow-up",
                    summary="Cross-dataset robustness remains unclear.",
                )
            ],
            ideas=[
                ResearchIdeaRecord(
                    idea_id="idea_1",
                    task_id="task-follow-up",
                    title="Evaluate missing-modality robustness",
                    motivation="new evidence",
                    approach="benchmark",
                    feasibility="high",
                    contribution="robustness comparison",
                )
            ],
        ),
        ResearchWorkspace(
            task_id="task-initial",
            topic="multimodal fusion",
            summary="The initial round maps fusion architectures.",
            papers=[PaperRecord(paper_id="paper-old", title="Fusion Architecture Survey")],
        ),
    ]


def test_semantic_synthesis_uses_one_bounded_llm_call(monkeypatch) -> None:
    calls = []

    def fake_call(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {
            "headline": "多模态融合研究已从架构梳理推进到鲁棒性验证",
            "summary": "追问补充了缺失模态鲁棒性证据，并形成可执行评测方向。",
            "new_findings": [
                {
                    "text": "缺失模态鲁棒性成为新增重点。",
                    "source_task_ids": ["task-follow-up"],
                    "evidence_ids": ["task-follow-up::idea::idea_1"],
                }
            ],
            "strengthened_findings": [],
            "revised_findings": [],
            "open_questions": [
                {
                    "text": "跨数据集稳定性仍需验证。",
                    "source_task_ids": ["task-follow-up"],
                    "evidence_ids": ["task-follow-up::gap::gap_1"],
                }
            ],
            "current_recommendations": [],
        }

    monkeypatch.setattr(conversation_synthesis_service, "has_openai_key", lambda: True)
    monkeypatch.setattr(conversation_synthesis_service, "call_openai_json", fake_call)
    workspaces = _workspaces()

    result = conversation_synthesis_service.synthesize_conversation_overview(
        topic="multimodal fusion",
        workspaces=workspaces,
        papers=[paper for workspace in workspaces for paper in workspace.papers],
        gaps=workspaces[0].gaps,
        ideas=workspaces[0].ideas,
    )

    assert len(calls) == 1
    assert calls[0][1]["max_output_tokens"] == 900
    assert result["source"] == "llm"
    assert result["new_findings"][0]["source_task_ids"] == ["task-follow-up"]


def test_core_paper_selector_uses_separate_bounded_llm_call(monkeypatch) -> None:
    calls = []

    def fake_call(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return {"paper_ids": ["paper-old", "paper-new", "paper-made-up"]}

    monkeypatch.setattr(conversation_synthesis_service, "has_openai_key", lambda: True)
    monkeypatch.setattr(conversation_synthesis_service, "call_openai_json", fake_call)
    workspaces = _workspaces()

    selected = conversation_synthesis_service.select_conversation_core_paper_ids(
        topic="multimodal fusion",
        workspaces=workspaces,
        papers=[paper for workspace in workspaces for paper in workspace.papers],
    )

    assert selected == ["paper-old", "paper-new"]
    assert len(calls) == 1
    assert calls[0][1]["max_output_tokens"] == 350


def test_semantic_synthesis_rejects_invented_evidence(monkeypatch) -> None:
    monkeypatch.setattr(conversation_synthesis_service, "has_openai_key", lambda: True)
    monkeypatch.setattr(
        conversation_synthesis_service,
        "call_openai_json",
        lambda *args, **kwargs: {
            "headline": "Invented overview",
            "summary": "This response cites evidence that was not provided.",
            "new_findings": [
                {
                    "text": "Unsupported claim",
                    "source_task_ids": ["task-made-up"],
                    "evidence_ids": ["paper::made-up"],
                }
            ],
            "strengthened_findings": [],
            "revised_findings": [],
            "open_questions": [],
            "current_recommendations": [],
        },
    )
    workspaces = _workspaces()

    result = conversation_synthesis_service.synthesize_conversation_overview(
        topic="multimodal fusion",
        workspaces=workspaces,
        papers=[],
        gaps=workspaces[0].gaps,
        ideas=workspaces[0].ideas,
    )

    assert result["source"] == "deterministic"
    assert "2 轮研究" in result["summary"]
