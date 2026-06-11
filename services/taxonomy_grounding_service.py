from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from product_agent.domain import GapRecord, PaperRecord


# ── Evidence tier thresholds ──────────────────────────────────────────────────
# Tunable constants for classifying taxonomy branch evidence strength.
STRONG_PAPER_MIN = 3
STRONG_COVERAGE_MIN = 0.5
MODERATE_COVERAGE_MIN = 0.3


def _compute_evidence_tier(paper_count: int, coverage_score: float) -> str:
    if paper_count <= 0:
        return "candidate"
    if paper_count >= STRONG_PAPER_MIN and coverage_score >= STRONG_COVERAGE_MIN:
        return "strong"
    if coverage_score >= MODERATE_COVERAGE_MIN:
        return "moderate"
    return "weak"


GENERIC_TERMS = {
    "agent",
    "agents",
    "ai",
    "llm",
    "llms",
    "model",
    "models",
    "system",
    "systems",
    "study",
    "studies",
    "research",
    "paper",
    "papers",
    "topic",
    "topics",
}


CHINESE_TERM_HINTS = {
    "评测": "evaluation",
    "评估": "evaluation",
    "基准": "benchmark",
    "指标": "metric",
    "方法": "method",
    "模型": "model",
    "架构": "architecture",
    "规划": "planning",
    "工具": "tool",
    "应用": "application",
    "场景": "application",
    "安全": "security",
    "鲁棒": "robustness",
    "效率": "efficiency",
    "成本": "cost",
    "交互": "interaction",
    "人机": "human",
    "协作": "collaboration",
    "软件": "software",
    "工程": "engineering",
    "记忆": "memory",
    "上下文": "context",
    "审稿": "review",
    "同行评审": "peer review",
}


BRANCH_ALIAS_HINTS = {
    "evaluation": ("benchmark", "metric", "metrics", "efficiency", "robustness", "cost", "performance"),
    "benchmark": ("evaluation", "metric", "dataset", "efficiency", "robustness"),
    "method": ("approach", "algorithm", "architecture", "framework", "planning", "tool use"),
    "methods": ("approach", "algorithm", "architecture", "framework", "planning", "tool use"),
    "architecture": ("planning", "tool use", "module", "framework", "agent workflow"),
    "software": ("repository", "code", "testing", "issue", "review", "development"),
    "engineering": ("repository", "code", "testing", "issue", "review", "development"),
    "interaction": ("human", "feedback", "usability", "trust", "developer"),
    "human": ("interaction", "feedback", "developer", "control", "trust"),
    "application": ("real world", "deployment", "production", "workflow", "industry"),
    "security": ("threat", "risk", "attack", "safety", "robustness"),
    "review": ("peer review", "reviewer", "submission", "paper review"),
}


@dataclass(frozen=True)
class TaxonomyBranchProfile:
    branch_id: str
    name: str
    description: str
    required_concepts: Sequence[str]
    tokens: frozenset[str]
    phrases: tuple[str, ...]


def ground_taxonomy(
    raw_taxonomy: Any,
    papers: List[PaperRecord],
    gaps: List[GapRecord] | None = None,
) -> Dict[str, Any]:
    normalized_input = _unwrap_taxonomy(raw_taxonomy)
    branch_payloads = _normalize_branch_payloads(normalized_input)
    branch_profiles = [_build_branch_profile(payload) for payload in branch_payloads]

    paper_assignments = _assign_papers_to_branches(branch_profiles, papers)
    gap_assignments = _assign_gaps_to_branches(branch_profiles, gaps or [])

    branches: List[Dict[str, Any]] = []
    coverage: Dict[str, Dict[str, Any]] = {}
    tree: List[Dict[str, Any]] = []

    paper_by_id = {p.paper_id: p for p in papers}

    for payload, profile in zip(branch_payloads, branch_profiles):
        matched_paper_ids = paper_assignments.get(profile.branch_id, [])
        matched_gap_ids = gap_assignments.get(profile.branch_id, [])
        paper_count = len(matched_paper_ids)
        gap_count = len(matched_gap_ids)
        coverage_score = _coverage_score(paper_count=paper_count, gap_count=gap_count)
        evidence_tier = _compute_evidence_tier(paper_count, coverage_score)
        branch_confidence = _compute_branch_confidence(
            matched_paper_ids=matched_paper_ids,
            paper_by_id=paper_by_id,
        )

        branches.append(
            {
                "branch_id": profile.branch_id,
                "name": payload["name"],
                "description": payload["description"],
                "required_concepts": list(payload["required_concepts"]),
                "paper_count": paper_count,
                "evidence_tier": evidence_tier,
                "branch_confidence": branch_confidence,
                "matched_paper_ids": matched_paper_ids,
                "matched_gap_ids": matched_gap_ids,
            }
        )
        coverage[profile.branch_id] = {
            "paper_count": paper_count,
            "gap_count": gap_count,
            "coverage_score": coverage_score,
            "evidence_tier": evidence_tier,
            "matched_paper_ids": matched_paper_ids,
            "matched_gap_ids": matched_gap_ids,
        }

    for branch in branches:
        parts = [part.strip() for part in re.split(r"[/>]", branch["name"]) if part.strip()]
        node = {
            "branch_id": branch["branch_id"],
            "name": branch["name"],
            "evidence_tier": branch["evidence_tier"],
            "children": [],
        }
        if not parts:
            tree.append(node)
            continue
        root = next((candidate for candidate in tree if candidate["name"] == parts[0]), None)
        if root is None:
            root = {
                "branch_id": _slug(parts[0]),
                "name": parts[0],
                "evidence_tier": branch["evidence_tier"],
                "children": [],
            }
            tree.append(root)
        if len(parts) > 1:
            root["children"].append(node)
        elif root["branch_id"] != branch["branch_id"]:
            root["children"].append(node)

    return {
        "branches": branches,
        "tree": tree,
        "coverage": coverage,
        "raw": normalized_input,
    }


def assign_papers_to_taxonomy(
    raw_taxonomy: Any,
    papers: Sequence[Any],
) -> Dict[str, List[str]]:
    """Map each paper to grounded expert-taxonomy branch names.

    This lightweight projection is used inside the agent pipeline before graph
    construction. It intentionally preserves the paper's original source
    category, such as ``cs.SE``, in a separate field.
    """
    normalized_input = _unwrap_taxonomy(raw_taxonomy)
    branch_payloads = _normalize_branch_payloads(normalized_input)
    branch_profiles = [_build_branch_profile(payload) for payload in branch_payloads]
    branch_assignments = _assign_papers_to_branches(branch_profiles, papers)
    branch_name_by_id = {
        profile.branch_id: profile.name
        for profile in branch_profiles
    }

    assignments: Dict[str, List[str]] = {
        str(getattr(paper, "paper_id", "")): []
        for paper in papers
        if str(getattr(paper, "paper_id", "")).strip()
    }
    for branch_id, paper_ids in branch_assignments.items():
        branch_name = branch_name_by_id.get(branch_id, branch_id)
        for paper_id in paper_ids:
            assignments.setdefault(paper_id, []).append(branch_name)
    return assignments


def _unwrap_taxonomy(raw_taxonomy: Any) -> Any:
    if isinstance(raw_taxonomy, dict) and "taxonomy" in raw_taxonomy:
        return raw_taxonomy["taxonomy"]
    return raw_taxonomy


def _normalize_branch_payloads(raw_taxonomy: Any) -> List[Dict[str, Any]]:
    branch_payloads: List[Dict[str, Any]] = []
    if isinstance(raw_taxonomy, dict):
        for name, payload in raw_taxonomy.items():
            if isinstance(payload, str):
                payload = {"description": payload}
            elif not isinstance(payload, dict):
                payload = {"description": str(payload)}
            branch_payloads.append(
                {
                    "branch_id": _slug(str(name).strip()),
                    "name": str(name).strip(),
                    "description": str(payload.get("description", "")).strip(),
                    "required_concepts": [
                        str(item).strip() for item in payload.get("required_concepts", []) if str(item).strip()
                    ],
                }
            )
    elif isinstance(raw_taxonomy, list):
        for item in raw_taxonomy:
            branch_name = str(item).strip()
            branch_payloads.append(
                {
                    "branch_id": _slug(branch_name),
                    "name": branch_name,
                    "description": "",
                    "required_concepts": [],
                }
            )
    elif raw_taxonomy:
        branch_name = str(raw_taxonomy).strip()
        branch_payloads.append(
            {
                "branch_id": _slug(branch_name),
                "name": branch_name,
                "description": "",
                "required_concepts": [],
            }
        )
    return branch_payloads


def _build_branch_profile(payload: Dict[str, Any]) -> TaxonomyBranchProfile:
    expanded_required = _expand_branch_aliases(payload)
    phrases = tuple(
        phrase
        for phrase in _unique(
            [
                str(payload["name"]).strip().lower(),
                str(payload["description"]).strip().lower(),
                *[str(item).strip().lower() for item in payload["required_concepts"]],
                *expanded_required,
            ]
        )
        if len(phrase) >= 4
    )
    token_sources = [payload["name"], payload["description"], *payload["required_concepts"], *expanded_required]
    tokens = frozenset(_focused_terms(" ".join(token_sources)))
    return TaxonomyBranchProfile(
        branch_id=payload["branch_id"],
        name=payload["name"],
        description=payload["description"],
        required_concepts=tuple(payload["required_concepts"]),
        tokens=tokens,
        phrases=phrases,
    )


def _assign_papers_to_branches(
    branch_profiles: Sequence[TaxonomyBranchProfile],
    papers: Sequence[PaperRecord],
) -> Dict[str, List[str]]:
    assignments = {profile.branch_id: [] for profile in branch_profiles}
    for paper in papers:
        scored = []
        for profile in branch_profiles:
            score = _paper_branch_score(paper, profile)
            if score > 0:
                scored.append((profile.branch_id, score))
        if not scored:
            continue
        scored.sort(key=lambda item: item[1], reverse=True)
        top_score = scored[0][1]
        min_score = max(0.18, min(0.32, top_score * 0.82))
        if top_score < min_score:
            continue
        selected = [
            branch_id
            for branch_id, score in scored
            if score >= min_score and score >= top_score * 0.72
        ]
        for branch_id in selected:
            assignments[branch_id].append(paper.paper_id)
    return assignments


def _assign_gaps_to_branches(
    branch_profiles: Sequence[TaxonomyBranchProfile],
    gaps: Sequence[GapRecord],
) -> Dict[str, List[str]]:
    assignments = {profile.branch_id: [] for profile in branch_profiles}
    for gap in gaps:
        scored = []
        for profile in branch_profiles:
            score = _gap_branch_score(gap, profile)
            if score > 0:
                scored.append((profile.branch_id, score))
        if not scored:
            continue
        scored.sort(key=lambda item: item[1], reverse=True)
        top_score = scored[0][1]
        selected = [
            branch_id
            for branch_id, score in scored
            if score >= 0.2 and score >= top_score * 0.72
        ]
        for branch_id in selected:
            assignments[branch_id].append(gap.gap_id)
    return assignments


def _paper_branch_score(paper: PaperRecord, profile: TaxonomyBranchProfile) -> float:
    paper_text = " ".join(
        [
            paper.title or "",
            paper.abstract or "",
            " ".join(paper.authors or []),
            " ".join(paper.keywords or []),
            paper.taxonomy_category or "",
        ]
    ).lower()
    paper_tokens = _focused_terms(paper_text)
    title_tokens = _focused_terms(paper.title or "")
    keyword_tokens = _focused_terms(" ".join(paper.keywords or []))
    category_tokens = _focused_terms(paper.taxonomy_category or "")

    shared_tokens = len(profile.tokens & paper_tokens)
    title_hits = len(profile.tokens & title_tokens)
    keyword_hits = len(profile.tokens & keyword_tokens)
    phrase_hits = sum(1 for phrase in profile.phrases if _phrase_match(phrase, paper_text))
    category_hits = len(profile.tokens & category_tokens)

    score = 0.0
    score += shared_tokens * 0.12
    score += title_hits * 0.18
    score += keyword_hits * 0.24
    score += phrase_hits * 0.24
    score += category_hits * 0.12

    if not keyword_hits and any(_phrase_match(phrase, " ".join(paper.keywords or []).lower()) for phrase in profile.phrases):
        score += 0.22
    if not category_hits and profile.name and _phrase_match(profile.name.lower(), (paper.taxonomy_category or "").lower()):
        score += 0.18

    return round(score, 4)


def _gap_branch_score(gap: GapRecord, profile: TaxonomyBranchProfile) -> float:
    gap_text = f"{gap.summary} {' '.join(gap.evidence)}".lower()
    gap_tokens = _focused_terms(gap_text)
    shared_tokens = len(profile.tokens & gap_tokens)
    phrase_hits = sum(1 for phrase in profile.phrases if _phrase_match(phrase, gap_text))
    score = shared_tokens * 0.16 + phrase_hits * 0.28
    return round(score, 4)


def _coverage_score(*, paper_count: int, gap_count: int) -> float:
    if paper_count <= 0 and gap_count <= 0:
        return 0.0
    return round(float(paper_count) / (paper_count + gap_count + 1), 3)


def _compute_branch_confidence(
    *,
    matched_paper_ids: List[str],
    paper_by_id: Dict[str, Any],
) -> float:
    """Confidence in [0,1] factoring paper count, citation counts, and source quality."""
    if not matched_paper_ids:
        return 0.0
    papers = [paper_by_id[pid] for pid in matched_paper_ids if pid in paper_by_id]
    if not papers:
        return 0.0

    paper_count = len(papers)
    citations = [getattr(p, "citation_count", 0) or 0 for p in papers]
    avg_citations = sum(citations) / len(citations) if citations else 0

    real_count = sum(
        1 for p in papers if getattr(p, "source", "") not in ("seed", "fallback")
    )
    real_ratio = real_count / paper_count if paper_count > 0 else 0

    confidence = (
        min(1.0, paper_count * 0.15)
        + min(1.0, avg_citations / 100.0) * 0.30
        + real_ratio * 0.40
    )
    return round(min(1.0, confidence), 3)


def _phrase_match(phrase: str, text: str) -> bool:
    normalized_phrase = _normalize_phrase(phrase)
    if len(normalized_phrase) < 4:
        return False
    return normalized_phrase in _normalize_phrase(text)


def _normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("_", " ").replace("-", " ").lower()).strip()


def _focused_terms(text: str) -> set[str]:
    tokens = set(_terms(text))
    return {token for token in tokens if token not in GENERIC_TERMS}


def _terms(text: str) -> List[str]:
    normalized = _normalize_phrase(text)
    tokens: List[str] = []
    for match in re.findall(r"[a-zA-Z][a-zA-Z0-9]{1,}", normalized):
        token = _normalize_token(match)
        if len(token) >= 3:
            tokens.append(token)
    for chinese_hint, english_token in CHINESE_TERM_HINTS.items():
        if chinese_hint in text:
            tokens.extend(_normalize_phrase(english_token).split(" "))
    return _unique(tokens)


def _expand_branch_aliases(payload: Dict[str, Any]) -> List[str]:
    seed_text = " ".join(
        [
            str(payload.get("name", "")),
            str(payload.get("description", "")),
            *[str(item) for item in payload.get("required_concepts", [])],
        ]
    )
    seed_tokens = _focused_terms(seed_text)
    aliases: List[str] = []
    for token in seed_tokens:
        aliases.extend(BRANCH_ALIAS_HINTS.get(token, ()))
    return _unique(aliases)


def _normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "branch"
