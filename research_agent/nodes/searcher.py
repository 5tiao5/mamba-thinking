from __future__ import annotations

import difflib
import os
from typing import Any, Dict, List

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
from ..retrieval_plan import relevance_query, summarize_retrieval_plan


def searcher_node(state: ResearchState) -> ResearchState:
    """Call retrieval tools and apply retrieval-plan-aware filtering."""

    topic = str(state.get("topic", "") or "")
    max_results = int(state.get("max_results", 8))
    retrieval_plan = _retrieval_plan(state, topic)
    queries = _query_sequence(state, retrieval_plan)
    scoring_query = relevance_query(retrieval_plan, fallback_topic=topic)

    papers: Dict[str, PaperNode] = dict(state.get("paper_nodes", {}))
    review_texts: List[str] = list(state.get("review_texts", []))
    working = dict(state)
    candidate_pool: List[PaperNode] = []
    semantic_scholar_empty_runs = 0
    filtered_out_total = 0
    previous_round_paper_ids = _previous_round_paper_ids(state)
    refresh_triggered = _should_refresh_for_new_evidence(state, retrieval_plan)
    working["retrieval_plan"] = retrieval_plan
    retrieval_outcome = _build_retrieval_outcome(
        retrieval_plan,
        real_paper_count=0,
        total_paper_count=0,
        filtered_out_count=0,
        fallback_used=False,
        refresh_triggered=refresh_triggered,
        novel_paper_count=0,
        reused_paper_count=0,
    )

    for query_spec in queries:
        query = str(query_spec.get("query", "") or "").strip()
        phase = str(query_spec.get("phase", "strict") or "strict")
        if not query:
            continue

        per_query_limit = max(1, (max_results + max(1, len(queries)) - 1) // max(1, len(queries)))
        tools = (search_papers,) if (fast_mode(state) or balanced_mode(state)) else (search_papers, search_semantic_scholar)
        if balanced_mode(state):
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
                filtered_results, filtered_out = _apply_retrieval_filters(raw_results, retrieval_plan)
                filtered_out_total += filtered_out
                candidate_pool.extend(filtered_results)
                results = select_relevant_papers(
                    scoring_query,
                    query,
                    filtered_results,
                    limit=per_query_limit,
                    relaxed=balanced_mode(state),
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
                    note=(
                        f"phase={phase}, raw={len(raw_results)}, post_filter={len(filtered_results)}, "
                        f"selected={len(results)}"
                    ),
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

    if not fast_mode(state) and not balanced_mode(state):
        timer = StageTimer()
        try:
            raw_surveys = list(search_survey_papers(topic, max_results=6))
            filtered_surveys, filtered_out = _apply_retrieval_filters(raw_surveys, retrieval_plan)
            filtered_out_total += filtered_out
            candidate_pool.extend(filtered_surveys)
            surveys = select_relevant_papers(
                scoring_query,
                topic,
                filtered_surveys,
                limit=3,
                relaxed=balanced_mode(state),
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
                note=f"raw={len(raw_surveys)}, post_filter={len(filtered_surveys)}, selected={len(surveys)}",
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

    if filtered_out_total:
        working.setdefault("logs", []).append(
            f"Searcher discarded {filtered_out_total} papers via retrieval-plan filters "
            f"({summarize_retrieval_plan(retrieval_plan) or 'no summary'})."
        )

    hard_constraints = _has_hard_constraints(retrieval_plan)
    if not papers:
        if hard_constraints:
            record_error_event(
                working,
                stage="searcher",
                error_type="ConstrainedNoSearchResults",
                message="No papers satisfied the hard retrieval constraints.",
                recovery="Use fallback background papers only and report that constrained evidence is insufficient.",
            )
            working.setdefault("logs", []).append(
                "Searcher preserved hard constraints instead of padding with off-constraint papers."
            )
        else:
            record_error_event(
                working,
                stage="searcher",
                error_type="NoSearchResults",
                message="All search tools returned no papers.",
                recovery="Use local fallback seed papers so the pipeline can continue.",
            )
        papers = _mark_fallback_background(fallback_papers(topic))
    elif balanced_mode(state):
        target_count = min(max_results, 3)
        before_count = len(papers)
        papers = supplement_balanced_papers(topic, papers, candidate_pool, target_count=target_count)
        if len(papers) > before_count:
            working.setdefault("logs", []).append(
                f"Balanced mode backfilled papers from {before_count} to {len(papers)} for demo stability."
            )
    elif not fast_mode(state):
        target_count = min(max_results, 6)
        before_count = len(papers)
        papers = supplement_full_mode_papers(topic, papers, candidate_pool, target_count=target_count)
        if len(papers) > before_count:
            working.setdefault("logs", []).append(
                f"Full mode backfilled papers from {before_count} to {len(papers)} to improve coverage."
            )

    if refresh_triggered and previous_round_paper_ids:
        before_novel_count = _count_novel_papers(papers, previous_round_paper_ids)
        papers = _prefer_novel_evidence(
            papers,
            candidate_pool,
            previous_round_paper_ids=previous_round_paper_ids,
            scoring_query=scoring_query,
            topic=topic,
            relaxed=balanced_mode(state),
            target_novel_count=1 if (fast_mode(state) or balanced_mode(state)) else 2,
        )
        after_novel_count = _count_novel_papers(papers, previous_round_paper_ids)
        if after_novel_count > before_novel_count:
            working.setdefault("logs", []).append(
                f"Searcher promoted {after_novel_count - before_novel_count} newly retrieved paper(s) for an expansion follow-up."
            )
        else:
            working.setdefault("logs", []).append(
                "Searcher re-ran retrieval for the expansion follow-up, but no stronger new papers displaced the existing evidence."
            )

    if os.environ.get("CITATION_ENRICHMENT") == "1" and not fast_mode(state) and not balanced_mode(state) and papers:
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

    _mark_round_novelty(papers, previous_round_paper_ids)
    before_dedup_count = len(papers)
    papers = _deduplicate_papers_by_title(papers)
    if len(papers) < before_dedup_count:
        working.setdefault("logs", []).append(f"Searcher collected {len(papers)} papers after title dedup.")

    novel_paper_count = _count_novel_papers(papers, previous_round_paper_ids)
    reused_paper_count = max(len(papers) - novel_paper_count, 0) if previous_round_paper_ids else 0
    retrieval_outcome = _build_retrieval_outcome(
        retrieval_plan,
        real_paper_count=_count_real_papers(papers),
        total_paper_count=len(papers),
        filtered_out_count=filtered_out_total,
        fallback_used=_count_fallback_papers(papers) > 0,
        refresh_triggered=refresh_triggered,
        novel_paper_count=novel_paper_count,
        reused_paper_count=reused_paper_count,
    )
    working["retrieval_outcome"] = retrieval_outcome

    updated = dict(working)
    updated["paper_nodes"] = papers
    updated["retrieval_outcome"] = retrieval_outcome
    updated["review_texts"] = dedupe(review_texts)
    record_decision(
        updated,
        stage="searcher",
        decision=f"Collected {len(papers)} papers ({retrieval_outcome.get('status', 'normal')}).",
        reason="The agent uses retrieval-plan-aware evidence for taxonomy and graph construction.",
        next_step="taxonomy",
    )
    diversity_report = _source_diversity_report(papers)
    if diversity_report:
        updated.setdefault("logs", []).append(diversity_report)

    updated.setdefault("logs", []).append(f"Searcher collected {len(papers)} papers.")
    return updated


def _retrieval_plan(state: ResearchState, topic: str) -> dict[str, Any]:
    raw = state.get("retrieval_plan", {}) or {}
    if isinstance(raw, dict) and raw.get("strict_queries"):
        return raw
    fallback_queries = list(state.get("search_queries") or [topic])
    return {
        "topic": topic,
        "user_goal": "follow_up",
        "strict_queries": fallback_queries[:2],
        "broad_queries": fallback_queries[2:],
        "filters": {},
        "rerank_signals": [],
        "strategy_note": "legacy_search_queries",
    }


def _query_sequence(state: ResearchState, retrieval_plan: dict[str, Any]) -> list[dict[str, str]]:
    strict_queries = [str(query).strip() for query in list(retrieval_plan.get("strict_queries", []) or []) if str(query).strip()]
    broad_queries = [str(query).strip() for query in list(retrieval_plan.get("broad_queries", []) or []) if str(query).strip()]

    if fast_mode(state):
        return [{"phase": "strict", "query": query} for query in strict_queries[:1] or broad_queries[:1]]
    if balanced_mode(state):
        queries = [{"phase": "strict", "query": query} for query in strict_queries[:2]]
        if broad_queries:
            queries.append({"phase": "broad", "query": broad_queries[0]})
        return queries
    return [
        *({"phase": "strict", "query": query} for query in strict_queries[:4]),
        *({"phase": "broad", "query": query} for query in broad_queries[:2]),
    ]


def _apply_retrieval_filters(
    papers: list[PaperNode],
    retrieval_plan: dict[str, Any],
) -> tuple[list[PaperNode], int]:
    filters = retrieval_plan.get("filters", {}) if isinstance(retrieval_plan.get("filters"), dict) else {}
    year_range = filters.get("year_range") if isinstance(filters.get("year_range"), dict) else None
    if not year_range:
        return papers, 0

    filtered: list[PaperNode] = []
    filtered_out = 0
    for paper in papers:
        if _matches_year_range(paper, year_range):
            filtered.append(paper)
        else:
            filtered_out += 1
    return filtered, filtered_out


def _has_hard_constraints(retrieval_plan: dict[str, Any]) -> bool:
    filters = retrieval_plan.get("filters", {}) if isinstance(retrieval_plan.get("filters"), dict) else {}
    return bool(filters)


def _count_real_papers(papers: Dict[str, PaperNode]) -> int:
    return sum(1 for paper in papers.values() if (paper.source or "").lower() not in {"seed", "fallback"})


def _count_fallback_papers(papers: Dict[str, PaperNode]) -> int:
    return sum(1 for paper in papers.values() if (paper.source or "").lower() in {"seed", "fallback"})


def _count_novel_papers(papers: Dict[str, PaperNode], previous_round_paper_ids: set[str]) -> int:
    if not previous_round_paper_ids:
        return 0
    return sum(1 for paper in papers.values() if paper.paper_id not in previous_round_paper_ids)


def _mark_fallback_background(papers: Dict[str, PaperNode]) -> Dict[str, PaperNode]:
    normalized: Dict[str, PaperNode] = {}
    for paper_id, paper in papers.items():
        paper.source = "fallback"
        paper.confidence_score = min(float(getattr(paper, "confidence_score", 1.0) or 1.0), 0.25)
        normalized[paper_id] = paper
    return normalized


def _build_retrieval_outcome(
    retrieval_plan: dict[str, Any],
    *,
    real_paper_count: int,
    total_paper_count: int,
    filtered_out_count: int,
    fallback_used: bool,
    refresh_triggered: bool,
    novel_paper_count: int,
    reused_paper_count: int,
) -> dict[str, Any]:
    hard_constraints = _has_hard_constraints(retrieval_plan)
    fallback_paper_count = max(total_paper_count - real_paper_count, 0) if fallback_used else 0
    plan_summary = summarize_retrieval_plan(retrieval_plan)

    status = "normal"
    message = "Retrieved evidence is sufficient for downstream analysis."
    if hard_constraints and real_paper_count == 0:
        status = "constrained_fallback_background"
        message = (
            "Hard retrieval constraints were preserved, but no real papers satisfied them. "
            "Fallback papers are kept as background references only."
        )
    elif hard_constraints and real_paper_count < 3:
        status = "partial_constrained_results"
        message = (
            f"Only {real_paper_count} real papers satisfied the hard constraints. "
            "The system keeps the constrained result set instead of padding with off-constraint papers."
        )
    elif fallback_used:
        status = "fallback_only"
        message = "Search tools returned no usable evidence. Fallback papers are shown as background references."
    elif refresh_triggered and novel_paper_count > 0:
        status = "fresh_evidence_added"
        message = (
            f"This round re-ran retrieval for the updated request and added {novel_paper_count} newly matched paper(s), "
            f"while keeping {reused_paper_count} still-relevant paper(s) from the previous round."
        )
    elif refresh_triggered:
        status = "refresh_reused_only"
        message = (
            "This round did re-run retrieval for the updated request, but the highest-relevance evidence still overlaps "
            "with the previous round and no stronger new papers were found."
        )
    elif filtered_out_count > 0:
        status = "constraint_preserved"
        message = (
            f"Filtered out {filtered_out_count} off-constraint papers and kept {real_paper_count} papers "
            "that better match the user question."
        )

    return {
        "status": status,
        "message": message,
        "hard_constraints": hard_constraints,
        "filtered_out_count": filtered_out_count,
        "real_paper_count": real_paper_count,
        "total_paper_count": total_paper_count,
        "fallback_paper_count": fallback_paper_count,
        "fallback_used": fallback_used,
        "fallback_role": "background_only" if fallback_used else "not_used",
        "refresh_triggered": refresh_triggered,
        "novel_paper_count": novel_paper_count,
        "reused_paper_count": reused_paper_count,
        "retrieval_plan": plan_summary,
    }


def _previous_round_paper_ids(state: ResearchState) -> set[str]:
    return {
        str(paper_id).strip()
        for paper_id in list(state.get("previous_round_paper_ids", []) or [])
        if str(paper_id).strip()
    }


def _should_refresh_for_new_evidence(state: ResearchState, retrieval_plan: dict[str, Any]) -> bool:
    if not _previous_round_paper_ids(state):
        return False
    user_goal = str(retrieval_plan.get("user_goal", "") or state.get("query_intent", {}).get("user_goal", "")).strip()
    if user_goal == "extend_context":
        return True
    current_year_range = _extract_year_range(retrieval_plan.get("filters", {}))
    previous_intent = state.get("previous_round_query_intent", {}) if isinstance(state.get("previous_round_query_intent"), dict) else {}
    previous_year_range = _extract_year_range_from_intent(previous_intent)
    return _is_broader_year_range(current_year_range, previous_year_range)


def _prefer_novel_evidence(
    papers: Dict[str, PaperNode],
    candidate_pool: list[PaperNode],
    *,
    previous_round_paper_ids: set[str],
    scoring_query: str,
    topic: str,
    relaxed: bool,
    target_novel_count: int,
) -> Dict[str, PaperNode]:
    if not papers or not candidate_pool or not previous_round_paper_ids or target_novel_count <= 0:
        return papers
    current_novel_count = _count_novel_papers(papers, previous_round_paper_ids)
    if current_novel_count >= target_novel_count:
        return papers

    candidate_map: Dict[str, PaperNode] = {}
    for paper in candidate_pool:
        paper_id = str(getattr(paper, "paper_id", "") or "").strip()
        if not paper_id or paper_id in previous_round_paper_ids:
            continue
        merge_paper(candidate_map, paper)
    if not candidate_map:
        return papers

    ranked_novel = select_relevant_papers(
        scoring_query,
        topic,
        list(candidate_map.values()),
        limit=max(target_novel_count * 3, target_novel_count),
        relaxed=relaxed,
    )
    if not ranked_novel:
        return papers

    updated = dict(papers)
    for candidate in ranked_novel:
        if _count_novel_papers(updated, previous_round_paper_ids) >= target_novel_count:
            break
        if candidate.paper_id in updated:
            continue
        replacement_id = _weakest_reused_paper_id(updated, previous_round_paper_ids)
        if not replacement_id:
            break
        del updated[replacement_id]
        merge_paper(updated, candidate)
    return updated


def _weakest_reused_paper_id(papers: Dict[str, PaperNode], previous_round_paper_ids: set[str]) -> str | None:
    reused = [paper for paper in papers.values() if paper.paper_id in previous_round_paper_ids]
    if not reused:
        return None
    weakest = min(reused, key=_replacement_priority)
    return weakest.paper_id


def _replacement_priority(paper: PaperNode) -> tuple[float, int, int]:
    source = str(getattr(paper, "source", "") or "").lower()
    source_penalty = 0 if source in {"seed", "fallback"} else 1
    confidence = float(getattr(paper, "confidence_score", 0.0) or 0.0)
    year = _paper_year(getattr(paper, "publish_date", "")) or 0
    return (source_penalty, confidence + (paper.citation_count / 1000.0), year)


def _mark_round_novelty(papers: Dict[str, PaperNode], previous_round_paper_ids: set[str]) -> None:
    for paper in papers.values():
        paper.is_new_this_round = bool(previous_round_paper_ids) and paper.paper_id not in previous_round_paper_ids


def _extract_year_range(filters: dict[str, Any]) -> tuple[int | None, int | None]:
    year_range = filters.get("year_range") if isinstance(filters.get("year_range"), dict) else {}
    return _as_year(year_range.get("start_year")), _as_year(year_range.get("end_year"))


def _extract_year_range_from_intent(intent: dict[str, Any]) -> tuple[int | None, int | None]:
    time_range = intent.get("time_range") if isinstance(intent.get("time_range"), dict) else {}
    return _as_year(time_range.get("start_year")), _as_year(time_range.get("end_year"))


def _is_broader_year_range(
    current_year_range: tuple[int | None, int | None],
    previous_year_range: tuple[int | None, int | None],
) -> bool:
    current_start, current_end = current_year_range
    previous_start, previous_end = previous_year_range
    if current_start is None and previous_start is None and current_end is None and previous_end is None:
        return False
    broadened_start = previous_start is not None and (current_start is None or current_start < previous_start)
    broadened_end = previous_end is not None and (current_end is None or current_end > previous_end)
    return broadened_start or broadened_end


def _matches_year_range(paper: PaperNode, year_range: dict[str, Any]) -> bool:
    start_year = _as_year(year_range.get("start_year"))
    end_year = _as_year(year_range.get("end_year"))
    publish_year = _paper_year(paper.publish_date)
    if publish_year is None:
        return not bool(year_range.get("strict", True))
    if start_year is not None and publish_year < start_year:
        return False
    if end_year is not None and publish_year > end_year:
        return False
    return True


def _paper_year(publish_date: str) -> int | None:
    year = str(publish_date or "")[:4]
    if year.isdigit():
        return int(year)
    return None


def _as_year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.isdigit() and len(text) == 4:
        return int(text)
    return None


def _deduplicate_papers_by_title(
    papers: Dict[str, PaperNode],
    title_similarity_threshold: float = 0.85,
) -> Dict[str, PaperNode]:
    """
    Deduplicate papers across different sources by title similarity.

    When two papers from different sources have very similar titles but
    different paper_ids, keep the richer one and merge metadata.
    """
    if len(papers) < 2:
        return papers

    titles = [(pid, p.title.lower().strip()) for pid, p in papers.items()]
    to_merge: list[tuple[str, str]] = []

    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            id_i, title_i = titles[i]
            id_j, title_j = titles[j]
            if id_i == id_j:
                continue

            len_ratio = max(len(title_i), len(title_j)) / max(1, min(len(title_i), len(title_j)))
            if len_ratio > 2.0:
                continue

            similarity = difflib.SequenceMatcher(None, title_i, title_j).ratio()
            if similarity >= title_similarity_threshold:
                p_i, p_j = papers[id_i], papers[id_j]
                i_quality = _paper_metadata_quality(p_i)
                j_quality = _paper_metadata_quality(p_j)
                keep, remove = (id_i, id_j) if i_quality >= j_quality else (id_j, id_i)
                to_merge.append((keep, remove))

    removed = set()
    for keep_id, remove_id in to_merge:
        if remove_id in removed or keep_id in removed:
            continue
        keep_paper = papers[keep_id]
        remove_paper = papers[remove_id]

        if not keep_paper.abstract or (remove_paper.abstract and len(remove_paper.abstract) > len(keep_paper.abstract)):
            keep_paper.abstract = remove_paper.abstract
        if remove_paper.citation_count > keep_paper.citation_count:
            keep_paper.citation_count = remove_paper.citation_count

        existing_kw = {k.lower() for k in keep_paper.keywords}
        for kw in remove_paper.keywords:
            if kw.lower() not in existing_kw:
                keep_paper.keywords.append(kw)

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
    for paper in papers.values():
        src = paper.source or "unknown"
        sources[src] = sources.get(src, 0) + 1

    real_sources = {source: count for source, count in sources.items() if source not in ("seed", "fallback")}
    total_real = sum(real_sources.values())
    if total_real == 0:
        return "Source diversity: all papers are seed/fallback."

    details = ", ".join(f"{source}={count}" for source, count in sorted(real_sources.items(), key=lambda item: -item[1]))
    return f"Source diversity: {total_real} real papers ({details})"
