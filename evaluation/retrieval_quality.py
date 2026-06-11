from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from product_agent.research_agent.nodes.searcher import searcher_node
from product_agent.research_agent.retrieval_plan import build_retrieval_plan


DEFAULT_CASES_PATH = Path(__file__).with_name("retrieval_cases.json")


@dataclass
class CaseResult:
    case_id: str
    topic: str
    passed: bool
    score: float
    real_paper_count: int
    direct_paper_count: int
    adjacent_paper_count: int
    fallback_paper_count: int
    precision_at_k: float
    constraint_pass_rate: float
    landmark_hits: list[str]
    failed_checks: list[str]
    papers: list[dict[str, Any]]
    retrieval_outcome: dict[str, Any]


def load_cases(path: Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_cases(payload)
    return payload


def validate_cases(payload: dict[str, Any]) -> None:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation dataset must contain a non-empty 'cases' list.")

    seen_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in seen_ids:
            raise ValueError(f"Each evaluation case needs a unique id: {case_id!r}")
        seen_ids.add(case_id)
        expectations = case.get("expectations")
        if not isinstance(expectations, dict):
            raise ValueError(f"{case_id}: missing expectations")
        groups = expectations.get("concept_groups")
        if not isinstance(groups, list) or len(groups) < 2:
            raise ValueError(f"{case_id}: at least two concept groups are required")
        for group in groups:
            if not str(group.get("name", "")).strip() or not list(group.get("aliases", []) or []):
                raise ValueError(f"{case_id}: each concept group needs a name and aliases")


def evaluate_case(case: dict[str, Any], *, mode_override: str | None = None) -> CaseResult:
    topic = str(case["topic"])
    mode = mode_override or str(case.get("mode", "balanced"))
    plan = build_retrieval_plan(
        topic=topic,
        query_intent=dict(case.get("query_intent", {}) or {}),
        mode=mode,
    )
    state = searcher_node(
        {
            "topic": topic,
            "mode": mode,
            "max_results": int(case.get("max_results", 8) or 8),
            "query_intent": dict(case.get("query_intent", {}) or {}),
            "retrieval_plan": plan.to_dict(),
            "paper_nodes": {},
            "logs": [],
            "decisions": [],
            "tool_events": [],
            "error_events": [],
        }
    )
    papers = list(state.get("paper_nodes", {}).values())
    expectations = dict(case["expectations"])
    paper_rows = [_paper_evaluation_row(paper, expectations) for paper in papers]

    real_rows = [row for row in paper_rows if row["source"] not in {"seed", "fallback"}]
    direct_count = sum(1 for row in real_rows if row["relevance_tier"] == "direct")
    adjacent_count = sum(1 for row in real_rows if row["relevance_tier"] == "adjacent")
    fallback_count = len(paper_rows) - len(real_rows)
    relevant_count = sum(1 for row in real_rows if row["human_contract_match"])
    precision_at_k = round(relevant_count / len(real_rows), 3) if real_rows else 0.0
    constrained_rows = [row for row in real_rows if row["constraint_applicable"]]
    constraint_pass_rate = (
        round(sum(1 for row in constrained_rows if row["constraint_pass"]) / len(constrained_rows), 3)
        if constrained_rows
        else 1.0
    )
    landmark_hits = _landmark_hits(real_rows, expectations.get("landmark_titles", []))

    failed_checks: list[str] = []
    min_real = int(expectations.get("min_real_papers", 1) or 1)
    min_direct = int(expectations.get("min_direct_papers", 0) or 0)
    min_precision = float(expectations.get("min_precision_at_k", 0.0) or 0.0)
    if len(real_rows) < min_real:
        failed_checks.append(f"real_papers {len(real_rows)} < {min_real}")
    if direct_count < min_direct:
        failed_checks.append(f"direct_papers {direct_count} < {min_direct}")
    if precision_at_k < min_precision:
        failed_checks.append(f"precision_at_k {precision_at_k:.3f} < {min_precision:.3f}")
    if constraint_pass_rate < 1.0:
        failed_checks.append(f"constraint_pass_rate {constraint_pass_rate:.3f} < 1.000")
    forbidden_hits = [
        row["title"]
        for row in real_rows
        if row["forbidden_title_hits"]
    ]
    if forbidden_hits:
        failed_checks.append(f"forbidden title terms matched {len(forbidden_hits)} paper(s)")

    availability_score = min(len(real_rows) / max(min_real, 1), 1.0) * 35
    precision_score = precision_at_k * 35
    direct_score = min(direct_count / max(min_direct, 1), 1.0) * 20 if min_direct else 20
    constraint_score = constraint_pass_rate * 10
    score = round(availability_score + precision_score + direct_score + constraint_score, 1)

    return CaseResult(
        case_id=str(case["id"]),
        topic=topic,
        passed=not failed_checks,
        score=score,
        real_paper_count=len(real_rows),
        direct_paper_count=direct_count,
        adjacent_paper_count=adjacent_count,
        fallback_paper_count=fallback_count,
        precision_at_k=precision_at_k,
        constraint_pass_rate=constraint_pass_rate,
        landmark_hits=landmark_hits,
        failed_checks=failed_checks,
        papers=paper_rows,
        retrieval_outcome=dict(state.get("retrieval_outcome", {}) or {}),
    )


def _paper_evaluation_row(paper: Any, expectations: dict[str, Any]) -> dict[str, Any]:
    title = str(getattr(paper, "title", "") or "")
    abstract = str(getattr(paper, "abstract", "") or "")
    text = _normalize(f"{title} {abstract}")
    matched_groups = [
        str(group["name"])
        for group in expectations.get("concept_groups", [])
        if any(_contains(text, alias) for alias in group.get("aliases", []))
    ]
    required_groups = int(expectations.get("min_concept_groups_per_paper", 2) or 2)
    forbidden_hits = [
        str(term)
        for term in expectations.get("forbidden_title_terms", [])
        if _contains(_normalize(title), str(term))
    ]
    year_range = expectations.get("year_range")
    publish_year = _paper_year(str(getattr(paper, "publish_date", "") or ""))
    constraint_applicable = isinstance(year_range, dict)
    constraint_pass = True
    if constraint_applicable:
        start = int(year_range.get("start_year") or 0)
        end = int(year_range.get("end_year") or 9999)
        constraint_pass = publish_year is not None and start <= publish_year <= end

    return {
        "paper_id": str(getattr(paper, "paper_id", "") or ""),
        "title": title,
        "source": str(getattr(paper, "source", "") or ""),
        "publish_date": str(getattr(paper, "publish_date", "") or ""),
        "relevance_tier": str(getattr(paper, "relevance_tier", "candidate") or "candidate"),
        "relevance_score": float(getattr(paper, "relevance_score", 0.0) or 0.0),
        "matched_concept_groups": matched_groups,
        "human_contract_match": len(matched_groups) >= required_groups and not forbidden_hits,
        "forbidden_title_hits": forbidden_hits,
        "constraint_applicable": constraint_applicable,
        "constraint_pass": constraint_pass,
        "url": str(getattr(paper, "url", "") or ""),
    }


def _landmark_hits(papers: list[dict[str, Any]], landmarks: list[str]) -> list[str]:
    hits: list[str] = []
    for landmark in landmarks:
        if any(_contains(_normalize(paper["title"]), landmark) for paper in papers):
            hits.append(str(landmark))
    return hits


def _paper_year(value: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold().replace("-", " ")).strip()


def _contains(text: str, value: str) -> bool:
    needle = _normalize(value)
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9+#. ]+", needle):
        variants = [needle]
        if not needle.endswith("s"):
            variants.append(f"{needle}s")
        return any(
            re.search(rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])", text) is not None
            for variant in variants
        )
    return needle in text


def write_reports(results: list[CaseResult], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"retrieval-quality-{timestamp}.json"
    markdown_path = output_dir / f"retrieval-quality-{timestamp}.md"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": _summary(results),
        "cases": [asdict(result) for result in results],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(results), encoding="utf-8")
    return json_path, markdown_path


def _summary(results: list[CaseResult]) -> dict[str, Any]:
    passed = sum(1 for result in results if result.passed)
    average_score = round(sum(result.score for result in results) / len(results), 1) if results else 0.0
    average_precision = (
        round(sum(result.precision_at_k for result in results) / len(results), 3)
        if results
        else 0.0
    )
    return {
        "case_count": len(results),
        "passed_count": passed,
        "pass_rate": round(passed / len(results), 3) if results else 0.0,
        "average_score": average_score,
        "average_precision_at_k": average_precision,
    }


def _markdown_report(results: list[CaseResult]) -> str:
    summary = _summary(results)
    lines = [
        "# Retrieval Quality Report",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Passed: {summary['passed_count']}",
        f"- Pass rate: {summary['pass_rate']:.1%}",
        f"- Average score: {summary['average_score']:.1f}",
        f"- Average precision@k: {summary['average_precision_at_k']:.3f}",
        "",
        "| Case | Pass | Score | Real | Direct | Adjacent | Precision@k |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result.case_id} | {'PASS' if result.passed else 'FAIL'} | "
            f"{result.score:.1f} | {result.real_paper_count} | {result.direct_paper_count} | "
            f"{result.adjacent_paper_count} | {result.precision_at_k:.3f} |"
        )
    lines.extend(["", "## Failures", ""])
    for result in results:
        if result.failed_checks:
            lines.append(f"### {result.case_id}")
            lines.extend(f"- {check}" for check in result.failed_checks)
            lines.append("")
    if all(not result.failed_checks for result in results):
        lines.append("No failed checks.")
    return "\n".join(lines).rstrip() + "\n"


def _select_cases(payload: dict[str, Any], case_ids: list[str], limit: int | None) -> list[dict[str, Any]]:
    cases = list(payload["cases"])
    if case_ids:
        requested = set(case_ids)
        cases = [case for case in cases if case["id"] in requested]
        missing = requested - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown case id(s): {', '.join(sorted(missing))}")
    return cases[:limit] if limit else cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Product Agent retrieval quality.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--case", action="append", default=[], help="Run one case id; repeatable.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--mode", choices=["fast", "balanced", "default"], default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "outputs" / "retrieval_eval")
    args = parser.parse_args()

    payload = load_cases(args.cases)
    selected = _select_cases(payload, args.case, args.limit)
    if args.validate_only:
        print(f"Validated {len(selected)} retrieval evaluation case(s).")
        return 0

    os.environ.setdefault("CITATION_ENRICHMENT", "0")
    results: list[CaseResult] = []
    for index, case in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] {case['id']}: {case['topic']}")
        result = evaluate_case(case, mode_override=args.mode)
        results.append(result)
        print(
            f"  {'PASS' if result.passed else 'FAIL'} score={result.score:.1f} "
            f"real={result.real_paper_count} direct={result.direct_paper_count} "
            f"precision@k={result.precision_at_k:.3f}"
        )

    json_path, markdown_path = write_reports(results, args.output_dir)
    summary = _summary(results)
    print(
        f"Completed: {summary['passed_count']}/{summary['case_count']} passed, "
        f"average score={summary['average_score']:.1f}"
    )
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if summary["passed_count"] == summary["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
