from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from product_agent.domain import GapRecord, PaperRecord, ResearchIdeaRecord, ResearchWorkspace


def workspace_from_agent_state(*, task_id: str, topic: str, state: Dict[str, Any]) -> ResearchWorkspace:
    """
    将旧版 Agent state 转成产品工作台对象。

    这是前后端契约稳定化的关键步骤。

    TODO(iter3-workspace-mapper):
    1. 继续补全 taxonomy summary / recommended papers / key comparisons
    2. 为前端增加 section-level payload
    3. 增加引用来源与 evidence mapping
    """

    papers = [_map_paper(paper) for paper in state.get("paper_nodes", {}).values()]
    gaps = [_map_gap(task_id, gap) for gap in state.get("detected_gaps", [])]
    gap_ids = {g.gap_id for g in gaps}

    # map graph edges with gap-awareness
    graph_edges = [_map_graph_edge(edge, gap_ids) for edge in state.get("evolution_graph", [])]

    # taxonomy normalization uses papers and gaps to build tree/coverage
    taxonomy = _normalize_taxonomy(state.get("expert_taxonomy", {}), papers, gaps)

    # ideas mapping can infer related papers / derived gaps
    ideas = [_map_idea(task_id, idea, papers, gaps) for idea in state.get("generated_ideas", [])]

    trace = _build_trace(state)

    return ResearchWorkspace(
        task_id=task_id,
        topic=topic,
        summary=state.get("final_report", "")[:400],
        summary_payload=state.get("final_report_summary", {}),
        papers=papers,
        taxonomy=taxonomy,
        graph_edges=graph_edges,
        gaps=gaps,
        ideas=ideas,
        alignment_score=float(state.get("alignment_score", 0.0) or 0.0),
        trace=trace,
    )


def _map_paper(paper: Any) -> PaperRecord:
    if hasattr(paper, "model_dump"):
        payload = paper.model_dump()
    elif isinstance(paper, dict):
        payload = paper
    else:
        payload = paper.__dict__
    return PaperRecord(
        paper_id=str(payload.get("paper_id", "")),
        title=str(payload.get("title", "")),
        abstract=str(payload.get("abstract", "")),
        authors=list(payload.get("authors", [])),
        publish_date=str(payload.get("publish_date", "")),
        source=str(payload.get("source", "")),
        taxonomy_category=str(payload.get("taxonomy_category", "")),
        citation_count=int(payload.get("citation_count", 0) or 0),
        url=str(payload.get("url", "")),
    )


def _map_gap(task_id: str, raw_gap: str) -> GapRecord:
    if isinstance(raw_gap, dict):
        gap_id = str(raw_gap.get("id") or raw_gap.get("gap_id") or f"gap_{abs(hash((task_id, json_safe(raw_gap)))) % 10_000_000}")
        summary = str(raw_gap.get("summary", raw_gap.get("description", raw_gap))).strip()
        evidence = [str(item).strip() for item in raw_gap.get("evidence", []) if str(item).strip()]
        severity = str(raw_gap.get("severity", "")).strip().lower() or (
            "high" if any(token in summary.lower() for token in ["missing", "unsupported", "dangling"]) else "medium"
        )
    else:
        gap_id = f"gap_{abs(hash((task_id, str(raw_gap)))) % 10_000_000}"
        summary = str(raw_gap).strip()
        evidence = []
        severity = "high" if any(token in summary.lower() for token in ["missing", "unsupported", "dangling"]) else "medium"

    return GapRecord(
        gap_id=gap_id,
        task_id=task_id,
        summary=summary,
        severity=severity,
        evidence=evidence,
    )


def _map_graph_edge(raw_edge: Any, gap_ids: set) -> Dict[str, Any]:
    if hasattr(raw_edge, "model_dump"):
        payload = raw_edge.model_dump()
    elif isinstance(raw_edge, dict):
        payload = raw_edge
    elif hasattr(raw_edge, "__dict__"):
        payload = {k: v for k, v in vars(raw_edge).items() if not k.startswith("_")}
    else:
        payload = {"raw": str(raw_edge)}

    source = str(payload.get("source", ""))
    target = str(payload.get("target", ""))
    relationship = str(payload.get("relationship", ""))
    reasoning = str(payload.get("reasoning", ""))
    edge_id = str(payload.get("id") or payload.get("edge_id") or f"edge_{source}_{target}")
    metadata = {
        key: value
        for key, value in payload.items()
        if key not in {"id", "edge_id", "source", "target", "relationship", "reasoning", "score", "type"}
    }

    # quality labels
    confidence = float(payload.get("confidence", payload.get("score") or 0.0) or 0.0)
    is_weak = confidence < 0.5
    # determine whether this edge relates to known gaps
    is_gap_related = False
    # explicit related gap fields from payload
    related_field = payload.get("related_gaps") or payload.get("related_gap_ids") or payload.get("gap_ids") or payload.get("gap_id")
    related_set = set()
    if related_field:
        if isinstance(related_field, (list, tuple, set)):
            related_set = set(str(x) for x in related_field)
        else:
            related_set = {str(related_field)}
    if related_set & set(gap_ids):
        is_gap_related = True
    # scan metadata values for gap ids
    if not is_gap_related:
        for v in metadata.values():
            if isinstance(v, str):
                for gid in gap_ids:
                    if gid and gid in v:
                        is_gap_related = True
                        break
            elif isinstance(v, (list, tuple, set)):
                if any(str(x) in gap_ids for x in v):
                    is_gap_related = True
                    break
            if is_gap_related:
                break
    # fallback: relation text mentions 'gap' or source/target look like gap ids
    if not is_gap_related:
        if relationship and "gap" in relationship.lower():
            is_gap_related = True
        elif str(source).startswith("gap_") or str(target).startswith("gap_"):
            is_gap_related = True

    edge_type = str(payload.get("type", relationship or "semantic")).strip() or "semantic"

    return {
        "edge_id": edge_id,
        "source": source,
        "target": target,
        "relationship": relationship,
        "reasoning": reasoning,
        "type": edge_type,
        "confidence": confidence,
        "is_weak": is_weak,
        "is_gap_related": is_gap_related,
        "metadata": metadata,
    }



def _map_idea(task_id: str, raw_idea: Any, papers: List[PaperRecord], gaps: List[GapRecord]) -> ResearchIdeaRecord:
    if isinstance(raw_idea, ResearchIdeaRecord):
        payload = {
            "idea_id": raw_idea.idea_id,
            "title": raw_idea.title,
            "motivation": raw_idea.motivation,
            "approach": raw_idea.approach,
            "feasibility": raw_idea.feasibility,
            "contribution": raw_idea.contribution,
            "related_papers": list(raw_idea.related_papers),
            "derived_from_gaps": list(raw_idea.derived_from_gaps),
            "confidence": raw_idea.confidence,
            "tags": list(raw_idea.tags),
            "raw_text": raw_idea.raw_text,
        }
    elif isinstance(raw_idea, dict):
        payload = raw_idea
    elif hasattr(raw_idea, "to_dict"):
        payload = raw_idea.to_dict()
    else:
        payload = {"title": _extract_title(str(raw_idea)), "raw_text": str(raw_idea)}

    title = str(payload.get("title", "")).strip() or _extract_title(str(payload.get("raw_text", "")))
    motivation = str(payload.get("motivation", "")).strip()
    approach = str(payload.get("approach", "")).strip()
    feasibility = str(payload.get("feasibility", "")).strip()
    contribution = str(payload.get("contribution", "")).strip()
    related_papers = [str(item).strip() for item in payload.get("related_papers", []) if str(item).strip()]
    derived_from_gaps = [str(item).strip() for item in payload.get("derived_from_gaps", []) if str(item).strip()]
    confidence = float(payload.get("confidence", 0.0) or 0.0)
    tags = [str(item).strip() for item in payload.get("tags", []) if str(item).strip()]
    raw_text = str(payload.get("raw_text", "")).strip() or title
    idea_id = str(payload.get("idea_id") or payload.get("id") or f"idea_{abs(hash((task_id, raw_text or title))) % 10_000_000}")
    # Auto-link related papers if missing
    if not related_papers and (raw_text or title):
        related_papers = _infer_related_papers(raw_text or title, papers)

    # Auto-match derived gaps if missing
    if not derived_from_gaps and raw_text:
        derived_from_gaps = _match_gap_text(raw_text, gaps)

    return ResearchIdeaRecord(
        idea_id=idea_id,
        task_id=task_id,
        title=title,
        motivation=motivation,
        approach=approach,
        feasibility=feasibility,
        contribution=contribution,
        related_papers=related_papers,
        derived_from_gaps=derived_from_gaps,
        confidence=confidence,
        tags=tags,
        raw_text=raw_text,
    )


def _extract_title(raw_idea: str) -> str:
    first_line = raw_idea.strip().splitlines()[0] if raw_idea.strip() else "Untitled Idea"
    first_line = re.sub(r"^\s*\d+[\.\、)]\s*", "", first_line).strip()
    return first_line[:120] or "Untitled Idea"


def _normalize_taxonomy(raw_taxonomy: Any, papers: List[PaperRecord], gaps: List[GapRecord] = None) -> Dict[str, Any]:
    if isinstance(raw_taxonomy, dict) and "taxonomy" in raw_taxonomy:
        raw_taxonomy = raw_taxonomy["taxonomy"]
    gaps = gaps or []

    branches: List[Dict[str, Any]] = []
    if isinstance(raw_taxonomy, dict):
        for name, payload in raw_taxonomy.items():
            if isinstance(payload, str):
                payload = {"description": payload}
            elif not isinstance(payload, dict):
                payload = {"description": str(payload)}

            branch_name = str(name).strip()
            description = str(payload.get("description", "")).strip()
            required_concepts = [
                str(item).strip() for item in payload.get("required_concepts", []) if str(item).strip()
            ]
            paper_count = sum(
                1
                for paper in papers
                if branch_name and branch_name.lower() in str(paper.taxonomy_category or "").lower()
            )
            branches.append(
                {
                    "branch_id": _slug(branch_name),
                    "name": branch_name,
                    "description": description,
                    "required_concepts": required_concepts,
                    "paper_count": paper_count,
                }
            )
    elif isinstance(raw_taxonomy, list):
        for item in raw_taxonomy:
            branch_name = str(item).strip()
            branches.append(
                {
                    "branch_id": _slug(branch_name),
                    "name": branch_name,
                    "description": "",
                    "required_concepts": [],
                    "paper_count": 0,
                }
            )
    elif raw_taxonomy:
        branch_name = str(raw_taxonomy).strip()
        branches.append(
            {
                "branch_id": _slug(branch_name),
                "name": branch_name,
                "description": "",
                "required_concepts": [],
                "paper_count": 0,
            }
        )

    # build a simple tree structure from branch names using '/' or '>' separators
    tree = []
    for b in branches:
        parts = [p.strip() for p in re.split(r"[/>]", b["name"]) if p.strip()]
        node = {"branch_id": b["branch_id"], "name": b["name"], "children": []}
        if not parts:
            tree.append(node)
            continue
        # For simplicity attach as flat entries grouped by first part
        root = next((t for t in tree if t["name"] == parts[0]), None)
        if not root:
            root = {"branch_id": _slug(parts[0]), "name": parts[0], "children": []}
            tree.append(root)
        if len(parts) > 1:
            child = {"branch_id": b["branch_id"], "name": b["name"], "children": []}
            root["children"].append(child)

    # coverage overlay: count papers and gaps per branch
    coverage = {}
    for b in branches:
        bid = b["branch_id"]
        paper_count = b.get("paper_count", 0)
        gap_count = sum(1 for g in gaps if bid in str(g.summary).lower() or (g.gap_id and bid in g.gap_id))
        coverage[bid] = {
            "paper_count": paper_count,
            "gap_count": gap_count,
            "coverage_score": float(paper_count) / (1 + gap_count) if (paper_count or gap_count) else 0.0,
        }

    return {"branches": branches, "tree": tree, "coverage": coverage, "raw": raw_taxonomy}


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "branch"


def _build_trace(state: Dict[str, Any]) -> Dict[str, Any]:
    thought = list(state.get("thought_trace", []))
    actions = list(state.get("action_history", []))
    tools = list(state.get("tool_events", []))
    timeline = []
    step = 1
    def add_events(items, type_name):
        nonlocal step
        for it in items:
            if isinstance(it, dict):
                summary = str(it.get("summary") or it.get("title") or it.get("name") or "").strip()
                ts = it.get("timestamp") or it.get("ts")
            else:
                summary = str(it).splitlines()[0][:200]
                ts = None
            timeline.append({"step": step, "type": type_name, "summary": summary, "timestamp": ts, "raw": it})
            step += 1

    add_events(actions, "action")
    add_events(thought, "thought")
    add_events(tools, "tool")

    return {
        "thought_trace": thought,
        "action_history": actions,
        "context_inputs": list(state.get("context_inputs", [])),
        "logs": list(state.get("logs", [])),
        "decisions": list(state.get("decisions", [])),
        "tool_events": tools,
        "timeline": timeline,
    }


def json_safe(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _infer_related_papers(text: str, papers: List[PaperRecord], top_n: int = 3) -> List[str]:
    text_lower = (text or "").lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", text_lower) if len(t) > 3]
    if not tokens:
        return []
    scores = []
    for p in papers:
        text_fields = f"{p.title or ""} {p.abstract or ""}".lower()
        score = sum(1 for t in tokens if t in text_fields)
        if score > 0:
            scores.append((score, p.paper_id or p.title))
    scores.sort(key=lambda x: -x[0])
    return [item[1] for item in scores[:top_n]]


def _match_gap_text(text: str, gaps: List[GapRecord]) -> List[str]:
    text_lower = (text or "").lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", text_lower) if len(t) > 3]
    matches = []
    for g in gaps:
        summary = (g.summary or "").lower()
        score = sum(1 for t in tokens if t in summary)
        if score > 0:
            matches.append((score, g.gap_id))
    matches.sort(key=lambda x: -x[0])
    return [m[1] for m in matches]
