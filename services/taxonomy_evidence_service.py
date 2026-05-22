from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Sequence

from models import PaperNode


def build_taxonomy_evidence_brief(
    topic: str,
    papers: Sequence[PaperNode],
    review_texts: Iterable[str] | None = None,
) -> str:
    """
    Build an evidence-first brief so taxonomy generation sees:
    1. what papers were actually retrieved
    2. which categories/keywords are repeatedly supported
    3. what evidence is still sparse
    """
    review_texts = list(review_texts or [])
    lines = [f"Research topic: {topic}"]

    if papers:
        category_counter = Counter()
        keyword_counter = Counter()
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

    lines.append(
        "Instruction: build a taxonomy that reflects the available evidence first. "
        "Prefer branches strongly supported by retrieved papers. "
        "Avoid inventing many unsupported branches."
    )
    return "\n".join(lines)
