from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

from product_agent.research_agent.models import PaperNode


OVERLAP_THRESHOLD = 0.40
LOW_CONFIDENCE_THRESHOLD = 0.45

IMPROVEMENT_TERMS = {
    "improve",
    "improved",
    "improves",
    "better",
    "enhance",
    "enhanced",
    "extend",
    "extends",
    "solve",
    "address",
}
EVALUATION_TERMS = {
    "experiment",
    "evaluation",
    "benchmark",
    "result",
    "results",
    "accuracy",
    "performance",
    "dataset",
}


@dataclass(frozen=True)
class TaxonomyBranch:
    name: str
    description: str
    required_concepts: Tuple[str, ...]


def canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ").lower()).strip()


def paper_search_text(paper: PaperNode) -> str:
    return canonical(" ".join([paper.title, paper.abstract, paper.taxonomy_category, " ".join(paper.keywords)]))


def keyword_overlap(left: PaperNode, right: PaperNode) -> float:
    left_words = set(left.keywords or re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", paper_search_text(left)))
    right_words = set(right.keywords or re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", paper_search_text(right)))
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


def contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and canonical(phrase) in text
