from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


class EvidenceSnapshotService:
    """Freeze the audited evidence used by all user-facing generators."""

    VERSION = "v1"

    def build(
        self,
        *,
        topic: str,
        papers: Dict[str, Any],
        taxonomy: Any,
        edges: Iterable[Any],
        gaps: Iterable[Any],
        retrieval_plan: Any,
        retrieval_outcome: Any,
        alignment_score: float,
        audit_reports: Iterable[Any],
    ) -> Dict[str, Any]:
        paper_items = [self._paper_payload(paper) for paper in papers.values()]
        paper_items.sort(key=lambda item: item["paper_id"])
        edge_items = [self._edge_payload(edge) for edge in edges]
        edge_items.sort(
            key=lambda item: (
                item["source"],
                item["target"],
                item["relationship"],
            )
        )
        gap_items = [self._gap_payload(gap, index) for index, gap in enumerate(gaps)]
        gap_items.sort(key=lambda item: item["gap_id"])
        branch_items = self._taxonomy_branches(taxonomy, paper_items)
        audit_items = [
            self._audit_payload(report, index)
            for index, report in enumerate(audit_reports)
        ]

        fallback_sources = {"fallback", "seed"}
        fallback_paper_count = sum(
            1 for paper in paper_items if paper["source"].lower() in fallback_sources
        )
        evidence_level_counts = self._count_by(edge_items, "evidence_level")
        relationship_counts = self._count_by(edge_items, "relationship")

        stable_payload = {
            "version": self.VERSION,
            "topic": str(topic or "").strip(),
            "papers": paper_items,
            "taxonomy": {"branches": branch_items},
            "graph": {"edges": edge_items},
            "gaps": gap_items,
            "audit_reports": audit_items,
            "retrieval_plan": self._json_object(retrieval_plan),
            "retrieval_outcome": self._json_object(retrieval_outcome),
            "alignment_score": round(float(alignment_score or 0.0), 6),
            "audit_report_count": len(audit_items),
        }
        snapshot_id = self._stable_id(stable_payload)

        return {
            "snapshot_id": snapshot_id,
            "version": self.VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **stable_payload,
            "stats": {
                "paper_count": len(paper_items),
                "real_paper_count": len(paper_items) - fallback_paper_count,
                "fallback_paper_count": fallback_paper_count,
                "new_paper_count": sum(1 for paper in paper_items if paper["is_new_this_round"]),
                "taxonomy_branch_count": len(branch_items),
                "grounded_taxonomy_branch_count": sum(
                    1 for branch in branch_items if branch["paper_ids"]
                ),
                "edge_count": len(edge_items),
                "evidence_level_counts": evidence_level_counts,
                "relationship_counts": relationship_counts,
                "gap_count": len(gap_items),
                "evidence_backed_gap_count": sum(
                    1 for gap in gap_items if gap["evidence"]
                ),
            },
        }

    def _paper_payload(self, paper: Any) -> Dict[str, Any]:
        payload = self._payload(paper)
        return {
            "paper_id": str(payload.get("paper_id", "") or ""),
            "title": str(payload.get("title", "") or ""),
            "abstract": str(payload.get("abstract", "") or "")[:800],
            "publish_date": str(payload.get("publish_date", "") or ""),
            "source": str(payload.get("source", "") or ""),
            "taxonomy_category": str(payload.get("taxonomy_category", "") or ""),
            "expert_taxonomy_branches": sorted(
                {
                    str(item).strip()
                    for item in payload.get("expert_taxonomy_branches", []) or []
                    if str(item).strip()
                }
            ),
            "citation_count": int(payload.get("citation_count", 0) or 0),
            "citation_count_known": bool(payload.get("citation_count_known", False)),
            "citation_source": str(payload.get("citation_source", "") or ""),
            "confidence_score": round(float(payload.get("confidence_score", 0.0) or 0.0), 6),
            "is_new_this_round": bool(payload.get("is_new_this_round", False)),
        }

    def _edge_payload(self, edge: Any) -> Dict[str, Any]:
        payload = self._payload(edge)
        return {
            "source": str(payload.get("source", "") or ""),
            "target": str(payload.get("target", "") or ""),
            "relationship": str(payload.get("relationship", "") or "related"),
            "reasoning": str(payload.get("reasoning", "") or "")[:600],
            "provenance": str(payload.get("provenance", "") or ""),
            "confidence": round(float(payload.get("confidence", 0.0) or 0.0), 6),
            "evidence_level": str(payload.get("evidence_level", "") or "candidate"),
            "evidence": str(payload.get("evidence", "") or "")[:800],
            "evidence_snippets": [
                str(item).strip()[:800]
                for item in list(payload.get("evidence_snippets", []) or [])[:3]
                if str(item).strip()
            ],
            "evidence_details": [
                {
                    "source_type": str(item.get("source_type", "") or ""),
                    "section": str(item.get("section", "") or "")[:120],
                    "page": int(item.get("page", 0) or 0),
                    "snippet": str(item.get("snippet", "") or "")[:800],
                    "source_url": str(item.get("source_url", "") or "")[:500],
                    "citation_label": str(item.get("citation_label", "") or "")[:40],
                    "reference_entry": str(item.get("reference_entry", "") or "")[:800],
                }
                for item in list(payload.get("evidence_details", []) or [])[:3]
                if isinstance(item, dict)
            ],
        }

    def _gap_payload(self, gap: Any, index: int) -> Dict[str, Any]:
        payload = self._payload(gap)
        if payload:
            summary = str(
                payload.get("summary", payload.get("description", ""))
                or ""
            ).strip()
            return {
                "gap_id": str(payload.get("id") or payload.get("gap_id") or f"gap_{index}"),
                "summary": summary,
                "severity": str(payload.get("severity", "") or "medium"),
                "evidence": [
                    str(item).strip()[:800]
                    for item in list(payload.get("evidence", []) or [])[:5]
                    if str(item).strip()
                ],
            }
        return {
            "gap_id": f"gap_{index}",
            "summary": str(gap).strip(),
            "severity": "medium",
            "evidence": [],
        }

    def _taxonomy_branches(
        self,
        taxonomy: Any,
        papers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        raw = self._json_object(taxonomy)
        definitions: Dict[str, Dict[str, Any]] = {}
        taxonomy_map = raw.get("taxonomy", {})
        if isinstance(taxonomy_map, dict):
            for name, definition in taxonomy_map.items():
                normalized_name = str(name).strip()
                if not normalized_name:
                    continue
                payload = definition if isinstance(definition, dict) else {}
                definitions[normalized_name] = {
                    "description": str(payload.get("description", "") or "")[:600],
                    "required_concepts": [
                        str(item).strip()
                        for item in list(payload.get("required_concepts", []) or [])[:12]
                        if str(item).strip()
                    ],
                }

        branches = raw.get("branches", [])
        if isinstance(branches, list):
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                normalized_name = str(branch.get("name", "")).strip()
                if not normalized_name:
                    continue
                definitions.setdefault(
                    normalized_name,
                    {
                        "description": str(branch.get("description", "") or "")[:600],
                        "required_concepts": [
                            str(item).strip()
                            for item in list(branch.get("required_concepts", []) or [])[:12]
                            if str(item).strip()
                        ],
                    },
                )

        for paper in papers:
            for name in paper["expert_taxonomy_branches"]:
                definitions.setdefault(name, {"description": "", "required_concepts": []})
            category = paper["taxonomy_category"]
            if category:
                definitions.setdefault(category, {"description": "", "required_concepts": []})

        return [
            {
                "name": name,
                **definitions[name],
                "paper_ids": [
                    paper["paper_id"]
                    for paper in papers
                    if name in paper["expert_taxonomy_branches"]
                    or name == paper["taxonomy_category"]
                ],
            }
            for name in sorted(definitions)
        ]

    def _audit_payload(self, report: Any, index: int) -> Dict[str, Any]:
        payload = self._payload(report)
        if not payload:
            return {"audit_id": f"audit_{index}", "summary": str(report)[:800]}
        normalized: Dict[str, Any] = {"audit_id": str(payload.get("id") or f"audit_{index}")}
        for key in (
            "status",
            "severity",
            "summary",
            "description",
            "message",
            "reason",
            "recommendation",
            "source",
            "target",
            "relationship",
        ):
            value = payload.get(key)
            if value not in (None, "", [], {}):
                normalized[key] = value
        return normalized

    def _count_by(self, items: Iterable[Dict[str, Any]], key: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            value = str(item.get(key, "") or "unknown")
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def _stable_id(self, payload: Dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        return f"evidence_{digest}"

    def _payload(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "to_dict"):
            result = value.to_dict()
            return dict(result) if isinstance(result, dict) else {}
        if hasattr(value, "model_dump"):
            result = value.model_dump()
            return dict(result) if isinstance(result, dict) else {}
        if hasattr(value, "__dict__"):
            return {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return {}

    def _json_object(self, value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}
