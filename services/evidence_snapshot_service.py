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
        branch_items = self._apply_required_facet_contract(
            branch_items,
            self._json_object(retrieval_outcome),
        )
        audit_items = [
            self._audit_payload(report, index)
            for index, report in enumerate(audit_reports)
        ]

        fallback_sources = {"fallback", "seed"}
        fallback_paper_count = sum(
            1 for paper in paper_items if paper["source"].lower() in fallback_sources
        )
        direct_paper_ids = [
            paper["paper_id"]
            for paper in paper_items
            if paper["relevance_tier"] == "direct"
            and paper["source"].lower() not in fallback_sources
        ]
        adjacent_paper_ids = [
            paper["paper_id"]
            for paper in paper_items
            if paper["relevance_tier"] == "adjacent"
            and paper["source"].lower() not in fallback_sources
        ]
        conclusion_contract = {
            "policy": "direct_evidence_required",
            "claimable_paper_ids": direct_paper_ids,
            "context_only_paper_ids": adjacent_paper_ids,
            "branch_contracts": [
                {
                    "name": branch["name"],
                    "evidence_status": branch["evidence_status"],
                    "claimable_paper_ids": list(
                        branch.get("claimable_paper_ids", [])
                    ),
                    "required_facet_evidence_level": str(
                        branch.get("required_facet_evidence_level", "")
                    ),
                }
                for branch in branch_items
            ],
            "recommendations_allowed": bool(direct_paper_ids),
            "definitive_claims_allowed": bool(direct_paper_ids),
            "adjacent_evidence_role": "background_or_hypothesis_only",
        }
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
            "conclusion_contract": conclusion_contract,
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
                "direct_paper_count": len(direct_paper_ids),
                "adjacent_paper_count": len(adjacent_paper_ids),
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
            "relevance_score": round(
                float(payload.get("relevance_score", 0.0) or 0.0),
                6,
            ),
            "relevance_tier": str(
                payload.get("relevance_tier", "") or "candidate"
            ).casefold(),
            "relevance_reasons": [
                str(item).strip()
                for item in list(payload.get("relevance_reasons", []) or [])[:12]
                if str(item).strip()
            ],
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
            raw_evidence = payload.get("evidence", []) or payload.get(
                "related_papers", []
            )
            return {
                "gap_id": str(payload.get("id") or payload.get("gap_id") or f"gap_{index}"),
                "summary": summary,
                "severity": str(payload.get("severity", "") or "medium"),
                "evidence": [
                    str(item).strip()[:800]
                    for item in list(raw_evidence)[:5]
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
        gap_ids_by_branch: Dict[str, List[str]] = {}
        paper_ids_by_branch: Dict[str, List[str]] = {}
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
                gap_ids_by_branch[normalized_name] = [
                    str(item).strip()
                    for item in list(payload.get("matched_gap_ids", []) or [])
                    if str(item).strip()
                ]
                paper_ids_by_branch[normalized_name] = [
                    str(item).strip()
                    for item in list(payload.get("matched_paper_ids", []) or [])
                    if str(item).strip()
                ]

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
                gap_ids_by_branch[normalized_name] = list(
                    dict.fromkeys(
                        [
                            *gap_ids_by_branch.get(normalized_name, []),
                            *[
                                str(item).strip()
                                for item in list(
                                    branch.get("matched_gap_ids", []) or []
                                )
                                if str(item).strip()
                            ],
                        ]
                    )
                )
                paper_ids_by_branch[normalized_name] = list(
                    dict.fromkeys(
                        [
                            *paper_ids_by_branch.get(normalized_name, []),
                            *[
                                str(item).strip()
                                for item in list(
                                    branch.get("matched_paper_ids", []) or []
                                )
                                if str(item).strip()
                            ],
                        ]
                    )
                )

        coverage = raw.get("coverage", {})
        if isinstance(coverage, dict):
            branch_names_by_id = {
                str(branch.get("branch_id", "") or ""): str(
                    branch.get("name", "") or ""
                ).strip()
                for branch in list(raw.get("branches", []) or [])
                if isinstance(branch, dict)
            }
            for branch_id, entry in coverage.items():
                if not isinstance(entry, dict):
                    continue
                branch_name = branch_names_by_id.get(str(branch_id), "")
                if not branch_name:
                    continue
                gap_ids_by_branch[branch_name] = list(
                    dict.fromkeys(
                        [
                            *gap_ids_by_branch.get(branch_name, []),
                            *[
                                str(item).strip()
                                for item in list(
                                    entry.get("matched_gap_ids", []) or []
                                )
                                if str(item).strip()
                            ],
                        ]
                    )
                )
                paper_ids_by_branch[branch_name] = list(
                    dict.fromkeys(
                        [
                            *paper_ids_by_branch.get(branch_name, []),
                            *[
                                str(item).strip()
                                for item in list(
                                    entry.get("matched_paper_ids", []) or []
                                )
                                if str(item).strip()
                            ],
                        ]
                    )
                )

        for paper in papers:
            for name in paper["expert_taxonomy_branches"]:
                definitions.setdefault(name, {"description": "", "required_concepts": []})
            category = paper["taxonomy_category"]
            if category:
                definitions.setdefault(category, {"description": "", "required_concepts": []})

        result: List[Dict[str, Any]] = []
        for name in sorted(definitions):
            explicit_paper_ids = set(paper_ids_by_branch.get(name, []))
            branch_papers = [
                paper
                for paper in papers
                if paper["paper_id"] in explicit_paper_ids
                or name in paper["expert_taxonomy_branches"]
                or name == paper["taxonomy_category"]
            ]
            direct_ids = [
                paper["paper_id"]
                for paper in branch_papers
                if paper["relevance_tier"] == "direct"
            ]
            adjacent_ids = [
                paper["paper_id"]
                for paper in branch_papers
                if paper["relevance_tier"] == "adjacent"
            ]
            evidence_status = (
                "grounded"
                if direct_ids
                else "exploratory"
                if adjacent_ids
                else "unsupported"
            )
            result.append({
                "name": name,
                **definitions[name],
                "paper_ids": [paper["paper_id"] for paper in branch_papers],
                "direct_paper_ids": direct_ids,
                "adjacent_paper_ids": adjacent_ids,
                "claimable_paper_ids": direct_ids,
                "matched_gap_ids": gap_ids_by_branch.get(name, []),
                "evidence_status": evidence_status,
            })
        return result

    def _apply_required_facet_contract(
        self,
        branches: List[Dict[str, Any]],
        retrieval_outcome: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        coverage = retrieval_outcome.get("facet_evidence_coverage", {})
        facets = coverage.get("facets", []) if isinstance(coverage, dict) else []
        required_facets = [
            facet
            for facet in facets
            if isinstance(facet, dict) and bool(facet.get("required", False))
        ]
        if not required_facets:
            return branches

        for branch in branches:
            branch_text = self._normalized_match_text(
                " ".join(
                    [
                        str(branch.get("name", "")),
                        str(branch.get("description", "")),
                        " ".join(branch.get("required_concepts", []) or []),
                    ]
                )
            )
            scored_facets = [
                (self._facet_branch_match_score(facet, branch_text), facet)
                for facet in required_facets
            ]
            best_score = max(
                (score for score, _facet in scored_facets),
                default=0.0,
            )
            matching_facets = [
                facet
                for score, facet in scored_facets
                if score > 0 and score == best_score
            ]
            if not matching_facets:
                continue

            levels = {
                str(facet.get("evidence_level", "") or "").casefold()
                for facet in matching_facets
            }
            branch["required_facet_evidence_level"] = self._weakest_facet_level(
                levels
            )
            direct_facet_paper_ids = {
                str(paper.get("paper_id", "") or "")
                for facet in matching_facets
                for paper in list(facet.get("matched_papers", []) or [])
                if isinstance(paper, dict)
                and str(paper.get("match_type", "") or "").casefold() == "direct"
                and str(paper.get("paper_id", "") or "")
            }
            branch_direct_ids = set(branch.get("direct_paper_ids", []) or [])
            branch["claimable_paper_ids"] = sorted(
                branch_direct_ids & direct_facet_paper_ids
            )
            if branch["claimable_paper_ids"]:
                branch["evidence_status"] = "grounded"
            elif branch.get("paper_ids"):
                branch["evidence_status"] = "exploratory"
            else:
                branch["evidence_status"] = "unsupported"
        return branches

    def _facet_branch_match_score(
        self,
        facet: Dict[str, Any],
        branch_text: str,
    ) -> float:
        candidates = [
            str(facet.get("label", "") or ""),
            *[
                str(term)
                for term in list(facet.get("search_terms", []) or [])
                if str(term).strip()
            ],
        ]
        branch_tokens = {
            self._match_token(token)
            for token in branch_text.split()
            if token
        }
        best_score = 0.0
        for candidate in candidates:
            normalized = self._normalized_match_text(candidate)
            if normalized and normalized in branch_text:
                best_score = max(
                    best_score,
                    10.0 + len(normalized.split()),
                )
                continue
            tokens = {
                self._match_token(token)
                for token in normalized.split()
                if len(token) >= 4
            }
            overlap = len(tokens & branch_tokens)
            if len(tokens) >= 2 and overlap >= 2:
                best_score = max(
                    best_score,
                    overlap / len(tokens),
                )
        return best_score

    def _match_token(self, token: str) -> str:
        return token[:-1] if len(token) > 4 and token.endswith("s") else token

    def _normalized_match_text(self, value: str) -> str:
        return " ".join(
            "".join(
                character.casefold() if character.isalnum() else " "
                for character in str(value or "")
            ).split()
        )

    def _weakest_facet_level(self, levels: set[str]) -> str:
        order = {
            "missing": 0,
            "unsupported": 0,
            "adjacent_only": 1,
            "weak": 1,
            "moderate": 2,
            "strong": 3,
        }
        return min(levels, key=lambda item: order.get(item, 1)) if levels else ""

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
