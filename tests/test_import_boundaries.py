from __future__ import annotations

import ast
from pathlib import Path

from product_agent import models
from product_agent.research_agent.nodes import auditor, planner, searcher


REPO_ROOT = Path(__file__).resolve().parents[1]
BARE_INTERNAL_MODULES = {
    "llm_client",
    "models",
    "observability",
    "pipeline_runtime",
    "pipeline_utils",
    "tools",
}


def test_research_nodes_share_canonical_model_classes() -> None:
    assert auditor.EvolutionEdge is models.EvolutionEdge
    assert planner.ResearchState is models.ResearchState
    assert searcher.PaperNode is models.PaperNode


def test_runtime_code_does_not_use_bare_internal_imports() -> None:
    violations: list[str] = []
    ignored_parts = {".venv", "__pycache__", "node_modules", "tests", "ui"}

    for path in REPO_ROOT.rglob("*.py"):
        if ignored_parts.intersection(path.relative_to(REPO_ROOT).parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                root_module = node.module.split(".", 1)[0]
                if root_module in BARE_INTERNAL_MODULES:
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".", 1)[0]
                    if root_module in BARE_INTERNAL_MODULES:
                        violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert violations == []
