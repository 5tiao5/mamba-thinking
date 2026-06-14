from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional


def _stringify_affected_item(item: object) -> str:
    """Convert structured audit payloads into stable string identifiers."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("id", "paper_id", "edge_id", "branch_id", "name", "title"):
            value = item.get(key)
            if value:
                return str(value)
        try:
            return json.dumps(item, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(item)
    if isinstance(item, (list, tuple, set)):
        return " | ".join(_stringify_affected_item(value) for value in item)
    return str(item)


def _make_gap_id(gap_type: str, affected_items: List[str]) -> str:
    """Generate a stable gap id from normalized affected items."""
    normalized = [_stringify_affected_item(item) for item in affected_items]
    sorted_items = sorted(set(normalized))
    key = f"{gap_type}:{':'.join(sorted_items)}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


@dataclass
class AuditReport:
    """Structured audit report."""

    type: str  # taxonomy, graph, llm
    severity: str  # info, warning, error
    description: str
    affected_items: List[str]
    suggestion: Optional[str] = None
    related_gap_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.affected_items = [_stringify_affected_item(item) for item in self.affected_items]
        self.related_gap_ids = [str(item) for item in self.related_gap_ids if str(item)]

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "affected_items": self.affected_items,
            "suggestion": self.suggestion,
            "related_gap_ids": self.related_gap_ids,
        }


@dataclass
class AuditGap:
    """Structured audit gap."""

    type: str  # taxonomy, graph, llm
    severity: str  # info, warning, error
    description: str
    affected_items: List[str]
    actionable: bool = False
    related_papers: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    suggestion: Optional[str] = None
    id: str | None = None
    confidence: Optional[float] = None

    def __post_init__(self):
        self.affected_items = [_stringify_affected_item(item) for item in self.affected_items]
        self.related_papers = [_stringify_affected_item(item) for item in self.related_papers]
        self.evidence = [_stringify_affected_item(item) for item in self.evidence]
        if self.id is None:
            self.id = _make_gap_id(self.type, self.affected_items)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "affected_items": self.affected_items,
            "actionable": self.actionable,
            "related_papers": self.related_papers,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass
class AuditResult:
    """Audit result."""

    score: float
    reports: List[AuditReport]
    gaps: List[AuditGap]


@dataclass
class AuditSummary:
    """Audit summary for dashboard display."""

    score: float
    gap_count: int
    report_count: int
    severity_distribution: dict
    actionable_gap_count: int
    gap_types: dict

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "gap_count": self.gap_count,
            "report_count": self.report_count,
            "severity_distribution": self.severity_distribution,
            "actionable_gap_count": self.actionable_gap_count,
            "gap_types": self.gap_types,
        }
