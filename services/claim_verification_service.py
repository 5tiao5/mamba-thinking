from __future__ import annotations

import re
from dataclasses import dataclass

from product_agent.services.text_cleaning import clean_internal_context_text


_CLAIM_CUES = {
    "problem": (
        "challenge",
        "problem",
        "remain",
        "lack",
        "need",
        "require",
        "address",
        "motivation",
        "问题",
        "挑战",
        "缺少",
        "需要",
        "解决",
    ),
    "method": (
        "propose",
        "present",
        "introduce",
        "method",
        "framework",
        "architecture",
        "model",
        "approach",
        "align",
        "fusion",
        "retrieve",
        "提出",
        "方法",
        "框架",
        "模型",
        "架构",
        "对齐",
        "融合",
        "检索",
    ),
    "evaluation": (
        "experiment",
        "evaluate",
        "benchmark",
        "result",
        "outperform",
        "improve",
        "accuracy",
        "performance",
        "实验",
        "评测",
        "基准",
        "结果",
        "提升",
        "优于",
    ),
    "contribution": (
        "contribution",
        "contribute",
        "show",
        "demonstrate",
        "novel",
        "first",
        "effective",
        "enable",
        "贡献",
        "证明",
        "展示",
        "首次",
        "有效",
    ),
    "limitation": (
        "limitation",
        "limited",
        "future",
        "fail",
        "failure",
        "challenge",
        "robust",
        "uncertainty",
        "局限",
        "限制",
        "未来",
        "失败",
        "鲁棒",
    ),
    "relation": (
        "related",
        "support",
        "category",
        "application",
        "task",
        "topic",
        "方向",
        "支撑",
        "相关",
        "任务",
    ),
}

_SECTION_HINTS = {
    "problem": ("abstract", "introduction", "background", "front matter"),
    "method": ("method", "methodology", "approach", "model", "framework", "system"),
    "evaluation": ("experiment", "evaluation", "result", "benchmark", "analysis"),
    "contribution": ("abstract", "introduction", "conclusion", "discussion"),
    "limitation": ("limitation", "discussion", "conclusion", "future"),
    "relation": ("abstract", "introduction", "method", "conclusion"),
}

_SECTION_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+)?"
    r"(abstract|introduction|background|related work|method(?:ology)?|"
    r"approach|model|framework|system|experiments?|evaluation|results?|"
    r"discussion|limitations?|conclusion|future work|references)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClaimEvidence:
    status: str
    evidence: str
    source_level: str
    section: str
    page: int
    caveat: str
    confidence: float


@dataclass(frozen=True)
class ClaimCandidate:
    claim_type: str
    claim: str
    section: str
    page: int
    score: float


@dataclass(frozen=True)
class _Passage:
    text: str
    page: int
    section: str


def verify_claim_against_full_text(
    *,
    claim_type: str,
    claim: str,
    full_text: str,
    title: str = "",
    category: str = "",
) -> ClaimEvidence | None:
    """Find page/section-aware support for one claim in uploaded or imported text.

    This is intentionally conservative: it only upgrades a claim when a sentence
    in the available full-text slice has lexical overlap with the claim or the
    paper identity plus a claim-type cue. It is not a substitute for human review.
    """

    clean_claim = clean_internal_context_text(claim, max_length=260)
    clean_full_text = str(full_text or "").strip()[:9000]
    if not clean_claim or len(clean_internal_context_text(clean_full_text, max_length=9000)) < 80:
        return None

    passages = _page_section_passages(clean_full_text)
    if not passages:
        return None

    normalized_type = _normalize_claim_type(claim_type)
    claim_tokens = _keywords(f"{clean_claim} {title} {category}")[:18]
    best: tuple[float, _Passage] | None = None
    for passage in passages:
        score = _score_passage(
            passage,
            claim_type=normalized_type,
            claim_tokens=claim_tokens,
        )
        if best is None or score > best[0]:
            best = (score, passage)

    if best is None or best[0] <= 0:
        return None

    score, passage = best
    status = "verified" if score >= 5.0 else "partial"
    section = passage.section or "full_text"
    page_label = f"p.{passage.page}" if passage.page > 0 else "page unknown"
    return ClaimEvidence(
        status=status,
        evidence=clean_internal_context_text(passage.text, max_length=320),
        source_level="full_text",
        section=f"{section} | {page_label}",
        page=passage.page,
        caveat=(
            "正文片段级核查 / 全文片段级核查：系统已在可解析正文中定位到支持片段，"
            "但仍未完成全篇逐 claim 冲突检测和实验数值复核。"
        ),
        confidence=min(round(score / 8.0, 2), 0.98),
    )


def summarize_full_text_verification(full_text: str) -> str:
    passages = _page_section_passages(str(full_text or "").strip()[:9000])
    if not passages:
        return "当前没有可用于全文核查的正文片段。"
    pages = sorted({passage.page for passage in passages if passage.page > 0})
    sections = []
    for passage in passages:
        normalized = passage.section.strip().lower()
        if normalized and normalized not in sections:
            sections.append(normalized)
    page_text = f"{len(pages)} 页" if pages else "页码未知"
    section_text = "、".join(sections[:5]) if sections else "未识别章节"
    return f"已解析 {page_text}正文片段，识别到 {section_text} 等章节线索。"


def extract_full_text_claim_candidates(full_text: str, *, max_candidates: int = 5) -> list[ClaimCandidate]:
    """Extract section-aware candidate claims from uploaded/imported full-text slices.

    The goal is not to summarize the whole paper. It gives Paper Brief a more
    credible backbone: method/evaluation/contribution/limitation claims should
    preferably come from their own sections instead of a single generic abstract.
    """

    passages = _page_section_passages(str(full_text or "").strip()[:12000])
    if not passages:
        return []

    claim_types = [
        ("method_claim", "method"),
        ("evaluation_claim", "evaluation"),
        ("contribution_claim", "contribution"),
        ("limitation_claim", "limitation"),
    ]
    candidates: list[ClaimCandidate] = []
    used_texts: set[str] = set()
    for output_type, normalized_type in claim_types:
        best: tuple[float, _Passage] | None = None
        for passage in passages:
            if _looks_like_reference_or_noise(passage):
                continue
            score = _score_passage(passage, claim_type=normalized_type, claim_tokens=[])
            if best is None or score > best[0]:
                best = (score, passage)
        if best is None:
            continue
        score, passage = best
        if score < 2.0:
            continue
        clean_text = clean_internal_context_text(passage.text, max_length=260)
        normalized_text = clean_text.casefold()
        if not clean_text or normalized_text in used_texts:
            continue
        used_texts.add(normalized_text)
        candidates.append(
            ClaimCandidate(
                claim_type=output_type,
                claim=clean_text,
                section=passage.section,
                page=passage.page,
                score=round(score, 2),
            )
        )
    return candidates[:max_candidates]


def _normalize_claim_type(claim_type: str) -> str:
    normalized = str(claim_type or "").casefold()
    if "method" in normalized:
        return "method"
    if "evaluation" in normalized or "result" in normalized:
        return "evaluation"
    if "contribution" in normalized:
        return "contribution"
    if "limit" in normalized:
        return "limitation"
    if "relation" in normalized or "topic" in normalized:
        return "relation"
    return "problem"


def _page_section_passages(text: str) -> list[_Passage]:
    current_page = 0
    current_section = "Front Matter"
    passages: list[_Passage] = []
    buffer: list[str] = []

    def flush() -> None:
        raw = " ".join(buffer).strip()
        buffer.clear()
        if not raw:
            return
        for sentence in _split_sentences(raw):
            if len(sentence) >= 20:
                passages.append(
                    _Passage(
                        text=sentence,
                        page=current_page,
                        section=current_section,
                    )
                )

    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        page_match = re.fullmatch(r"\[Page\s+(\d{1,4})\]", stripped, flags=re.IGNORECASE)
        if page_match:
            flush()
            current_page = int(page_match.group(1))
            continue
        heading_match = _SECTION_HEADING_RE.fullmatch(stripped)
        if heading_match:
            flush()
            current_section = heading_match.group(1).title()
            continue
        buffer.append(stripped)
    flush()
    return passages


def _split_sentences(text: str) -> list[str]:
    dehyphenated = re.sub(r"(?<=[A-Za-z])-\s+(?=[A-Za-z])", "", str(text or ""))
    parts = re.split(r"(?<=[.!?。！？])\s+", dehyphenated)
    return [clean_internal_context_text(part.strip(), max_length=360) for part in parts if part.strip()]


def _keywords(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}|[\u4e00-\u9fa5]{2,}", str(text or "").casefold())
    stopwords = {
        "this",
        "that",
        "with",
        "from",
        "paper",
        "study",
        "method",
        "current",
        "research",
        "system",
        "model",
        "based",
        "using",
        "用于",
        "当前",
        "论文",
        "研究",
        "系统",
        "方法",
    }
    result = []
    for token in tokens:
        if token in stopwords or token in result:
            continue
        result.append(token)
    return result


def _score_passage(
    passage: _Passage,
    *,
    claim_type: str,
    claim_tokens: list[str],
) -> float:
    normalized = passage.text.casefold()
    token_hits = sum(1 for token in claim_tokens if token and token in normalized)
    cues = _CLAIM_CUES.get(claim_type, ())
    cue_hits = sum(1 for cue in cues if cue in normalized)
    section_bonus = 0.0
    section = passage.section.casefold()
    if any(hint in section for hint in _SECTION_HINTS.get(claim_type, ())):
        section_bonus = 1.4
    length_bonus = 0.5 if 70 <= len(passage.text) <= 300 else 0.0
    return float(token_hits) + min(cue_hits, 2) * 1.2 + section_bonus + length_bonus


def _looks_like_reference_or_noise(passage: _Passage) -> bool:
    section = passage.section.casefold()
    text = passage.text.strip()
    if "reference" in section:
        return True
    if len(text) < 35:
        return True
    if re.fullmatch(r"[\W\d_]+", text):
        return True
    return False
