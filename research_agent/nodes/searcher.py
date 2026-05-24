from __future__ import annotations

import difflib
import os
from typing import Dict, List

from observability import StageTimer, record_decision, record_error_event, record_tool_event
from pipeline_utils import (
    balanced_mode,
    dedupe,
    fallback_papers,
    fast_mode,
    merge_paper,
    select_relevant_papers,
    supplement_balanced_papers,
    supplement_full_mode_papers,
    tool_name,
)
from tools import enrich_paper_references, search_papers, search_semantic_scholar, search_survey_papers

from ..models import PaperNode, ResearchState


def searcher_node(state: ResearchState) -> ResearchState:
    """调用外部检索工具并汇总论文证据。"""

    topic = state.get("topic", "")
    max_results = int(state.get("max_results", 8))
    queries = list(state.get("search_queries") or [topic])
    if fast_mode():
        queries = queries[:1]
    elif balanced_mode():
        queries = queries[:2]

    papers: Dict[str, PaperNode] = dict(state.get("paper_nodes", {}))
    review_texts: List[str] = list(state.get("review_texts", []))
    working = dict(state)
    candidate_pool: List[PaperNode] = []
    semantic_scholar_empty_runs = 0

    for query in queries:
        per_query_limit = max(1, (max_results + max(1, len(queries)) - 1) // max(1, len(queries)))
        tools = (search_papers,) if (fast_mode() or balanced_mode()) else (search_papers, search_semantic_scholar)
        if balanced_mode():
            record_tool_event(
                working,
                tool_name="Semantic Scholar",
                input_summary=query,
                status="skipped",
                note="Balanced mode skips Semantic Scholar to reduce runtime.",
            )

        for tool in tools:
            if tool is search_semantic_scholar and semantic_scholar_empty_runs >= 2:
                record_tool_event(
                    working,
                    tool_name="Semantic Scholar",
                    input_summary=query,
                    status="skipped",
                    note="Skipped after repeated empty Semantic Scholar responses to reduce runtime.",
                )
                continue
            timer = StageTimer()
            try:
                raw_limit = max(per_query_limit, min(max_results, per_query_limit * 3))
                raw_results = list(tool(query, max_results=raw_limit))
                candidate_pool.extend(raw_results)
                results = select_relevant_papers(
                    topic,
                    query,
                    raw_results,
                    limit=per_query_limit,
                    relaxed=balanced_mode(),
                )
                for paper in results:
                    merge_paper(papers, paper)
                record_tool_event(
                    working,
                    tool_name=tool_name(getattr(tool, "__name__", "")),
                    input_summary=query,
                    status="success",
                    output_count=len(results),
                    duration_sec=timer.elapsed(),
                    note=f"raw={len(raw_results)}, filtered={len(results)}",
                )
                if tool is search_semantic_scholar:
                    semantic_scholar_empty_runs = 0 if raw_results else semantic_scholar_empty_runs + 1
            except Exception as exc:
                record_tool_event(
                    working,
                    tool_name=tool_name(getattr(tool, "__name__", "")),
                    input_summary=query,
                    status="failed",
                    duration_sec=timer.elapsed(),
                    note=str(exc),
                )
                record_error_event(
                    working,
                    stage="searcher",
                    error_type=type(exc).__name__,
                    message=str(exc),
                    recovery="Continue with other tools or fallback seed papers.",
                )
                working.setdefault("logs", []).append(f"Search tool failed for '{query}': {exc}")
                if tool is search_semantic_scholar:
                    semantic_scholar_empty_runs = 2

    if not fast_mode() and not balanced_mode():
        timer = StageTimer()
        try:
            raw_surveys = list(search_survey_papers(topic, max_results=6))
            candidate_pool.extend(raw_surveys)
            surveys = select_relevant_papers(
                topic,
                topic,
                raw_surveys,
                limit=3,
                relaxed=balanced_mode(),
            )
            for survey in surveys:
                merge_paper(papers, survey)
                if survey.abstract:
                    review_texts.append(f"{survey.title}\n{survey.abstract}")
            record_tool_event(
                working,
                tool_name="ArXiv survey search",
                input_summary=topic,
                status="success",
                output_count=len(surveys),
                duration_sec=timer.elapsed(),
                note=f"raw={len(raw_surveys)}, filtered={len(surveys)}",
            )
        except Exception as exc:
            record_tool_event(
                working,
                tool_name="ArXiv survey search",
                input_summary=topic,
                status="failed",
                duration_sec=timer.elapsed(),
                note=str(exc),
            )
            record_error_event(
                working,
                stage="searcher",
                error_type=type(exc).__name__,
                message=str(exc),
                recovery="Continue with non-survey paper abstracts.",
            )

    if not papers:
        record_error_event(
            working,
            stage="searcher",
            error_type="NoSearchResults",
            message="All search tools returned no papers.",
            recovery="Use local fallback seed papers so the pipeline can continue.",
        )
        papers = fallback_papers(topic)
    elif balanced_mode():
        target_count = min(max_results, 3)
        before_count = len(papers)
        papers = supplement_balanced_papers(topic, papers, candidate_pool, target_count=target_count)
        if len(papers) > before_count:
            working.setdefault("logs", []).append(
                f"Balanced mode backfilled papers from {before_count} to {len(papers)} for demo stability."
            )
    elif not fast_mode():
        target_count = min(max_results, 6)
        before_count = len(papers)
        papers = supplement_full_mode_papers(topic, papers, candidate_pool, target_count=target_count)
        if len(papers) > before_count:
            working.setdefault("logs", []).append(
                f"Full mode backfilled papers from {before_count} to {len(papers)} to improve coverage."
            )

    if os.environ.get("CITATION_ENRICHMENT") == "1" and not fast_mode() and not balanced_mode() and papers:
        timer = StageTimer()
        enriched_count, linked_references = enrich_paper_references(papers, max_papers=min(6, len(papers)))
        record_tool_event(
            working,
            tool_name="Semantic Scholar citation enrichment",
            input_summary=f"papers={len(papers)}",
            status="success" if enriched_count or linked_references else "skipped",
            output_count=linked_references,
            duration_sec=timer.elapsed(),
            note=f"enriched_papers={enriched_count}",
        )
        if linked_references:
            working.setdefault("logs", []).append(
                f"Citation enrichment linked {linked_references} local references across {enriched_count} papers."
            )

    updated = dict(working)
    updated["paper_nodes"] = papers
    updated["review_texts"] = dedupe(review_texts)
    record_decision(
        updated,
        stage="searcher",
        decision=f"Collected {len(papers)} papers.",
        reason="The agent uses retrieved metadata as evidence for taxonomy and graph construction.",
        next_step="taxonomy",
    )
    # ── Cross-source title deduplication ──────────────────────────────────────
    papers = _deduplicate_papers_by_title(papers)
    working.setdefault("logs", []).append(
        f"Searcher collected {len(papers)} papers after title dedup."
    )

    # ── Source diversity check ───────────────────────────────────────────────
    diversity_report = _source_diversity_report(papers)
    if diversity_report:
        working.setdefault("logs", []).append(diversity_report)

    updated.setdefault("logs", []).append(f"Searcher collected {len(papers)} papers.")
    return updated


# ── Cross-source deduplication helpers ──────────────────────────────────────


def _deduplicate_papers_by_title(
    papers: Dict[str, PaperNode],
    title_similarity_threshold: float = 0.85,
) -> Dict[str, PaperNode]:
    """
    Deduplicate papers across different sources by title similarity.

    When two papers from different sources (e.g., ArXiv and Semantic Scholar)
    have very similar titles but different paper_ids, merge the richer one
    and remove the duplicate.
    """
    if len(papers) < 2:
        return papers

    titles = [(pid, p.title.lower().strip()) for pid, p in papers.items()]
    to_merge: list[tuple[str, str]] = []  # (keep_id, remove_id)

    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            id_i, title_i = titles[i]
            id_j, title_j = titles[j]

            # Quick check: same paper_id → already merged
            if id_i == id_j:
                continue

            # Quick rejection on length ratio (avoid comparing very different titles)
            len_ratio = max(len(title_i), len(title_j)) / max(1, min(len(title_i), len(title_j)))
            if len_ratio > 2.0:
                continue

            similarity = difflib.SequenceMatcher(None, title_i, title_j).ratio()
            if similarity >= title_similarity_threshold:
                # Keep the one with richer metadata
                p_i, p_j = papers[id_i], papers[id_j]
                i_quality = _paper_metadata_quality(p_i)
                j_quality = _paper_metadata_quality(p_j)
                keep, remove = (id_i, id_j) if i_quality >= j_quality else (id_j, id_i)
                to_merge.append((keep, remove))

    removed = set()
    for keep_id, remove_id in to_merge:
        if remove_id in removed or keep_id in removed:
            continue
        # Merge metadata from removed into kept
        keep_paper = papers[keep_id]
        remove_paper = papers[remove_id]

        # Ensure we keep the best abstract
        if not keep_paper.abstract or (remove_paper.abstract and len(remove_paper.abstract) > len(keep_paper.abstract)):
            keep_paper.abstract = remove_paper.abstract

        # Keep higher citation count
        if remove_paper.citation_count > keep_paper.citation_count:
            keep_paper.citation_count = remove_paper.citation_count

        # Merge keywords
        existing_kw = {k.lower() for k in keep_paper.keywords}
        for kw in remove_paper.keywords:
            if kw.lower() not in existing_kw:
                keep_paper.keywords.append(kw)

        # Prefer arxiv or s2 source over seed/fallback
        if keep_paper.source in ("seed", "fallback") and remove_paper.source not in ("seed", "fallback"):
            keep_paper.source = remove_paper.source

        papers[keep_id] = keep_paper
        removed.add(remove_id)

    for remove_id in removed:
        del papers[remove_id]

    return papers


def _paper_metadata_quality(paper: PaperNode) -> int:
    """Score metadata richness (higher = richer)."""
    score = 0
    if paper.abstract:
        score += 2
    if paper.citation_count > 0:
        score += 1
    if paper.keywords:
        score += 1
    if paper.source not in ("seed", "fallback"):
        score += 2
    if paper.url:
        score += 1
    return score


def _source_diversity_report(papers: Dict[str, PaperNode]) -> str:
    """Check source diversity and return a log message if imbalanced."""
    sources: Dict[str, int] = {}
    for p in papers.values():
        src = p.source or "unknown"
        sources[src] = sources.get(src, 0) + 1

    real_sources = {s: c for s, c in sources.items() if s not in ("seed", "fallback")}
    total_real = sum(real_sources.values())
    if total_real == 0:
        return "Source diversity: all papers are seed/fallback."

    details = ", ".join(f"{s}={c}" for s, c in sorted(real_sources.items(), key=lambda x: -x[1]))
    return f"Source diversity: {total_real} real papers ({details})"
