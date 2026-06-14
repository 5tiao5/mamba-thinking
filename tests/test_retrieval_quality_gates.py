from __future__ import annotations

from product_agent.research_agent.nodes.corrector import corrector_node
from product_agent.research_agent.nodes.synthesizer import (
    _should_suppress_research_ideas,
)
from product_agent.research_agent.query_expansion import expand_focus_facets
from product_agent.research_agent.retrieval_plan import build_retrieval_plan
from product_agent.services.query_intent import derive_query_intent
from product_agent.services.summary_generation_service import (
    SummaryGenerationInput,
    SummaryGenerationService,
)


TOPIC = "\u5927\u6a21\u578b\u591a\u6a21\u6001\u878d\u5408"
FOLLOW_UP = (
    "\u8fdb\u4e00\u6b65\u8c03\u7814\u5927\u6a21\u578b\u591a\u6a21\u6001\u878d\u5408"
    "\u7684\u8bc4\u6d4b\u65b9\u6cd5\uff0c\u91cd\u70b9\u8865\u5145"
    "\u516c\u5f00\u6570\u636e\u96c6\u3001\u8bc4\u4ef7\u6307\u6807\u548c"
    "\u6d88\u878d\u5b9e\u9a8c\uff0c\u5e76\u6bd4\u8f83 early fusion\u3001"
    "late fusion \u4e0e intermediate fusion \u7684\u6027\u80fd\u548c"
    "\u9002\u7528\u573a\u666f\u3002"
)


def _multimodal_intent():
    return derive_query_intent(
        raw_user_request=FOLLOW_UP,
        task_topic=f"{TOPIC} - {FOLLOW_UP}",
        conversation_topic=TOPIC,
        knowledge_scope="shared",
    )


def test_complex_follow_up_preserves_all_required_dimensions() -> None:
    intent = _multimodal_intent()

    assert [facet["label"] for facet in intent.focus_facets] == [
        "public datasets",
        "evaluation metrics",
        "ablation studies",
        "early fusion",
        "late fusion",
        "intermediate fusion",
    ]
    assert "survey review" not in intent.paper_scope


def test_every_executable_focus_query_keeps_the_multimodal_topic_anchor() -> None:
    intent = _multimodal_intent()
    expanded, outcome = expand_focus_facets(
        query_intent=intent.to_dict(),
        topic=intent.core_topic,
        mode="balanced",
    )
    plan = build_retrieval_plan(
        topic=intent.core_topic,
        query_intent=expanded,
        mode="balanced",
    )

    assert outcome["status"] == "direct"
    assert plan.topic_anchor == "multimodal large language model fusion"
    assert all("LLM agent" not in query for query in plan.strict_queries)
    assert all(plan.topic_anchor in query for query in plan.recall_queries)
    for facet in plan.focus_facets:
        assert plan.topic_anchor in facet["query_candidates"][0]


def test_generic_follow_up_never_invents_an_llm_agent_domain() -> None:
    intent = derive_query_intent(
        raw_user_request=(
            "Compare public datasets, evaluation metrics, and ablation studies."
        ),
        task_topic="quantum error correction",
        conversation_topic="quantum error correction",
        knowledge_scope="conversation",
    )
    plan = build_retrieval_plan(
        topic=intent.core_topic,
        query_intent=intent.to_dict(),
        mode="balanced",
    )

    assert plan.topic_anchor == "quantum error correction"
    assert all("LLM agent" not in query for query in plan.strict_queries)


def test_balanced_mode_repairs_when_no_direct_evidence_exists() -> None:
    updated = corrector_node(
        {
            "topic": TOPIC,
            "mode": "balanced",
            "alignment_score": 0.9,
            "retry_count": 0,
            "detected_gaps": [],
            "retrieval_outcome": {
                "real_paper_count": 18,
                "direct_paper_count": 0,
                "adjacent_paper_count": 18,
            },
            "retrieval_plan": {
                "topic": TOPIC,
                "topic_anchor": "multimodal large language model fusion",
                "strict_queries": [
                    "multimodal large language model fusion evaluation metrics"
                ],
                "rerank_signals": [
                    "evaluation metrics",
                    "ablation studies",
                ],
            },
            "search_queries": [],
            "paper_nodes": {},
            "logs": [],
            "decisions": [],
            "audit_events": [],
        }
    )

    assert updated["retry_requested"] is True
    assert updated.get("repair_stop_reason") != "speed_mode"
    assert updated["evidence_repair_reason"] == "no_direct_evidence"
    assert updated["retrieval_plan"]["strict_queries"][0].startswith(
        "multimodal large language model fusion"
    )


def test_balanced_mode_repairs_when_required_facet_is_adjacent_only() -> None:
    updated = corrector_node(
        {
            "topic": TOPIC,
            "mode": "balanced",
            "alignment_score": 0.9,
            "retry_count": 0,
            "detected_gaps": [],
            "retrieval_outcome": {
                "real_paper_count": 8,
                "direct_paper_count": 3,
                "facet_evidence_coverage": {
                    "missing_count": 0,
                    "weak_count": 1,
                    "unevaluable_count": 0,
                    "weak_facets": ["ablation studies"],
                },
            },
            "retrieval_plan": {
                "topic": TOPIC,
                "topic_anchor": "multimodal large language model fusion",
                "strict_queries": [
                    "multimodal large language model fusion ablation studies"
                ],
                "rerank_signals": ["ablation studies"],
            },
            "evidence_coverage": {
                "missing_count": 0,
                "weak_count": 1,
                "unevaluable_count": 0,
                "weak_facets": ["ablation studies"],
            },
            "search_queries": [],
            "paper_nodes": {},
            "logs": [],
            "decisions": [],
            "audit_events": [],
        }
    )

    assert updated["retry_requested"] is True
    assert (
        updated["evidence_repair_reason"]
        == "required_facets_not_directly_supported"
    )
    assert "ablation studies" in updated["retrieval_plan"]["strict_queries"][0]


def test_balanced_mode_still_skips_optional_repair_when_evidence_is_healthy() -> None:
    updated = corrector_node(
        {
            "topic": TOPIC,
            "mode": "balanced",
            "alignment_score": 0.9,
            "retry_count": 0,
            "detected_gaps": [],
            "retrieval_outcome": {
                "real_paper_count": 8,
                "direct_paper_count": 5,
            },
            "logs": [],
            "decisions": [],
            "audit_events": [],
        }
    )

    assert updated["retry_requested"] is False
    assert updated["repair_stop_reason"] == "speed_mode"


def test_zero_direct_evidence_suppresses_ideas_and_recommendations() -> None:
    state = {
        "retrieval_outcome": {
            "real_paper_count": 18,
            "direct_paper_count": 0,
        }
    }
    assert _should_suppress_research_ideas(state) is True

    output = SummaryGenerationService().run(
        SummaryGenerationInput(
            topic=TOPIC,
            alignment_score=0.7,
            paper_nodes=[],
            detected_gaps=[],
            ideas=[],
            report_text="",
            allow_recommendation=False,
        )
    )
    assert output.source == "deterministic-evidence-limited"
    assert "Direct evidence is insufficient" in output.summary["recommendation"]
