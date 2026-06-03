from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from observability import (  # noqa: E402
    render_demo_dashboard,
    render_demo_summary,
    render_state_timeline,
    render_workflow_mmd,
)
from product_agent.research_agent.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="迭代三重构版科研演进审计 Agent")
    parser.add_argument("topic", help="检索关键词或科研主题，例如：AI Agent Tool Use")
    parser.add_argument("--max-results", type=int, default=10, help="每轮最多检索论文数量")
    parser.add_argument("--output-dir", default="product_agent_outputs", help="输出目录")
    parser.add_argument("--fast", action="store_true", help="快速模式：减少检索并禁用 LLM")
    parser.add_argument("--balanced", action="store_true", help="平衡模式：减少 API 次数但保留部分生成能力")
    parser.add_argument("--no-llm", action="store_true", help="禁用 OpenAI/DeepSeek，使用规则回退")
    parser.add_argument("--quiet", action="store_true", help="不显示终端进度条")
    parser.add_argument("--citation-enrichment", action="store_true", help="尝试补充真实引用关系")
    args = parser.parse_args()

    _apply_mode_flags(args)
    selected_mode = _selected_mode(args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state = run_pipeline(
        args.topic,
        max_results=args.max_results,
        mode=selected_mode,
        show_progress=not args.quiet,
    )
    paths = _write_outputs(state, output_dir)

    print("=" * 72)
    print("重构版 Agent 运行完成")
    print(f"主题: {args.topic}")
    print(f"论文数: {len(state.get('paper_nodes', {}))}")
    print(f"演进边: {len(state.get('evolution_graph', []))}")
    print(f"对齐分数: {state.get('alignment_score', 0)}")
    print(f"报告: {paths['report']}")
    print(f"图谱: {paths['graph']}")
    print(f"状态: {paths['state']}")
    print(f"Timeline: {paths['timeline']}")
    print(f"Workflow: {paths['workflow']}")
    print(f"Demo summary: {paths['demo_summary']}")
    print(f"Demo dashboard: {paths['demo_dashboard']}")
    print("=" * 72)


def _apply_mode_flags(args: argparse.Namespace) -> None:
    if args.fast:
        os.environ["FAST_MODE"] = "1"
        os.environ["DISABLE_LLM"] = "1"
        args.max_results = min(args.max_results, 3)
    if args.balanced:
        os.environ["BALANCED_MODE"] = "1"
        os.environ["SKIP_TAXONOMY_LLM"] = "1"
        os.environ["SKIP_AUDITOR_LLM"] = "1"
        os.environ["SKIP_REPORT_LLM"] = "1"
        os.environ.setdefault("LLM_TIMEOUT", "25")
        args.max_results = min(args.max_results, 4)
    if args.no_llm:
        os.environ["DISABLE_LLM"] = "1"
    if args.citation_enrichment:
        os.environ["CITATION_ENRICHMENT"] = "1"
    if not args.quiet:
        os.environ["SHOW_LIVE_EVENTS"] = "1"


def _selected_mode(args: argparse.Namespace) -> str:
    if args.fast:
        return "fast"
    if args.balanced:
        return "balanced"
    return "default"


def _write_outputs(state: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    report_path = output_dir / "report.md"
    graph_path = output_dir / "graph.mmd"
    state_path = output_dir / "state.json"
    timeline_path = output_dir / "state_timeline.md"
    workflow_path = output_dir / "workflow.mmd"
    demo_summary_path = output_dir / "demo_summary.md"
    demo_dashboard_path = output_dir / "demo_dashboard.html"

    state["state_timeline"] = render_state_timeline(state)
    state["workflow_graph"] = render_workflow_mmd(state)
    state["demo_summary"] = render_demo_summary(state)
    state["demo_dashboard_html"] = render_demo_dashboard(state, live_mode=False)

    report_path.write_text(state.get("final_report", ""), encoding="utf-8")
    graph_path.write_text(state.get("mermaid_graph", ""), encoding="utf-8")
    state_path.write_text(json.dumps(_jsonable(state), ensure_ascii=False, indent=2), encoding="utf-8")
    timeline_path.write_text(state.get("state_timeline", ""), encoding="utf-8")
    workflow_path.write_text(state.get("workflow_graph", ""), encoding="utf-8")
    demo_summary_path.write_text(state.get("demo_summary", ""), encoding="utf-8")
    demo_dashboard_path.write_text(state.get("demo_dashboard_html", ""), encoding="utf-8")
    return {
        "report": report_path,
        "graph": graph_path,
        "state": state_path,
        "timeline": timeline_path,
        "workflow": workflow_path,
        "demo_summary": demo_summary_path,
        "demo_dashboard": demo_dashboard_path,
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    main()
