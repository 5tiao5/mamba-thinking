from __future__ import annotations

from product_agent.api.handlers import ProductApiHandlers
from product_agent.app_container import AppContainer
from product_agent.models import PaperNode
from product_agent.pipeline_utils import initial_state
from product_agent.research_agent.nodes.searcher import (
    _deduplicate_papers_by_title,
    _select_papers_for_analysis,
    searcher_node,
)
from product_agent.schemas import ContinueConversationRequest


def _add_paper(
    container: AppContainer,
    *,
    conversation_id: str,
    title: str,
    status: str,
    year: int = 2025,
):
    document = container.knowledge_service.import_document(
        title=title,
        content=(
            f"[Page 1]\n{title}\nAbstract\n"
            "This paper evaluates tool selection, function calling, and failure recovery. "
            "Introduction The study reports benchmark results."
        ),
        tags=["paper", "tool-use", "evaluation"],
        conversation_id=conversation_id,
        metadata_extra={
            "authors": ["Researcher A", "Researcher B"],
            "year": year,
            "paper_source": "user_upload",
            "import_method": "pdf_upload",
        },
    )
    return container.research_paper_service.add_document(
        conversation_id=conversation_id,
        document=document,
        origin="user_upload",
        status=status,
    )


def test_research_context_materializes_active_papers_and_blocks_excluded_papers() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(
        topic="AI agent tool-use evaluation"
    )
    core = _add_paper(
        container,
        conversation_id=conversation.conversation_id,
        title="Core Tool Use Benchmark",
        status="core",
    )
    candidate = _add_paper(
        container,
        conversation_id=conversation.conversation_id,
        title="Candidate Failure Recovery Study",
        status="candidate",
    )
    excluded = _add_paper(
        container,
        conversation_id=conversation.conversation_id,
        title="Excluded Tool Use Paper",
        status="excluded",
    )
    task = container.research_service.create_task(
        conversation_id=conversation.conversation_id,
        topic="AI agent tool-use evaluation",
        knowledge_scope="conversation_only",
    )

    context = container.research_service._build_research_context(task)

    assert {paper["document_id"] for paper in context.research_papers} == {
        core.document_id,
        candidate.document_id,
    }
    assert {paper["status"] for paper in context.research_papers} == {"core", "candidate"}
    assert excluded.document_id not in {
        hit["document_id"] for hit in context.knowledge_hits
    }


def test_initial_state_seeds_imported_papers_without_running_research() -> None:
    state = initial_state(
        "tool-use evaluation",
        research_context={
            "research_papers": [
                {
                    "paper_id": "imported:core",
                    "document_id": "doc-core",
                    "title": "Core Evaluation Paper",
                    "abstract": "A benchmark for tool-use agents.",
                    "review_text": "Fuller uploaded evidence for taxonomy construction.",
                    "source": "user_upload",
                    "origin": "user_upload",
                    "status": "core",
                },
                {
                    "paper_id": "imported:excluded",
                    "document_id": "doc-excluded",
                    "title": "Excluded Paper",
                    "status": "excluded",
                },
            ]
        },
    )

    assert list(state["evidence_pool"]) == ["imported:core"]
    assert state["evidence_pool"]["imported:core"].paper_pool_status == "core"
    assert state["evidence_pool"]["imported:core"].relevance_tier == "direct"
    assert state["evidence_pool"]["imported:core"].review_text == "Fuller uploaded evidence for taxonomy construction."
    assert "uploaded evidence" in state["review_texts"][0]
    assert state["paper_nodes"] == {}


def test_core_papers_survive_deduplication_and_analysis_limits() -> None:
    papers = {
        f"core-{index}": PaperNode(
            paper_id=f"core-{index}",
            title=f"User Core Paper {index}",
            source="user_upload",
            paper_pool_status="core",
            relevance_tier="direct",
            relevance_score=1.0,
        )
        for index in range(5)
    }
    papers.update(
        {
            f"search-{index}": PaperNode(
                paper_id=f"search-{index}",
                title=f"Retrieved Paper {index}",
                source="arxiv",
                relevance_tier="direct",
                relevance_score=0.9,
            )
            for index in range(5)
        }
    )

    selected = _select_papers_for_analysis(
        papers,
        state={"mode": "fast"},
        max_results=3,
    )

    assert len(selected) == 5
    assert set(selected) == {f"core-{index}" for index in range(5)}

    deduplicated = _deduplicate_papers_by_title(
        {
            "uploaded": PaperNode(
                paper_id="uploaded",
                title="Reliable Tool Use Benchmark",
                source="user_upload",
                paper_pool_status="core",
                document_id="doc-core",
                origin="user_upload",
            ),
            "arxiv": PaperNode(
                paper_id="arxiv",
                title="Reliable Tool-Use Benchmark",
                abstract="A richer abstract from the external index.",
                source="arxiv",
                citation_count=42,
                citation_count_known=True,
            ),
        }
    )

    assert len(deduplicated) == 1
    retained = next(iter(deduplicated.values()))
    assert retained.paper_pool_status == "core"
    assert retained.document_id == "doc-core"
    assert retained.citation_count == 42


def test_hybrid_analysis_keeps_external_search_papers_when_imports_dominate() -> None:
    papers = {
        f"core-{index}": PaperNode(
            paper_id=f"core-{index}",
            title=f"User Imported Causal Paper {index}",
            source="user_upload",
            paper_pool_status="core",
            relevance_tier="direct",
            relevance_score=1.0,
        )
        for index in range(8)
    }
    papers.update(
        {
            "arxiv-causal": PaperNode(
                paper_id="arxiv-causal",
                title="Causal Reasoning with Large Language Models",
                abstract="Causal discovery and counterfactual reasoning with LLMs.",
                source="arxiv",
                relevance_tier="direct",
                relevance_score=0.92,
            ),
            "s2-causal": PaperNode(
                paper_id="s2-causal",
                title="LLM Causal Discovery Benchmarks",
                abstract="Benchmarking causal discovery for large language models.",
                source="semantic_scholar",
                relevance_tier="direct",
                relevance_score=0.9,
            ),
        }
    )

    selected = _select_papers_for_analysis(
        papers,
        state={"mode": "balanced", "research_mode": "hybrid"},
        max_results=8,
    )

    assert "arxiv-causal" in selected
    assert "s2-causal" in selected
    assert all(f"core-{index}" in selected for index in range(8))


def test_follow_up_analysis_reserves_slots_for_new_external_papers() -> None:
    papers = {
        "core-upload": PaperNode(
            paper_id="core-upload",
            title="Uploaded Multimodal Fusion Survey",
            source="user_upload",
            origin="user_upload",
            paper_pool_status="core",
            relevance_tier="direct",
            relevance_score=1.0,
        )
    }
    papers.update(
        {
            f"old-{index}": PaperNode(
                paper_id=f"old-{index}",
                title=f"Previously Selected Fusion Paper {index}",
                source="arxiv",
                relevance_tier="direct",
                relevance_score=0.95 - index * 0.01,
            )
            for index in range(7)
        }
    )
    papers.update(
        {
            f"novel-{index}": PaperNode(
                paper_id=f"novel-{index}",
                title=f"Robot Vision Lightweight Fusion Architecture {index}",
                abstract="A recent robot vision paper about lightweight multimodal fusion architecture.",
                source="arxiv",
                relevance_tier="direct",
                relevance_score=0.72 - index * 0.01,
            )
            for index in range(3)
        }
    )

    selected = _select_papers_for_analysis(
        papers,
        state={
            "topic": "multimodal large language model fusion",
            "mode": "balanced",
            "research_mode": "hybrid",
            "previous_round_paper_ids": ["core-upload", *[f"old-{index}" for index in range(7)]],
            "retrieval_plan": {
                "topic": "multimodal large language model fusion",
                "user_goal": "extend_context",
                "strict_queries": [
                    "multimodal large language model fusion robot vision lightweight fusion architecture"
                ],
                "broad_queries": [],
                "filters": {},
                "rerank_signals": ["robot vision", "lightweight", "fusion architecture"],
            },
        },
        max_results=8,
    )

    assert "core-upload" in selected
    assert len([paper_id for paper_id in selected if paper_id.startswith("novel-")]) >= 2


def test_search_only_excludes_conversation_papers_from_formal_and_rag_context() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(
        topic="AI agent tool-use evaluation"
    )
    imported = _add_paper(
        container,
        conversation_id=conversation.conversation_id,
        title="Imported Benchmark",
        status="core",
    )
    task = container.research_service.create_task(
        conversation_id=conversation.conversation_id,
        topic="AI agent tool-use evaluation",
        knowledge_scope="conversation_only",
        research_mode="search_only",
    )

    context = container.research_service._build_research_context(task)

    assert context.research_mode == "search_only"
    assert context.research_papers == []
    assert imported.document_id not in {
        hit["document_id"] for hit in context.knowledge_hits
    }


def test_search_only_follow_up_hides_imported_papers_from_immediate_context() -> None:
    container = AppContainer(storage_backend="memory")
    conversation = container.conversation_service.create_conversation(
        topic="AI agent tool-use evaluation"
    )
    imported = _add_paper(
        container,
        conversation_id=conversation.conversation_id,
        title="Imported Benchmark",
        status="core",
    )
    handlers = ProductApiHandlers(
        conversation_service=container.conversation_service,
        message_service=container.message_service,
        research_service=container.research_service,
        workspace_service=container.workspace_service,
        tool_service=container.tool_service,
        skill_service=container.skill_service,
        knowledge_service=container.knowledge_service,
        research_paper_service=container.research_paper_service,
    )

    response = handlers.continue_conversation(
        ContinueConversationRequest(
            conversation_id=conversation.conversation_id,
            content="Find more papers about failure recovery.",
            knowledge_scope="conversation_only",
            research_mode="search_only",
        )
    )

    assert response.success is True
    assert response.data["research_mode_applied"] == "search_only"
    assert response.data["follow_up_task"]["research_mode"] == "search_only"
    assert imported.document_id not in {
        hit["document_id"] for hit in response.data["knowledge_hits"]
    }


def test_imported_only_search_skips_tools_and_does_not_add_fallback(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("external retrieval should not run")

    monkeypatch.setattr(
        "product_agent.research_agent.nodes.searcher.search_papers",
        fail_if_called,
    )
    paper = PaperNode(
        paper_id="imported:core",
        title="Imported Tool Use Benchmark",
        abstract="Evaluation of tool selection and failure recovery.",
        source="user_upload",
        paper_pool_status="core",
        relevance_tier="direct",
        relevance_score=1.0,
    )
    result = searcher_node(
        {
            "topic": "AI agent tool-use evaluation",
            "research_mode": "imported_only",
            "mode": "balanced",
            "max_results": 8,
            "evidence_pool": {paper.paper_id: paper},
            "paper_nodes": {},
            "review_texts": [paper.abstract],
            "search_queries": ["agent tool use evaluation"],
            "logs": [],
            "decisions": [],
            "tool_events": [],
            "error_events": [],
        }
    )

    assert list(result["evidence_pool"]) == ["imported:core"]
    assert list(result["paper_nodes"]) == ["imported:core"]
    assert result["retrieval_outcome"]["external_search_skipped"] is True
    assert result["retrieval_outcome"]["fallback_used"] is False


def test_imported_only_without_papers_stays_empty() -> None:
    result = searcher_node(
        {
            "topic": "AI agent tool-use evaluation",
            "research_mode": "imported_only",
            "mode": "balanced",
            "max_results": 8,
            "evidence_pool": {},
            "paper_nodes": {},
            "review_texts": [],
            "search_queries": ["agent tool use evaluation"],
            "logs": [],
            "decisions": [],
            "tool_events": [],
            "error_events": [],
        }
    )

    assert result["evidence_pool"] == {}
    assert result["paper_nodes"] == {}
    assert result["retrieval_outcome"]["fallback_used"] is False
