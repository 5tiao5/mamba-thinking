from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from rapidfuzz import fuzz

from ..models import PaperNode


@dataclass(frozen=True)
class PaperRelevance:
    score: float
    tier: str
    reasons: list[str]
    matched_groups: list[str]
    expected_groups: list[str]
    topic_score: float
    topic_tier: str
    topic_matched_groups: list[str]
    topic_expected_groups: list[str]


_KNOWN_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "agent",
        (
            "ai agent",
            "ai agents",
            "llm agent",
            "llm agents",
            "language agent",
            "language agents",
            "agentic",
            "autonomous agent",
            "autonomous agents",
            "智能体",
        ),
    ),
    (
        "tool_use",
        (
            "tool use",
            "tool using",
            "tool-using",
            "tool calling",
            "function calling",
            "api calling",
            "api use",
            "tool learning",
            "工具使用",
            "工具调用",
            "函数调用",
        ),
    ),
    (
        "evaluation",
        (
            "benchmark",
            "evaluation",
            "evaluate",
            "assessment",
            "metric",
            "robustness",
            "reliability",
            "failure mode",
            "评测",
            "评估",
            "基准",
            "可靠性",
            "鲁棒性",
        ),
    ),
    (
        "software_engineering",
        (
            "software engineering",
            "software development",
            "code agent",
            "coding agent",
            "repository",
            "program repair",
            "软件工程",
            "代码智能体",
            "代码生成",
        ),
    ),
    (
        "memory",
        (
            "agent memory",
            "episodic memory",
            "long-term memory",
            "working memory",
            "memory augmentation",
            "记忆",
        ),
    ),
    (
        "retrieval",
        (
            "retrieval augmented",
            "retrieval-augmented",
            "rag",
            "document retrieval",
            "knowledge retrieval",
            "检索增强",
            "知识检索",
        ),
    ),
    (
        "methodology",
        (
            "software development methodology",
            "software engineering methodology",
            "development methodology",
            "development process",
            "development lifecycle",
            "methodological framework",
        ),
    ),
    (
        "team_process",
        (
            "agent team",
            "agent teams",
            "multi-agent",
            "multi agent",
            "collaborative agent",
            "development workflow",
            "software workflow",
            "orchestration",
            "collaboration",
        ),
    ),
    (
        "scientific_research",
        (
            "scientific literature",
            "scholarly literature",
            "literature review",
            "literature synthesis",
            "research assistant",
            "research agent",
            "scientific research",
            "scholarly question answering",
        ),
    ),
    (
        "evidence_grounding",
        (
            "evidence citation",
            "evidence-based",
            "evidence grounded",
            "grounded citation",
            "citation attribution",
            "citation system",
            "source attribution",
            "verifiable citation",
            "verifiable citations",
            "citation accuracy",
        ),
    ),
)

_TOPIC_ANCHOR_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "multimodal",
        (
            "multimodal",
            "multi-modal",
            "multi modal",
            "cross-modal",
            "cross modal",
            "vision-language",
            "vision language",
            "audio-visual",
            "audio visual",
        ),
    ),
    (
        "large_language_model",
        (
            "large language model",
            "large language models",
            "llm",
            "llms",
            "multimodal large language model",
            "multimodal large language models",
            "mllm",
            "mllms",
            "vision-language model",
            "vision-language models",
            "vlm",
            "vlms",
        ),
    ),
    (
        "fusion",
        (
            "fusion",
            "fusing",
            "feature integration",
            "data integration",
        ),
    ),
    (
        "causal_reasoning",
        (
            "causal",
            "causality",
            "causal reasoning",
            "causal inference",
            "causal discovery",
            "counterfactual",
            "counterfactual reasoning",
            "causal representation",
            "causal representation learning",
        ),
    ),
)

_FUZZY_MULTI_TOKEN_ALIAS_THRESHOLD = 96
_FUZZY_SINGLE_TOKEN_ALIAS_THRESHOLD = 94
_FUZZY_SINGLE_TOKEN_ALLOWLIST = {
    "benchmark",
    "evaluation",
    "evaluate",
    "robustness",
    "reliability",
}

_GENERIC_STOPWORDS = {
    "agent",
    "agents",
    "ai",
    "llm",
    "language",
    "model",
    "models",
    "paper",
    "papers",
    "research",
    "study",
    "recent",
    "survey",
    "review",
    "method",
    "methods",
    "system",
    "systems",
    "evaluation",
    "benchmark",
    "software",
    "engineering",
    "methodology",
    "methodologies",
    "process",
    "workflow",
    "assistant",
    "scientific",
    "literature",
    "citation",
    "evidence",
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "with",
    "from",
    "to",
    "of",
    "in",
    "on",
    "by",
    "as",
    "at",
    "into",
    "about",
    "around",
}


def evaluate_paper_relevance(
    paper: PaperNode,
    *,
    topic: str,
    query: str,
    retrieval_plan: dict[str, Any] | None = None,
) -> PaperRelevance:
    """Classify a paper only after it passes the independent topic gate."""

    plan = retrieval_plan or {}
    groups = _build_concept_groups(topic=topic, query=query, retrieval_plan=plan)
    title_text = _normalize(" ".join([paper.title, *paper.keywords]))
    abstract_text = _normalize(paper.abstract)

    (
        matched_groups,
        title_matched_groups,
        strengths,
        facet_reasons,
    ) = _match_groups(
        groups,
        title_text=title_text,
        abstract_text=abstract_text,
    )

    group_count = len(groups)
    matched_count = len(matched_groups)
    coverage = matched_count / group_count if group_count else 0.0
    mean_strength = sum(strengths) / group_count if group_count else 0.0
    facet_score = round(min(1.0, coverage * 0.75 + mean_strength * 0.25), 3)
    expected_groups = [name for name, _ in groups]
    direct_anchor_satisfied = _direct_anchor_satisfied(
        expected_groups=expected_groups,
        matched_groups=matched_groups,
        title_matched_groups=title_matched_groups,
    )

    if group_count >= 3:
        facet_tier = (
            "direct"
            if matched_count >= 3 and facet_score >= 0.58 and direct_anchor_satisfied
            else "adjacent"
            if matched_count >= 2
            else "candidate"
        )
    elif group_count == 2:
        facet_tier = (
            "direct"
            if matched_count == 2 and direct_anchor_satisfied
            else "adjacent"
            if matched_count >= 1 and facet_score >= 0.35
            else "candidate"
        )
    else:
        facet_tier = (
            "direct"
            if matched_count == 1
            and facet_score >= 0.55
            and direct_anchor_satisfied
            else "candidate"
        )

    topic_groups = _build_topic_anchor_groups(
        str(plan.get("topic_anchor", "") or plan.get("topic", "") or topic)
    )
    (
        topic_matched_groups,
        _topic_title_matches,
        topic_strengths,
        topic_reasons,
    ) = _match_groups(
        topic_groups,
        title_text=title_text,
        abstract_text=abstract_text,
        reason_prefix="topic:",
    )
    topic_expected_groups = [name for name, _ in topic_groups]
    topic_score, topic_tier = _topic_gate_result(
        expected_count=len(topic_expected_groups),
        matched_count=len(topic_matched_groups),
        strengths=topic_strengths,
    )
    tier = _lower_tier(facet_tier, topic_tier)
    score = round(min(facet_score, topic_score), 3)
    reasons = [
        f"topic_gate:{topic_tier}",
        *topic_reasons,
        *facet_reasons,
    ]

    return PaperRelevance(
        score=score,
        tier=tier,
        reasons=reasons,
        matched_groups=matched_groups,
        expected_groups=expected_groups,
        topic_score=topic_score,
        topic_tier=topic_tier,
        topic_matched_groups=topic_matched_groups,
        topic_expected_groups=topic_expected_groups,
    )


def rank_relevant_papers(
    papers: Iterable[PaperNode],
    *,
    topic: str,
    query: str,
    retrieval_plan: dict[str, Any] | None = None,
    limit: int | None = None,
) -> tuple[list[PaperNode], int]:
    """Return direct evidence first, then adjacent evidence; reject candidates."""

    accepted: list[PaperNode] = []
    rejected_count = 0
    for paper in papers:
        relevance = evaluate_paper_relevance(
            paper,
            topic=topic,
            query=query,
            retrieval_plan=retrieval_plan,
        )
        paper.relevance_score = relevance.score
        paper.relevance_tier = relevance.tier
        paper.relevance_reasons = relevance.reasons
        if relevance.tier == "candidate":
            rejected_count += 1
            continue
        accepted.append(paper)

    accepted.sort(
        key=lambda paper: (
            1 if paper.relevance_tier == "direct" else 0,
            paper.relevance_score,
            paper.citation_count,
        ),
        reverse=True,
    )
    if limit is not None:
        accepted = accepted[: max(1, limit)]
    return accepted, rejected_count


def _build_concept_groups(
    *,
    topic: str,
    query: str,
    retrieval_plan: dict[str, Any],
) -> list[tuple[str, tuple[str, ...]]]:
    signals = [
        str(item).strip()
        for item in list(retrieval_plan.get("rerank_signals", []) or [])
        if str(item).strip()
    ]
    intent_text = _normalize(" ".join([topic, query, *signals]))
    groups: list[tuple[str, tuple[str, ...]]] = []
    covered_signal_tokens: set[str] = set()

    for name, aliases in _KNOWN_GROUPS:
        if _first_matching_alias(intent_text, aliases):
            groups.append((name, aliases))
            covered_signal_tokens.update(_meaningful_tokens(" ".join(aliases)))

    topic_anchor = str(retrieval_plan.get("topic_anchor", "") or topic)
    generic_candidates = _meaningful_tokens(" ".join([*signals, topic_anchor]))
    for token in generic_candidates:
        if token in covered_signal_tokens or any(_contains_alias(token, alias) for _, aliases in groups for alias in aliases):
            continue
        groups.append((f"focus:{token}", (token,)))
        if len(groups) >= 5:
            break

    if not groups:
        fallback_tokens = _meaningful_tokens(" ".join([topic, query]))[:3]
        groups.extend((f"focus:{token}", (token,)) for token in fallback_tokens)
    return groups[:5]


def _build_topic_anchor_groups(
    topic_anchor: str,
) -> list[tuple[str, tuple[str, ...]]]:
    """Turn the stable research topic into a gate independent from facets."""

    normalized_anchor = _normalize(topic_anchor)
    groups: list[tuple[str, tuple[str, ...]]] = []
    covered_tokens: set[str] = set()

    for name, aliases in (*_KNOWN_GROUPS, *_TOPIC_ANCHOR_GROUPS):
        if _first_matching_alias(normalized_anchor, aliases):
            groups.append((name, aliases))
            covered_tokens.update(_meaningful_tokens(" ".join(aliases)))

    if not groups:
        for token in _meaningful_tokens(normalized_anchor):
            if token in covered_tokens:
                continue
            groups.append((f"topic:{token}", (token,)))
            if len(groups) >= 5:
                break

    return groups[:5]


def _match_groups(
    groups: list[tuple[str, tuple[str, ...]]],
    *,
    title_text: str,
    abstract_text: str,
    reason_prefix: str = "",
) -> tuple[list[str], list[str], list[float], list[str]]:
    matched_groups: list[str] = []
    title_matched_groups: list[str] = []
    strengths: list[float] = []
    reasons: list[str] = []
    for group_name, aliases in groups:
        title_alias = _first_matching_text_alias(title_text, aliases)
        abstract_alias = _first_matching_text_alias(abstract_text, aliases)
        if title_alias:
            matched_groups.append(group_name)
            title_matched_groups.append(group_name)
            strengths.append(1.0)
            reasons.append(
                f"{reason_prefix}{group_name}:title:{title_alias}"
            )
        elif abstract_alias:
            matched_groups.append(group_name)
            strengths.append(0.55)
            reasons.append(
                f"{reason_prefix}{group_name}:abstract:{abstract_alias}"
            )
    return matched_groups, title_matched_groups, strengths, reasons


def _topic_gate_result(
    *,
    expected_count: int,
    matched_count: int,
    strengths: list[float],
) -> tuple[float, str]:
    if expected_count == 0:
        return 1.0, "direct"

    coverage = matched_count / expected_count
    mean_strength = sum(strengths) / expected_count
    score = round(min(1.0, coverage * 0.8 + mean_strength * 0.2), 3)

    if expected_count == 1:
        tier = "direct" if matched_count == 1 else "candidate"
    elif expected_count == 2:
        tier = "direct" if matched_count == 2 else "candidate"
    else:
        tier = (
            "direct"
            if coverage >= 0.75 and matched_count >= 3
            else "adjacent"
            if coverage >= 0.5 and matched_count >= 2
            else "candidate"
        )
    return score, tier


def _lower_tier(first: str, second: str) -> str:
    priority = {"candidate": 0, "adjacent": 1, "direct": 2}
    return min((first, second), key=lambda tier: priority.get(tier, 0))


def _direct_anchor_satisfied(
    *,
    expected_groups: list[str],
    matched_groups: list[str],
    title_matched_groups: list[str],
) -> bool:
    """Require the defining concept of narrow product scenarios in the title.

    Abstract-only mentions remain useful neighboring evidence, but they should
    not stop broad query expansion for methodology or research-assistant tasks.
    """

    expected = set(expected_groups)
    matched = set(matched_groups)
    title_matched = set(title_matched_groups)
    if "methodology" in expected:
        return "methodology" in title_matched and "agent" in matched
    if {"team_process", "software_engineering"}.issubset(expected):
        return "team_process" in title_matched and "software_engineering" in matched
    if {"retrieval", "scientific_research"}.issubset(expected):
        return "retrieval" in matched and "scientific_research" in title_matched
    if {"scientific_research", "evidence_grounding"}.issubset(expected):
        return "scientific_research" in title_matched and "evidence_grounding" in matched
    return True


def _meaningful_tokens(text: str) -> list[str]:
    normalized = _normalize(text)
    tokens = re.findall(r"[a-z0-9][a-z0-9+#.-]{2,}|[\u4e00-\u9fff]{2,}", normalized)
    result: list[str] = []
    for token in tokens:
        clean = token.strip(".-")
        if clean in _GENERIC_STOPWORDS or clean.isdigit() or clean in result:
            continue
        result.append(clean)
    return result


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold().replace("_", " ")).strip()


def _first_matching_alias(text: str, aliases: Iterable[str]) -> str:
    for alias in aliases:
        if _contains_alias(text, alias):
            return alias
    return ""


def _first_matching_text_alias(text: str, aliases: Iterable[str]) -> str:
    exact_alias = _first_matching_alias(text, aliases)
    if exact_alias:
        return exact_alias
    for alias in aliases:
        if _fuzzy_contains_alias(text, alias):
            return alias
    return ""


def _contains_alias(text: str, alias: str) -> bool:
    normalized_alias = _normalize(alias).replace("-", " ")
    normalized_text = text.replace("-", " ")
    if not normalized_alias:
        return False
    if re.fullmatch(r"[a-z0-9+#. ]+", normalized_alias):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])"
        return re.search(pattern, normalized_text) is not None
    return normalized_alias in normalized_text


def _fuzzy_contains_alias(text: str, alias: str) -> bool:
    normalized_alias = _normalize(alias).replace("-", " ")
    normalized_text = text.replace("-", " ")
    if not normalized_alias or not normalized_text:
        return False
    if not re.fullmatch(r"[a-z0-9+#. ]+", normalized_alias):
        return False

    alias_tokens = normalized_alias.split()
    if len(alias_tokens) >= 2:
        threshold = _FUZZY_MULTI_TOKEN_ALIAS_THRESHOLD
        score = fuzz.token_set_ratio(normalized_alias, normalized_text)
    elif len(normalized_alias) >= 8 and (
        normalized_alias not in _GENERIC_STOPWORDS
        or normalized_alias in _FUZZY_SINGLE_TOKEN_ALLOWLIST
    ):
        threshold = _FUZZY_SINGLE_TOKEN_ALIAS_THRESHOLD
        score = fuzz.partial_ratio(normalized_alias, normalized_text)
    else:
        return False

    return score >= threshold
