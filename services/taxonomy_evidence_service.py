from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Sequence

from models import PaperNode

# Research facets used to detect evidence gaps — same facets as query_decomposition
_RESEARCH_FACET_KEYWORDS: dict[str, list[str]] = {
    "methods / core approaches": ["method", "approach", "technique", "algorithm", "model", "architecture", "framework", "planning"],
    "benchmark / evaluation": ["benchmark", "evaluation", "experiment", "metric", "performance", "accuracy", "dataset", "result"],
    "applications / real-world use": ["application", "deployment", "real-world", "industry", "practice", "production", "workflow", "case study"],
    "limitations / failure modes": ["limitation", "challenge", "failure", "issue", "problem", "bottleneck", "gap", "error"],
    "future directions": ["future", "direction", "opportunity", "potential", "trend", "promising", "open problem"],
    "security / safety": ["security", "safety", "threat", "risk", "attack", "robustness", "adversarial", "defense"],
    "human / interaction": ["human", "interaction", "developer", "usability", "trust", "feedback", "control", "collaboration"],
}


def build_taxonomy_evidence_brief(
    topic: str,
    papers: Sequence[PaperNode],
    review_texts: Iterable[str] | None = None,
) -> str:
    review_texts = list(review_texts or [])
    papers = list(papers)
    lines = [f"Research topic: {topic}"]
    total_papers = len(papers)
    seed_count = sum(1 for p in papers if getattr(p, "source", "") in ("seed", "fallback"))
    real_count = total_papers - seed_count

    lines.append(f"Evidence summary: {total_papers} papers total ({real_count} real, {seed_count} seed/fallback).")

    if papers:
        category_counter: Counter = Counter()
        keyword_counter: Counter = Counter()
        category_examples: dict[str, list[str]] = defaultdict(list)

        for paper in papers:
            category = (paper.taxonomy_category or "Uncategorized").strip()
            category_counter[category] += 1
            if len(category_examples[category]) < 3:
                category_examples[category].append(paper.title.strip())
            for keyword in paper.keywords or []:
                keyword_counter[keyword.strip().lower()] += 1

        lines.append("Evidence categories:")
        for category, count in category_counter.most_common():
            examples = "; ".join(category_examples[category])
            lines.append(f"- {category}: {count} papers. Examples: {examples}")

        top_keywords = [keyword for keyword, _ in keyword_counter.most_common(12)]
        if top_keywords:
            lines.append(f"Evidence keywords: {', '.join(top_keywords)}")

        # ── Facet-level evidence gap analysis ──────────────────────────────────
        all_text = " ".join(
            f"{p.title} {p.abstract} {' '.join(p.keywords or [])} {p.taxonomy_category or ''}"
            for p in papers
        ).lower()

        lines.append("Evidence coverage by research facet:")
        unsupported_facets: list[str] = []
        for facet_name, facet_kws in _RESEARCH_FACET_KEYWORDS.items():
            count = sum(
                1 for p in papers
                if any(kw in (p.title + " " + p.abstract).lower() for kw in facet_kws)
            )
            mark = "✓" if count >= 2 else ("⚠" if count == 0 else "○")
            lines.append(f"  {mark} {facet_name}: {count} papers")
            if count == 0:
                unsupported_facets.append(facet_name)

        if unsupported_facets:
            lines.append(f"⚠ Evidence GAPS — no papers for: {', '.join(unsupported_facets)}")

        lines.append("Representative papers:")
        for paper in papers[:8]:
            abstract = " ".join((paper.abstract or "").split())
            abstract_excerpt = abstract[:220]
            keywords = ", ".join((paper.keywords or [])[:6])
            lines.append(
                f"- Title: {paper.title}\n"
                f"  Category: {paper.taxonomy_category or 'Uncategorized'}\n"
                f"  Keywords: {keywords or 'N/A'}\n"
                f"  Abstract: {abstract_excerpt}"
            )
    elif review_texts:
        lines.append("No direct paper evidence was retrieved; fallback to survey/review text.")

    if review_texts:
        lines.append("Survey or review context:")
        for snippet in review_texts[:4]:
            compact = " ".join(str(snippet).split())
            lines.append(f"- {compact[:260]}")

    # ── Stronger anti-invention instruction ────────────────────────────────────
    if total_papers <= 5:
        lines.append(
            f"CRITICAL: Evidence is VERY LIMITED ({total_papers} papers total, "
            f"only {real_count} real). Generate at most 3 taxonomy branches. "
            "Every branch MUST have at least 1 supporting paper."
        )
    elif total_papers <= 10:
        lines.append(
            f"NOTE: Evidence is LIMITED ({total_papers} papers, {real_count} real). "
            "Generate at most 5 taxonomy branches. Every branch should have at least 1 paper."
        )

    lines.append(
        "Instruction: Only create taxonomy branches that have real paper support. "
        "For facets listed above as ⚠ (no evidence), do NOT create branches. "
        "Prefer 3-4 well-supported branches over 6-8 thinly-supported ones. "
        "Mark any speculative branch as [candidate]."
    )
    return "\n".join(lines)
