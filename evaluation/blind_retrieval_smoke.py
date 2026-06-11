from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from product_agent.research_agent.nodes.searcher import searcher_node
from product_agent.research_agent.retrieval_plan import build_retrieval_plan


CASES: list[dict[str, Any]] = [
    {
        "name": "中文自然输入",
        "topic": "大模型智能体调用外部工具时为什么容易出错，有哪些评测方法",
        "intent": {
            "core_topic": "LLM agent tool calling failure modes and evaluation",
            "user_goal": "benchmark_evaluation",
            "focus_terms": ["tool calling", "failure modes"],
            "paper_scope": ["evaluation benchmark"],
        },
    },
    {
        "name": "中英混输",
        "topic": "面向软件工程的 multi-agent collaboration workflow",
        "intent": {
            "core_topic": "multi-agent collaboration workflow for software engineering",
            "user_goal": "survey",
            "focus_terms": ["multi-agent collaboration", "workflow"],
            "paper_scope": ["software engineering"],
        },
    },
    {
        "name": "具体科研助手方向",
        "topic": "能自动阅读论文并给出可核验引用的 research agent",
        "intent": {
            "core_topic": "research agent for scientific literature with verifiable citations",
            "user_goal": "survey",
            "focus_terms": ["scientific literature", "verifiable citations"],
            "paper_scope": ["research assistant"],
        },
    },
    {
        "name": "近三年约束",
        "topic": "近三年关于代码智能体仓库级任务评测的论文",
        "intent": {
            "core_topic": "repository-level code agent evaluation",
            "user_goal": "narrow_literature_scope",
            "focus_terms": ["code agent", "repository-level"],
            "paper_scope": ["benchmark evaluation"],
            "time_range": {"start_year": 2024, "end_year": 2026, "strict": True},
        },
    },
    {
        "name": "偏冷门方法论",
        "topic": "AI agent 团队参与软件开发时的生命周期和方法论",
        "intent": {
            "core_topic": "AI agent teams software development lifecycle methodology",
            "user_goal": "extend_context",
            "focus_terms": ["AI agent teams", "development lifecycle"],
            "paper_scope": ["software development methodology"],
        },
    },
]


def main() -> None:
    for index, case in enumerate(CASES, start=1):
        plan = build_retrieval_plan(
            topic=case["topic"],
            query_intent=case["intent"],
            mode="balanced",
        )
        result = searcher_node(
            {
                "topic": case["topic"],
                "mode": "balanced",
                "max_results": 6,
                "query_intent": case["intent"],
                "retrieval_plan": plan.to_dict(),
                "paper_nodes": {},
                "logs": [],
                "decisions": [],
                "tool_events": [],
                "error_events": [],
            }
        )
        outcome = result["retrieval_outcome"]
        evidence_pool = result.get("evidence_pool", result["paper_nodes"])
        print(f"\n[{index}/{len(CASES)}] {case['name']}: {case['topic']}")
        print(f"queries={outcome.get('queries_attempted', [])}")
        print(
            "status={status} pool={pool} analyzed={analyzed} direct={direct} "
            "adjacent={adjacent} fallback={fallback} broad={broad} filtered={filtered}".format(
                status=outcome.get("status"),
                pool=len(evidence_pool),
                analyzed=len(result["paper_nodes"]),
                direct=outcome.get("direct_paper_count"),
                adjacent=outcome.get("adjacent_paper_count"),
                fallback=outcome.get("fallback_paper_count"),
                broad=outcome.get("broad_search_triggered"),
                filtered=outcome.get("low_relevance_filtered_count"),
            )
        )
        for paper in evidence_pool.values():
            print(
                f"- {paper.relevance_tier:<8} {paper.relevance_score:.3f} "
                f"{paper.publish_date[:4]:<4} {paper.title}"
            )


if __name__ == "__main__":
    main()
